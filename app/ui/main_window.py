"""Main window with left sidebar navigation and stacked content views."""

from __future__ import annotations

import asyncio
import gc
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QFileDialog,
    QLabel,
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
from app.events.bus import EventBus
from app.events.qt_bridge import QtEventBridge
from app.storage.state_repository import StateRepository
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
        self._last_generated_scene_id: str | None = None
        self._generation_in_progress: bool = False

        self._repo = Repository(Path.home() / "NovelForge")
        self._current_project: ProjectModel | None = None
        self._current_project_dir: Path | None = None
        self._previous_tab_index: int = 0

        # Event bus for live UI refresh
        self._domain_bus = EventBus()
        self._event_bridge = QtEventBridge(self._domain_bus)
        self._state_repo = StateRepository(bus=self._domain_bus)

        self._setup_menu()
        self._setup_ui()
        self._token_status_label = QLabel("Tokens: —")
        self._token_status_label.setStyleSheet("color: #888; font-size: 11px; padding: 0 8px;")
        self.statusBar().addPermanentWidget(self._token_status_label)

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
        if self._previous_tab_index == 1:
            bible = self.views["bible"]
            if isinstance(bible, BibleEditorView) and bible._project_dir is not None:
                bible._on_save()

        # Auto-save Outline editor when navigating away from it
        if self._previous_tab_index == 2:
            outline = self.views["outline"]
            if isinstance(outline, OutlineEditorView) and outline._project_dir is not None:
                outline._on_save()

        # Wire event bus to Bible Editor's character editor when navigating to Bible
        if index == 1:
            bible = self.views["bible"]
            if isinstance(bible, BibleEditorView):
                bible._character_editor.set_event_bus(self._domain_bus)

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
                    workspace.fact_approval.facts_approved.disconnect()
                except TypeError:
                    pass
                workspace.fact_approval.facts_approved.connect(
                    lambda facts: self._on_facts_approved(facts)
                )
                try:
                    workspace.fact_approval.state_changes_approved.disconnect()
                except TypeError:
                    pass
                workspace.fact_approval.state_changes_approved.connect(
                    lambda changes: self._on_state_changes_approved(changes)
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
                try:
                    workspace.retry_requested.disconnect()
                except TypeError:
                    pass
                workspace.retry_requested.connect(self._retry_agent)

        # Check for legacy character files and offer migration
        self._check_legacy_migration(Path(dir_path))

    def _on_llm_settings(self) -> None:
        """Open the LLM provider settings dialog."""
        dialog = SettingsDialog(self)
        dialog.exec()

    def _on_scene_selected(self, scene_id: str) -> None:
        """Handle scene selection: assemble context, find chapter, load prose, update workspace."""
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

        # Load existing prose if available
        if chapter_id:
            from app.storage.project_files import load_scene_prose
            prose = load_scene_prose(self._current_project_dir, chapter_id, scene_id)
            if prose:
                workspace.editor.setPlainText(prose)

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
        workspace.editor.setPlainText("")
        workspace.trace_panel.clear()
        workspace.trace_panel.set_waiting("正在组装上下文...")
        workspace.hide_review_result()

        from app.pipeline.pipeline import ScenePipeline

        pipeline = ScenePipeline()

        import asyncio

        plan_loop = asyncio.get_event_loop()
        plan_decision: asyncio.Future[bool] | None = None

        def _on_plan_approved():
            if plan_decision is not None and not plan_decision.done():
                plan_decision.set_result(True)
                workspace.planner_checkpoint.hide_plan()

        def _on_plan_rejected():
            if plan_decision is not None and not plan_decision.done():
                plan_decision.set_result(False)
                workspace.planner_checkpoint.hide_plan()
                workspace.set_generating(False)
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
                result = await plan_decision
                return result
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
                        if result.prose:
                            workspace._status_label.setText("已生成")
                            self._update_status_bar_tokens()
                            if result.review is not None:
                                workspace.show_review_result(
                                    result.review.overall_pass,
                                    result.review.summary,
                                )
                            self._save_generated_scene(result)
                            extracted = getattr(result, 'extracted_facts', [])
                            state_changes = getattr(result, 'state_changes', [])
                            if extracted or state_changes:
                                workspace.show_fact_approval(extracted, state_changes)
                        elif result.plan is not None:
                            pass
                        else:
                            workspace._status_label.setText("生成失败")
                        return
            except Exception:
                workspace.trace_panel.clear()
                workspace.set_generating(False)
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

    def _save_generated_scene(self, result) -> None:
        """Save generated prose, plan, intents, review, and generation record to disk."""
        if self._current_project_dir is None:
            return

        chapter_id = self._find_chapter_for_scene(result.scene_id)
        if not chapter_id:
            return

        from app.storage.project_files import save_scene_generation_record
        from app.storage.models import SceneGenerationRecord

        version = _get_next_version(self._current_project_dir, chapter_id, result.scene_id)
        _save_versioned_prose(
            self._current_project_dir, chapter_id, result.scene_id, result.prose, version
        )

        plan_dict = result.plan.model_dump(mode="json") if result.plan else {}
        intents_dict = {
            k: v.model_dump(mode="json")
            for k, v in result.character_intents.items()
        }
        review_dict = result.review.model_dump(mode="json") if result.review else None

        record = SceneGenerationRecord(
            scene_id=result.scene_id,
            generation_mode="standard",
            scene_plan=plan_dict,
            character_intents=intents_dict,
            draft_text=result.prose,
            review=review_dict,
            final_text=result.prose,
            extracted_facts_raw=getattr(result, 'extracted_facts', []),
            state_changes_raw=getattr(result, 'state_changes', []),
        )
        save_scene_generation_record(self._current_project_dir, record)

    def _on_facts_approved(self, approved_facts: list[dict]) -> None:
        """Save approved facts to canon/facts.yaml."""
        if self._current_project_dir is None:
            return
        from app.storage.models import CanonFact
        from app.storage.project_files import load_canon_facts, save_canon_facts

        workspace = self.views.get("workspace")
        scene_id = workspace._current_scene_id if isinstance(workspace, SceneWorkspaceView) else ""

        try:
            existing = load_canon_facts(self._current_project_dir)
        except Exception:
            existing = []

        new_facts: list[CanonFact] = []
        for fd in approved_facts:
            fact = CanonFact(
                description=fd.get("description", ""),
                category=fd.get("category", "world"),
                source_scene_id=scene_id or "",
                importance=3,
                tags=[],
            )
            is_dup = any(
                e.description == fact.description and e.category == fact.category
                for e in existing
            )
            if not is_dup:
                new_facts.append(fact)

        all_facts = list(existing) + new_facts
        save_canon_facts(self._current_project_dir, all_facts)

    def _on_state_changes_approved(self, approved_changes: list[dict]) -> None:
        """Apply approved state changes via StateRepository (event-sourced)."""
        if self._current_project_dir is None:
            return

        import uuid as uuid_mod

        workspace = self.views.get("workspace")
        scene_id = workspace._current_scene_id if isinstance(workspace, SceneWorkspaceView) else ""
        tx_id = str(uuid_mod.uuid4())

        for proposal_dict in approved_changes:
            char_id = proposal_dict.get("character_id", "")
            if not char_id:
                continue
            char_dir = self._current_project_dir / "characters" / char_id

            # Convert the approved dict back to a StateChangeProposal
            changes_data = proposal_dict.get("changes", [])
            from app.storage.models import StateChangeProposal

            # Parse changes_data which may be raw dicts or already the right format
            parsed_changes = []
            for c in changes_data:
                t = c.get("type", "")
                if t == "set_field":
                    parsed_changes.append({"type": "set_field", "field": c.get("field", ""), "value": c.get("value", "")})
                elif t == "relationship_change":
                    parsed_changes.append({"type": "relationship_change", "target_character_id": c.get("target_character_id", ""), "relationship": c.get("relationship", "")})
                elif t in ("knowledge_add", "knowledge_remove", "secret_add", "secret_remove"):
                    parsed_changes.append({"type": t, "fact": c.get("fact", "")})

            if not parsed_changes:
                continue

            proposal = StateChangeProposal(
                character_id=char_id,
                character_name=proposal_dict.get("character_name", ""),
                changes=parsed_changes,
            )

            try:
                self._state_repo.commit_proposal(
                    char_dir=char_dir,
                    proposal=proposal,
                    scene_id=scene_id,
                    transaction_id=tx_id,
                    request_id=str(uuid_mod.uuid4()),
                )
            except Exception:
                pass


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
                migrated += 1
            except Exception:
                continue

        QMessageBox.information(
            self, "迁移完成",
            f"已迁移 {migrated} 个角色。\n备份存储在: {backup_dir}"
        )

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
    """Write scene prose to scenes/<chapter>/<scene_id>.v{version}.md."""
    chapter_dir = project_dir / "scenes" / chapter_id
    chapter_dir.mkdir(parents=True, exist_ok=True)
    filepath = chapter_dir / f"{scene_id}.v{version}.md"
    with open(filepath, "w", encoding="utf-8") as fh:
        fh.write(prose)
