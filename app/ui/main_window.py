"""Main window with left sidebar navigation and stacked content views."""

from __future__ import annotations

import asyncio
import weakref
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QSignalBlocker, Qt, QUrl
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog,
    QLabel,
    QHBoxLayout,
    QComboBox,
    QMainWindow,
    QMenu,
    QMessageBox,
    QSplitter,
    QStackedWidget,
    QWidget,
)

from app.application.project_context import (
    ProjectApplicationContext,
    build_project_application,
)
from app.application.scene_workflow import SceneWorkflowObserver
from app.storage.models import Project as ProjectModel
from app.storage.repository import Repository
from app.storage.editor_layout import EditorLayoutStore
from app.storage.project_files import create_quick_project
import logging

from app.events.bus import EventBus
from app.events.qt_bridge import QtEventBridge
from app.ui.bible_editor import BibleEditorView

logger = logging.getLogger(__name__)
from app.ui.create_project_dialog import CreateProjectDialog
from app.ui.settings_dialog import SettingsDialog
from app.ui.dashboard import DashboardView
from app.ui.outline_editor import OutlineEditorView
from app.ui.scene_workspace import SceneWorkspaceView
from app.ui.experience_presentations import DeepCreationPresentation, QuickCreationPresentation
from app.ui.quick_story_view import QuickStoryView
from app.ui.quick_outline_view import QuickOutlineView

class MainWindow(QMainWindow):
    def __init__(self, *, quick_creation_enabled: bool | None = None) -> None:
        super().__init__()
        self._quick_creation_enabled = (
            True if quick_creation_enabled is None else quick_creation_enabled
        )
        self.setWindowTitle("NovelForge")
        self.resize(1200, 800)
        self._current_prose_version: str | None = None

        self._repo = Repository(Path.home() / "NovelForge")
        self._current_project: ProjectModel | None = None
        self._current_project_dir: Path | None = None
        self._application: ProjectApplicationContext | None = None
        self._previous_tab_index: int = 0
        self._previous_destination = "dashboard"
        self._experience_mode = "deep"
        self._editor_layout_store: EditorLayoutStore | None = None
        self._pending_plan_patch: tuple[object, str] | None = None

        # Event bus for live UI refresh
        self._domain_bus = EventBus()
        self._event_bridge = QtEventBridge(self._domain_bus)

        self._setup_menu()
        self._setup_ui()
        self._token_status_label = QLabel("Tokens: —")
        self._token_status_label.setStyleSheet("color: #888; font-size: 11px; padding: 0 8px;")
        self.statusBar().addPermanentWidget(self._token_status_label)

    def closeEvent(self, event) -> None:
        if self._maybe_close_current_project():
            event.accept()
        else:
            event.ignore()

    def _setup_menu(self) -> None:
        menubar = self.menuBar()

        self._file_menu = QMenu("文件(&F)", menubar)
        menubar.addMenu(self._file_menu)
        file_menu = self._file_menu

        new_action = QAction("新建项目(&N)", self)
        new_action.triggered.connect(self._on_new_project)
        file_menu.addAction(new_action)

        open_action = QAction("打开项目(&O)", self)
        open_action.triggered.connect(self._on_open_project)
        file_menu.addAction(open_action)

        open_folder_action = QAction("打开项目文件夹(&F)", self)
        open_folder_action.triggered.connect(self._on_open_project_folder)
        file_menu.addAction(open_folder_action)

        file_menu.addSeparator()
        settings_action = QAction("LLM 设置(&S)...", self)
        settings_action.triggered.connect(self._on_llm_settings)
        file_menu.addAction(settings_action)

        help_action = QAction("创作帮助(&H)", self)
        help_action.triggered.connect(self._show_creation_help)
        file_menu.addAction(help_action)
        self._help_action = help_action

        file_menu.addSeparator()
        export_md_action = QAction("导出 Markdown(&M)...", self)
        export_md_action.triggered.connect(self._on_export_markdown)
        file_menu.addAction(export_md_action)

        export_epub_action = QAction("导出 EPUB(&E)...", self)
        export_epub_action.triggered.connect(self._on_export_epub)
        file_menu.addAction(export_epub_action)

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._experience_switch = QComboBox()
        self._experience_switch.addItem("快速创作", "quick")
        self._experience_switch.addItem("深度创作", "deep")
        self._experience_switch.setVisible(self._quick_creation_enabled)
        self._experience_switch.currentIndexChanged.connect(self._on_experience_changed)
        layout.addWidget(self._experience_switch)
        self._presentation_stack = QStackedWidget()
        self._deep_presentation = DeepCreationPresentation()
        self._quick_presentation = QuickCreationPresentation()
        self._presentation_stack.addWidget(self._deep_presentation)
        self._presentation_stack.addWidget(self._quick_presentation)
        self.sidebar = self._deep_presentation.sidebar
        self.stack = self._deep_presentation.stack
        self._dashboard_view = DashboardView()
        self._quick_story_view = QuickStoryView()
        self._bible_view = BibleEditorView()
        self._outline_view = OutlineEditorView()
        self._quick_outline_view = QuickOutlineView()
        self._workspace_view = SceneWorkspaceView()
        self._deep_save_in_progress = False
        window_ref = weakref.ref(self)

        def guard_deep_save(save: Callable[[], bool]) -> bool:
            window = window_ref()
            return window.guard_deep_save(save) if window is not None else save()

        self._bible_view.set_save_handler(guard_deep_save)
        self._outline_view.set_save_handler(guard_deep_save)
        self._views: dict[str, QWidget] = {
            "dashboard": self._dashboard_view,
            "story": self._quick_story_view,
            "bible": self._bible_view,
            "outline": self._outline_view,
            "workspace": self._workspace_view,
        }
        self._deep_presentation.stack.addWidget(self._dashboard_view)
        self._deep_presentation.stack.addWidget(self._bible_view)
        self._deep_presentation.stack.addWidget(self._outline_view)
        self._quick_presentation.stack.addWidget(self._quick_story_view)
        self._quick_presentation.stack.addWidget(self._quick_outline_view)
        self._deep_presentation.destination_changed.connect(self._on_destination_changed)
        self._quick_presentation.destination_changed.connect(self._on_destination_changed)
        self._connect_view_signals()
        layout.addWidget(self._presentation_stack)
        self._activate_presentation("deep", "dashboard")

        # Disable non-dashboard sidebar items until a project is loaded
        self._set_nav_items_enabled(False)

    def _open_scene_from_bible(self, scene_id: str) -> None:
        self._select_destination("workspace")
        self._outline_view.activate_scene(scene_id)

    def _open_quick_scene(self, scene_id: str) -> None:
        self._on_scene_selected(scene_id)
        self._select_destination("workspace")

    def _open_deep_character(self, character_id: str) -> None:
        self._set_experience_mode("deep")
        self._select_destination("bible")
        self._bible_view.open_character(character_id)

    def _open_deep_world_element(self, element_id: str) -> None:
        self._set_experience_mode("deep")
        self._select_destination("bible")
        self._bible_view.open_world_element(element_id)

    def _open_deep_outline(self, chapter_id: str) -> None:
        self._set_experience_mode("deep")
        self._select_destination("outline")
        if self._current_project_dir is not None:
            self._outline_view.load_project_dir(self._current_project_dir)
        scene_id = self._scene_for_chapter(chapter_id)
        if scene_id:
            self._outline_view.activate_scene(scene_id)

    def _scene_for_chapter(self, chapter_id: str) -> str | None:
        if self._current_project_dir is None:
            return None
        from app.storage.project_files import load_all_volumes

        return next(
            (
                chapter.scenes[0].id
                for volume in load_all_volumes(self._current_project_dir)
                for chapter in volume.chapters
                if chapter.id == chapter_id and chapter.scenes
            ),
            None,
        )

    def _chapter_length(self, chapter_id: str) -> tuple[str, int]:
        if self._current_project_dir is None:
            return "standard", 3000
        from app.application.scene_workflow import resolve_chapter_target
        from app.storage.project_files import load_all_volumes, load_project

        project = load_project(self._current_project_dir)
        chapter = next(
            (
                item
                for volume in load_all_volumes(self._current_project_dir)
                for item in volume.chapters
                if item.id == chapter_id
            ),
            None,
        )
        setting = chapter.chapter_length_override if chapter else None
        mode = setting.preset if setting is not None else project.chapter_length.preset
        return mode, resolve_chapter_target(project, chapter)

    def _connect_view_signals(self) -> None:
        """Connect view signals once during UI construction."""
        self._bible_view.elements_changed.connect(
            self._outline_view.refresh_world_elements
        )
        self._bible_view.scene_requested.connect(self._open_scene_from_bible)
        self._outline_view.scene_selected.connect(self._on_scene_selected)
        self._workspace_view.generate_requested.connect(self._on_generate_requested)
        self._workspace_view.retry_requested.connect(self._retry_agent)
        self._workspace_view.next_scene_requested.connect(self._on_next_scene)
        self._workspace_view.continue_review_requested.connect(
            self._on_continue_review_requested
        )
        self._workspace_view.prose_version_selected.connect(
            self._on_prose_version_selected
        )
        self._workspace_view.publish_version_requested.connect(
            self._on_set_active_prose_version
        )
        self._workspace_view.approval_batch_approved.connect(
            self._on_approval_batch_approved
        )
        self._workspace_view.plan_approved.connect(self._on_plan_approved)
        self._workspace_view.plan_rejected.connect(self._on_plan_rejected)
        self._workspace_view.quick_start_requested.connect(self._on_quick_start)
        self._workspace_view.quick_adjust_requested.connect(
            self._open_deep_workspace_for_chapter
        )
        self._workspace_view.quick_save_requested.connect(self._on_quick_save)
        self._workspace_view.quick_regenerate_requested.connect(
            self._on_quick_regenerate
        )
        self._workspace_view.quick_revision_instruction_requested.connect(
            self._on_quick_revision_instruction
        )
        self._workspace_view.quick_length_changed.connect(
            self._on_quick_length_changed
        )
        self._workspace_view.quick_ai_fix_requested.connect(self._on_quick_ai_fix)
        self._workspace_view.quick_details_requested.connect(
            self._open_deep_workspace
        )
        self._workspace_view.quick_override_requested.connect(
            self._on_continue_review_requested
        )
        self._workspace_view.quick_approve_requested.connect(self._on_quick_approve)
        self._workspace_view.quick_approve_next_requested.connect(
            self._on_quick_approve_next
        )
        self._workspace_view.deep_control_requested.connect(
            self._open_deep_control
        )
        self._quick_story_view.settings_requested.connect(self._on_llm_settings)
        self._quick_story_view.bootstrap_approved.connect(self._reload_after_bootstrap)
        self._quick_story_view.character_requested.connect(self._open_deep_character)
        self._quick_story_view.world_element_requested.connect(self._open_deep_world_element)
        self._quick_outline_view.scene_selected.connect(self._open_quick_scene)
        self._quick_outline_view.deep_outline_requested.connect(self._open_deep_outline)

    def _reload_after_bootstrap(self) -> None:
        """Refresh existing canonical editors after Quick approves a bootstrap."""
        self._bible_view.reload()
        if self._current_project_dir is not None:
            self._outline_view.load_project_dir(self._current_project_dir)
            self._quick_outline_view.refresh()

    def _bind_project_application(self, project_dir: Path) -> None:
        self._current_project_dir = project_dir
        self._application = build_project_application(
            project_dir,
            event_bus=self._domain_bus,
        )
        self._bible_view.bind_application(self._application)
        self._outline_view.bind_application(self._application.outlines)
        self._quick_outline_view.bind_application(self._application.quick_planning)
        self._quick_story_view.bind_application(self._application)
        self._editor_layout_store = EditorLayoutStore(project_dir)
        self._set_nav_items_enabled(True)
        preferred = self._editor_layout_store.layout.experience_mode
        self._set_experience_mode(preferred)

    def _set_experience_mode(self, mode: str) -> None:
        """Swap presentation navigation while preserving shared editor widgets."""
        if mode == "quick" and not self._quick_creation_enabled:
            mode = "deep"
        self._experience_mode = mode if mode == "quick" else "deep"
        index = self._experience_switch.findData(self._experience_mode)
        blocker = QSignalBlocker(self._experience_switch)
        self._experience_switch.setCurrentIndex(index)
        del blocker
        self._activate_presentation(self._experience_mode, None)

    def _activate_presentation(self, mode: str, destination: str | None) -> None:
        target = self._quick_presentation if mode == "quick" else self._deep_presentation
        source = self._deep_presentation if target is self._quick_presentation else self._quick_presentation
        self._workspace_view.set_experience_mode(mode)
        for view in (self._workspace_view,):
            if source.stack.indexOf(view) >= 0:
                source.stack.removeWidget(view)
                target.stack.addWidget(view)
            elif target.stack.indexOf(view) < 0:
                target.stack.addWidget(view)
        self._views["outline"] = (
            self._quick_outline_view if mode == "quick" else self._outline_view
        )
        self._presentation_stack.setCurrentWidget(target)
        self.sidebar, self.stack = target.sidebar, target.stack
        destinations = target.destinations
        if destination is None:
            layout = self._editor_layout_store.layout if self._editor_layout_store else None
            destination = (
                layout.quick_destination if mode == "quick" else layout.deep_destination
            ) if layout else None
        if destination not in {key for _, key in destinations}:
            destination = "story" if mode == "quick" else "dashboard"
        self._select_destination(destination)

    def _select_destination(self, key: str) -> None:
        for row in range(self.sidebar.count()):
            if self.sidebar.item(row).data(Qt.ItemDataRole.UserRole) == key:
                self.sidebar.setCurrentRow(row)
                return

    def _on_destination_changed(self, key: str) -> None:
        self._on_nav_changed(self.sidebar.currentRow())

    def _on_experience_changed(self, _index: int) -> None:
        mode = self._experience_switch.currentData()
        if mode == "quick" and not self._quick_creation_enabled:
            blocker = QSignalBlocker(self._experience_switch)
            self._experience_switch.setCurrentIndex(self._experience_switch.findData("deep"))
            del blocker
            return
        if mode not in {"quick", "deep"} or mode == self._experience_mode:
            return
        current = self._previous_destination
        if mode == "deep" and current == "story":
            remembered = (
                self._editor_layout_store.layout.deep_destination
                if self._editor_layout_store is not None
                else None
            )
            target = remembered or "bible"
        elif mode == "quick" and current == "bible":
            target = "story"
        else:
            target = current
        leaving_bible = current == "bible" and target != "bible"
        if leaving_bible and not self._maybe_close_current_project():
            blocker = QSignalBlocker(self._experience_switch)
            self._experience_switch.setCurrentIndex(
                self._experience_switch.findData(self._experience_mode)
            )
            del blocker
            return
        if leaving_bible:
            self._previous_destination = target
        if (
            self._experience_mode == "deep"
            and current == "outline"
            and self._outline_view.is_loaded
        ):
            if not self._save_deep_outline():
                blocker = QSignalBlocker(self._experience_switch)
                self._experience_switch.setCurrentIndex(
                    self._experience_switch.findData(self._experience_mode)
                )
                del blocker
                return
            self._quick_outline_view.refresh()
        self._experience_mode = mode
        if mode == "quick" and self._application is not None:
            self._application.story_designer.ensure_quick_brief()
            self._quick_story_view.refresh_brief()
        if self._editor_layout_store is not None:
            self._editor_layout_store.layout.experience_mode = mode
            self._editor_layout_store.save()
        self._activate_presentation(mode, target)
        if (
            mode == "deep"
            and target == "outline"
            and self._current_project_dir is not None
        ):
            chapter_id = self._quick_outline_view.selected_chapter_id
            self._outline_view.load_project_dir(self._current_project_dir)
            scene_id = self._scene_for_chapter(chapter_id)
            if scene_id:
                self._outline_view.activate_scene(scene_id)

    def _on_nav_changed(self, index: int) -> None:
        item = self.sidebar.item(index)
        if item is None:
            return
        key = item.data(Qt.ItemDataRole.UserRole)
        previous_key = self._previous_destination
        if self.sidebar.currentRow() != index or previous_key not in self._views:
            previous_items = self._quick_presentation.destinations if self._experience_mode == "quick" else self._deep_presentation.destinations
            previous_key = previous_items[self._previous_tab_index][1]
        if (
            previous_key == "bible"
            and key != "bible"
            and not self._maybe_close_current_project()
        ):
            blocker = QSignalBlocker(self.sidebar)
            self.sidebar.setCurrentRow(self._previous_tab_index)
            del blocker
            return

        # Auto-save Outline editor when navigating away from it
        if (
            self._experience_mode == "deep"
            and previous_key == "outline"
            and key != "outline"
            and self._outline_view.is_loaded
        ):
            if not self._save_deep_outline():
                blocker = QSignalBlocker(self.sidebar)
                self.sidebar.setCurrentRow(self._previous_tab_index)
                del blocker
                return

        # Wire event bus to Bible Editor's character editor when navigating to Bible
        if key == "bible":
            self._bible_view.set_event_bus(self._domain_bus)
            self._bible_view.refresh_usage()

        # Load workspace when navigating to it
        if key == "workspace" and self._current_project_dir is not None:
            self._workspace_view.load_project_dir(self._current_project_dir)

        self._previous_tab_index = index
        self._previous_destination = key
        if not (item.flags() & Qt.ItemFlag.ItemIsEnabled):
            self.sidebar.setCurrentRow(0)
            return
        if self._editor_layout_store is not None:
            if self._experience_mode == "quick":
                self._editor_layout_store.layout.quick_destination = key
            else:
                self._editor_layout_store.layout.deep_destination = key
            self._editor_layout_store.schedule_save()
        if key in self._views:
            self.stack.setCurrentWidget(self._views[key])

    # ── Actions ───────────────────────────────────────────────────────────

    def _maybe_close_current_project(self) -> bool:
        if not self._bible_view.is_loaded or not self._bible_view.is_dirty:
            return True

        reply = QMessageBox.question(
            self,
            "未保存的更改",
            "设定集有未保存的更改。是否保存？",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Save:
            return self._bible_view.save_all()
        if reply == QMessageBox.StandardButton.Discard:
            self._bible_view.reload()
            return True
        return False

    def _confirm_bootstrap_discard(self) -> bool:
        """Warn once before a Deep canonical save clears a bootstrap draft."""
        if self._application is None or not self._application.story_designer.has_unapproved_bootstrap():
            return True
        reply = QMessageBox.question(
            self,
            "未采用的故事启动包",
            "深度创作的保存会丢弃未采用的故事启动包，但会保留故事意向和已采用的故事提案。继续吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return False
        return True

    def _save_deep_outline(self) -> bool:
        return self._outline_view.save()

    def guard_deep_save(self, save: Callable[[], bool]) -> bool:
        if self._deep_save_in_progress:
            return save()
        if not self._confirm_bootstrap_discard():
            return False
        self._deep_save_in_progress = True
        try:
            saved = save()
        finally:
            self._deep_save_in_progress = False
        if saved and self._application is not None:
            self._application.story_designer.discard_unapproved_bootstrap()
        return saved

    def _on_new_project(self) -> None:
        from PySide6.QtCore import QSettings

        settings = QSettings()
        last_parent = settings.value("projects/last_parent", str(Path.home() / "NovelForge"))
        dialog = CreateProjectDialog(
            self,
            Path(str(last_parent)),
            self._quick_creation_enabled,
        )
        if not dialog.exec():
            return

        result = dialog.get_result()
        if result is None:
            return
        if not self._maybe_close_current_project():
            return

        try:
            if result.get("creation_mode", "blank") == "quick":
                proj_dir = create_quick_project(Path(result["storage_dir"]), result["title"])
                project = self._repo.open(proj_dir)
                layout = EditorLayoutStore(proj_dir)
                layout.layout.experience_mode = "quick"
                layout.layout.quick_destination = "story"
                layout.save()
            else:
                project = ProjectModel(
                    title=result["title"],
                    genre=result["genre"],
                    llm_provider=result["llm_provider"],
                )
                proj_dir = Repository(Path(result["storage_dir"])).create(project)
        except FileExistsError:
            QMessageBox.warning(self, "错误", f"项目「{result['title']}」已存在")
            return

        self._current_project = project
        self._current_project_dir = proj_dir
        self._bind_project_application(proj_dir)
        self.setWindowTitle(f"NovelForge — {project.title}")

        self._set_nav_items_enabled(True)

        from app.pipeline.token_tracker import TokenTracker
        TokenTracker.reset()
        TokenTracker.get()
        self._update_status_bar_tokens()

        self._bible_view.load_project_dir(proj_dir)
        self._dashboard_view.load_project_dir(proj_dir)
        self._outline_view.load_project_dir(proj_dir)
        self._workspace_view.load_project_dir(proj_dir)
        settings.setValue("projects/last_parent", str(proj_dir.parent))

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
            project_dir = Path(dir_path)
            project = self._repo.open(project_dir)
            from app.storage.project_files import (
                load_all_characters,
                load_all_volumes,
                load_canon_facts,
            )
            load_all_volumes(project_dir)
            load_all_characters(project_dir)
            load_canon_facts(project_dir)
        except FileNotFoundError:
            QMessageBox.warning(self, "错误", "所选目录不是有效项目")
            return
        except ValueError as e:
            QMessageBox.warning(self, "项目文件无效", str(e))
            return

        if not self._maybe_close_current_project():
            return

        self._current_project = project
        self._current_project_dir = project_dir
        self._bind_project_application(project_dir)
        from app.storage.timeline_repository import recover_pending_publication
        recover_pending_publication(project_dir)
        self.setWindowTitle(f"NovelForge — {project.title}")

        self._set_nav_items_enabled(True)

        from app.pipeline.token_tracker import TokenTracker
        TokenTracker.reset()
        TokenTracker.get()
        self._update_status_bar_tokens()

        self._bible_view.load_project_dir(project_dir)
        self._dashboard_view.load_project_dir(project_dir)
        self._outline_view.load_project_dir(project_dir)
        self._workspace_view.load_project_dir(project_dir)

        from PySide6.QtCore import QSettings
        settings = QSettings()
        settings.setValue("projects/last_parent", str(project_dir.parent))
        key = f"last_scene/{Path(dir_path)}"
        last_scene_id = settings.value(key)
        resume_scene_id = None
        if last_scene_id and isinstance(last_scene_id, str):
            chapter_id = self._find_chapter_for_scene(last_scene_id)
            if chapter_id:
                resume_scene_id = last_scene_id
        if resume_scene_id is None:
            from app.application.scene_workflow import choose_resume_chapter

            chapter_id = choose_resume_chapter(project_dir)
            resume_scene_id = self._scene_for_chapter(chapter_id) if chapter_id else None
        if resume_scene_id:
            self._select_destination("workspace")
            self._outline_view.activate_scene(resume_scene_id)
        else:
            self.sidebar.setCurrentRow(0)

        # Check for legacy character files and offer migration
        self._check_legacy_migration(Path(dir_path))

    def _on_open_project_folder(self) -> None:
        if self._current_project_dir is None:
            QMessageBox.warning(self, "提示", "请先打开或创建项目")
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._current_project_dir))):
            QMessageBox.warning(self, "错误", f"无法打开项目文件夹:\n{self._current_project_dir}")

    def _on_llm_settings(self) -> None:
        """Open the LLM provider settings dialog."""
        dialog = SettingsDialog(self)
        dialog.exec()

    def _on_export_markdown(self) -> None:
        """Export all approved scenes as a single Markdown file."""
        if self._current_project_dir is None or self._current_project is None:
            QMessageBox.warning(self, "提示", "请先打开或创建项目")
            return

        try:
            from app.export import export_markdown
            path = export_markdown(
                self._current_project_dir, self._current_project.title
            )
            fallback_warning = self._active_version_fallback_warning()
            if fallback_warning:
                QMessageBox.warning(
                    self,
                    "导出完成但版本已回退",
                    f"{fallback_warning}\n\nMarkdown 已导出到:\n{path}",
                )
                return
            QMessageBox.information(
                self, "导出成功",
                f"Markdown 已导出到:\n{path}"
            )
        except ValueError as e:
            QMessageBox.warning(self, "导出失败", str(e))
        except Exception as e:
            QMessageBox.critical(self, "导出错误", f"导出过程中发生错误:\n{e}")

    def _on_export_epub(self) -> None:
        """Export all approved scenes as an EPUB file."""
        if self._current_project_dir is None or self._current_project is None:
            QMessageBox.warning(self, "提示", "请先打开或创建项目")
            return

        try:
            from app.export import export_epub
            path = export_epub(
                self._current_project_dir,
                self._current_project.title,
                author="",
            )
            fallback_warning = self._active_version_fallback_warning()
            if fallback_warning:
                QMessageBox.warning(
                    self,
                    "导出完成但版本已回退",
                    f"{fallback_warning}\n\nEPUB 已导出到:\n{path}",
                )
                return
            QMessageBox.information(
                self, "导出成功",
                f"EPUB 已导出到:\n{path}"
            )
        except ValueError as e:
            QMessageBox.warning(self, "导出失败", str(e))
        except ImportError:
            QMessageBox.critical(
                self, "缺少依赖",
                "EPUB 导出需要 ebooklib 库。\n请运行: pip install ebooklib"
            )
        except Exception as e:
            QMessageBox.critical(self, "导出错误", f"导出过程中发生错误:\n{e}")

    def _on_scene_selected(self, scene_id: str) -> None:
        """Handle scene selection: assemble context, find chapter, load prose, update workspace."""
        if self._current_project_dir is None:
            return

        referenced_ids = (
            set(self._application.outlines.scene_element_ids(scene_id))
            if self._application is not None
            else set()
        )
        self._bible_view.set_current_scene_context(scene_id, referenced_ids)
        chapter_id = self._find_chapter_for_scene(scene_id)
        self._workspace_view.set_scene(scene_id, chapter_id or "")
        if chapter_id and self._application is not None:
            self._application.scene_workflow.remember_active_chapter(chapter_id)
            mode, target = self._chapter_length(chapter_id)
            self._workspace_view.set_quick_length(mode, target)

        from PySide6.QtCore import QSettings
        settings = QSettings()
        if self._current_project_dir is not None:
            key = f"last_scene/{self._current_project_dir}"
            settings.setValue(key, scene_id)

        try:
            from app.pipeline.context_builder import RetrievalEngine
            engine = RetrievalEngine()
            context = engine.assemble(self._current_project_dir, scene_id=scene_id)
            self._workspace_view.show_context(context)
        except Exception:
            self._workspace_view.clear_context()

        # Load existing prose if available
        if chapter_id:
            self._quick_outline_view.select_chapter(chapter_id)
            self._load_scene_prose_into_editor(
                self._workspace_view, chapter_id, scene_id
            )

    def _active_version_fallback_warning(self) -> str:
        """Return export warning text if any active prose version is missing."""
        if self._current_project_dir is None:
            return ""

        from app.storage.project_files import load_all_volumes, load_scene_prose_status

        missing: list[str] = []
        for volume in load_all_volumes(self._current_project_dir):
            for chapter in volume.chapters:
                for scene in chapter.scenes:
                    _, _, active_missing = load_scene_prose_status(
                        self._current_project_dir, chapter.id, scene.id
                    )
                    if active_missing:
                        missing.append(scene.title or scene.id)

        if not missing:
            return ""
        listed = "、".join(missing[:5])
        if len(missing) > 5:
            listed += f" 等 {len(missing)} 个场景"
        return f"以下场景的当前正文版本文件不存在，已使用最新可用版本：\n{listed}"

    def _load_scene_prose_into_editor(
        self, workspace: SceneWorkspaceView, chapter_id: str, scene_id: str
    ) -> None:
        """Load active scene prose and update the version selector."""
        from app.storage.project_files import (
            load_scene_prose_status,
            load_scene_prose_version,
            load_scene_writer_draft,
        )

        recovered_prose = load_scene_writer_draft(self._current_project_dir, scene_id)
        if recovered_prose and self._application is not None:
            recovered_record = self._application.scene_workflow.recover_writer_draft(
                scene_id, chapter_id, recovered_prose
            )
            if recovered_record is not None:
                self._refresh_prose_versions(
                    chapter_id, scene_id, f"v{recovered_record.revision_number}"
                )
                workspace.set_prose_text(recovered_prose)
                QMessageBox.information(
                    self,
                    "已恢复未完成草稿",
                    f"写作完成后的正文已恢复为 v{recovered_record.revision_number} 草稿；审查尚未完成。",
                )
                return

        prose, version, active_missing = load_scene_prose_status(
            self._current_project_dir, chapter_id, scene_id
        )
        versions = self._refresh_prose_versions(chapter_id, scene_id, version)
        if version is None and not active_missing and versions:
            version = versions[0]
            prose = load_scene_prose_version(
                self._current_project_dir, chapter_id, scene_id, version
            )
        workspace.set_prose_text(prose)
        if active_missing:
            QMessageBox.warning(
                self,
                "当前版本不可用",
                "当前正文版本文件不存在，已显示最新可用版本。请重新设为当前。",
            )

    def _refresh_prose_versions(
        self, chapter_id: str, scene_id: str, current: str | None = None
    ) -> list[str]:
        """Refresh editor version choices for the current scene."""
        if self._current_project_dir is None:
            return []
        from app.storage.project_files import (
            get_active_scene_prose_version,
            list_scene_prose_versions,
        )

        versions = list_scene_prose_versions(
            self._current_project_dir, chapter_id, scene_id
        )
        if not self._workspace_view.is_showing_scene(scene_id, chapter_id):
            return versions
        if current is None and versions:
            current = versions[0]
        self._current_prose_version = current
        published = get_active_scene_prose_version(
            self._current_project_dir, chapter_id, scene_id
        )
        self._workspace_view.set_prose_versions(versions, current, published)
        if current:
            from app.storage.project_files import load_scene_generation_record

            record = load_scene_generation_record(
                self._current_project_dir, scene_id, version=current
            )
            if record is not None:
                self._show_quick_revision(record)
        return versions

    def _show_quick_revision(self, record) -> None:
        review = record.review or {}
        if self._application is not None:
            chapter_id = self._find_chapter_for_scene(record.scene_id) or ""
            self._application.scene_workflow.restore_draft(record, chapter_id)
            if self._application.scene_workflow.state.artifacts:
                self._workspace_view.update_trace(
                    self._application.scene_workflow.state.artifacts
                )
        self._workspace_view.set_quick_revision_metadata(
            record.scene_id,
            record.revision_id,
            bool(review.get("overall_pass", False)),
            str(review.get("summary", "")),
            record.approved_facts if record.published_at else record.extracted_facts_raw,
            (
                record.approved_state_change_proposals
                if record.published_at
                else record.state_changes_raw
            ),
        )
        if record.stale_input and not record.stale_input_reviewed:
            self._workspace_view.show_stale_warning()
        elif review:
            self._workspace_view.show_review_result(
                bool(review.get("overall_pass", False)),
                str(review.get("summary", "")),
            )
        else:
            self._workspace_view.hide_continue_review()
            self._workspace_view.hide_review_result()

    def _on_prose_version_selected(self, version: str) -> None:
        """Load the selected prose version into the editor."""
        if version == self._current_prose_version or self._current_project_dir is None:
            return
        workspace = self._workspace_view
        scene_id = workspace.current_scene_id
        chapter_id = workspace.current_chapter_id
        if not scene_id or not chapter_id:
            return

        if workspace.prose_is_modified():
            answer = QMessageBox.question(
                self,
                "切换版本",
                "当前正文有未保存修改。切换版本会替换编辑器内容，继续吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                self._refresh_prose_versions(chapter_id, scene_id, self._current_prose_version)
                return

        from app.storage.project_files import (
            load_scene_generation_record,
            load_scene_prose_version,
        )

        workspace.set_prose_text(
            load_scene_prose_version(self._current_project_dir, chapter_id, scene_id, version)
        )
        self._current_prose_version = version
        if self._application is not None:
            record = load_scene_generation_record(
                self._current_project_dir, scene_id, version=version
            )
            if record is not None:
                self._application.scene_workflow.select_revision(record.revision_id)
                self._show_quick_revision(record)

    def _on_set_active_prose_version(self, version: str) -> None:
        """Offer publication for the selected revision; selection alone is view-only."""
        if self._current_project_dir is None:
            return
        workspace = self._workspace_view
        scene_id = workspace.current_scene_id
        chapter_id = workspace.current_chapter_id
        if not scene_id or not chapter_id or not version:
            return

        from app.storage.project_files import load_scene_generation_record

        record = load_scene_generation_record(
            self._current_project_dir, scene_id, version=version
        )
        if record is None:
            QMessageBox.warning(self, "无法发布", "此旧版本没有生成记录，只能查看。")
            return
        if workspace.prose_is_modified():
            self._continue_with_edited_draft(workspace, record)
            return
        if not record.review_overridden and not (record.review or {}).get("overall_pass", False):
            QMessageBox.warning(self, "无法发布", "此版本未通过审查，也没有继续发布授权。")
            return
        facts = record.approved_facts if record.published_at else record.extracted_facts_raw
        changes = (
            record.approved_state_change_proposals
            if record.published_at
            else record.state_changes_raw
        )
        workspace.show_fact_approval(scene_id, record.revision_id, facts, changes)

    def _continue_with_edited_draft(self, workspace, source_record) -> None:
        """Save edited prose as a new overridden draft, then re-analyze its memory."""
        answer = QMessageBox.question(
            self,
            "正文已修改",
            "修改后的正文尚未重新审查。是否将其保存为新版本并继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        if self._application is not None:
            asyncio.ensure_future(
                self._application.scene_workflow.save_edited_draft(
                    workspace.prose_text(), source_record, self._scene_workflow_observer()
                )
            )

    def _on_plan_approved(self, edited_plan: dict) -> None:
        """Resolve the current planner decision as approved."""
        if self._application is not None:
            if self._pending_plan_patch is not None:
                source_record, instruction = self._pending_plan_patch
                self._pending_plan_patch = None
                from app.storage.models import ScenePlanPatch

                patch = ScenePlanPatch(
                    base_revision_id=source_record.revision_id,
                    **{
                        key: edited_plan.get(key)
                        for key in (
                            "scene_goal",
                            "required_beats",
                            "conflict",
                            "emotional_arc",
                            "ending_hook",
                            "continuity_constraints",
                        )
                    },
                )
                _, target = self._chapter_length(
                    self._find_chapter_for_scene(source_record.scene_id) or ""
                )
                try:
                    self._application.scene_workflow.regenerate(
                        source_record.scene_id,
                        source_record,
                        self._scene_workflow_observer(),
                        instruction=instruction,
                        plan_patch=patch,
                        target_characters=target,
                    )
                    self._workspace_view.begin_generation()
                except Exception as error:
                    QMessageBox.warning(self, "无法重新生成", str(error))
                self._workspace_view.hide_plan_checkpoint()
                return
            self._application.scene_workflow.approve_plan(edited_plan)
            self._workspace_view.hide_plan_checkpoint()
            return

    def _on_plan_rejected(self) -> None:
        """Resolve the current planner decision as rejected."""
        if self._application is not None:
            if self._pending_plan_patch is not None:
                self._pending_plan_patch = None
                self._workspace_view.hide_plan_checkpoint()
                return
            self._application.scene_workflow.reject_plan()
            self._workspace_view.hide_plan_checkpoint()
            return

    def _open_deep_workspace(self) -> None:
        self._set_experience_mode("deep")
        self._select_destination("workspace")

    def _open_deep_workspace_for_chapter(self, _chapter_id: str) -> None:
        self._open_deep_workspace()

    def _open_deep_control(self, control: str) -> None:
        self._open_deep_workspace()
        self._workspace_view.focus_deep_control(control)

    def _on_quick_start(self, _chapter_id: str, scene_id: str) -> None:
        if self._application is None:
            return
        workflow = self._application.scene_workflow
        if workflow.waiting_for_plan:
            workflow.approve_plan(self._workspace_view.quick_plan())
            self._workspace_view.hide_plan_checkpoint()
        elif scene_id:
            self._on_generate_requested(scene_id)

    def _selected_generation_record(self):
        if self._current_project_dir is None:
            return None
        scene_id = self._workspace_view.current_scene_id
        version = self._current_prose_version
        if not scene_id or not version:
            return None
        from app.storage.project_files import load_scene_generation_record

        return load_scene_generation_record(
            self._current_project_dir, scene_id, version=version
        )

    def _on_quick_save(self) -> None:
        record = self._selected_generation_record()
        if record is None or self._application is None:
            QMessageBox.warning(self, "无法保存", "请先生成章节草稿。")
            return
        asyncio.ensure_future(
            self._application.scene_workflow.save_edited_draft(
                self._workspace_view.prose_text(),
                record,
                self._scene_workflow_observer(),
                analyze=False,
            )
        )

    def _regenerate_quick(self, instruction: str = "") -> None:
        record = self._selected_generation_record()
        if record is None or self._application is None:
            QMessageBox.warning(self, "无法重新生成", "请选择带有已批准计划的草稿。")
            return
        scene_id = record.scene_id
        _, target = self._chapter_length(
            self._find_chapter_for_scene(scene_id) or ""
        )
        try:
            self._application.scene_workflow.regenerate(
                scene_id,
                record,
                self._scene_workflow_observer(),
                instruction=instruction,
                target_characters=target,
            )
            self._workspace_view.begin_generation()
        except Exception as error:
            QMessageBox.warning(self, "无法重新生成", str(error))

    def _on_quick_regenerate(self) -> None:
        self._regenerate_quick()

    def _on_quick_revision_instruction(self, instruction: str) -> None:
        if not instruction:
            return
        from app.application.scene_workflow import (
            prose_instruction_requires_plan_patch,
        )

        record = self._selected_generation_record()
        if record is None:
            QMessageBox.warning(self, "无法重新生成", "请选择带有已批准计划的草稿。")
            return
        if prose_instruction_requires_plan_patch(instruction):
            self._pending_plan_patch = (record, instruction)
            self._workspace_view.show_plan_checkpoint(record.scene_plan)
            self._open_deep_workspace()
            return
        self._regenerate_quick(instruction)

    def _on_quick_ai_fix(self) -> None:
        self._on_quick_revision_instruction(
            f"修改正文，修复审查指出的问题：{self._workspace_view.review_summary}"
        )

    def _on_quick_length_changed(self, mode: str, target: int) -> None:
        if self._current_project_dir is None:
            return
        chapter_id = self._workspace_view.current_chapter_id
        if not chapter_id:
            return
        from app.storage.models import ChapterLength
        from app.storage.project_files import load_all_volumes, save_volume_outline

        for volume in load_all_volumes(self._current_project_dir):
            chapter = next(
                (item for item in volume.chapters if item.id == chapter_id), None
            )
            if chapter is not None:
                chapter.chapter_length_override = ChapterLength(
                    preset=mode, target_chinese_characters=target
                )
                save_volume_outline(self._current_project_dir, volume)
                self._workspace_view.set_quick_length(mode, target)
                return

    def _on_quick_approve(self) -> bool:
        batch = self._workspace_view.quick_approval_batch()
        if not batch[0] or not batch[1]:
            QMessageBox.warning(self, "无法批准", "请先完成审查和记忆确认。")
            return False
        return self._on_approval_batch_approved(*batch)

    def _show_creation_help(self) -> None:
        QMessageBox.information(
            self,
            "创作帮助",
            "快速创作适合快速推进故事，深度创作提供完整的设定、大纲和审查控制。\n\n"
            "故事模板：可预览，并在明确应用后写入故事设定；生成指南：只影响生成提示，"
            "不会成为故事设定。\n\n"
            "保存修改：保存当前章节草稿，仍可继续编辑；批准本章：确认审查结果并发布，"
            "让正文和记忆进入故事主线。",
        )

    def _on_quick_approve_next(self) -> None:
        if self._on_quick_approve():
            self._on_next_scene()

    def _on_next_scene(self) -> None:
        """Navigate to the next scene in the outline sequence."""
        scene_id = self._workspace_view.current_scene_id
        if not scene_id:
            return
        next_id = self._outline_view.select_next_scene(scene_id)
        if next_id is None:
            self._workspace_view.mark_last_scene()

    def _on_generate_requested(self, scene_id: str) -> None:
        """Trigger full pipeline generation for the given scene."""
        if self._current_project_dir is None or self._application is None:
            return
        workspace = self._workspace_view
        observer = self._scene_workflow_observer()
        _, target = self._chapter_length(
            self._find_chapter_for_scene(scene_id) or ""
        )
        try:
            self._application.scene_workflow.start(
                scene_id,
                self._find_chapter_for_scene(scene_id) or "",
                observer,
                target_characters=target,
            )
            workspace.begin_generation()
        except Exception as error:
            workspace.set_generating(False)
            QMessageBox.warning(self, "正在生成", str(error))

    def _scene_workflow_observer(self) -> SceneWorkflowObserver:
        """Build the current workspace's rendering adapter."""
        workspace = self._workspace_view
        return SceneWorkflowObserver(
            trace=workspace.update_trace,
            prose=workspace.append_prose,
            plan=workspace.show_plan_checkpoint,
            status=workspace.set_status,
            generating=workspace.set_generating,
            review=workspace.show_review_result,
            draft=self._on_workflow_draft,
            memory=workspace.show_fact_approval,
            length_warning=self._show_length_warning,
            error=self._show_workflow_error,
        )

    def _show_workflow_error(self, error: Exception) -> None:
        logger.error(
            "Scene workflow failed: %s",
            error,
            exc_info=(type(error), error, error.__traceback__),
        )
        from app.providers.config import ProviderConfigurationError

        if isinstance(error, ProviderConfigurationError):
            QMessageBox.warning(
                self,
                "需要配置模型",
                f"{error}\n\n请打开“文件 → LLM 设置”完成配置后重试。",
            )
        else:
            QMessageBox.warning(
                self,
                "生成失败",
                f"{error}\n\n已保存的结果会保留，可重试当前章节。",
            )

    def _show_length_warning(self, warning: str) -> None:
        chapter_id = self._workspace_view.current_chapter_id or ""
        mode, target = self._chapter_length(chapter_id)
        self._workspace_view.set_quick_length(mode, target, warning)
        self._workspace_view.set_status(warning)

    def _on_workflow_draft(self, record) -> None:
        chapter_id = self._find_chapter_for_scene(record.scene_id)
        if chapter_id:
            self._refresh_prose_versions(chapter_id, record.scene_id, f"v{record.revision_number}")
            mode, target = self._chapter_length(chapter_id)
            self._workspace_view.set_quick_length(
                mode, target, record.length_warning
            )
        self._workspace_view.set_prose_text(record.draft_text)
        if record.stale_input and not record.stale_input_reviewed:
            self._workspace_view.show_stale_warning()
        self._update_status_bar_tokens()

    def _on_continue_review_requested(self) -> None:
        if self._application is None:
            return
        workflow = self._application.scene_workflow
        record = workflow.state.draft_record
        if record is not None and record.stale_input and not record.stale_input_reviewed:
            self._workspace_view.hide_continue_review()
            asyncio.ensure_future(self._continue_stale_record(record.revision_id))
            return
        self._workspace_view.hide_continue_review()
        asyncio.ensure_future(workflow.continue_review())

    async def _continue_stale_record(self, revision_id: str) -> None:
        if self._application is None:
            return
        try:
            record = await self._application.scene_workflow.continue_stale(revision_id)
        except Exception:
            logger.exception("Could not continue stale scene revision %s", revision_id)
            self._workspace_view.show_stale_warning()
            self._workspace_view.set_status("复核失败，请重试")
            return
        review = record.review or {}
        self._workspace_view.show_review_result(
            bool(review.get("overall_pass")), review.get("summary", "")
        )
        self._workspace_view.set_status("已复核旧设定，可继续发布或重新生成")

    def _on_approval_batch_approved(
        self,
        scene_id: str,
        revision_id: str,
        approved_facts: list[dict],
        approved_changes: list[dict],
    ) -> bool:
        """Publish the exact draft revision and its approved memory."""
        if self._current_project_dir is None:
            return False
        workspace = self._workspace_view
        if workspace.prose_is_modified():
            from app.storage.project_files import load_scene_generation_record

            source_record = load_scene_generation_record(
                self._current_project_dir, scene_id, revision_id=revision_id
            )
            if source_record is not None:
                self._continue_with_edited_draft(workspace, source_record)
            return False
        try:
            if self._application is not None:
                self._application.scene_workflow.publish(
                    scene_id, revision_id, approved_facts, approved_changes
                )
            else:
                return False
        except Exception as exc:
            logger.exception("Could not publish scene revision %s", revision_id)
            QMessageBox.critical(self, "发布失败", str(exc))
            return False
        workspace.hide_fact_approval()
        chapter_id = self._find_chapter_for_scene(scene_id)
        record = None
        if chapter_id:
            from app.storage.project_files import load_scene_generation_record
            record = load_scene_generation_record(
                self._current_project_dir, scene_id, revision_id=revision_id
            )
            if record is not None:
                self._refresh_prose_versions(chapter_id, scene_id, f"v{record.revision_number}")
        workspace.set_status("已发布")
        return True


    def _retry_agent(self, agent_name: str) -> None:
        """Retry generation from the current scene (re-runs full pipeline)."""
        if self._application is not None:
            try:
                self._application.scene_workflow.retry()
            except Exception:
                return

    def _update_status_bar_tokens(self) -> None:
        """Update the status bar with session token totals and cost."""
        from app.pipeline.token_tracker import TokenTracker
        tracker = TokenTracker.get()
        total = tracker.session_total_tokens
        cost = tracker.session_cost
        parts = [f"Session: {total:,} tokens"]
        if cost > 0:
            parts.append(f"${cost:.4f}")
        self._token_status_label.setText("  ".join(parts))

    def _find_chapter_for_scene(self, scene_id: str) -> str | None:
        """Find the chapter ID containing a scene by scanning all volumes."""
        if self._application is not None:
            return self._application.outlines.chapter_for_scene(scene_id)
        from app.storage.project_files import load_all_volumes

        volumes = load_all_volumes(self._current_project_dir)
        for vol in volumes:
            for ch in vol.chapters:
                for sc in ch.scenes:
                    if sc.id == scene_id:
                        return ch.id
        return None

    def _check_legacy_migration(self, project_dir: Path) -> None:
        """Check for legacy character files and offer migration."""
        from pathlib import Path
        char_dir = project_dir / "characters"
        if not char_dir.exists():
            return
        legacy = list(char_dir.glob("*.yaml"))
        # Filter out files that already have .bak suffix
        legacy = [f for f in legacy if not f.name.endswith(".bak")]
        if not legacy:
            return

        reply = QMessageBox.question(
            self,
            "格式迁移",
            f"项目包含 {len(legacy)} 个旧格式角色文件。\n"
            "建议迁移到新格式以使用完整功能。\n\n"
            "迁移会创建备份，不会丢失数据。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._migrate_legacy_characters(project_dir, legacy)

    def _migrate_legacy_characters(self, project_dir: Path, legacy_files: list) -> None:
        """Migrate legacy characters/<name>.yaml to per-directory layout."""
        import shutil
        from datetime import datetime
        from app.storage.project_files import load_character, save_character

        char_root = project_dir / "characters"
        backup_dir = project_dir / ".backups" / f"migration-{datetime.now().strftime('%Y-%m-%d')}"
        backup_dir.mkdir(parents=True, exist_ok=True)

        migrated = 0
        for f in legacy_files:
            # Backup
            shutil.copy2(f, backup_dir / f.name)

            # Load and re-save (triggers new layout via save_character)
            try:
                char = load_character(project_dir, f.stem)
                save_character(project_dir, char)
                f.replace(f.with_suffix(".yaml.bak"))
                migrated += 1
            except Exception:
                continue

        QMessageBox.information(
            self, "迁移完成",
            f"已迁移 {migrated} 个角色。\n备份存储在: {backup_dir}"
        )

        if migrated > 0:
            self._bible_view.reload_characters()

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
