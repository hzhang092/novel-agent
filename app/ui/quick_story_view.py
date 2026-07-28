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
from app.storage.models import ChapterLength, StoryBrief
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
        layout.addStretch()

    def bind_application(self, application) -> None:
        self._application = application
        planning = load_planning(application.project_dir)
        if planning.story_brief:
            self._set_brief(planning.story_brief)
        self.ending_edit.setText(planning.provisional_destination)
        self._show_proposal(planning.active_draft or planning.approved_proposal)

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
        if brief.custom_target_chapters:
            self.custom_target.setValue(brief.custom_target_chapters)
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
        if self._application is None:
            return
        if not prepared:
            self._prepare_brief()
        instruction = self.ending_edit.text().strip()
        if self.target_combo.currentData() == "ongoing" and instruction:
            instruction = f"长篇连载的暂定去向：{instruction}"
        try:
            draft = await self._application.story_designer.generate_proposal(instruction)
        except ProviderConfigurationError as error:
            self._provider_error(str(error), self._generate_proposal)
            return
        except (StoryDesignerProviderError, ConcurrentModificationError, OperationBlockedError) as error:
            self._provider_error(f"生成失败：{error}", self._generate_proposal)
            return
        self._show_proposal(draft)

    async def _adjust_proposal(self) -> None:
        if self._application is None:
            return
        self._prepare_brief()
        planning = load_planning(self._application.project_dir)
        if planning.active_draft is None:
            return await self._generate_proposal(prepared=True)
        try:
            draft = await self._application.story_designer.adjust_proposal(
                self.adjust_edit.text().strip(), base_revision=planning.active_draft.revision
            )
        except ProviderConfigurationError as error:
            self._provider_error(str(error), self._adjust_proposal)
            return
        except (StoryDesignerProviderError, ConcurrentModificationError, OperationBlockedError) as error:
            self._provider_error(f"调整失败：{error}", self._adjust_proposal)
            return
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
        box = QMessageBox(QMessageBox.Icon.Warning, "Story Designer", message, parent=self)
        retry_button = box.addButton("重试", QMessageBox.ButtonRole.AcceptRole) if retry else None
        settings_button = box.addButton("打开设置", QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        if box.clickedButton() is settings_button:
            self.settings_requested.emit()
        elif retry_button is not None and box.clickedButton() is retry_button:
            QTimer.singleShot(0, lambda: self._start_task(retry()))
