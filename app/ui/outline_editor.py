"""Outline editor — tree view (Volumes → Chapters → Scenes) with detail forms."""
from __future__ import annotations

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
    QMessageBox,
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


class OutlineEditorView(QWidget):
    """Tree-based outline editor for Volumes → Chapters → Scenes.

    Receives the project directory path via ``load_project_dir()``.
    """

    saved = pyqtSignal()

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

        # Splitter: tree | detail placeholder
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

        # Detail placeholder
        self._detail_label = QLabel("选择一个节点查看详情")
        self._detail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        splitter.addWidget(self._detail_label)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter)

    # ── Tree Management ────────────────────────────────────────────────────

    def _rebuild_tree(self) -> None:
        """Rebuild the tree from self._volumes."""
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
        if current is None:
            self._delete_btn.setEnabled(False)
            self._up_btn.setEnabled(False)
            self._down_btn.setEnabled(False)
            return
        self._delete_btn.setEnabled(True)
        self._selected_node_id = current.data(0, ROLE_NODE_ID)

        parent = current.parent()
        if parent is None:
            idx = self._tree.indexOfTopLevelItem(current)
            total = self._tree.topLevelItemCount()
        else:
            idx = parent.indexOfChild(current)
            total = parent.childCount()
        self._up_btn.setEnabled(idx > 0)
        self._down_btn.setEnabled(idx < total - 1)

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

    def _on_save(self) -> None:
        """Save all volumes to disk."""
        pass
