"""Compact Story Brief and Story Proposal editor for Quick Creation."""

from __future__ import annotations

import asyncio
import re

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QSpinBox, QTextEdit, QVBoxLayout, QWidget,
)

from app.providers.config import ProviderConfigurationError
from app.application.errors import (
    ConcurrentModificationError,
    OperationBlockedError,
    StoryDesignerProviderError,
)
from app.storage.models import (
    ActiveBootstrapDraft,
    ActiveStoryPatchDraft,
    ChapterLength,
    StoryBootstrap,
    StoryBrief,
)
from app.storage.project_files import load_planning


_CHIPS = {
    "setting_tags": ("世界", ("现代", "仙侠", "末世", "校园")),
    "protagonist_tags": ("主角", ("成长", "强者归来", "普通人", "双主角")),
    "relationship_tags": ("关系", ("师徒", "伙伴", "恋人", "暧昧", "宿敌")),
    "plot_engine_tags": ("剧情", ("探案", "升级", "复仇", "冒险")),
    "tone_tags": ("气质", ("热血", "轻松", "悬疑", "治愈")),
}
_ROMANCE_CHIPS = {"恋人", "暧昧"}


class QuickStoryView(QWidget):
    settings_requested = Signal()
    bootstrap_approved = Signal()
    character_requested = Signal(str)
    world_element_requested = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._application = None
        self._proposal_task = None
        self._chips: dict[str, dict[str, QCheckBox]] = {}
        self._custom: dict[str, QLineEdit] = {}
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("故事意向"))
        self.premise_edit = QTextEdit()
        self.premise_edit.setPlaceholderText("一句话故事方向（可选）")
        self.premise_edit.setFixedHeight(55)
        layout.addWidget(self.premise_edit)
        for field, (label, values) in _CHIPS.items():
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            chips: dict[str, QCheckBox] = {}
            for value in values:
                chip = QCheckBox(value)
                chips[value] = chip
                row.addWidget(chip)
            custom = QLineEdit()
            custom.setPlaceholderText("自定义")
            self._custom[field] = custom
            row.addWidget(custom)
            row.addStretch()
            layout.addLayout(row)
            self._chips[field] = chips
        form = QFormLayout()
        self.target_combo = QComboBox()
        for label, value in (("短篇", "short"), ("约 30 章", "around_30"), ("约 100 章", "around_100"), ("长篇连载", "ongoing"), ("自定义", "custom")):
            self.target_combo.addItem(label, value)
        form.addRow("目标长度", self.target_combo)
        self.custom_target = QSpinBox()
        self.custom_target.setRange(1, 100000)
        self.custom_target.setValue(30)
        form.addRow("自定义章节", self.custom_target)
        self.romance_combo = QComboBox()
        for label, value in (("无", "none"), ("次要", "secondary"), ("主要", "primary")):
            self.romance_combo.addItem(label, value)
        self.romance_combo.currentIndexChanged.connect(self._update_romance_chips)
        form.addRow("感情线", self.romance_combo)
        self.protagonist_combo = QComboBox()
        for label, value in (("单主角", "single"), ("双主角", "dual"), ("群像", "ensemble")):
            self.protagonist_combo.addItem(label, value)
        form.addRow("主角结构", self.protagonist_combo)
        self.chapter_combo = QComboBox()
        for label, value in (("短", "short"), ("标准", "standard"), ("长", "long"), ("自定义", "custom")):
            self.chapter_combo.addItem(label, value)
        self._set_combo(self.chapter_combo, "standard")
        form.addRow("章节长度", self.chapter_combo)
        self.chapter_chars = QSpinBox()
        self.chapter_chars.setRange(1, 100000)
        self.chapter_chars.setValue(3000)
        form.addRow("目标汉字数", self.chapter_chars)
        self.ending_edit = QLineEdit()
        self.ending_edit.setPlaceholderText("长篇连载的暂定远方（可调整）")
        form.addRow("暂定去向", self.ending_edit)
        layout.addLayout(form)
        save = QPushButton("保存故事意向")
        save.clicked.connect(self._save_brief)
        layout.addWidget(save)
        layout.addWidget(QLabel("故事提案"))
        self.proposal_label = QLabel("尚未生成")
        self.proposal_label.setWordWrap(True)
        layout.addWidget(self.proposal_label)
        self.approved_brief_label = QLabel("")
        self.approved_brief_label.setWordWrap(True)
        layout.addWidget(self.approved_brief_label)
        self.quick_projection_label = QLabel("")
        self.quick_projection_label.setWordWrap(True)
        layout.addWidget(self.quick_projection_label)
        self.quick_projection_actions = QHBoxLayout()
        layout.addLayout(self.quick_projection_actions)
        self.story_patch_edit = QLineEdit()
        self.story_patch_edit.setPlaceholderText("用一句话调整主角或核心设定")
        layout.addWidget(self.story_patch_edit)
        story_patch_actions = QHBoxLayout()
        self.generate_story_patch_button = QPushButton("生成调整预览")
        self.apply_story_patch_button = QPushButton("应用调整")
        self.cancel_story_patch_button = QPushButton("取消调整")
        self.generate_story_patch_button.clicked.connect(
            lambda: self._start_task(self._generate_story_patch())
        )
        self.apply_story_patch_button.clicked.connect(self._apply_story_patch)
        self.cancel_story_patch_button.clicked.connect(self._cancel_story_patch)
        for button in (
            self.generate_story_patch_button,
            self.apply_story_patch_button,
            self.cancel_story_patch_button,
        ):
            story_patch_actions.addWidget(button)
        layout.addLayout(story_patch_actions)
        self.story_patch_label = QLabel("")
        self.story_patch_label.setWordWrap(True)
        layout.addWidget(self.story_patch_label)
        self.adjust_edit = QLineEdit()
        self.adjust_edit.setPlaceholderText("告诉 AI 如何调整")
        layout.addWidget(self.adjust_edit)
        actions = QHBoxLayout()
        self.adopt_button = QPushButton("采用这个故事")
        self.adjust_button = QPushButton("调整")
        self.another_button = QPushButton("换一个方向")
        self.generate_button = QPushButton("生成故事提案")
        self.adopt_button.clicked.connect(lambda: self._start_task(self._adopt_proposal()))
        self.adjust_button.clicked.connect(lambda: self._start_task(self._adjust_proposal()))
        self.another_button.clicked.connect(lambda: self._start_task(self._generate_proposal()))
        self.generate_button.clicked.connect(lambda: self._start_task(self._generate_proposal()))
        actions.addWidget(self.generate_button)
        for button in (self.adopt_button, self.adjust_button, self.another_button):
            actions.addWidget(button)
        layout.addLayout(actions)
        layout.addWidget(QLabel("故事启动包"))
        self.bootstrap_label = QLabel("采用故事后可生成")
        self.bootstrap_label.setWordWrap(True)
        layout.addWidget(self.bootstrap_label)
        self.bootstrap_button = QPushButton("生成故事启动包")
        self.bootstrap_button.clicked.connect(lambda: self._start_task(self._generate_bootstrap()))
        layout.addWidget(self.bootstrap_button)
        self.bootstrap_cards = QVBoxLayout()
        layout.addLayout(self.bootstrap_cards)
        self.bootstrap_advanced = QTextEdit()
        self.bootstrap_advanced.setReadOnly(True)
        self.bootstrap_advanced.setPlaceholderText("高级生成字段（只读）")
        self.bootstrap_advanced.setFixedHeight(70)
        layout.addWidget(self.bootstrap_advanced)
        self.bootstrap_adjust_edit = QLineEdit()
        self.bootstrap_adjust_edit.setPlaceholderText("告诉 AI 如何调整启动包")
        layout.addWidget(self.bootstrap_adjust_edit)
        self.bootstrap_patch_label = QLabel("")
        self.bootstrap_patch_label.setWordWrap(True)
        layout.addWidget(self.bootstrap_patch_label)
        bootstrap_actions = QHBoxLayout()
        self.save_bootstrap_button = QPushButton("保存修改")
        self.adjust_bootstrap_button = QPushButton("调整")
        self.apply_bootstrap_patch_button = QPushButton("应用调整")
        self.cancel_bootstrap_patch_button = QPushButton("取消调整")
        self.approve_bootstrap_button = QPushButton("采用启动包")
        self.save_bootstrap_button.clicked.connect(self._save_bootstrap)
        self.adjust_bootstrap_button.clicked.connect(lambda: self._start_task(self._adjust_bootstrap()))
        self.apply_bootstrap_patch_button.clicked.connect(self._apply_bootstrap_patch)
        self.cancel_bootstrap_patch_button.clicked.connect(self._cancel_bootstrap_patch)
        self.approve_bootstrap_button.clicked.connect(self._approve_bootstrap)
        for button in (self.save_bootstrap_button, self.adjust_bootstrap_button, self.apply_bootstrap_patch_button, self.cancel_bootstrap_patch_button, self.approve_bootstrap_button):
            bootstrap_actions.addWidget(button)
        layout.addLayout(bootstrap_actions)
        self._bootstrap_draft = None
        self._bootstrap_preview = None
        self._bootstrap_fields = []
        self._story_patch_preview = None
        self._set_story_projection(None)
        layout.addStretch()

    def bind_application(self, application) -> None:
        self.cancel_generation()
        self._proposal_task = None
        self._application = application
        planning = load_planning(application.project_dir)
        self._set_brief(planning.story_brief or StoryBrief())
        self.ending_edit.setText(planning.provisional_destination)
        self.adjust_edit.clear()
        proposal = planning.active_draft if hasattr(planning.active_draft, "proposal") else planning.approved_proposal
        self._show_proposal(proposal)
        self.refresh_quick_projection()
        if isinstance(planning.active_draft, ActiveStoryPatchDraft):
            self._story_patch_preview = planning.active_draft
            self._show_story_patch()
        self._show_bootstrap(planning.active_draft if isinstance(planning.active_draft, ActiveBootstrapDraft) else None)

    def refresh_quick_projection(self) -> None:
        """Refresh the compact post-bootstrap projection from canonical storage."""
        if self._application is None:
            self._set_story_projection(None)
            return
        planning = load_planning(self._application.project_dir)
        if planning.approved_brief is not None:
            self.approved_brief_label.setText(
                f"已批准 Brief：{planning.approved_brief.premise or '（未填写）'}"
            )
        else:
            self.approved_brief_label.clear()
        self._set_story_projection(self._application.quick_planning.story_projection())

    def _set_story_projection(self, projection) -> None:
        while self.quick_projection_actions.count():
            item = self.quick_projection_actions.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.quick_projection_label.clear()
        if projection is None:
            self.generate_story_patch_button.setEnabled(False)
            self._cancel_story_patch()
            return
        characters = "、".join(
            f"{character.name}（{character.identity or '未设定'}）"
            for character in projection.main_characters
        ) or "暂无主角"
        setting = projection.core_setting
        self.quick_projection_label.setText(
            "快速总览\n"
            f"主角：{characters}\n"
            f"核心世界：{setting.geography or '未设定'}；规则：{'、'.join(setting.rules) or '未设定'}"
        )
        for character in projection.main_characters:
            button = QPushButton(f"高级角色：{character.name}")
            button.clicked.connect(
                lambda checked=False, character_id=character.id: self.character_requested.emit(character_id)
            )
            self.quick_projection_actions.addWidget(button)
        overview_button = QPushButton("高级世界设定")
        overview_button.clicked.connect(
            lambda: self.world_element_requested.emit("overview")
        )
        self.quick_projection_actions.addWidget(overview_button)
        if self._application is not None:
            elements = self._application.story_bible.load_editor_snapshot().bible.elements
            for element in elements:
                if getattr(getattr(element, "element_type", None), "value", None) != "power_system":
                    continue
                button = QPushButton(f"高级能力：{element.name}")
                button.clicked.connect(
                    lambda checked=False, element_id=element.id: self.world_element_requested.emit(element_id)
                )
                self.quick_projection_actions.addWidget(button)
        self.generate_story_patch_button.setEnabled(True)

    async def _generate_story_patch(self) -> None:
        if self._application is None or not self.story_patch_edit.text().strip():
            return
        application = self._application
        try:
            self._story_patch_preview = await application.quick_planning.generate_story_patch(
                self.story_patch_edit.text().strip()
            )
        except (ProviderConfigurationError, StoryDesignerProviderError,
                ConcurrentModificationError, OperationBlockedError) as error:
            if self._application is application:
                self._provider_error(f"调整失败：{error}", self._generate_story_patch)
            return
        if self._application is application:
            self._show_story_patch()

    def _show_story_patch(self) -> None:
        self.story_patch_label.setText(
            "变更：" + "；".join(self._story_patch_preview.changes or ["无具体变更"])
            + "\n影响：" + "；".join(self._story_patch_preview.consequences or ["无"])
        )
        self.apply_story_patch_button.setEnabled(True)
        self.cancel_story_patch_button.setEnabled(True)

    def _apply_story_patch(self) -> None:
        if self._application is None or self._story_patch_preview is None:
            return
        try:
            self._application.quick_planning.apply_story_patch(self._story_patch_preview)
        except (ConcurrentModificationError, OperationBlockedError, ValueError) as error:
            self._provider_error(f"应用失败：{error}")
            return
        self._cancel_story_patch(clear_persisted=False)
        self.refresh_quick_projection()

    def _cancel_story_patch(self, *, clear_persisted: bool = True) -> None:
        if (
            clear_persisted
            and self._application is not None
            and self._story_patch_preview is not None
        ):
            try:
                self._application.quick_planning.cancel_story_patch(
                    self._story_patch_preview
                )
            except ConcurrentModificationError:
                pass
        self._story_patch_preview = None
        self.story_patch_label.clear()
        self.apply_story_patch_button.setEnabled(False)
        self.cancel_story_patch_button.setEnabled(False)

    def _start_task(self, coroutine) -> None:
        if self._proposal_task is None or self._proposal_task.done():
            self._proposal_task = asyncio.ensure_future(coroutine)
        else:
            coroutine.close()

    def cancel_generation(self) -> None:
        if self._proposal_task is not None and not self._proposal_task.done():
            self._proposal_task.cancel()

    def _set_brief(self, brief: StoryBrief) -> None:
        self.premise_edit.setPlainText(brief.premise)
        for field, values in self._chips.items():
            selected = getattr(brief, field)
            for name, chip in values.items():
                chip.setChecked(name in selected)
            custom = [value for value in selected if value not in values]
            self._custom[field].setText("、".join(custom))
        self._set_combo(self.target_combo, brief.target_length)
        self.custom_target.setValue(brief.custom_target_chapters or 30)
        self._set_combo(self.romance_combo, brief.romance_emphasis)
        self._set_combo(self.protagonist_combo, brief.protagonist_structure)
        self._set_combo(self.chapter_combo, brief.chapter_length.preset)
        self.chapter_chars.setValue(brief.chapter_length.target_chinese_characters)
        self._update_romance_chips()

    @staticmethod
    def _set_combo(combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _update_romance_chips(self) -> None:
        disabled = self.romance_combo.currentData() == "none"
        for name in _ROMANCE_CHIPS:
            chip = self._chips["relationship_tags"][name]
            chip.setEnabled(not disabled)
            if disabled:
                chip.setChecked(False)

    def _brief(self) -> StoryBrief:
        values: dict[str, list[str]] = {}
        for field, chips in self._chips.items():
            selected = [name for name, chip in chips.items() if chip.isChecked()]
            selected.extend(
                value.strip() for value in re.split(r"[、，,]", self._custom[field].text())
            )
            values[field] = selected
        if self.romance_combo.currentData() == "none":
            values["relationship_tags"] = [
                value for value in values["relationship_tags"] if value not in _ROMANCE_CHIPS
            ]
        target = self.target_combo.currentData()
        return StoryBrief(
            **values,
            premise=self.premise_edit.toPlainText(),
            target_length=target,
            custom_target_chapters=self.custom_target.value() if target == "custom" else None,
            romance_emphasis=self.romance_combo.currentData(),
            protagonist_structure=self.protagonist_combo.currentData(),
            chapter_length=ChapterLength(
                preset=self.chapter_combo.currentData(),
                target_chinese_characters=self.chapter_chars.value(),
            ),
        )

    def _save_brief(self) -> None:
        if self._application is not None:
            self._application.story_designer.save_brief(
                self._brief(),
                provisional_destination=(
                    self.ending_edit.text() if self.target_combo.currentData() == "ongoing" else ""
                ),
            )

    def _prepare_brief(self) -> None:
        """Persist changed brief inputs without invalidating a current draft."""
        if self._application is None:
            return
        planning = load_planning(self._application.project_dir)
        brief = self._brief()
        if planning.story_brief is not None:
            brief.revision = planning.story_brief.revision
        destination = self.ending_edit.text() if self.target_combo.currentData() == "ongoing" else ""
        if (
            planning.story_brief == brief
            and planning.provisional_destination == " ".join(destination.split())
        ):
            return
        self._application.story_designer.save_brief(
            brief, provisional_destination=destination
        )

    async def _generate_proposal(self, *, prepared: bool = False) -> None:
        application = self._application
        if application is None:
            return
        if not prepared:
            self._prepare_brief()
        instruction = self.ending_edit.text().strip()
        if self.target_combo.currentData() == "ongoing" and instruction:
            instruction = f"长篇连载的暂定去向：{instruction}"
        try:
            draft = await application.story_designer.generate_proposal(instruction)
        except ProviderConfigurationError as error:
            if self._application is application:
                self._provider_error(str(error), self._generate_proposal)
            return
        except (StoryDesignerProviderError, ConcurrentModificationError, OperationBlockedError) as error:
            if self._application is application:
                self._provider_error(f"生成失败：{error}", self._generate_proposal)
            return
        if self._application is application:
            self._show_proposal(draft)

    async def _adjust_proposal(self) -> None:
        application = self._application
        if application is None:
            return
        self._prepare_brief()
        planning = load_planning(application.project_dir)
        if planning.active_draft is None:
            return await self._generate_proposal(prepared=True)
        try:
            draft = await application.story_designer.adjust_proposal(
                self.adjust_edit.text().strip(), base_revision=planning.active_draft.revision
            )
        except ProviderConfigurationError as error:
            if self._application is application:
                self._provider_error(str(error), self._adjust_proposal)
            return
        except (StoryDesignerProviderError, ConcurrentModificationError, OperationBlockedError) as error:
            if self._application is application:
                self._provider_error(f"调整失败：{error}", self._adjust_proposal)
            return
        if self._application is application:
            self._show_proposal(draft)

    async def _adopt_proposal(self) -> None:
        if self._application is None:
            return
        planning = load_planning(self._application.project_dir)
        if planning.active_draft is None:
            return
        try:
            approved = self._application.story_designer.approve_proposal(
                base_revision=planning.active_draft.revision, accept_title=True
            )
        except (ConcurrentModificationError, OperationBlockedError) as error:
            self._provider_error(f"采用失败：{error}")
            return
        self._show_proposal(approved)
        self._show_bootstrap(None)

    async def _generate_bootstrap(self) -> None:
        application = self._application
        if application is None:
            return
        try:
            draft = await application.story_designer.generate_bootstrap()
        except ProviderConfigurationError as error:
            if self._application is application:
                self._provider_error(str(error), self._generate_bootstrap)
            return
        except (StoryDesignerProviderError, ConcurrentModificationError, OperationBlockedError) as error:
            if self._application is application:
                self._provider_error(f"生成失败：{error}", self._generate_bootstrap)
            return
        if self._application is application:
            self._show_bootstrap(draft)

    def _show_bootstrap(self, draft) -> None:
        self._bootstrap_draft = draft
        self._bootstrap_preview = None
        self.bootstrap_patch_label.clear()
        while self.bootstrap_cards.count():
            item = self.bootstrap_cards.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._bootstrap_fields = []
        editable = draft is not None
        approved = self._application is not None and load_planning(self._application.project_dir).approved_proposal is not None
        can_generate = self._application is not None and self._application.story_designer.can_generate_bootstrap()
        self.bootstrap_button.setVisible(can_generate and not editable)
        self.another_button.setVisible(not editable and self.proposal_label.text() != "尚未生成")
        self.save_bootstrap_button.setEnabled(editable)
        self.adjust_bootstrap_button.setEnabled(editable)
        self.approve_bootstrap_button.setEnabled(editable)
        self.apply_bootstrap_patch_button.setEnabled(False)
        self.cancel_bootstrap_patch_button.setEnabled(False)
        if not editable:
            self.bootstrap_label.setText("采用故事后可生成" if not approved else ("尚未生成" if can_generate else "已采用"))
            self.bootstrap_advanced.clear()
            return
        bootstrap = draft.bootstrap
        self.bootstrap_label.setText(f"v{draft.revision}：可编辑简要卡片；高级字段只读。")
        self._add_bootstrap_field("地理", bootstrap.overview.geography, ("overview", "geography"))
        self._add_bootstrap_field("世界规则", bootstrap.overview.rules, ("overview", "rules"))
        self._add_bootstrap_field("禁忌", bootstrap.overview.taboos, ("overview", "taboos"))
        self._add_bootstrap_field("技术水平", bootstrap.overview.technology_level, ("overview", "technology_level"))
        self._add_bootstrap_field("社会结构", bootstrap.overview.social_structure, ("overview", "social_structure"))
        for index, element in enumerate(bootstrap.elements):
            self._add_bootstrap_field(f"设定 {index + 1} 名称", element.name, ("elements", index, "name"))
            detail = "description" if hasattr(element, "description") else (
                "definition" if hasattr(element, "definition") else "summary"
            )
            self._add_bootstrap_field(f"设定 {index + 1} 简述", getattr(element, detail), ("elements", index, detail))
        for index, character in enumerate(bootstrap.characters):
            self._add_bootstrap_field(f"角色 {index + 1} 名称", character.core.name, ("characters", index, "core", "name"))
            self._add_bootstrap_field(f"角色 {index + 1} 身份", character.core.identity, ("characters", index, "core", "identity"))
            self._add_bootstrap_field(f"角色 {index + 1} 性格", character.core.personality, ("characters", index, "core", "personality"))
        for index, arc in enumerate(bootstrap.arcs):
            self._add_bootstrap_field(f"故事弧 {index + 1}", arc.title, ("arcs", index, "title"))
            self._add_bootstrap_field(f"故事弧 {index + 1} 概要", arc.summary, ("arcs", index, "summary"))
        for index, chapter in enumerate(bootstrap.arcs[0].chapters):
            self._add_bootstrap_field(f"第 {index + 1} 章标题", chapter.title, ("arcs", 0, "chapters", index, "title"))
            self._add_bootstrap_field(f"第 {index + 1} 章概要", chapter.summary, ("arcs", 0, "chapters", index, "summary"))
            self._add_bootstrap_field(f"第 {index + 1} 章钩子", chapter.scenes[0].ending_hook, ("arcs", 0, "chapters", index, "scenes", 0, "ending_hook"))
        for field in ("pacing", "dialogue_density", "description_style", "tone", "sentence_length", "pov"):
            self._add_bootstrap_field(f"风格 {field}", getattr(bootstrap.style, field), ("style", field))
        self.bootstrap_advanced.setPlainText(bootstrap.model_dump_json(indent=2))

    def _add_bootstrap_field(self, label: str, value: str | list[str], path: tuple) -> None:
        row = QHBoxLayout()
        row.addWidget(QLabel(label))
        field = QLineEdit("、".join(value) if isinstance(value, list) else value)
        row.addWidget(field)
        self.bootstrap_cards.addLayout(row)
        self._bootstrap_fields.append((field, path, isinstance(value, list)))

    def _edited_bootstrap(self) -> StoryBootstrap | None:
        if self._bootstrap_draft is None:
            return None
        data = self._bootstrap_draft.bootstrap.model_dump(mode="json")
        for field, path, is_list in self._bootstrap_fields:
            target = data
            for part in path[:-1]:
                target = target[part]
            target[path[-1]] = [item.strip() for item in field.text().replace("，", "、").split("、") if item.strip()] if is_list else field.text()
        return StoryBootstrap.model_validate(data)

    def _save_bootstrap(self) -> bool:
        if self._application is None or self._bootstrap_draft is None:
            return False
        try:
            bootstrap = self._edited_bootstrap()
            if bootstrap is None:
                return False
            saved = self._application.story_designer.save_bootstrap(
                bootstrap, base_revision=self._bootstrap_draft.revision
            )
            self._show_bootstrap(saved)
        except (ConcurrentModificationError, ValueError) as error:
            self._provider_error(f"保存失败：{error}")
            return False
        return True

    async def _adjust_bootstrap(self) -> None:
        if self._application is None or self._bootstrap_draft is None:
            return
        if not self._save_bootstrap():
            return
        application = self._application
        try:
            preview = await application.story_designer.adjust_bootstrap(
                self.bootstrap_adjust_edit.text(), base_revision=self._bootstrap_draft.revision
            )
        except (ProviderConfigurationError, StoryDesignerProviderError, ConcurrentModificationError, OperationBlockedError) as error:
            if self._application is application:
                self._provider_error(f"调整失败：{error}", self._adjust_bootstrap)
            return
        if self._application is application:
            self._bootstrap_preview = preview
            self.bootstrap_patch_label.setText("变更：" + "；".join(preview.changes) + "\n影响：" + "；".join(preview.consequences))
            self.apply_bootstrap_patch_button.setEnabled(True)
            self.cancel_bootstrap_patch_button.setEnabled(True)

    def _apply_bootstrap_patch(self) -> None:
        if self._application is None or self._bootstrap_preview is None:
            return
        try:
            self._show_bootstrap(self._application.story_designer.apply_bootstrap_patch(self._bootstrap_preview))
        except (ConcurrentModificationError, ValueError) as error:
            self._provider_error(f"应用失败：{error}")

    def _cancel_bootstrap_patch(self) -> None:
        self._bootstrap_preview = None
        self.bootstrap_patch_label.clear()
        self.apply_bootstrap_patch_button.setEnabled(False)
        self.cancel_bootstrap_patch_button.setEnabled(False)

    def _approve_bootstrap(self) -> None:
        if self._application is None or self._bootstrap_draft is None:
            return
        if not self._save_bootstrap():
            return
        try:
            self._application.story_designer.approve_bootstrap(base_revision=self._bootstrap_draft.revision)
        except (ConcurrentModificationError, OperationBlockedError, ValueError) as error:
            self._provider_error(f"采用失败：{error}")
            return
        self._show_bootstrap(None)
        self.bootstrap_approved.emit()

    def _show_proposal(self, value) -> None:
        if value is None:
            self.proposal_label.setText("尚未生成")
            self.generate_button.setVisible(True)
            self.adopt_button.setEnabled(False)
            self.adjust_button.setEnabled(False)
            self.another_button.setVisible(False)
            return
        self.generate_button.setVisible(False)
        is_draft = hasattr(value, "proposal")
        self.adopt_button.setEnabled(is_draft)
        self.adjust_button.setEnabled(is_draft)
        self.another_button.setVisible(True)
        proposal = value.proposal if hasattr(value, "proposal") else value
        revision = getattr(value, "revision", "")
        self.proposal_label.setText(
            f"v{revision}\n标题：{proposal.title}\n一句话：{proposal.logline}\n"
            f"主角：{'、'.join(proposal.main_characters)}\n核心冲突：{proposal.core_conflict}\n"
            f"看点：{'、'.join(proposal.story_promises)}\n结局方向：{proposal.ending_direction}"
        )

    def _provider_error(self, message: str, retry=None) -> None:
        application = self._application
        box = QMessageBox(QMessageBox.Icon.Warning, "Story Designer", message, parent=self)
        retry_button = box.addButton("重试", QMessageBox.ButtonRole.AcceptRole) if retry else None
        settings_button = box.addButton("打开设置", QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        if box.clickedButton() is settings_button:
            self.settings_requested.emit()
        elif retry_button is not None and box.clickedButton() is retry_button:
            QTimer.singleShot(
                0,
                lambda: self._start_task(retry()) if self._application is application else None,
            )
