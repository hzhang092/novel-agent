"""Main window with left sidebar navigation and stacked content views."""

from __future__ import annotations

import asyncio
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStackedWidget,
    QWidget,
)

from app.storage.models import Project as ProjectModel
from app.storage.repository import Repository
from app.ui.bible_editor import BibleEditorView
from app.ui.create_project_dialog import CreateProjectDialog
from app.ui.settings_dialog import SettingsDialog
from app.ui.dashboard import DashboardView
from app.ui.outline_editor import OutlineEditorView
from app.ui.scene_workspace import SceneWorkspaceView

NAV_ITEMS = [
    ("总览", "dashboard"),
    ("设定集", "bible"),
    ("大纲", "outline"),
    ("写作台", "workspace"),
]


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("NovelForge")
        self.resize(1200, 800)

        self._repo = Repository(Path.home() / "NovelForge")
        self._current_project: ProjectModel | None = None
        self._current_project_dir: Path | None = None
        self._previous_tab_index: int = 0

        self._setup_menu()
        self._setup_ui()

    def _setup_menu(self) -> None:
        menubar = self.menuBar()

        file_menu = menubar.addMenu("文件(&F)")

        new_action = QAction("新建项目(&N)", self)
        new_action.triggered.connect(self._on_new_project)
        file_menu.addAction(new_action)

        open_action = QAction("打开项目(&O)", self)
        open_action.triggered.connect(self._on_open_project)
        file_menu.addAction(open_action)

        file_menu.addSeparator()
        settings_action = QAction("LLM 设置(&S)...", self)
        settings_action.triggered.connect(self._on_llm_settings)
        file_menu.addAction(settings_action)

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Sidebar
        self.sidebar = QListWidget()
        self.sidebar.setFixedWidth(180)
        self.sidebar.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for label, key in NAV_ITEMS:
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, key)
            self.sidebar.addItem(item)

        # Stacked views
        self.stack = QStackedWidget()
        self.views: dict[str, QWidget] = {
            "dashboard": DashboardView(),
            "bible": BibleEditorView(),
            "outline": OutlineEditorView(),
            "workspace": SceneWorkspaceView(),
        }
        for key in ["dashboard", "bible", "outline", "workspace"]:
            self.stack.addWidget(self.views[key])

        # Layout: sidebar | content
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.sidebar)
        splitter.addWidget(self.stack)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter)

        # Connect navigation
        self.sidebar.currentRowChanged.connect(self._on_nav_changed)
        self.sidebar.setCurrentRow(0)

        # Disable non-dashboard sidebar items until a project is loaded
        self._set_nav_items_enabled(False)

    def _on_nav_changed(self, index: int) -> None:
        # Auto-save Bible editor when navigating away from it
        if self._previous_tab_index == 1:  # Bible tab index
            bible = self.views["bible"]
            if isinstance(bible, BibleEditorView) and bible._project_dir is not None:
                bible._on_save()

        # Auto-save Outline editor when navigating away from it
        if self._previous_tab_index == 2:  # Outline tab index
            outline = self.views["outline"]
            if isinstance(outline, OutlineEditorView) and outline._project_dir is not None:
                outline._on_save()

        # Load workspace when navigating to it
        if index == 3:  # Workspace tab index
            workspace = self.views["workspace"]
            if isinstance(workspace, SceneWorkspaceView) and self._current_project_dir is not None:
                workspace.load_project_dir(self._current_project_dir)
                try:
                    workspace.generate_requested.disconnect()
                except TypeError:
                    pass
                workspace.generate_requested.connect(self._on_generate_requested)

        self._previous_tab_index = index

        item = self.sidebar.item(index)
        if item is None:
            return
        # Block navigation to disabled items
        if not (item.flags() & Qt.ItemFlag.ItemIsEnabled):
            self.sidebar.setCurrentRow(0)
            return
        key = item.data(Qt.ItemDataRole.UserRole)
        if key in self.views:
            self.stack.setCurrentWidget(self.views[key])

    # ── Actions ───────────────────────────────────────────────────────────

    def _on_new_project(self) -> None:
        dialog = CreateProjectDialog(self)
        if not dialog.exec():
            return

        result = dialog.get_result()
        if result is None:
            return

        project = ProjectModel(
            title=result["title"],
            genre=result["genre"],
            llm_provider=result["llm_provider"],
        )

        try:
            proj_dir = self._repo.create(project)
        except FileExistsError:
            QMessageBox.warning(self, "错误", f"项目「{result['title']}」已存在")
            return

        self._current_project = project
        self._current_project_dir = proj_dir
        self.setWindowTitle(f"NovelForge — {project.title}")

        self._set_nav_items_enabled(True)

        bible = self.views["bible"]
        if isinstance(bible, BibleEditorView):
            bible.load_project_dir(proj_dir)

        outline = self.views["outline"]
        if isinstance(outline, OutlineEditorView):
            outline.load_project_dir(proj_dir)
            try:
                outline.scene_selected.disconnect()
            except TypeError:
                pass

        QMessageBox.information(
            self, "创建成功", f"项目「{project.title}」已创建\n{proj_dir}"
        )

    def _on_open_project(self) -> None:
        dir_path = QFileDialog.getExistingDirectory(
            self, "打开项目", str(Path.home() / "NovelForge")
        )
        if not dir_path:
            return

        try:
            project = self._repo.open(Path(dir_path))
        except FileNotFoundError:
            QMessageBox.warning(self, "错误", "所选目录不是有效项目")
            return
        except ValueError as e:
            QMessageBox.warning(self, "错误", f"项目文件无效:\n{e}")
            return

        self._current_project = project
        self._current_project_dir = Path(dir_path)
        self.setWindowTitle(f"NovelForge — {project.title}")

        self._set_nav_items_enabled(True)

        bible = self.views["bible"]
        if isinstance(bible, BibleEditorView):
            bible.load_project_dir(Path(dir_path))

        outline = self.views["outline"]
        if isinstance(outline, OutlineEditorView):
            outline.load_project_dir(Path(dir_path))
            try:
                outline.scene_selected.disconnect()
            except TypeError:
                pass
            outline.scene_selected.connect(self._on_scene_selected)

            workspace = self.views["workspace"]
            if isinstance(workspace, SceneWorkspaceView):
                workspace.load_project_dir(Path(dir_path))
                try:
                    workspace.generate_requested.disconnect()
                except TypeError:
                    pass
                workspace.generate_requested.connect(self._on_generate_requested)

    def _on_llm_settings(self) -> None:
        """Open the LLM provider settings dialog."""
        dialog = SettingsDialog(self)
        dialog.exec()

    def _on_scene_selected(self, scene_id: str) -> None:
        """Handle scene selection: assemble context, find chapter, update workspace."""
        if self._current_project_dir is None:
            return

        workspace = self.views.get("workspace")
        if not isinstance(workspace, SceneWorkspaceView):
            return

        chapter_id = self._find_chapter_for_scene(scene_id)
        workspace.set_scene(scene_id, chapter_id or "")

        try:
            from app.pipeline.context_builder import RetrievalEngine
            engine = RetrievalEngine()
            context = engine.assemble(self._current_project_dir, scene_id=scene_id)
            workspace.show_context(context)
        except Exception:
            workspace.clear_context()

    def _on_generate_requested(self, scene_id: str) -> None:
        """Trigger scene generation for the given scene."""
        if self._current_project_dir is None:
            return

        workspace = self.views.get("workspace")
        if not isinstance(workspace, SceneWorkspaceView):
            return

        from app.providers.config import get_provider_for_step, load_provider_config

        config = load_provider_config()
        provider = get_provider_for_step("writer", config)

        workspace.set_generating(True)
        workspace.editor.setPlainText("")
        workspace.trace_panel.set_running("Writer")

        from app.pipeline.pipeline import ScenePipeline

        pipeline = ScenePipeline()

        async def _run():
            try:
                async for token, result in pipeline.generate_stream(
                    self._current_project_dir, scene_id, provider
                ):
                    if token is not None:
                        workspace.editor.append(token)
                    if result is not None:
                        workspace.trace_panel.set_completed(
                            "Writer",
                            result.total_duration_ms,
                            result.total_tokens,
                        )
                        workspace.set_generating(False)
                        workspace._status_label.setText("\u5df2\u751f\u6210")
                        self._save_generated_scene(result)
                        return
            except Exception as e:
                workspace.trace_panel.set_failed("Writer", str(e))
                workspace.set_generating(False)
                workspace._status_label.setText("\u751f\u6210\u5931\u8d25")

        asyncio.ensure_future(_run())

    def _save_generated_scene(self, result) -> None:
        """Save generated prose and generation record to disk."""
        if self._current_project_dir is None:
            return

        chapter_id = self._find_chapter_for_scene(result.scene_id)
        if not chapter_id:
            return

        from app.storage.project_files import save_scene_prose, save_scene_generation_record
        from app.storage.models import SceneGenerationRecord

        save_scene_prose(self._current_project_dir, chapter_id, result.scene_id, result.prose)

        record = SceneGenerationRecord(
            scene_id=result.scene_id,
            generation_mode="standard",
            draft_text=result.prose,
            final_text=result.prose,
        )
        save_scene_generation_record(self._current_project_dir, record)

    def _find_chapter_for_scene(self, scene_id: str) -> str | None:
        """Find the chapter ID containing a scene by scanning all volumes."""
        from app.storage.project_files import load_all_volumes

        volumes = load_all_volumes(self._current_project_dir)
        for vol in volumes:
            for ch in vol.chapters:
                for sc in ch.scenes:
                    if sc.id == scene_id:
                        return ch.id
        return None

    def _set_nav_items_enabled(self, enabled: bool) -> None:
        """Enable or disable all non-dashboard sidebar items."""
        for i in range(1, self.sidebar.count()):
            item = self.sidebar.item(i)
            if item is not None:
                flags = item.flags()
                if enabled:
                    flags |= Qt.ItemFlag.ItemIsEnabled
                    flags |= Qt.ItemFlag.ItemIsSelectable
                else:
                    flags &= ~Qt.ItemFlag.ItemIsEnabled
                    flags &= ~Qt.ItemFlag.ItemIsSelectable
                item.setFlags(flags)
            outline.scene_selected.connect(self._on_scene_selected)

