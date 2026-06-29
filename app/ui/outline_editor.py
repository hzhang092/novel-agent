"""Outline editor — tree view (Volumes → Chapters → Scenes) with detail forms."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.ui.widgets import StringListEditor

ROLE_NODE_TYPE = Qt.ItemDataRole.UserRole
ROLE_NODE_ID = Qt.ItemDataRole.UserRole + 1
ROLE_CHARACTER_ID = Qt.ItemDataRole.UserRole + 2


class OutlineEditorView(QWidget):
    """Tree-based outline editor for Volumes → Chapters → Scenes.

    Receives the project directory path via ``load_project_dir()``.
    """

    saved = pyqtSignal()
    scene_selected = pyqtSignal(str)  # emits scene_id when user clicks a scene node

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._project_dir: Path | None = None
        self._volumes: list = []
        self._selected_node_id: str | None = None
        self._setup_ui()

    def load_project_dir(self, project_dir: Path) -> None:
        """Load all volumes from disk and populate the tree."""
        from app.storage.project_files import load_all_volumes

        self._project_dir = project_dir
        self._volumes = load_all_volumes(project_dir)
        self._rebuild_tree()

    # ── UI Setup ───────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Toolbar
        toolbar = QHBoxLayout()
        self._add_vol_btn = QPushButton("添加卷")
        self._add_vol_btn.clicked.connect(self._on_add_volume)
        toolbar.addWidget(self._add_vol_btn)

        self._add_ch_btn = QPushButton("添加章")
        self._add_ch_btn.clicked.connect(self._on_add_chapter)
        toolbar.addWidget(self._add_ch_btn)

        self._add_sc_btn = QPushButton("添加场景")
        self._add_sc_btn.clicked.connect(self._on_add_scene)
        toolbar.addWidget(self._add_sc_btn)

        toolbar.addSpacing(12)

        self._delete_btn = QPushButton("删除")
        self._delete_btn.setEnabled(False)
        self._delete_btn.clicked.connect(self._on_delete_node)
        toolbar.addWidget(self._delete_btn)

        self._up_btn = QPushButton("上移")
        self._up_btn.setEnabled(False)
        self._up_btn.clicked.connect(self._on_move_up)
        toolbar.addWidget(self._up_btn)

        self._down_btn = QPushButton("下移")
        self._down_btn.setEnabled(False)
        self._down_btn.clicked.connect(self._on_move_down)
        toolbar.addWidget(self._down_btn)

        toolbar.addStretch()

        self._heatmap_btn = QPushButton("热度图")
        self._heatmap_btn.setCheckable(True)
        self._heatmap_btn.toggled.connect(self._on_toggle_heatmap)
        toolbar.addWidget(self._heatmap_btn)

        self._save_btn = QPushButton("保存")
        self._save_btn.clicked.connect(self._on_save)
        toolbar.addWidget(self._save_btn)
        layout.addLayout(toolbar)

        # Splitter: tree | detail
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Tree
        tree_container = QWidget()
        tree_layout = QVBoxLayout(tree_container)
        tree_layout.setContentsMargins(0, 0, 0, 0)
        tree_layout.addWidget(QLabel("<b>大纲树</b>"))
        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["标题"])
        self._tree.header().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._tree.currentItemChanged.connect(self._on_tree_selection_changed)
        tree_layout.addWidget(self._tree)
        splitter.addWidget(tree_container)

        # Detail forms stacked widget
        self._detail_stack = QStackedWidget()

        self._volume_form = self._build_volume_form()
        self._detail_stack.addWidget(self._volume_form)

        self._chapter_form = self._build_chapter_form()
        self._detail_stack.addWidget(self._chapter_form)

        self._scene_form = self._build_scene_form()
        self._detail_stack.addWidget(self._scene_form)

        self._empty_detail = QLabel("选择一个节点查看详情")
        self._empty_detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._detail_stack.addWidget(self._empty_detail)
        self._detail_stack.setCurrentWidget(self._empty_detail)

        splitter.addWidget(self._detail_stack)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter)

    # ── Volume Detail Form ─────────────────────────────────────────────────

    def _build_volume_form(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        form = QVBoxLayout(container)

        form.addWidget(QLabel("<b>卷标题</b>"))
        self._vol_title = QLineEdit()
        form.addWidget(self._vol_title)

        form.addWidget(QLabel("<b>卷概要</b>"))
        self._vol_summary = QTextEdit()
        self._vol_summary.setMaximumHeight(100)
        form.addWidget(self._vol_summary)

        form.addStretch()
        scroll.setWidget(container)
        return scroll

    def _populate_volume_form(self, vol) -> None:
        self._vol_title.setText(vol.title)
        self._vol_summary.setPlainText(vol.summary)

    # ── Chapter Detail Form ────────────────────────────────────────────────

    def _build_chapter_form(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        form = QVBoxLayout(container)

        form.addWidget(QLabel("<b>章节标题</b>"))
        self._ch_title = QLineEdit()
        form.addWidget(self._ch_title)

        form.addWidget(QLabel("<b>章节概要</b>"))
        self._ch_summary = QTextEdit()
        self._ch_summary.setMaximumHeight(100)
        form.addWidget(self._ch_summary)

        form.addWidget(QLabel("<b>目标字数</b>"))
        self._ch_word_count = QLineEdit()
        self._ch_word_count.setPlaceholderText("3000")
        form.addWidget(self._ch_word_count)

        form.addStretch()
        scroll.setWidget(container)
        return scroll

    def _populate_chapter_form(self, ch) -> None:
        self._ch_title.setText(ch.title)
        self._ch_summary.setPlainText(ch.summary)
        self._ch_word_count.setText(str(ch.target_word_count))

    # ── Scene Detail Form ──────────────────────────────────────────────────

    def _build_scene_form(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        form = QVBoxLayout(container)

        form.addWidget(QLabel("<b>场景标题</b>"))
        self._scene_title = QLineEdit()
        form.addWidget(self._scene_title)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("地点:"))
        self._scene_location = QLineEdit()
        row1.addWidget(self._scene_location)
        row1.addWidget(QLabel("时间:"))
        self._scene_time = QLineEdit()
        row1.addWidget(self._scene_time)
        form.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("视角角色:"))
        self._scene_pov = QComboBox()
        self._scene_pov.setEditable(False)
        row2.addWidget(self._scene_pov)
        form.addLayout(row2)

        form.addWidget(QLabel("<b>参与角色</b>（多选）"))
        self._scene_participants = QListWidget()
        self._scene_participants.setSelectionMode(
            QListWidget.SelectionMode.MultiSelection
        )
        self._scene_participants.setMaximumHeight(100)
        form.addWidget(self._scene_participants)

        form.addWidget(QLabel("<b>场景目标</b>"))
        self._scene_goal = QTextEdit()
        self._scene_goal.setMaximumHeight(60)
        form.addWidget(self._scene_goal)

        form.addWidget(QLabel("<b>冲突</b>"))
        self._scene_conflict = QTextEdit()
        self._scene_conflict.setMaximumHeight(60)
        form.addWidget(self._scene_conflict)

        form.addWidget(QLabel("<b>情节节拍</b>"))
        self._scene_beats = StringListEditor()
        form.addWidget(self._scene_beats)

        form.addWidget(QLabel("<b>情绪转折</b>"))
        self._scene_emotional = QLineEdit()
        self._scene_emotional.setPlaceholderText("如：紧张→对峙→爆发→余波")
        form.addWidget(self._scene_emotional)

        form.addWidget(QLabel("<b>断章（结尾钩子）</b>"))
        self._scene_ending_hook = QTextEdit()
        self._scene_ending_hook.setMaximumHeight(60)
        self._scene_ending_hook.setPlaceholderText("本章结尾的悬念钩子，用于吸引读者继续阅读")
        form.addWidget(self._scene_ending_hook)

        form.addWidget(QLabel("<b>约束条件</b>"))
        self._scene_constraints = StringListEditor()
        form.addWidget(self._scene_constraints)

        form.addStretch()
        scroll.setWidget(container)
        return scroll

    def _character_label(self, character, duplicate_names: set[str]) -> str:
        name = character.core.name
        if name in duplicate_names:
            return f"{name} · {character.core.tier.value} · {character.core.id[:8]}"
        return name

    def _populate_scene_form(self, sc) -> None:
        self._scene_title.setText(sc.title)
        self._scene_location.setText(sc.location)
        self._scene_time.setText(sc.time)

        self._refresh_character_dropdowns()
        idx = self._scene_pov.findData(sc.pov_character_id or "")
        if idx < 0:
            idx = self._scene_pov.findData("")
        if idx >= 0:
            self._scene_pov.setCurrentIndex(idx)

        selected_ids = set(sc.participating_character_ids)
        for i in range(self._scene_participants.count()):
            item = self._scene_participants.item(i)
            item.setSelected(item.data(ROLE_CHARACTER_ID) in selected_ids)

        self._scene_goal.setPlainText(sc.scene_goal)
        self._scene_conflict.setPlainText(sc.conflict)
        self._scene_beats.set_items(sc.required_plot_beats)
        self._scene_emotional.setText(sc.emotional_turn)
        self._scene_ending_hook.setPlainText(sc.ending_hook)
        self._scene_constraints.set_items(sc.constraints)

    def _refresh_character_dropdowns(self) -> None:
        if self._project_dir is None:
            return

        from app.storage.project_files import load_all_characters

        chars = load_all_characters(self._project_dir)
        name_counts = Counter(c.core.name for c in chars)
        duplicate_names = {name for name, count in name_counts.items() if count > 1}

        current_pov_id = self._scene_pov.currentData() or ""
        self._scene_pov.clear()
        self._scene_pov.addItem("", "")
        for char in chars:
            self._scene_pov.addItem(self._character_label(char, duplicate_names), char.core.id)
        idx = self._scene_pov.findData(current_pov_id)
        if idx >= 0:
            self._scene_pov.setCurrentIndex(idx)

        current_selected = {
            self._scene_participants.item(i).data(ROLE_CHARACTER_ID)
            for i in range(self._scene_participants.count())
            if self._scene_participants.item(i).isSelected()
        }
        self._scene_participants.clear()
        for char in chars:
            item = QListWidgetItem(self._character_label(char, duplicate_names))
            item.setData(ROLE_CHARACTER_ID, char.core.id)
            if char.core.id in current_selected:
                item.setSelected(True)
            self._scene_participants.addItem(item)

    def _gather_scene(self, sc_id: str):
        from app.storage.models import SceneOutline

        pov_id = self._scene_pov.currentData() or ""
        participants = [
            self._scene_participants.item(i).data(ROLE_CHARACTER_ID)
            for i in range(self._scene_participants.count())
            if self._scene_participants.item(i).isSelected()
        ]

        return SceneOutline(
            id=sc_id,
            title=self._scene_title.text().strip(),
            location=self._scene_location.text().strip(),
            time=self._scene_time.text().strip(),
            pov_character_id=pov_id,
            participating_character_ids=participants,
            scene_goal=self._scene_goal.toPlainText().strip(),
            conflict=self._scene_conflict.toPlainText().strip(),
            required_plot_beats=self._scene_beats.get_items(),
            emotional_turn=self._scene_emotional.text().strip(),
            ending_hook=self._scene_ending_hook.toPlainText().strip(),
            constraints=self._scene_constraints.get_items(),
        )

    # ── Tree Management ────────────────────────────────────────────────────

    def _rebuild_tree(self) -> None:
        self._tree.blockSignals(True)
        self._tree.clear()
        for vol in self._volumes:
            vol_item = QTreeWidgetItem([vol.title])
            vol_item.setData(0, ROLE_NODE_TYPE, "volume")
            vol_item.setData(0, ROLE_NODE_ID, vol.id)
            for ch in vol.chapters:
                ch_item = QTreeWidgetItem([ch.title])
                ch_item.setData(0, ROLE_NODE_TYPE, "chapter")
                ch_item.setData(0, ROLE_NODE_ID, ch.id)
                for sc in ch.scenes:
                    sc_item = QTreeWidgetItem([sc.title])
                    sc_item.setData(0, ROLE_NODE_TYPE, "scene")
                    sc_item.setData(0, ROLE_NODE_ID, sc.id)
                    ch_item.addChild(sc_item)
                vol_item.addChild(ch_item)
            self._tree.addTopLevelItem(vol_item)
        self._tree.expandAll()
        self._tree.blockSignals(False)

    def _on_tree_selection_changed(self, current, _previous) -> None:
        # Gather unsaved changes from the previous selection
        self._gather_current_form()

        if current is None:
            self._delete_btn.setEnabled(False)
            self._up_btn.setEnabled(False)
            self._down_btn.setEnabled(False)
            return
        self._delete_btn.setEnabled(True)
        self._selected_node_id = current.data(0, ROLE_NODE_ID)
        node_type = current.data(0, ROLE_NODE_TYPE)

        parent = current.parent()
        if parent is None:
            idx = self._tree.indexOfTopLevelItem(current)
            total = self._tree.topLevelItemCount()
        else:
            idx = parent.indexOfChild(current)
            total = parent.childCount()
        self._up_btn.setEnabled(idx > 0)
        self._down_btn.setEnabled(idx < total - 1)

        # Populate detail form based on node type
        if node_type == "volume":
            vol = self._find_volume(self._selected_node_id)
            if vol:
                self._populate_volume_form(vol)
            self._detail_stack.setCurrentWidget(self._volume_form)
        elif node_type == "chapter":
            for vol in self._volumes:
                for ch in vol.chapters:
                    if ch.id == self._selected_node_id:
                        self._populate_chapter_form(ch)
                        break
            self._detail_stack.setCurrentWidget(self._chapter_form)
        elif node_type == "scene":
            for vol in self._volumes:
                for ch in vol.chapters:
                    for sc in ch.scenes:
                        if sc.id == self._selected_node_id:
                            self._populate_scene_form(sc)
                            self.scene_selected.emit(sc.id)
                            break
            self._detail_stack.setCurrentWidget(self._scene_form)

    # ── CRUD Actions ──────────────────────────────────────────────────────

    def _on_add_volume(self) -> None:
        from app.storage.models import VolumeOutline

        vol = VolumeOutline(title="新卷")
        self._volumes.append(vol)
        item = QTreeWidgetItem([vol.title])
        item.setData(0, ROLE_NODE_TYPE, "volume")
        item.setData(0, ROLE_NODE_ID, vol.id)
        self._tree.addTopLevelItem(item)
        self._tree.setCurrentItem(item)
        self._tree.expandItem(item)

    def _on_add_chapter(self) -> None:
        current = self._tree.currentItem()
        if current is None:
            return
        node_type = current.data(0, ROLE_NODE_TYPE)

        from app.storage.models import ChapterOutline

        ch = ChapterOutline(title="新章")
        if node_type == "volume":
            vol = self._find_volume(current.data(0, ROLE_NODE_ID))
            if vol:
                vol.chapters.append(ch)
        elif node_type == "chapter":
            vid = self._get_parent_volume_id(current)
            vol = self._find_volume(vid)
            if vol:
                ch_id = current.data(0, ROLE_NODE_ID)
                for i, existing in enumerate(vol.chapters):
                    if existing.id == ch_id:
                        vol.chapters.insert(i + 1, ch)
                        break
                else:
                    vol.chapters.append(ch)
        else:
            return

        self._rebuild_tree()
        self._select_by_id(ch.id)

    def _on_add_scene(self) -> None:
        current = self._tree.currentItem()
        if current is None:
            return
        node_type = current.data(0, ROLE_NODE_TYPE)
        if node_type not in ("chapter", "scene"):
            return

        from app.storage.models import SceneOutline

        sc = SceneOutline(title="新场景")
        if node_type == "chapter":
            ch_id = current.data(0, ROLE_NODE_ID)
        else:
            parent = current.parent()
            ch_id = parent.data(0, ROLE_NODE_ID)

        for vol in self._volumes:
            for ch in vol.chapters:
                if ch.id == ch_id:
                    if node_type == "scene":
                        sc_id = current.data(0, ROLE_NODE_ID)
                        for i, existing in enumerate(ch.scenes):
                            if existing.id == sc_id:
                                ch.scenes.insert(i + 1, sc)
                                break
                        else:
                            ch.scenes.append(sc)
                    else:
                        ch.scenes.append(sc)
                    break

        self._rebuild_tree()
        self._select_by_id(sc.id)

    def _on_delete_node(self) -> None:
        current = self._tree.currentItem()
        if current is None:
            return
        node_type = current.data(0, ROLE_NODE_TYPE)
        node_id = current.data(0, ROLE_NODE_ID)

        if node_type == "volume":
            self._volumes = [v for v in self._volumes if v.id != node_id]
        elif node_type == "chapter":
            for vol in self._volumes:
                vol.chapters = [c for c in vol.chapters if c.id != node_id]
        elif node_type == "scene":
            for vol in self._volumes:
                for ch in vol.chapters:
                    ch.scenes = [s for s in ch.scenes if s.id != node_id]

        self._rebuild_tree()

    def _on_move_up(self) -> None:
        self._move_node(-1)

    def _on_move_down(self) -> None:
        self._move_node(1)

    def _move_node(self, offset: int) -> None:
        current = self._tree.currentItem()
        if current is None:
            return
        node_type = current.data(0, ROLE_NODE_TYPE)
        node_id = current.data(0, ROLE_NODE_ID)
        parent = current.parent()

        if node_type == "volume":
            idx = self._tree.indexOfTopLevelItem(current)
            new_idx = idx + offset
            if 0 <= new_idx < len(self._volumes):
                self._volumes.insert(new_idx, self._volumes.pop(idx))
        elif node_type == "chapter":
            vid = parent.data(0, ROLE_NODE_ID) if parent else self._get_parent_volume_id(current)
            vol = self._find_volume(vid)
            if vol:
                for i, ch in enumerate(vol.chapters):
                    if ch.id == node_id:
                        new_i = i + offset
                        if 0 <= new_i < len(vol.chapters):
                            vol.chapters.insert(new_i, vol.chapters.pop(i))
                        break
        elif node_type == "scene":
            parent_ch = parent
            ch_id = parent_ch.data(0, ROLE_NODE_ID) if parent_ch else None
            for vol in self._volumes:
                for ch in vol.chapters:
                    if ch.id == ch_id:
                        for i, sc in enumerate(ch.scenes):
                            if sc.id == node_id:
                                new_i = i + offset
                                if 0 <= new_i < len(ch.scenes):
                                    ch.scenes.insert(new_i, ch.scenes.pop(i))
                                break
                        break

        self._rebuild_tree()
        self._select_by_id(node_id)

    # ── Helpers ────────────────────────────────────────────────────────────


    def select_next_scene(self, current_scene_id: str) -> str | None:
        """Find and select the next scene in sequence after the given scene_id.

        Returns the next scene's ID, or None if this is the last scene.
        Navigates across chapter and volume boundaries.
        """
        flat_scenes: list[tuple[str, str]] = []  # (scene_id, chapter_id)
        for vol in self._volumes:
            for ch in vol.chapters:
                for sc in ch.scenes:
                    flat_scenes.append((sc.id, ch.id))

        for i, (sid, _chid) in enumerate(flat_scenes):
            if sid == current_scene_id:
                if i + 1 < len(flat_scenes):
                    next_sid = flat_scenes[i + 1][0]
                    self._select_by_id(next_sid)
                    return next_sid
                return None

        return None

    def _find_volume(self, volume_id: str):
        for vol in self._volumes:
            if vol.id == volume_id:
                return vol
        return None

    def _get_parent_volume_id(self, item: QTreeWidgetItem) -> str | None:
        current = item.parent()
        while current:
            if current.data(0, ROLE_NODE_TYPE) == "volume":
                return current.data(0, ROLE_NODE_ID)
            current = current.parent()
        return None

    def _select_by_id(self, node_id: str) -> None:
        def find_in_item(parent_item):
            if parent_item.data(0, ROLE_NODE_ID) == node_id:
                self._tree.setCurrentItem(parent_item)
                return True
            for i in range(parent_item.childCount()):
                if find_in_item(parent_item.child(i)):
                    return True
            return False

        for i in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(i)
            if item.data(0, ROLE_NODE_ID) == node_id:
                self._tree.setCurrentItem(item)
                return
            if find_in_item(item):
                return

    # ── Heatmap ────────────────────────────────────────────────────────────

    def _on_toggle_heatmap(self, checked: bool) -> None:
        green = QColor("#27ae60")
        red = QColor("#e74c3c")

        for i in range(self._tree.topLevelItemCount()):
            vol_item = self._tree.topLevelItem(i)
            vol_id = vol_item.data(0, ROLE_NODE_ID)
            vol = self._find_volume(vol_id)
            if vol is None:
                continue
            for j in range(vol_item.childCount()):
                ch_item = vol_item.child(j)
                ch_id = ch_item.data(0, ROLE_NODE_ID)
                has_hook = False
                for ch in vol.chapters:
                    if ch.id == ch_id:
                        has_hook = any(sc.ending_hook.strip() for sc in ch.scenes)
                        break
                if checked:
                    ch_item.setBackground(0, QBrush(green if has_hook else red))
                    text = ch_item.text(0).replace("⚠ ", "")
                    if not has_hook:
                        ch_item.setText(0, f"⚠ {text}")
                else:
                    ch_item.setBackground(0, QBrush())
                    ch_item.setText(0, ch_item.text(0).replace("⚠ ", ""))

    # ── Save ───────────────────────────────────────────────────────────────

    def _gather_current_form(self) -> None:
        """Gather data from the currently visible detail form into the data model."""
        if self._selected_node_id is None:
            return
        current = self._tree.currentItem()
        if current is None:
            return
        node_type = current.data(0, ROLE_NODE_TYPE)

        if node_type == "volume":
            vol = self._find_volume(self._selected_node_id)
            if vol:
                vol.title = self._vol_title.text().strip()
                vol.summary = self._vol_summary.toPlainText().strip()
        elif node_type == "chapter":
            for vol in self._volumes:
                for ch in vol.chapters:
                    if ch.id == self._selected_node_id:
                        ch.title = self._ch_title.text().strip()
                        ch.summary = self._ch_summary.toPlainText().strip()
                        try:
                            ch.target_word_count = int(self._ch_word_count.text().strip())
                        except ValueError:
                            ch.target_word_count = 3000
                        break
        elif node_type == "scene":
            for vol in self._volumes:
                for ch in vol.chapters:
                    for sc in ch.scenes:
                        if sc.id == self._selected_node_id:
                            gathered = self._gather_scene(self._selected_node_id)
                            sc.title = gathered.title
                            sc.location = gathered.location
                            sc.time = gathered.time
                            sc.pov_character_id = gathered.pov_character_id
                            sc.participating_character_ids = gathered.participating_character_ids
                            sc.scene_goal = gathered.scene_goal
                            sc.conflict = gathered.conflict
                            sc.required_plot_beats = gathered.required_plot_beats
                            sc.emotional_turn = gathered.emotional_turn
                            sc.ending_hook = gathered.ending_hook
                            sc.constraints = gathered.constraints
                            break

    def _on_save(self) -> None:
        """Persist all volumes to disk."""
        if self._project_dir is None:
            return

        self._gather_current_form()

        from app.storage.project_files import save_volume_outline

        for vol in self._volumes:
            save_volume_outline(self._project_dir, vol)

        self.saved.emit()
