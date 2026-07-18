"""Main window with left sidebar navigation and stacked content views."""

from __future__ import annotations

import asyncio
import gc
import os
from pathlib import Path
import tempfile

from PySide6.QtCore import QSignalBlocker, Qt, QUrl
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog,
    QLabel,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QSplitter,
    QStackedWidget,
    QWidget,
)

from app.storage.models import Project as ProjectModel
from app.storage.repository import Repository
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
        self._last_generated_scene_id: str | None = None
        self._generation_in_progress: bool = False
        self._current_prose_version: str | None = None
        self._pending_draft: tuple | None = None
        self._project_signal_connections = []

        self._repo = Repository(Path.home() / "NovelForge")
        self._current_project: ProjectModel | None = None
        self._current_project_dir: Path | None = None
        self._previous_tab_index: int = 0

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

        bible = self.views["bible"]
        outline = self.views["outline"]
        if isinstance(bible, BibleEditorView) and isinstance(outline, OutlineEditorView):
            bible.elements_changed.connect(
                lambda: outline._refresh_world_elements()
            )
            bible.scene_requested.connect(self._open_scene_from_bible)

        workspace = self.views["workspace"]
        if isinstance(workspace, SceneWorkspaceView):
            workspace.editor.version_selected.connect(self._on_prose_version_selected)
            workspace.editor.set_active_requested.connect(self._on_set_active_prose_version)

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

    def _open_scene_from_bible(self, scene_id: str) -> None:
        self.sidebar.setCurrentRow(3)
        if self.sidebar.currentRow() != 3:
            return
        outline = self.views.get("outline")
        if isinstance(outline, OutlineEditorView):
            blocker = QSignalBlocker(outline)
            outline._select_by_id(scene_id)
            del blocker
            self._on_scene_selected(scene_id)

    def _wire_project_signals(self) -> None:
        """Connect project view signals once, regardless of how the project loaded."""
        for signal, slot in self._project_signal_connections:
            signal.disconnect(slot)
        outline = self.views.get("outline")
        workspace = self.views.get("workspace")
        connections = []
        if isinstance(outline, OutlineEditorView):
            connections.append((outline.scene_selected, self._on_scene_selected))
        if isinstance(workspace, SceneWorkspaceView):
            connections.extend((
                (workspace.generate_requested, self._on_generate_requested),
                (workspace.retry_requested, self._retry_agent),
                (workspace.next_scene_requested, self._on_next_scene),
            ))
        for signal, slot in connections:
            signal.connect(slot)
        self._project_signal_connections = connections

    def _on_nav_changed(self, index: int) -> None:
        if (
            self._previous_tab_index == 1
            and index != 1
            and not self._maybe_close_current_project()
        ):
            blocker = QSignalBlocker(self.sidebar)
            self.sidebar.setCurrentRow(self._previous_tab_index)
            del blocker
            return

        # Auto-save Outline editor when navigating away from it
        if self._previous_tab_index == 2:
            outline = self.views["outline"]
            if isinstance(outline, OutlineEditorView) and outline._project_dir is not None:
                outline._on_save()

        # Wire event bus to Bible Editor's character editor when navigating to Bible
        if index == 1:
            bible = self.views["bible"]
            if isinstance(bible, BibleEditorView):
                bible._character_tab.set_event_bus(self._domain_bus)
                bible.refresh_usage()

        # Load workspace when navigating to it
        if index == 3:
            workspace = self.views["workspace"]
            if isinstance(workspace, SceneWorkspaceView) and self._current_project_dir is not None:
                workspace.load_project_dir(self._current_project_dir)
                try:
                    workspace.generate_requested.disconnect()
                except TypeError:
                    pass
                workspace.generate_requested.connect(self._on_generate_requested)
                try:
                    workspace.retry_requested.disconnect()
                except TypeError:
                    pass
                workspace.retry_requested.connect(self._retry_agent)
                try:
                    workspace.next_scene_requested.disconnect()
                except TypeError:
                    pass
                workspace.next_scene_requested.connect(self._on_next_scene)
                try:
                    workspace.fact_approval.approval_batch_approved.disconnect()
                except TypeError:
                    pass
                workspace.fact_approval.approval_batch_approved.connect(
                    self._on_approval_batch_approved
                )
                try:
                    workspace.continue_review_requested.disconnect()
                except TypeError:
                    pass
                workspace.continue_review_requested.connect(
                    self._on_continue_review_requested
                )
                try:
                    workspace.retry_requested.disconnect()
                except TypeError:
                    pass
                workspace.retry_requested.connect(self._retry_agent)

        self._previous_tab_index = index

        item = self.sidebar.item(index)
        if item is None:
            return
        if not (item.flags() & Qt.ItemFlag.ItemIsEnabled):
            self.sidebar.setCurrentRow(0)
            return
        key = item.data(Qt.ItemDataRole.UserRole)
        if key in self.views:
            self.stack.setCurrentWidget(self.views[key])

    # ── Actions ───────────────────────────────────────────────────────────

    def _maybe_close_current_project(self) -> bool:
        bible = self.views["bible"]
        if (
            not isinstance(bible, BibleEditorView)
            or bible._project_dir is None
            or not bible.is_dirty
        ):
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
            return bible.save_all()
        if reply == QMessageBox.StandardButton.Discard:
            bible.load_project_dir(bible._project_dir)
            return True
        return False

    def _on_new_project(self) -> None:
        dialog = CreateProjectDialog(self, Path.home() / "NovelForge")
        if not dialog.exec():
            return

        result = dialog.get_result()
        if result is None:
            return
        if not self._maybe_close_current_project():
            return

        project = ProjectModel(
            title=result["title"],
            genre=result["genre"],
            llm_provider=result["llm_provider"],
        )

        try:
            proj_dir = Repository(Path(result["storage_dir"])).create(project)
        except FileExistsError:
            QMessageBox.warning(self, "错误", f"项目「{result['title']}」已存在")
            return

        self._current_project = project
        self._current_project_dir = proj_dir
        self.setWindowTitle(f"NovelForge — {project.title}")

        self._set_nav_items_enabled(True)

        from app.pipeline.token_tracker import TokenTracker
        TokenTracker.reset()
        TokenTracker.get()
        self._update_status_bar_tokens()

        bible = self.views["bible"]
        if isinstance(bible, BibleEditorView):
            bible.load_project_dir(proj_dir)
        dashboard = self.views["dashboard"]
        if isinstance(dashboard, DashboardView):
            dashboard.load_project_dir(proj_dir)

        outline = self.views["outline"]
        if isinstance(outline, OutlineEditorView):
            outline.load_project_dir(proj_dir)
        workspace = self.views["workspace"]
        if isinstance(workspace, SceneWorkspaceView):
            workspace.load_project_dir(proj_dir)
        self._wire_project_signals()

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
        from app.storage.timeline_repository import recover_pending_publication
        recover_pending_publication(project_dir)
        self.setWindowTitle(f"NovelForge — {project.title}")

        self._set_nav_items_enabled(True)

        from app.pipeline.token_tracker import TokenTracker
        TokenTracker.reset()
        TokenTracker.get()
        self._update_status_bar_tokens()

        bible = self.views["bible"]
        if isinstance(bible, BibleEditorView):
            bible.load_project_dir(Path(dir_path))
        dashboard = self.views["dashboard"]
        if isinstance(dashboard, DashboardView):
            dashboard.load_project_dir(Path(dir_path))

        outline = self.views["outline"]
        if isinstance(outline, OutlineEditorView):
            outline.load_project_dir(Path(dir_path))
        workspace = self.views["workspace"]
        if isinstance(workspace, SceneWorkspaceView):
            workspace.load_project_dir(Path(dir_path))
        self._wire_project_signals()

        from PySide6.QtCore import QSettings
        settings = QSettings()
        key = f"last_scene/{Path(dir_path)}"
        last_scene_id = settings.value(key)
        if last_scene_id and isinstance(last_scene_id, str):
            chapter_id = self._find_chapter_for_scene(last_scene_id)
            if chapter_id:
                self.sidebar.setCurrentRow(3)
                if isinstance(outline, OutlineEditorView):
                    outline._select_by_id(last_scene_id)
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

        bible = self.views.get("bible")
        if isinstance(bible, BibleEditorView):
            bible.set_current_scene_id(scene_id)
            from app.storage.project_files import load_all_volumes

            referenced_ids = next(
                (
                    set(scene.world_element_ids)
                    for volume in load_all_volumes(self._current_project_dir)
                    for chapter in volume.chapters
                    for scene in chapter.scenes
                    if scene.id == scene_id
                ),
                set(),
            )
            bible._world_tab.set_current_scene_element_ids(referenced_ids)

        workspace = self.views.get("workspace")
        if not isinstance(workspace, SceneWorkspaceView):
            return

        chapter_id = self._find_chapter_for_scene(scene_id)
        workspace.set_scene(scene_id, chapter_id or "")

        from PySide6.QtCore import QSettings
        settings = QSettings()
        if self._current_project_dir is not None:
            key = f"last_scene/{self._current_project_dir}"
            settings.setValue(key, scene_id)

        try:
            from app.pipeline.context_builder import RetrievalEngine
            engine = RetrievalEngine()
            context = engine.assemble(self._current_project_dir, scene_id=scene_id)
            workspace.show_context(context)
        except Exception:
            workspace.clear_context()

        # Load existing prose if available
        if chapter_id:
            self._load_scene_prose_into_editor(workspace, chapter_id, scene_id)

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
            discard_scene_writer_draft,
            load_scene_generation_record,
            load_scene_prose_status,
            load_scene_prose_version,
            load_scene_writer_draft,
            list_scene_prose_versions,
        )

        recovered_prose = load_scene_writer_draft(self._current_project_dir, scene_id)
        if recovered_prose:
            recovered_record = None
            partial_version = None
            for candidate_version in list_scene_prose_versions(
                self._current_project_dir, chapter_id, scene_id
            ):
                if candidate_version == "legacy":
                    continue
                try:
                    candidate_record = load_scene_generation_record(
                        self._current_project_dir,
                        scene_id,
                        version=candidate_version,
                    )
                except ValueError:
                    candidate_record = None
                if (
                    candidate_record is not None
                    and candidate_record.status == "draft"
                    and candidate_record.draft_text == recovered_prose
                ):
                    recovered_record = candidate_record
                    break
                if candidate_record is None and load_scene_prose_version(
                    self._current_project_dir,
                    chapter_id,
                    scene_id,
                    candidate_version,
                ) == recovered_prose:
                    partial_version = int(candidate_version[1:])
                    break
            if recovered_record is None:
                from app.pipeline.pipeline import GenerationResult

                recovered_record = self._save_generated_scene(
                    GenerationResult(scene_id=scene_id, prose=recovered_prose),
                    version=partial_version,
                )
            else:
                discard_scene_writer_draft(self._current_project_dir, scene_id)
                self._refresh_prose_versions(
                    chapter_id, scene_id, f"v{recovered_record.revision_number}"
                )
                workspace.editor.setPlainText(recovered_prose)
            if recovered_record is not None:
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
        workspace.editor.setPlainText(prose)
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
        workspace = self.views.get("workspace")
        if not isinstance(workspace, SceneWorkspaceView):
            return []

        from app.storage.project_files import list_scene_prose_versions

        versions = list_scene_prose_versions(
            self._current_project_dir, chapter_id, scene_id
        )
        if (
            workspace._current_scene_id != scene_id
            or workspace._current_chapter_id != chapter_id
        ):
            return versions
        if current is None and versions:
            current = versions[0]
        self._current_prose_version = current
        workspace.editor.set_versions(versions, current)
        return versions

    def _on_prose_version_selected(self, version: str) -> None:
        """Load the selected prose version into the editor."""
        if version == self._current_prose_version or self._current_project_dir is None:
            return
        workspace = self.views.get("workspace")
        if not isinstance(workspace, SceneWorkspaceView):
            return
        scene_id = workspace._current_scene_id
        chapter_id = workspace._current_chapter_id
        if not scene_id or not chapter_id:
            return

        if workspace.editor.is_modified():
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

        from app.storage.project_files import load_scene_prose_version

        workspace.editor.setPlainText(
            load_scene_prose_version(self._current_project_dir, chapter_id, scene_id, version)
        )
        self._current_prose_version = version

    def _on_set_active_prose_version(self, version: str) -> None:
        """Offer publication for the selected revision; selection alone is view-only."""
        if self._current_project_dir is None:
            return
        workspace = self.views.get("workspace")
        if not isinstance(workspace, SceneWorkspaceView):
            return
        scene_id = workspace._current_scene_id
        chapter_id = workspace._current_chapter_id
        if not scene_id or not chapter_id or not version:
            return

        from app.storage.project_files import load_scene_generation_record

        record = load_scene_generation_record(
            self._current_project_dir, scene_id, version=version
        )
        if record is None:
            QMessageBox.warning(self, "无法发布", "此旧版本没有生成记录，只能查看。")
            return
        if workspace.editor.is_modified():
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
        from app.pipeline.pipeline import GenerationResult, ScenePipeline
        from app.storage.models import CharacterIntent, ScenePlan
        from app.storage.project_files import save_scene_generation_record

        result = GenerationResult(
            scene_id=source_record.scene_id,
            prose=workspace.editor.toPlainText(),
            plan=ScenePlan.model_validate(source_record.scene_plan)
            if source_record.scene_plan
            else None,
            character_intents={
                name: CharacterIntent.model_validate(intent)
                for name, intent in source_record.character_intents.items()
            },
            generated_with=source_record.generated_with,
        )
        pipeline = ScenePipeline()
        record = self._save_generated_scene(result)
        if record is None:
            return
        record.review_overridden = True
        save_scene_generation_record(self._current_project_dir, record)
        self._pending_draft = (pipeline, result, record)
        self._schedule_analysis_with_retry(
            pipeline, result, record, workspace, workspace.trace_panel.update_trace
        )

    def _on_next_scene(self) -> None:
        """Navigate to the next scene in the outline sequence."""
        workspace = self.views.get("workspace")
        if not isinstance(workspace, SceneWorkspaceView):
            return
        if not workspace._current_scene_id:
            return

        outline = self.views.get("outline")
        if not isinstance(outline, OutlineEditorView):
            return

        next_id = outline.select_next_scene(workspace._current_scene_id)
        if next_id is None:
            workspace._next_scene_btn.setEnabled(False)
            workspace._status_label.setText("已是最后一场景")

    def _on_generate_requested(self, scene_id: str) -> None:
        """Trigger full pipeline generation for the given scene."""
        self._last_generated_scene_id = scene_id
        if self._current_project_dir is None:
            return

        workspace = self.views.get("workspace")
        if not isinstance(workspace, SceneWorkspaceView):
            return

        from app.providers.config import get_provider_for_step, load_provider_config

        config = load_provider_config()
        planner_provider = get_provider_for_step("planner", config)
        char_provider = get_provider_for_step("characters", config)
        writer_provider = get_provider_for_step("writer", config)
        reviewer_provider = get_provider_for_step("reviewer", config)

        workspace.set_generating(True)
        self._generation_in_progress = True
        workspace.editor.setPlainText("")
        workspace.trace_panel.clear()
        workspace.trace_panel.set_waiting("正在组装上下文...")
        workspace.hide_review_result()
        workspace.hide_fact_approval()

        from app.pipeline.pipeline import ScenePipeline

        pipeline = ScenePipeline()

        import asyncio

        plan_loop = asyncio.get_event_loop()
        plan_decision: asyncio.Future[tuple[bool, dict | None]] | None = None

        def _on_plan_approved(edited_plan: dict):
            if plan_decision is not None and not plan_decision.done():
                plan_decision.set_result((True, edited_plan))
                workspace.planner_checkpoint.hide_plan()

        def _on_plan_rejected():
            if plan_decision is not None and not plan_decision.done():
                plan_decision.set_result((False, None))
                workspace.planner_checkpoint.hide_plan()
                workspace.set_generating(False)
                self._generation_in_progress = False
                workspace.trace_panel.clear()

        try:
            workspace.planner_checkpoint.approved.disconnect()
        except TypeError:
            pass
        workspace.planner_checkpoint.approved.connect(_on_plan_approved)

        try:
            workspace.planner_checkpoint.rejected.disconnect()
        except TypeError:
            pass
        workspace.planner_checkpoint.rejected.connect(_on_plan_rejected)

        async def on_plan_ready(plan) -> bool:
            nonlocal plan_decision
            plan_decision = plan_loop.create_future()
            workspace.planner_checkpoint.show_plan(plan.model_dump(mode="json"))
            try:
                approved, edited_plan = await plan_decision
                if approved and edited_plan is not None:
                    validated = type(plan).model_validate(edited_plan)
                    for field, value in validated.model_dump().items():
                        setattr(plan, field, value)
                return approved
            finally:
                plan_decision = None

        def on_trace(trace):
            workspace.trace_panel.update_trace(trace)

        async def _run():
            providers = [planner_provider, char_provider, writer_provider, reviewer_provider]
            try:
                async for token, result in pipeline.generate_stream(
                    self._current_project_dir,
                    scene_id,
                    planner_provider,
                    char_provider,
                    writer_provider,
                    reviewer_provider,
                    on_trace=on_trace,
                    on_plan_ready=on_plan_ready,
                ):
                    if token is not None:
                        workspace.editor.append(token)
                    if result is not None:
                        workspace.set_generating(False)
                        self._generation_in_progress = False
                        if result.prose:
                            workspace._status_label.setText("已生成")
                            self._update_status_bar_tokens()
                            if result.review is not None:
                                workspace.show_review_result(
                                    result.review.overall_pass,
                                    result.review.summary,
                                )
                            else:
                                workspace.show_review_result(
                                    False, "审查未完成；草稿未进入记忆，可选择仍然继续"
                                )
                            record = self._save_generated_scene(result)
                            if record is None:
                                return
                            self._pending_draft = (pipeline, result, record)
                            if result.review is not None and result.review.overall_pass:
                                await self._analyze_and_offer_publication(
                                    pipeline, result, record, workspace, on_trace
                                )
                            else:
                                workspace._status_label.setText("草稿已保存")
                        elif result.plan is not None:
                            pass
                        else:
                            workspace._status_label.setText("生成失败")
                        return
            except Exception:
                workspace.trace_panel.clear()
                workspace.set_generating(False)
                self._generation_in_progress = False
                workspace._status_label.setText("生成失败")
            finally:
                for p in providers:
                    try:
                        await p.close()
                    except Exception:
                        pass
                # Force GC while event loop is still running to prevent
                # httpcore async-generator cleanup warnings on shutdown.
                gc.collect()
                await asyncio.sleep(0)

        asyncio.ensure_future(_run())

    def _save_generated_scene(self, result, version: int | None = None):
        """Save generated prose and artifacts as a non-canonical draft."""
        if self._current_project_dir is None:
            return None

        chapter_id = self._find_chapter_for_scene(result.scene_id)
        if not chapter_id:
            return None

        from app.storage.project_files import (
            discard_scene_writer_draft,
            save_scene_generation_record,
        )
        from app.storage.models import SceneGenerationRecord
        from app.storage.timeline_repository import (
            find_scene_position,
        )

        if version is None:
            version = _get_next_version(
                self._current_project_dir, chapter_id, result.scene_id
            )
        _save_versioned_prose(
            self._current_project_dir, chapter_id, result.scene_id, result.prose, version
        )
        self._refresh_prose_versions(chapter_id, result.scene_id, f"v{version}")

        plan_dict = result.plan.model_dump(mode="json") if result.plan else {}
        intents_dict = {
            k: v.model_dump(mode="json")
            for k, v in result.character_intents.items()
        }
        review_dict = result.review.model_dump(mode="json") if result.review else None
        generated_with = getattr(result, "generated_with", {})
        from app.storage.models import parse_generation_read_points

        character_read_points = parse_generation_read_points(
            generated_with
        ).characters
        generated_from_checkpoint_id = next(
            (
                read_point.get("checkpoint_id", "")
                for read_point in character_read_points.values()
                if read_point.get("checkpoint_id")
            ),
            "",
        )
        position = find_scene_position(self._current_project_dir, result.scene_id)

        record = SceneGenerationRecord(
            scene_id=result.scene_id,
            revision_number=version,
            scene_order=position.scene_order if position else 0,
            generated_from_checkpoint_id=generated_from_checkpoint_id,
            generated_with=generated_with,
            status="draft",
            generation_mode="standard",
            scene_plan=plan_dict,
            character_intents=intents_dict,
            draft_text=result.prose,
            review=review_dict,
            final_text="",
            extracted_facts_raw=getattr(result, 'extracted_facts', []),
            state_changes_raw=getattr(result, 'state_changes', []),
        )
        save_scene_generation_record(self._current_project_dir, record)
        discard_scene_writer_draft(self._current_project_dir, result.scene_id)
        workspace = self.views.get("workspace")
        if isinstance(workspace, SceneWorkspaceView):
            workspace.editor.setPlainText(result.prose)
        return record

    async def _analyze_and_offer_publication(
        self, pipeline, result, record, workspace, on_trace
    ) -> None:
        from app.providers.config import get_provider_for_step, load_provider_config

        providers = []
        try:
            config = load_provider_config()
            fact_provider = get_provider_for_step("fact_extractor", config)
            providers.append(fact_provider)
            state_provider = get_provider_for_step("state_updater", config)
            providers.append(state_provider)
            await pipeline.analyze_draft(
                self._current_project_dir,
                result,
                fact_provider=fact_provider,
                state_provider=state_provider,
                review_overridden=record.review_overridden,
                on_trace=on_trace,
            )
        finally:
            for provider in providers:
                try:
                    await provider.close()
                except Exception:
                    pass
        from app.storage.project_files import save_scene_generation_record

        record.extracted_facts_raw = result.extracted_facts
        record.state_changes_raw = result.state_changes
        record.scene_summary_raw = result.scene_summary
        save_scene_generation_record(self._current_project_dir, record)
        workspace.show_fact_approval(
            result.scene_id,
            record.revision_id,
            result.extracted_facts,
            result.state_changes,
        )
        workspace._status_label.setText("等待发布")

    def _schedule_analysis_with_retry(
        self, pipeline, result, record, workspace, on_trace
    ) -> None:
        """Run detached memory analysis and restore its retry control on failure."""

        async def _run() -> None:
            try:
                await self._analyze_and_offer_publication(
                    pipeline, result, record, workspace, on_trace
                )
            except Exception:
                workspace._status_label.setText("记忆分析失败")
                workspace.show_review_result(
                    False, "记忆分析失败；草稿已保存，可重试"
                )

        asyncio.ensure_future(_run())

    def _on_continue_review_requested(self) -> None:
        if self._pending_draft is None or self._current_project_dir is None:
            return
        pipeline, result, record = self._pending_draft
        workspace = self.views.get("workspace")
        if not isinstance(workspace, SceneWorkspaceView):
            return
        from app.storage.project_files import save_scene_generation_record

        record.review_overridden = True
        save_scene_generation_record(self._current_project_dir, record)
        workspace._continue_review_btn.hide()
        self._schedule_analysis_with_retry(
            pipeline, result, record, workspace, workspace.trace_panel.update_trace
        )

    def _on_approval_batch_approved(
        self,
        scene_id: str,
        revision_id: str,
        approved_facts: list[dict],
        approved_changes: list[dict],
    ) -> None:
        """Publish the exact draft revision and its approved memory."""
        if self._current_project_dir is None:
            return
        workspace = self.views.get("workspace")
        if isinstance(workspace, SceneWorkspaceView) and workspace.editor.is_modified():
            from app.storage.project_files import load_scene_generation_record

            source_record = load_scene_generation_record(
                self._current_project_dir, scene_id, revision_id=revision_id
            )
            if source_record is not None:
                self._continue_with_edited_draft(workspace, source_record)
            return
        from app.storage.timeline_repository import publish_scene_revision

        try:
            publish_scene_revision(
                self._current_project_dir,
                scene_id,
                revision_id,
                approved_facts,
                approved_changes,
                self._domain_bus,
            )
        except Exception as exc:
            logger.exception("Could not publish scene revision %s", revision_id)
            QMessageBox.critical(self, "发布失败", str(exc))
            return
        if isinstance(workspace, SceneWorkspaceView):
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
        if isinstance(workspace, SceneWorkspaceView):
            workspace._status_label.setText("已发布")
        self._pending_draft = None


    def _retry_agent(self, agent_name: str) -> None:
        """Retry generation from the current scene (re-runs full pipeline)."""
        if self._last_generated_scene_id and not self._generation_in_progress:
            self._on_generate_requested(self._last_generated_scene_id)

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

        # Reload the Bible Editor's character tab to pick up migrated characters
        if migrated > 0:
            bible = self.views.get("bible")
            if isinstance(bible, BibleEditorView):
                bible._character_tab.load_project_dir(project_dir)

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


def _get_next_version(project_dir: Path, chapter_id: str, scene_id: str) -> int:
    """Determine the next version number for a scene by scanning existing files."""
    chapter_dir = project_dir / "scenes" / chapter_id
    if not chapter_dir.exists():
        return 1
    existing = list(chapter_dir.glob(f"{scene_id}.v*.md"))
    if not existing:
        return 1
    versions = []
    for f in existing:
        stem = f.stem
        parts = stem.rsplit(".v", 1)
        if len(parts) == 2:
            try:
                versions.append(int(parts[1]))
            except ValueError:
                continue
    return max(versions, default=0) + 1


def _save_versioned_prose(
    project_dir: Path, chapter_id: str, scene_id: str, prose: str, version: int
) -> None:
    """Atomically write scene prose to its versioned Markdown file."""
    chapter_dir = project_dir / "scenes" / chapter_id
    chapter_dir.mkdir(parents=True, exist_ok=True)
    filepath = chapter_dir / f"{scene_id}.v{version}.md"
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=chapter_dir,
            prefix=f".{scene_id}.v{version}.",
            suffix=".tmp",
            delete=False,
        ) as fh:
            temp_path = Path(fh.name)
            fh.write(prose)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temp_path, filepath)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
