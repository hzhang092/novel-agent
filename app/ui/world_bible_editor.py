"""World Overview and typed Story Element editor."""

from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtCore import QSignalBlocker, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.storage.bible_models import (
    BibleElement,
    BibleElementRelation,
    BibleElementType,
    TerminologyElement,
    WorldOverview,
)
from app.storage.bible_repository import WorldBibleService
from app.storage.editor_layout import EditorLayoutStore
from app.storage.project_files import load_all_volumes
from app.ui.bible_element_dialog import BibleElementDialog
from app.ui.bible_element_editor import BibleElementEditor
from app.ui.bible_element_list import BibleElementList
from app.ui.widgets import CollapsibleSection, StringListEditor
from app.ui.world_section_catalog import WORLD_SECTION_DEFINITIONS

logger = logging.getLogger(__name__)


class WorldBibleEditorView(QWidget):
    dirty_changed = pyqtSignal(bool)
    content_changed = pyqtSignal()
    element_saved = pyqtSignal(str)
    element_deleted = pyqtSignal(str)
    elements_changed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._project_dir: Path | None = None
        self._service: WorldBibleService | None = None
        self._layout_store: EditorLayoutStore | None = None
        self._elements: list[BibleElement] = []
        self._persisted_ids: set[str] = set()
        self._current_id: str | None = None
        self._baseline_overview = WorldOverview()
        self._overview_dirty = False
        self._snapshot_dirty = False
        self._last_dirty = False
        self._populating = False
        self._selection_change_in_progress = False
        self._overview_sections: dict[str, CollapsibleSection] = {}
        self._setup_ui()
        self._connect_changes()

    @property
    def is_dirty(self) -> bool:
        return self._snapshot_dirty or self._overview_dirty or self._element_is_dirty()

    def set_layout_store(self, layout_store: EditorLayoutStore) -> None:
        self._layout_store = layout_store

    def load_project_dir(self, project_dir: Path) -> None:
        self._project_dir = Path(project_dir)
        if (
            self._layout_store is None
            or self._layout_store.project_dir != self._project_dir
        ):
            self._layout_store = EditorLayoutStore(self._project_dir)
        self._service = WorldBibleService(self._project_dir)
        try:
            bible = self._service.load()
        except Exception as error:
            self._project_dir = None
            self._service = None
            self._layout_store = None
            self._elements = []
            self._persisted_ids = set()
            self._current_id = None
            self._baseline_overview = WorldOverview()
            self._populate_overview(self._baseline_overview)
            self._overview_dirty = False
            self._snapshot_dirty = False
            self._element_list.set_unsaved_ids(set())
            self._element_list.set_elements([])
            self._detail_stack.setCurrentWidget(self._overview_page)
            self._migration_notice.setText(
                "World Bible migration failed. Story Element editing is disabled."
            )
            self._migration_notice.setVisible(True)
            self._splitter.setEnabled(False)
            self.content_changed.emit()
            self._emit_dirty()
            QMessageBox.warning(self, "World Bible migration failed", str(error))
            return

        self._splitter.setEnabled(True)
        notice_marker = (
            self._project_dir
            / ".novel-agent"
            / "world-bible-migration-notice-shown"
        )
        migrated_now = (
            bible.manifest.migrated_from_world_setting and not notice_marker.exists()
        )
        self._migration_notice.setText(
            "World Bible upgraded. A backup of the previous world files was created."
        )
        self._migration_notice.setVisible(migrated_now)
        if migrated_now:
            notice_marker.parent.mkdir(parents=True, exist_ok=True)
            notice_marker.touch()
        self._elements = list(bible.elements)
        self._persisted_ids = {element.id for element in self._elements}
        self._baseline_overview = bible.overview.model_copy(deep=True)
        self._populate_overview(bible.overview)
        self._overview_dirty = False
        self._snapshot_dirty = False
        self._apply_layout()
        self._element_list.set_elements(self._elements)

        selected = self._layout_store.layout.world.selected_item_id
        if selected != "overview" and selected not in self._persisted_ids:
            selected = "overview"
        self._element_list.select_element(selected)
        if self._current_id != selected:
            self._select_item(selected)
        self._emit_dirty()

    def save_all(self) -> bool:
        if self._snapshot_dirty:
            return self._save_snapshot()
        if self._element_is_dirty() and not self.save_current_element():
            return False
        if self._overview_dirty and not self._save_overview():
            return False
        return True

    def stage_snapshot(
        self, overview: WorldOverview, elements: list[BibleElement]
    ) -> None:
        """Replace the in-memory World Bible without writing to disk."""
        if self._current_id not in (None, "overview"):
            try:
                self._replace_element(self._element_editor.gather_element())
            except Exception:
                pass
        self._elements = [element.model_copy(deep=True) for element in elements]
        self._populate_overview(overview)
        self._overview_dirty = overview != self._baseline_overview
        persisted = (
            self._service.load().elements if self._service is not None else []
        )
        self._snapshot_dirty = (
            self._overview_dirty
            or [element.model_dump() for element in self._elements]
            != [element.model_dump() for element in persisted]
        )
        self._current_id = "overview"
        self._detail_stack.setCurrentWidget(self._overview_page)
        self._refresh_element_list("overview")
        self._element_list.select_element("overview")
        self.elements_changed.emit()
        self.content_changed.emit()
        self._emit_dirty()

    def save_current_element(self) -> bool:
        if self._snapshot_dirty:
            return self._save_snapshot()
        if self._current_id in (None, "overview") or self._service is None:
            return self._save_overview() if self._current_id == "overview" else True
        try:
            element = self._element_editor.gather_element()
        except Exception as error:
            QMessageBox.warning(self, "Story Element save failed", str(error))
            return False
        if not element.name:
            QMessageBox.warning(self, "Story Element save failed", "Name is required")
            return False
        if isinstance(element, TerminologyElement) and not element.definition.strip():
            QMessageBox.warning(
                self, "Story Element save failed", "Definition is required"
            )
            return False
        try:
            saved = self._service.save_element(element)
        except Exception as error:
            QMessageBox.warning(self, "Story Element save failed", str(error))
            return False

        was_new = saved.id not in self._persisted_ids
        self._replace_element(saved)
        self._persisted_ids.add(saved.id)
        self._element_editor.load_element(
            saved,
            elements=self._elements,
            inbound_relations=self._inbound_relations(saved.id),
        )
        self._refresh_element_list(saved.id)
        self.element_saved.emit(saved.id)
        if was_new:
            self.elements_changed.emit()
        self.content_changed.emit()
        self._emit_dirty()
        return True

    def _save_snapshot(self) -> bool:
        if not self._snapshot_dirty or self._service is None:
            return True
        if self._current_id not in (None, "overview"):
            try:
                self._replace_element(self._element_editor.gather_element())
            except Exception as error:
                QMessageBox.warning(self, "World Bible save failed", str(error))
                return False
        previous_ids = set(self._persisted_ids)
        try:
            saved = self._service.apply_snapshot(
                self._gather_overview(), self._elements
            )
        except Exception as error:
            QMessageBox.warning(self, "World Bible save failed", str(error))
            return False
        self._elements = [element.model_copy(deep=True) for element in saved]
        self._persisted_ids = {element.id for element in saved}
        self._baseline_overview = self._gather_overview().model_copy(deep=True)
        self._overview_dirty = False
        self._snapshot_dirty = False
        self._refresh_element_list("overview")
        for element_id in previous_ids - self._persisted_ids:
            self.element_deleted.emit(element_id)
        for element_id in self._persisted_ids:
            self.element_saved.emit(element_id)
        self.elements_changed.emit()
        self.content_changed.emit()
        self._emit_dirty()
        return True

    def open_add_element_dialog(
        self, default_type: BibleElementType | None = None
    ) -> None:
        if not self._resolve_dirty_before_switch():
            return
        dialog = BibleElementDialog(self, default_type=default_type)
        if not dialog.exec():
            return
        draft = dialog.create_draft()
        self._elements.append(draft)
        self._refresh_element_list(draft.id)
        self._element_list.select_element(draft.id)
        if self._current_id != draft.id:
            self._select_item(draft.id)
        self.elements_changed.emit()
        self._emit_dirty()

    def elements_in_memory(self) -> list[BibleElement]:
        if self._current_id not in (None, "overview"):
            try:
                self._replace_element(self._element_editor.gather_element())
            except Exception:
                pass
        return [element.model_copy(deep=True) for element in self._elements]

    def overview_in_memory(self) -> WorldOverview:
        return self._gather_overview()

    def set_current_scene_element_ids(self, element_ids: set[str] | None) -> None:
        self._element_list.set_current_scene_element_ids(element_ids)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._migration_notice = QLabel()
        self._migration_notice.setWordWrap(True)
        self._migration_notice.setVisible(False)
        layout.addWidget(self._migration_notice)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        self._element_list = BibleElementList()
        left_layout.addWidget(self._element_list)
        self._add_button = QPushButton("+ Add Element")
        self._add_button.clicked.connect(lambda: self.open_add_element_dialog())
        left_layout.addWidget(self._add_button)
        self._splitter.addWidget(left)

        self._detail_stack = QStackedWidget()
        self._overview_page = self._build_overview_page()
        self._element_page = self._build_element_page()
        self._detail_stack.addWidget(self._overview_page)
        self._detail_stack.addWidget(self._element_page)
        self._splitter.addWidget(self._detail_stack)
        self._splitter.setStretchFactor(1, 1)
        layout.addWidget(self._splitter)

    def _build_overview_page(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        form = QVBoxLayout(container)
        form.addWidget(QLabel("<h2>World Overview</h2>"))
        self._overview_geography = QTextEdit()
        self._overview_technology = QLineEdit()
        self._overview_society = QLineEdit()
        self._overview_rules = StringListEditor()
        self._overview_taboos = StringListEditor()

        contents: dict[str, QWidget] = {}
        geography = QWidget()
        geography_layout = QVBoxLayout(geography)
        geography_layout.addWidget(self._overview_geography)
        contents["geography"] = geography
        society = QWidget()
        society_layout = QVBoxLayout(society)
        society_layout.addWidget(QLabel("Technology level"))
        society_layout.addWidget(self._overview_technology)
        society_layout.addWidget(QLabel("Social structure"))
        society_layout.addWidget(self._overview_society)
        contents["society"] = society
        for section_id, widget in (
            ("rules", self._overview_rules),
            ("taboos", self._overview_taboos),
        ):
            content = QWidget()
            content_layout = QVBoxLayout(content)
            content_layout.addWidget(widget)
            contents[section_id] = content

        for definition in WORLD_SECTION_DEFINITIONS:
            section = CollapsibleSection(
                definition.label, section_id=definition.section_id
            )
            section.set_content_widget(contents[definition.section_id])
            section.expanded_changed.connect(
                lambda expanded, section_id=definition.section_id:
                self._on_overview_section_expanded(section_id, expanded)
            )
            self._overview_sections[definition.section_id] = section
            form.addWidget(section)
        form.addStretch()
        scroll.setWidget(container)
        return scroll

    def _build_element_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        toolbar = QHBoxLayout()
        toolbar.addStretch()
        self._delete_button = QPushButton("Delete")
        self._delete_button.clicked.connect(self._on_delete_element)
        toolbar.addWidget(self._delete_button)
        self._save_button = QPushButton("Save")
        self._save_button.clicked.connect(self.save_current_element)
        toolbar.addWidget(self._save_button)
        layout.addLayout(toolbar)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._element_editor = BibleElementEditor()
        scroll.setWidget(self._element_editor)
        layout.addWidget(scroll)
        return page

    def _connect_changes(self) -> None:
        self._element_list.element_selected.connect(self._on_item_selected)
        self._element_list.filters_changed.connect(self._on_filters_changed)
        self._element_list.group_collapsed_changed.connect(
            self._on_group_collapsed_changed
        )
        self._element_editor.dirty_changed.connect(lambda _dirty: self._emit_dirty())
        self._element_editor.changed.connect(self._on_element_changed)
        self._element_editor.element_requested.connect(self._element_list.select_element)
        self._overview_geography.textChanged.connect(self._recompute_overview_dirty)
        self._overview_technology.textChanged.connect(self._recompute_overview_dirty)
        self._overview_society.textChanged.connect(self._recompute_overview_dirty)
        self._overview_rules.changed.connect(self._recompute_overview_dirty)
        self._overview_taboos.changed.connect(self._recompute_overview_dirty)

    def _populate_overview(self, overview: WorldOverview) -> None:
        self._populating = True
        try:
            self._overview_geography.setPlainText(overview.geography)
            self._overview_technology.setText(overview.technology_level)
            self._overview_society.setText(overview.social_structure)
            self._overview_rules.set_items(overview.rules)
            self._overview_taboos.set_items(overview.taboos)
        finally:
            self._populating = False

    def _gather_overview(self) -> WorldOverview:
        return WorldOverview(
            geography=self._overview_geography.toPlainText().strip(),
            technology_level=self._overview_technology.text().strip(),
            social_structure=self._overview_society.text().strip(),
            rules=self._overview_rules.get_items(),
            taboos=self._overview_taboos.get_items(),
        )

    def _recompute_overview_dirty(self, *_args) -> None:
        if self._populating:
            return
        self._overview_dirty = self._gather_overview() != self._baseline_overview
        self.content_changed.emit()
        self._emit_dirty()

    def _save_overview(self) -> bool:
        if not self._overview_dirty or self._service is None:
            return True
        overview = self._gather_overview()
        try:
            self._service.save_overview(overview)
        except Exception as error:
            QMessageBox.warning(self, "World Overview save failed", str(error))
            return False
        self._baseline_overview = overview.model_copy(deep=True)
        self._overview_dirty = False
        self.content_changed.emit()
        self._emit_dirty()
        return True

    def _on_item_selected(self, item_id: str) -> None:
        if self._selection_change_in_progress or item_id == self._current_id:
            return
        previous = self._current_id
        if not self._resolve_dirty_before_switch():
            if previous is not None:
                self._restore_selection(previous)
            return
        self._select_item(item_id)

    def _resolve_dirty_before_switch(self) -> bool:
        if not self.is_dirty:
            return True
        name = "World Overview"
        if self._current_id not in (None, "overview"):
            current = self._element_by_id(self._current_id)
            name = current.name if current is not None else "Unnamed element"
        reply = QMessageBox.question(
            self,
            "Unsaved changes",
            f'“{name}” has unsaved changes.',
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Save:
            return self.save_current_element()
        if reply == QMessageBox.StandardButton.Discard:
            self._discard_current_changes()
            return True
        return False

    def _select_item(self, item_id: str) -> None:
        self._current_id = item_id
        if item_id == "overview":
            self._detail_stack.setCurrentWidget(self._overview_page)
        else:
            element = self._element_by_id(item_id)
            if element is None:
                self._current_id = "overview"
                self._detail_stack.setCurrentWidget(self._overview_page)
                item_id = "overview"
            else:
                self._detail_stack.setCurrentWidget(self._element_page)
                self._element_editor.load_element(
                    element,
                    elements=self._elements,
                    inbound_relations=self._inbound_relations(item_id),
                )
        if self._layout_store is not None:
            self._layout_store.layout.world.selected_item_id = item_id
            self._layout_store.schedule_save()
        self._emit_dirty()

    def _discard_current_changes(self) -> None:
        if self._snapshot_dirty and self._service is not None:
            bible = self._service.load()
            self._elements = [element.model_copy(deep=True) for element in bible.elements]
            self._persisted_ids = {element.id for element in bible.elements}
            self._baseline_overview = bible.overview.model_copy(deep=True)
            self._populate_overview(bible.overview)
            self._overview_dirty = False
            self._snapshot_dirty = False
            self._refresh_element_list("overview")
            self.elements_changed.emit()
            self.content_changed.emit()
        elif self._current_id == "overview":
            self._populate_overview(self._baseline_overview)
            self._overview_dirty = False
        elif self._current_id is not None:
            if self._current_id not in self._persisted_ids:
                self._elements = [
                    item for item in self._elements if item.id != self._current_id
                ]
                self.elements_changed.emit()
            elif self._service is not None:
                self._replace_element(self._service.repository.load(self._current_id))
            self._refresh_element_list()
        self._emit_dirty()

    def _on_element_changed(self) -> None:
        if self._current_id in (None, "overview"):
            return
        try:
            self._replace_element(self._element_editor.gather_element())
        except Exception:
            pass
        self._element_list.set_unsaved_ids({self._current_id})
        self.content_changed.emit()
        self._emit_dirty()

    def _on_delete_element(self) -> None:
        if self._current_id in (None, "overview") or self._service is None:
            return
        element_id = self._current_id
        element = self._element_by_id(element_id)
        if element is None:
            return
        if element_id not in self._persisted_ids:
            message = f'Discard unsaved element “{element.name}”?'
        else:
            inbound = len(self._service.repository.get_inbound_relations(element_id))
            outgoing = len(element.relationships)
            scenes = sum(
                element_id in scene.world_element_ids
                for volume in load_all_volumes(self._project_dir)
                for chapter in volume.chapters
                for scene in chapter.scenes
            )
            primary = (
                self._service.repository.load_manifest().primary_power_system_id
                == element_id
            )
            message = (
                f'Delete “{element.name}”?\n\nReferenced by:\n'
                f'• {inbound} Story Elements\n• {scenes} Scenes\n'
                f'• Outgoing relationships: {outgoing}\n'
                f'• Primary power system: {"yes" if primary else "no"}\n\n'
                "Deleting it will remove these references."
            )
        if not self._confirm_delete(message):
            return
        try:
            if element_id in self._persisted_ids:
                self._service.delete_element(element_id, unlink_references=True)
        except Exception as error:
            QMessageBox.warning(self, "Story Element deletion failed", str(error))
            return
        self._elements = [item for item in self._elements if item.id != element_id]
        self._persisted_ids.discard(element_id)
        self._refresh_element_list("overview")
        self._element_list.select_element("overview")
        if self._current_id != "overview":
            self._select_item("overview")
        self.element_deleted.emit(element_id)
        self.elements_changed.emit()
        self.content_changed.emit()
        self._emit_dirty()

    def _confirm_delete(self, message: str) -> bool:
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Delete Story Element")
        dialog.setText(message)
        dialog.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        delete_button = dialog.addButton(
            "Delete and unlink", QMessageBox.ButtonRole.DestructiveRole
        )
        dialog.exec()
        return dialog.clickedButton() is delete_button

    def _apply_layout(self) -> None:
        if self._layout_store is None:
            return
        layout = self._layout_store.layout.world
        supported = set(self._overview_sections)
        if not layout.overview_visible_sections:
            layout.overview_visible_sections = [
                definition.section_id for definition in WORLD_SECTION_DEFINITIONS
            ]
            self._layout_store.schedule_save()
        unknown = (
            set(layout.overview_visible_sections)
            | set(layout.overview_collapsed_sections)
        ) - supported
        if unknown:
            logger.warning("Ignoring unknown World Overview layout IDs: %s", sorted(unknown))
            layout.overview_visible_sections = [
                item for item in layout.overview_visible_sections if item in supported
            ]
            layout.overview_collapsed_sections = [
                item for item in layout.overview_collapsed_sections if item in supported
            ]
            self._layout_store.schedule_save()
        visible = set(layout.overview_visible_sections)
        collapsed = set(layout.overview_collapsed_sections)
        for section_id, section in self._overview_sections.items():
            section.setVisible(section_id in visible)
            section.set_expanded(section_id not in collapsed)
        self._element_list.set_type_filter(layout.type_filter)
        self._element_list.set_tag_filters(layout.tag_filters)
        self._element_list.set_collapsed_type_groups(layout.collapsed_type_groups)

    def _on_filters_changed(self, type_filter: str, tag_filters: list[str]) -> None:
        if self._layout_store is None:
            return
        layout = self._layout_store.layout.world
        layout.type_filter = type_filter
        layout.tag_filters = list(tag_filters)
        self._layout_store.schedule_save()

    def _on_group_collapsed_changed(self, _group_id: str, _collapsed: bool) -> None:
        if self._layout_store is None:
            return
        self._layout_store.layout.world.collapsed_type_groups = (
            self._element_list.collapsed_type_groups()
        )
        self._layout_store.schedule_save()

    def _on_overview_section_expanded(
        self, section_id: str, expanded: bool
    ) -> None:
        if self._layout_store is None or self._populating:
            return
        collapsed = set(
            self._layout_store.layout.world.overview_collapsed_sections
        )
        if expanded:
            collapsed.discard(section_id)
        else:
            collapsed.add(section_id)
        self._layout_store.layout.world.overview_collapsed_sections = sorted(collapsed)
        self._layout_store.schedule_save()

    def _refresh_element_list(self, selected_id: str | None = None) -> None:
        self._element_list.set_elements(self._elements)
        unsaved = (
            {self._current_id}
            if self._current_id not in (None, "overview") and self._element_is_dirty()
            else set()
        )
        self._element_list.set_unsaved_ids(unsaved)
        if selected_id is not None:
            self._element_list.select_element(selected_id)

    def _restore_selection(self, item_id: str) -> None:
        item = self._element_list._find_item(item_id)
        if item is None:
            return
        self._selection_change_in_progress = True
        try:
            blocker = QSignalBlocker(self._element_list._tree)
            self._element_list._tree.setCurrentItem(item)
            del blocker
        finally:
            self._selection_change_in_progress = False

    def _element_is_dirty(self) -> bool:
        return self._current_id not in (None, "overview") and (
            self._current_id not in self._persisted_ids
            or self._element_editor.is_dirty
        )

    def _emit_dirty(self) -> None:
        dirty = self.is_dirty
        self._save_button.setEnabled(self._current_id not in (None, "overview") and dirty)
        if dirty != self._last_dirty:
            self._last_dirty = dirty
            self.dirty_changed.emit(dirty)

    def _element_by_id(self, element_id: str) -> BibleElement | None:
        return next((item for item in self._elements if item.id == element_id), None)

    def _replace_element(self, replacement: BibleElement) -> None:
        self._elements = [
            replacement if item.id == replacement.id else item for item in self._elements
        ]

    def _inbound_relations(
        self, element_id: str
    ) -> list[tuple[BibleElement, BibleElementRelation]]:
        return [
            (source, relation)
            for source in self._elements
            for relation in source.relationships
            if relation.target_element_id == element_id
        ]
