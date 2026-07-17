"""Review structured Story Bible suggestions before the caller applies them."""

from __future__ import annotations

import json

from pydantic import TypeAdapter, ValidationError
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.pipeline.bible_suggestions import (
    AddCharacterRelationSuggestion,
    AddElementRelationSuggestion,
    BibleSuggestion,
    CreateElementSuggestion,
    UpdateElementSuggestion,
    find_duplicate_candidates,
)
from app.storage.bible_models import BibleElement, BibleElementBase
from app.storage.bible_models import BibleElementType, BibleRelationKind
from app.storage.models import CharacterElementRelationKind


class BibleSuggestionDialog(QDialog):
    """Edits proposals in memory; persistence remains the caller's job."""

    proposals_accepted = pyqtSignal(list)

    def __init__(self, proposals: list[BibleSuggestion], existing_elements=(), parent=None):
        super().__init__(parent)
        self.setWindowTitle("Review Story Bible Suggestions")
        self._proposals = proposals
        self._existing = list(existing_elements)
        self._checks: dict[str, QCheckBox] = {}
        self._editors: dict[str, dict[str, QWidget]] = {}
        self._errors: dict[str, QLabel] = {}
        self._duplicate_choices: dict[str, QComboBox] = {}
        layout = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        rows = QVBoxLayout(body)
        for proposal in proposals:
            rows.addWidget(self._proposal_editor(proposal))
        rows.addStretch()
        scroll.setWidget(body)
        layout.addWidget(scroll)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Apply
        )
        buttons.button(QDialogButtonBox.StandardButton.Apply).setText("Apply selected")
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self._accept_selected)
        layout.addWidget(buttons)

    def selected_proposals(self) -> list[BibleSuggestion]:
        self._clear_errors()
        selected = []
        for proposal in self._proposals:
            if not self._checks[proposal.proposal_id].isChecked():
                continue
            try:
                selected.append(self._edited(proposal))
            except ValueError as error:
                self._invalid(proposal, error)
        replacement_refs: dict[str, str] = {}
        result: list[BibleSuggestion] = []
        for proposal in selected:
            if isinstance(proposal, CreateElementSuggestion):
                choice = self._duplicate_choices[proposal.proposal_id].currentData()
                if choice == "skip":
                    continue
                if choice != "create":
                    replacement_refs[proposal.proposal_id] = choice
                    proposal = UpdateElementSuggestion(
                        proposal_id=proposal.proposal_id,
                        confidence=proposal.confidence,
                        rationale=proposal.rationale,
                        source_excerpt=proposal.source_excerpt,
                        target_element_id=choice,
                        name=proposal.name,
                        aliases=proposal.aliases,
                        summary=proposal.summary,
                        typed_fields=proposal.typed_fields,
                    )
            try:
                self._validate_element_fields(proposal)
            except ValueError as error:
                self._invalid(proposal, error)
            result.append(proposal)
        created = {item.proposal_id for item in result if isinstance(item, CreateElementSuggestion)}
        existing = {element.id for element in self._existing}
        valid_refs = created | existing | set(replacement_refs.values())
        validated = []
        for proposal in result:
            if isinstance(proposal, (AddElementRelationSuggestion, AddCharacterRelationSuggestion)):
                source = replacement_refs.get(getattr(proposal, "source_ref", ""), getattr(proposal, "source_ref", ""))
                target = replacement_refs.get(proposal.target_ref, proposal.target_ref)
                if target not in valid_refs or (
                    isinstance(proposal, AddElementRelationSuggestion) and source not in valid_refs
                ):
                    self._invalid(
                        proposal,
                        ValueError(
                            "Relation targets must be an accepted new element or existing element"
                        ),
                    )
                proposal = proposal.model_copy(update={"target_ref": target, **({"source_ref": source} if isinstance(proposal, AddElementRelationSuggestion) else {})})
            validated.append(proposal)
        return validated

    def _proposal_editor(self, proposal: BibleSuggestion) -> QGroupBox:
        box = QGroupBox(f"{proposal.action.value.replace('_', ' ')} · {proposal.confidence:.0%}")
        layout = QVBoxLayout(box)
        check = QCheckBox("Include")
        check.setChecked(True)
        self._checks[proposal.proposal_id] = check
        layout.addWidget(check)
        if proposal.source_excerpt:
            excerpt = QLabel(proposal.source_excerpt)
            excerpt.setWordWrap(True)
            layout.addWidget(excerpt)
        form = QFormLayout()
        editors: dict[str, QWidget] = {}
        fields = _editable_fields(proposal)
        for key, value in fields.items():
            editor = _enum_editor(key, value)
            if editor is None:
                editor = QTextEdit() if key in {"summary", "rationale", "source_excerpt", "note", "typed_fields"} else QLineEdit()
            if isinstance(editor, QTextEdit):
                editor.setPlainText(value)
                editor.setMaximumHeight(70)
            elif isinstance(editor, QLineEdit):
                editor.setText(value)
            form.addRow(key.replace("_", " ").title(), editor)
            editors[key] = editor
        self._editors[proposal.proposal_id] = editors
        layout.addLayout(form)
        error = QLabel()
        error.setWordWrap(True)
        error.setStyleSheet("color: #c0392b;")
        error.hide()
        self._errors[proposal.proposal_id] = error
        layout.addWidget(error)
        if isinstance(proposal, CreateElementSuggestion):
            choice = QComboBox()
            choice.addItem("Create separate element", "create")
            for candidate in find_duplicate_candidates(proposal, self._existing):
                choice.addItem(f"Merge into {candidate.element_id}", candidate.element_id)
            choice.addItem("Skip", "skip")
            self._duplicate_choices[proposal.proposal_id] = choice
            form.addRow("Duplicate", choice)
        return box

    def _edited(self, proposal: BibleSuggestion) -> BibleSuggestion:
        updates = {
            key: _editor_value(editor)
            for key, editor in self._editors[proposal.proposal_id].items()
        }
        if "aliases" in updates:
            updates["aliases"] = [item.strip() for item in updates["aliases"].splitlines() if item.strip()]
        if "typed_fields" in updates:
            try:
                updates["typed_fields"] = json.loads(updates["typed_fields"] or "{}")
            except json.JSONDecodeError as error:
                raise ValueError("Typed fields must be valid JSON") from error
            if not isinstance(updates["typed_fields"], dict):
                raise ValueError("Typed fields JSON must be an object")
        try:
            return type(proposal).model_validate({**proposal.model_dump(), **updates})
        except ValidationError as error:
            raise ValueError(error.errors()[0]["msg"]) from error

    def _accept_selected(self) -> None:
        try:
            selected = self.selected_proposals()
        except ValueError as error:
            return
        self.proposals_accepted.emit(selected)
        super().accept()

    def _validate_element_fields(self, proposal: BibleSuggestion) -> None:
        if isinstance(proposal, CreateElementSuggestion):
            if not proposal.name.strip():
                raise ValueError("Name is required")
            try:
                created = TypeAdapter(BibleElement).validate_python(
                    {
                        "element_type": proposal.element_type,
                        "name": proposal.name,
                        "aliases": proposal.aliases,
                        "summary": proposal.summary,
                        **proposal.typed_fields,
                    }
                )
                allowed = set(type(created).model_fields) - set(BibleElementBase.model_fields)
                if set(proposal.typed_fields) - allowed:
                    raise ValueError("invalid typed fields")
            except ValidationError as error:
                raise ValueError("invalid typed fields: " + error.errors()[0]["msg"]) from error
        elif isinstance(proposal, UpdateElementSuggestion):
            current = next(
                (element for element in self._existing if element.id == proposal.target_element_id),
                None,
            )
            if current is None:
                raise ValueError("Update target must be an existing element")
            protected = set(proposal.typed_fields) & set(BibleElementBase.model_fields)
            unknown = set(proposal.typed_fields) - set(type(current).model_fields)
            if protected or unknown:
                raise ValueError("invalid typed fields")
            try:
                TypeAdapter(BibleElement).validate_python(
                    {
                        **current.model_dump(),
                        **{
                            key: value
                            for key, value in {
                                "name": proposal.name,
                                "aliases": proposal.aliases,
                                "summary": proposal.summary,
                            }.items()
                            if value is not None
                        },
                        **proposal.typed_fields,
                    }
                )
            except ValidationError as error:
                raise ValueError("invalid typed fields: " + error.errors()[0]["msg"]) from error

    def _clear_errors(self) -> None:
        for label in self._errors.values():
            label.clear()
            label.hide()

    def _invalid(self, proposal: BibleSuggestion, error: ValueError) -> None:
        label = self._errors[proposal.proposal_id]
        label.setText(str(error))
        label.show()
        raise error


def _editable_fields(proposal: BibleSuggestion) -> dict[str, str]:
    if isinstance(proposal, CreateElementSuggestion):
        return {"element_type": proposal.element_type.value, "name": proposal.name, "aliases": "\n".join(proposal.aliases), "summary": proposal.summary, "typed_fields": json.dumps(proposal.typed_fields, ensure_ascii=False)}
    if isinstance(proposal, UpdateElementSuggestion):
        fields = {"typed_fields": json.dumps(proposal.typed_fields, ensure_ascii=False)}
        if proposal.name is not None:
            fields["name"] = proposal.name
        if proposal.aliases is not None:
            fields["aliases"] = "\n".join(proposal.aliases)
        if proposal.summary is not None:
            fields["summary"] = proposal.summary
        return fields
    if isinstance(proposal, AddElementRelationSuggestion):
        return {"source_ref": proposal.source_ref, "kind": proposal.kind.value, "target_ref": proposal.target_ref, "note": proposal.note}
    return {"character_id": proposal.character_id, "kind": proposal.kind.value, "target_ref": proposal.target_ref, "note": proposal.note}


def _enum_editor(key: str, value: str) -> QComboBox | None:
    choices = {
        "element_type": BibleElementType,
        "kind": BibleRelationKind if value in {item.value for item in BibleRelationKind} else CharacterElementRelationKind,
    }.get(key)
    if choices is None:
        return None
    editor = QComboBox()
    for choice in choices:
        editor.addItem(choice.value.replace("_", " "), choice.value)
    editor.setCurrentIndex(editor.findData(value))
    return editor


def _editor_value(editor: QWidget) -> str:
    if isinstance(editor, QComboBox):
        return editor.currentData()
    return editor.toPlainText().strip() if isinstance(editor, QTextEdit) else editor.text().strip()
