# Novel Bible: World & Style Editors — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Bible placeholder view with a full tabbed editor for world setting and style guide. The world editor provides structured form fields for all WorldSetting model fields, including the PowerSystem sub-form. The style editor provides trait pickers, pattern lists, reference passage management, and freeform notes. A one-click Xianxia template pre-fills cultivation realms, common faction types, and pacing rules. All edits save to the project's on-disk files.

**Architecture:** The Bible editor is a `QTabWidget` with two tabs (世界设定 / 写作风格), each a scrollable form. The editor receives the project directory path from MainWindow and handles its own persistence — loading data from `project.yaml` (via `load_project`) and saving via two new functions in `project_files.py`. The MainWindow stores `_current_project_dir` alongside `_current_project` and passes it to the Bible editor on project open/create. Auto-save triggers when the user navigates away from the Bible tab.

**Tech Stack:** Python 3.12+, PyQt6, Pydantic v2, PyYAML, pytest

---

## File Map

| File | Responsibility |
|---|---|
| `app/utils/__init__.py` | New package marker |
| `app/utils/xianxia_template.py` | Xianxia template data: `get_xianxia_template()` returns `(WorldSetting, StyleGuide)` |
| `app/storage/project_files.py` | Add `save_world_setting()` and `save_style_guide()`; enrich `_write_world_md()` |
| `app/storage/repository.py` | Add `save_world_setting()` and `save_style_guide()` thin wrappers |
| `app/ui/bible_editor.py` | Complete rewrite: `QTabWidget` with World tab and Style tab, template button, save button |
| `app/ui/main_window.py` | Store `_current_project_dir`, pass to Bible editor on project load/create, auto-save on tab switch |
| `tests/test_project_files.py` | Add tests for new save functions |
| `tests/test_xianxia_template.py` | Test template data validity |
| `tests/test_bible_editor.py` | Integration test: load → edit → save → reload round-trip |

---

### Task 1: Update storage layer for WorldSetting + StyleGuide persistence

**Files:**
- Modify: `app/storage/project_files.py`
- Modify: `app/storage/repository.py`
- Modify: `tests/test_project_files.py`
- Create: `app/utils/__init__.py`

- [ ] **Step 1: Add `save_world_setting()` and `save_style_guide()` to `project_files.py`**

These functions reload the project YAML, update the relevant sub-model, update `updated_at`, and write both the project YAML and the companion file (`world.md` or `style.yaml`).

Append to `app/storage/project_files.py`:

```python
def save_world_setting(project_dir: Path, world: WorldSetting) -> None:
    """Update the world setting in project.yaml and rewrite world.md.

    Args:
        project_dir: Path to an existing project directory.
        world: The updated WorldSetting model.

    Raises:
        FileNotFoundError: If project_dir is not a valid project.
        ValueError: If the project YAML is corrupt.
    """
    from datetime import datetime, timezone

    project = load_project(project_dir)
    project.world_setting = world
    project.updated_at = datetime.now(timezone.utc)
    _write_project_yaml(project_dir, project)
    _write_world_md(project_dir, world)


def save_style_guide(project_dir: Path, style: StyleGuide) -> None:
    """Update the style guide in project.yaml and rewrite style.yaml.

    Args:
        project_dir: Path to an existing project directory.
        style: The updated StyleGuide model.

    Raises:
        FileNotFoundError: If project_dir is not a valid project.
        ValueError: If the project YAML is corrupt.
    """
    from datetime import datetime, timezone

    project = load_project(project_dir)
    project.style_guide = style
    project.updated_at = datetime.now(timezone.utc)
    _write_project_yaml(project_dir, project)
    _write_style_yaml(project_dir, style)
```

- [ ] **Step 2: Enrich `_write_world_md()` to produce structured markdown**

Replace the existing `_write_world_md` function (lines ~55-58 of project_files.py) with a richer version that renders all WorldSetting fields:

```python
def _write_world_md(proj_path: Path, world: WorldSetting) -> None:
    lines = ["# 世界观", ""]
    lines.append(f"## 地理\n\n{world.geography}\n")

    if world.power_system:
        lines.append("## 修炼体系\n")
        ps = world.power_system
        if ps.realms:
            lines.append("### 境界")
            for r in ps.realms:
                lines.append(f"- {r}")
            lines.append("")
        if ps.abilities:
            lines.append("### 能力")
            for realm, desc in ps.abilities.items():
                lines.append(f"- **{realm}**: {desc}")
            lines.append("")
        if ps.limitations:
            lines.append(f"### 限制\n" + "\n".join(f"- {x}" for x in ps.limitations) + "\n")
        if ps.costs:
            lines.append(f"### 代价\n" + "\n".join(f"- {x}" for x in ps.costs) + "\n")
        if ps.rare_resources:
            lines.append(f"### 稀有资源\n" + "\n".join(f"- {x}" for x in ps.rare_resources) + "\n")
        if ps.forbidden_methods:
            lines.append(f"### 禁忌之术\n" + "\n".join(f"- {x}" for x in ps.forbidden_methods) + "\n")

    if world.factions:
        lines.append("## 势力\n")
        for f in world.factions:
            name = f.get("name", "")
            desc = f.get("description", "")
            goals = f.get("goals", "")
            lines.append(f"### {name}\n{desc}\n\n**目标**: {goals}\n")

    if world.history:
        lines.append(f"## 历史\n\n{world.history}\n")

    if world.rules:
        lines.append(f"## 规则\n" + "\n".join(f"- {x}" for x in world.rules) + "\n")

    if world.taboos:
        lines.append(f"## 禁忌\n" + "\n".join(f"- {x}" for x in world.taboos) + "\n")

    if world.technology_level:
        lines.append(f"## 科技水平\n\n{world.technology_level}\n")

    if world.social_structure:
        lines.append(f"## 社会结构\n\n{world.social_structure}\n")

    if world.terminology:
        lines.append("## 术语表\n")
        for term, defn in world.terminology.items():
            lines.append(f"- **{term}**: {defn}")
        lines.append("")

    with open(proj_path / WORLD_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
```

- [ ] **Step 3: Add thin wrappers to `Repository`**

Append to `app/storage/repository.py`:

```python
    def save_world_setting(self, project_dir: Path, world) -> None:
        """Update world setting on disk."""
        from app.storage.models import WorldSetting
        from app.storage.project_files import save_world_setting as _save_world
        _save_world(Path(project_dir), world)

    def save_style_guide(self, project_dir: Path, style) -> None:
        """Update style guide on disk."""
        from app.storage.models import StyleGuide
        from app.storage.project_files import save_style_guide as _save_style
        _save_style(Path(project_dir), style)
```

- [ ] **Step 4: Create `app/utils/__init__.py`**

Empty file: `app/utils/__init__.py`

- [ ] **Step 5: Write tests for `save_world_setting` and `save_style_guide`**

Add to `tests/test_project_files.py` after the existing round-trip test:

```python
def test_save_world_setting_preserves_other_fields(tmp_path):
    from app.storage.project_files import (
        create_project,
        load_project,
        save_world_setting,
    )
    from app.storage.models import PowerSystem, WorldSetting, Project

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    new_world = WorldSetting(
        geography="新地理描述",
        power_system=PowerSystem(realms=["炼气", "筑基"]),
        rules=["新规则"],
    )
    save_world_setting(proj_dir, new_world)

    loaded = load_project(proj_dir)
    assert loaded.title == "测试"
    assert loaded.world_setting.geography == "新地理描述"
    assert len(loaded.world_setting.power_system.realms) == 2
    assert loaded.world_setting.rules == ["新规则"]

    # Verify world.md was rewritten
    md_content = (proj_dir / "world.md").read_text(encoding="utf-8")
    assert "新地理描述" in md_content
    assert "炼气" in md_content


def test_save_style_guide_preserves_other_fields(tmp_path):
    from app.storage.project_files import (
        create_project,
        load_project,
        save_style_guide,
    )
    from app.storage.models import StyleGuide, Project

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    new_style = StyleGuide(
        pacing="快节奏",
        tone="热血",
        taboo_patterns=["禁止灌水"],
        reference_passages=["参考段落一"],
    )
    save_style_guide(proj_dir, new_style)

    loaded = load_project(proj_dir)
    assert loaded.title == "测试"
    assert loaded.style_guide.pacing == "快节奏"
    assert loaded.style_guide.tone == "热血"
    assert loaded.style_guide.taboo_patterns == ["禁止灌水"]
    assert loaded.style_guide.reference_passages == ["参考段落一"]
```

- [ ] **Step 6: Run all storage tests**

```powershell
conda activate fourteen; python -m pytest tests/test_project_files.py -v
```

Expected: all tests pass (including existing ones).

- [ ] **Step 7: Commit**

```bash
git add app/storage/project_files.py app/storage/repository.py tests/test_project_files.py app/utils/__init__.py
git commit -m "feat: save_world_setting and save_style_guide with enriched world.md output"
```

---

### Task 2: Xianxia template data

**Files:**
- Create: `app/utils/xianxia_template.py`
- Create: `tests/test_xianxia_template.py`

- [ ] **Step 1: Write `app/utils/xianxia_template.py`**

```python
"""Xianxia (修仙) genre template — pre-fills world setting and style guide
with cultivation realms, common faction types, tribulation mechanics, and
reviewer pacing rules for the web-novel format."""

from __future__ import annotations

from app.storage.models import PowerSystem, StyleGuide, WorldSetting


def get_xianxia_template() -> tuple[WorldSetting, StyleGuide]:
    """Return a pre-filled WorldSetting and StyleGuide for Xianxia novels.

    The world setting includes cultivation realms from 炼气 through 渡劫,
    common factions (宗门, 散修联盟, 魔道, 商会, 皇朝), and standard rules.
    The style guide is tuned for web-novel pacing with fast rhythm, hook-heavy
    chapter endings, and face-slapping (打脸) beat patterns.
    """
    world = WorldSetting(
        geography="东荒大陆，广袤无垠。东部临海，西部荒漠，南部群山，北部冰原。"
                  "中央为中原九州，修士云集之地。",
        power_system=PowerSystem(
            realms=[
                "炼气", "筑基", "金丹", "元婴",
                "化神", "炼虚", "合体", "大乘", "渡劫",
            ],
            abilities={
                "炼气": "灵气感知，基础法术",
                "筑基": "御器飞行，法术增强",
                "金丹": "金丹领域，本命法宝",
                "元婴": "元婴出窍，神识覆盖",
                "化神": "化神分魂，法则初悟",
                "炼虚": "虚空穿梭，炼化空间",
                "合体": "身与道合，神通大成",
                "大乘": "渡劫准备，天地共鸣",
                "渡劫": "飞升仙界的最后一步",
            },
            limitations=[
                "每个大境界需要突破瓶颈",
                "突破需要大量灵石或天材地宝",
                "修炼速度受灵根资质限制",
                "高境界修士出手会受到天道压制",
            ],
            costs=[
                "修炼消耗灵石",
                "突破失败可能导致修为倒退",
                "使用禁术消耗寿元",
            ],
            rare_resources=[
                "灵石（下品/中品/上品/极品）",
                "万年灵芝",
                "天火",
                "玄冰晶",
                "龙血草",
                "空间石",
            ],
            forbidden_methods=[
                "血祭之术",
                "吞噬他人修为",
                "夺舍",
                "炼制活人傀儡",
                "逆转阴阳",
            ],
        ),
        factions=[
            {
                "name": "青云宗",
                "description": "正道第一宗门，以剑修闻名，坐落于青云山脉。",
                "goals": "维护大陆秩序，对抗魔道势力",
            },
            {
                "name": "魔渊殿",
                "description": "魔道最强势力，隐藏于地底魔渊，行事诡秘。",
                "goals": "收集上古魔器，打开魔界通道",
            },
            {
                "name": "天机阁",
                "description": "中立的商业情报组织，遍布大陆各城。",
                "goals": "收集天下情报，垄断修炼资源交易",
            },
            {
                "name": "散修联盟",
                "description": "无门无派的散修聚集组织，以自由为信条。",
                "goals": "为散修争取修炼资源，互帮互助",
            },
            {
                "name": "大楚皇朝",
                "description": "凡间最强世俗政权，皇室拥有祖传修炼功法。",
                "goals": "统一大陆，皇权凌驾于宗门之上",
            },
        ],
        history=(
            "万年前神魔大战，仙界通道崩毁，大陆灵气溃散。"
            "千年前灵气复苏，修仙文明重新崛起。"
            "五百年前正魔大战，双方元气大伤，进入冷战期。"
            "如今大陆表面和平，暗流涌动。"
        ),
        rules=[
            "修士不可对凡人出手，违者天谴",
            "秘境百年开启一次，进入者限骨龄三十以下",
            "元婴以上修士不得在凡人城市全力出手",
            "宗门大比每十年一次，决定资源分配",
        ],
        taboos=[
            "修炼魔功",
            "背叛师门",
            "残害同门",
            "勾结魔道",
        ],
        technology_level="修仙文明，凡人处于封建时代",
        social_structure="宗门制，强者为尊。宗门 > 皇朝 > 世家 > 凡人。",
        terminology={
            "灵石": "修炼资源货币，分下品/中品/上品/极品",
            "灵根": "修炼天赋，分金木水火土五行及变异灵根",
            "秘境": "上古遗迹，内有天材地宝和传承",
            "天劫": "突破大境界时天道降下的考验",
            "神识": "修士的精神感知能力",
            "丹田": "存储灵气的核心",
        },
    )

    style = StyleGuide(
        pacing="快节奏",
        dialogue_density="对白适中",
        description_style="简练",
        tone="热血",
        sentence_length="短句多",
        pov="第三人称",
        taboo_patterns=[
            "过度描述内心独白",
            "拖节奏的环境描写",
            "战斗中的冗长对话",
            "配角抢主角戏份",
            "女主过于被动",
        ],
        preferred_patterns=[
            "每章结尾留悬念（断章）",
            "战斗节奏明快，招式清晰",
            "打脸要有铺垫→冲突→反转→余波四步",
            "修炼突破要有仪式感",
            "主角智商在线，不无脑莽",
        ],
        reference_passages=[],
        freeform_notes=(
            "整体风格参考《凡人修仙传》的冷静克制 + "
            "《斗破苍穹》的热血节奏。"
            "主角成长线清晰，金手指合理有限制。"
        ),
    )

    return world, style
```

- [ ] **Step 2: Write `tests/test_xianxia_template.py`**

```python
"""Tests for Xianxia template data validity."""

from app.utils.xianxia_template import get_xianxia_template


def test_template_returns_valid_models():
    world, style = get_xianxia_template()

    # WorldSetting fields
    assert world.geography != ""
    assert world.power_system is not None
    assert len(world.power_system.realms) == 9
    assert len(world.power_system.abilities) == 9
    assert len(world.factions) >= 3
    assert len(world.rules) >= 2
    assert len(world.taboos) >= 2
    assert len(world.terminology) >= 4

    # StyleGuide fields
    assert style.pacing != ""
    assert style.tone != ""
    assert style.pov != ""
    assert len(style.taboo_patterns) >= 3
    assert len(style.preferred_patterns) >= 3
    assert style.freeform_notes != ""
```

- [ ] **Step 3: Run template tests**

```powershell
conda activate fourteen; python -m pytest tests/test_xianxia_template.py -v
```

Expected: 1 test passes.

- [ ] **Step 4: Commit**

```bash
git add app/utils/xianxia_template.py tests/test_xianxia_template.py
git commit -m "feat: Xianxia template with cultivation realms and reviewer pacing rules"
```

---

### Task 3: Bible editor UI — World and Style tabs

**Files:**
- Rewrite: `app/ui/bible_editor.py`

- [ ] **Step 1: Rewrite `app/ui/bible_editor.py`**

The Bible editor is a `QWidget` containing a `QTabWidget` with two tabs. Each tab is a `QScrollArea` containing a form built from `QFormLayout` plus custom list/table widgets. A toolbar area above the tabs holds the "修仙模板" button and a save button.

```python
"""Novel Bible editor — tabbed world setting and style guide editor."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.storage.models import Project as ProjectModel
from app.storage.models import StyleGuide, WorldSetting
from app.storage.project_files import (
    load_project,
    save_style_guide,
    save_world_setting,
)
from app.utils.xianxia_template import get_xianxia_template


class BibleEditorView(QWidget):
    """Tabbed editor for world setting and style guide.

    Receives the project directory path via ``load_project_dir()`` and
    handles its own persistence. Emits ``saved`` after successful writes.
    """

    saved = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._project_dir: Path | None = None
        self._setup_ui()

    # ── Public API ─────────────────────────────────────────────────────────

    def load_project_dir(self, project_dir: Path) -> None:
        """Load project data from disk and populate the editor."""
        self._project_dir = project_dir
        project = load_project(project_dir)
        self._populate_world_tab(project.world_setting)
        self._populate_style_tab(project.style_guide)

    # ── UI Setup ───────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Toolbar
        toolbar = QHBoxLayout()
        self._template_btn = QPushButton("修仙模板")
        self._template_btn.setToolTip("一键填充修仙世界观和写作风格")
        self._template_btn.clicked.connect(self._on_apply_template)
        toolbar.addWidget(self._template_btn)
        toolbar.addStretch()
        self._save_btn = QPushButton("保存")
        self._save_btn.setToolTip("保存所有修改到磁盘")
        self._save_btn.clicked.connect(self._on_save)
        toolbar.addWidget(self._save_btn)
        layout.addLayout(toolbar)

        # Tabs
        self._tabs = QTabWidget()
        self._world_tab = self._build_world_tab()
        self._style_tab = self._build_style_tab()
        self._tabs.addTab(self._world_tab, "世界设定")
        self._tabs.addTab(self._style_tab, "写作风格")
        layout.addWidget(self._tabs)

    # ── World Tab ──────────────────────────────────────────────────────────

    def _build_world_tab(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        form = QVBoxLayout(container)

        # Geography
        form.addWidget(QLabel("<b>地理</b>"))
        self._geo_edit = QTextEdit()
        self._geo_edit.setPlaceholderText("描述世界观的地理环境...")
        self._geo_edit.setMaximumHeight(100)
        form.addWidget(self._geo_edit)

        # History
        form.addWidget(QLabel("<b>历史</b>"))
        self._history_edit = QTextEdit()
        self._history_edit.setPlaceholderText("世界观的历史背景...")
        self._history_edit.setMaximumHeight(80)
        form.addWidget(self._history_edit)

        # Technology & Social
        row = QHBoxLayout()
        row.addWidget(QLabel("科技水平:"))
        self._tech_edit = QLineEdit()
        self._tech_edit.setPlaceholderText("如：修仙文明")
        row.addWidget(self._tech_edit)
        row.addWidget(QLabel("社会结构:"))
        self._social_edit = QLineEdit()
        self._social_edit.setPlaceholderText("如：宗门制，强者为尊")
        row.addWidget(self._social_edit)
        form.addLayout(row)

        # Rules
        form.addWidget(QLabel("<b>规则</b>"))
        self._rules_list = _StringListEditor()
        form.addWidget(self._rules_list)

        # Taboos
        form.addWidget(QLabel("<b>禁忌</b>"))
        self._taboos_list = _StringListEditor()
        form.addWidget(self._taboos_list)

        # Factions
        form.addWidget(QLabel("<b>势力</b>"))
        self._factions_table = _KeyValueTable(["势力名称", "描述", "目标"])
        form.addWidget(self._factions_table)

        # Terminology
        form.addWidget(QLabel("<b>术语表</b>"))
        self._term_table = _KeyValueTable(["术语", "定义"])
        form.addWidget(self._term_table)

        # Power System
        ps_group = QGroupBox("修炼体系")
        ps_layout = QVBoxLayout(ps_group)

        ps_layout.addWidget(QLabel("<b>境界</b>"))
        self._realms_list = _StringListEditor()
        ps_layout.addWidget(self._realms_list)

        ps_layout.addWidget(QLabel("<b>能力</b>（境界 → 能力描述）"))
        self._abilities_table = _KeyValueTable(["境界", "能力描述"])
        ps_layout.addWidget(self._abilities_table)

        ps_layout.addWidget(QLabel("<b>限制</b>"))
        self._limitations_list = _StringListEditor()
        ps_layout.addWidget(self._limitations_list)

        ps_layout.addWidget(QLabel("<b>代价</b>"))
        self._costs_list = _StringListEditor()
        ps_layout.addWidget(self._costs_list)

        ps_layout.addWidget(QLabel("<b>稀有资源</b>"))
        self._resources_list = _StringListEditor()
        ps_layout.addWidget(self._resources_list)

        ps_layout.addWidget(QLabel("<b>禁忌之术</b>"))
        self._forbidden_list = _StringListEditor()
        ps_layout.addWidget(self._forbidden_list)

        form.addWidget(ps_group)
        form.addStretch()

        scroll.setWidget(container)
        return scroll

    # ── Style Tab ──────────────────────────────────────────────────────────

    def _build_style_tab(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        form = QVBoxLayout(container)

        # Trait pickers
        pacing_label = QLabel("<b>节奏</b>")
        self._pacing_slider = QSlider(Qt.Orientation.Horizontal)
        self._pacing_slider.setRange(1, 5)
        self._pacing_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._pacing_slider.setTickInterval(1)
        pacing_display = QLabel("适中")
        self._pacing_slider.valueChanged.connect(
            lambda v: pacing_display.setText(
                {1: "很慢", 2: "偏慢", 3: "适中", 4: "偏快", 5: "很快"}.get(v, "")
            )
        )
        pacing_row = QHBoxLayout()
        pacing_row.addWidget(pacing_label)
        pacing_row.addWidget(self._pacing_slider)
        pacing_row.addWidget(pacing_display)
        form.addLayout(pacing_row)

        self._tone_combo = self._labeled_combo("基调:", ["", "严肃", "轻松", "热血", "黑暗"])
        form.addLayout(self._tone_combo)

        self._dialogue_combo = self._labeled_combo("对白密度:", ["", "对白多", "适中", "对白少"])
        form.addLayout(self._dialogue_combo)

        self._desc_combo = self._labeled_combo("描写风格:", ["", "简练", "细致"])
        form.addLayout(self._desc_combo)

        self._sent_combo = self._labeled_combo("句长偏好:", ["", "长句多", "短句多", "混合"])
        form.addLayout(self._sent_combo)

        self._pov_combo = self._labeled_combo("视角:", ["", "第三人称", "第一人称", "多视角"])
        form.addLayout(self._pov_combo)

        # Pattern lists
        form.addWidget(QLabel("<b>禁忌模式</b>"))
        self._taboo_patterns_list = _StringListEditor()
        form.addWidget(self._taboo_patterns_list)

        form.addWidget(QLabel("<b>偏好模式</b>"))
        self._preferred_patterns_list = _StringListEditor()
        form.addWidget(self._preferred_patterns_list)

        # Reference passages
        form.addWidget(QLabel("<b>参考段落</b>（每段一个，用于风格参照）"))
        self._ref_passages_edit = QTextEdit()
        self._ref_passages_edit.setPlaceholderText("粘贴参考文本段落，每段用空行分隔...")
        self._ref_passages_edit.setMaximumHeight(120)
        form.addWidget(self._ref_passages_edit)

        # Freeform notes
        form.addWidget(QLabel("<b>自由笔记</b>"))
        self._notes_edit = QTextEdit()
        self._notes_edit.setPlaceholderText("任何关于写作风格的补充说明...")
        self._notes_edit.setMaximumHeight(100)
        form.addWidget(self._notes_edit)

        form.addStretch()
        scroll.setWidget(container)
        return scroll

    @staticmethod
    def _labeled_combo(label: str, items: list[str]) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(QLabel(label))
        combo = QComboBox()
        combo.addItems(items)
        row.addWidget(combo)
        return row

    # ── Populate ───────────────────────────────────────────────────────────

    def _populate_world_tab(self, world: WorldSetting) -> None:
        self._geo_edit.setPlainText(world.geography)
        self._history_edit.setPlainText(world.history)
        self._tech_edit.setText(world.technology_level)
        self._social_edit.setText(world.social_structure)
        self._rules_list.set_items(world.rules)
        self._taboos_list.set_items(world.taboos)
        self._factions_table.set_rows(
            [["", "", ""]] if not world.factions
            else [[f.get("name", ""), f.get("description", ""), f.get("goals", "")]
                  for f in world.factions]
        )
        self._term_table.set_rows(
            [[k, v] for k, v in world.terminology.items()]
        )
        if world.power_system:
            ps = world.power_system
            self._realms_list.set_items(ps.realms)
            self._abilities_table.set_rows([[k, v] for k, v in ps.abilities.items()])
            self._limitations_list.set_items(ps.limitations)
            self._costs_list.set_items(ps.costs)
            self._resources_list.set_items(ps.rare_resources)
            self._forbidden_list.set_items(ps.forbidden_methods)

    def _populate_style_tab(self, style: StyleGuide) -> None:
        pacing_map = {"": 3, "很慢": 1, "偏慢": 2, "适中": 3, "偏快": 4, "很快": 5}
        self._pacing_slider.setValue(pacing_map.get(style.pacing, 3))
        _set_combo(self._tone_combo, style.tone)
        _set_combo(self._dialogue_combo, style.dialogue_density)
        _set_combo(self._desc_combo, style.description_style)
        _set_combo(self._sent_combo, style.sentence_length)
        _set_combo(self._pov_combo, style.pov)
        self._taboo_patterns_list.set_items(style.taboo_patterns)
        self._preferred_patterns_list.set_items(style.preferred_patterns)
        self._ref_passages_edit.setPlainText("\n\n".join(style.reference_passages))
        self._notes_edit.setPlainText(style.freeform_notes)

    # ── Gather ─────────────────────────────────────────────────────────────

    def _gather_world(self) -> WorldSetting:
        from app.storage.models import PowerSystem

        factions = []
        for row in range(self._factions_table.rowCount()):
            name = _cell(self._factions_table, row, 0)
            desc = _cell(self._factions_table, row, 1)
            goals = _cell(self._factions_table, row, 2)
            if name or desc or goals:
                factions.append({"name": name, "description": desc, "goals": goals})

        terminology = {}
        for row in range(self._term_table.rowCount()):
            term = _cell(self._term_table, row, 0)
            defn = _cell(self._term_table, row, 1)
            if term:
                terminology[term] = defn

        abilities = {}
        for row in range(self._abilities_table.rowCount()):
            realm = _cell(self._abilities_table, row, 0)
            desc = _cell(self._abilities_table, row, 1)
            if realm:
                abilities[realm] = desc

        return WorldSetting(
            geography=self._geo_edit.toPlainText().strip(),
            power_system=PowerSystem(
                realms=self._realms_list.get_items(),
                abilities=abilities,
                limitations=self._limitations_list.get_items(),
                costs=self._costs_list.get_items(),
                rare_resources=self._resources_list.get_items(),
                forbidden_methods=self._forbidden_list.get_items(),
            ),
            factions=factions,
            history=self._history_edit.toPlainText().strip(),
            rules=self._rules_list.get_items(),
            taboos=self._taboos_list.get_items(),
            technology_level=self._tech_edit.text().strip(),
            social_structure=self._social_edit.text().strip(),
            terminology=terminology,
        )

    def _gather_style(self) -> StyleGuide:
        pacing_map = {1: "很慢", 2: "偏慢", 3: "适中", 4: "偏快", 5: "很快"}
        ref_text = self._ref_passages_edit.toPlainText().strip()
        ref_passages = [p.strip() for p in ref_text.split("\n\n") if p.strip()] if ref_text else []

        return StyleGuide(
            pacing=pacing_map.get(self._pacing_slider.value(), ""),
            dialogue_density=_combo_val(self._dialogue_combo),
            description_style=_combo_val(self._desc_combo),
            tone=_combo_val(self._tone_combo),
            sentence_length=_combo_val(self._sent_combo),
            pov=_combo_val(self._pov_combo),
            taboo_patterns=self._taboo_patterns_list.get_items(),
            preferred_patterns=self._preferred_patterns_list.get_items(),
            reference_passages=ref_passages,
            freeform_notes=self._notes_edit.toPlainText().strip(),
        )

    # ── Actions ────────────────────────────────────────────────────────────

    def _on_save(self) -> None:
        if self._project_dir is None:
            return
        try:
            save_world_setting(self._project_dir, self._gather_world())
            save_style_guide(self._project_dir, self._gather_style())
            self.saved.emit()
        except Exception as e:
            QMessageBox.warning(self, "保存失败", str(e))

    def _on_apply_template(self) -> None:
        world, style = get_xianxia_template()
        self._populate_world_tab(world)
        self._populate_style_tab(style)


# ── Reusable Editor Widgets ────────────────────────────────────────────────

class _StringListEditor(QWidget):
    """Editable list of strings with add/remove buttons."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._list = QListWidget()
        self._list.setMaximumHeight(100)
        layout.addWidget(self._list)
        btn_row = QHBoxLayout()
        add_btn = QPushButton("+")
        add_btn.setFixedWidth(30)
        add_btn.clicked.connect(self._on_add)
        btn_row.addWidget(add_btn)
        del_btn = QPushButton("-")
        del_btn.setFixedWidth(30)
        del_btn.clicked.connect(self._on_remove)
        btn_row.addWidget(del_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    def _on_add(self) -> None:
        item = QListWidgetItem("")
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        self._list.addItem(item)
        self._list.editItem(item)

    def _on_remove(self) -> None:
        for item in self._list.selectedItems():
            self._list.takeItem(self._list.row(item))

    def set_items(self, items: list[str]) -> None:
        self._list.clear()
        for text in items:
            item = QListWidgetItem(text)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            self._list.addItem(item)

    def get_items(self) -> list[str]:
        result = []
        for i in range(self._list.count()):
            text = self._list.item(i).text().strip()
            if text:
                result.append(text)
        return result


class _KeyValueTable(QWidget):
    """Editable key-value table with add/remove row buttons."""

    def __init__(self, headers: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._headers = headers
        self._table = QTableWidget(0, len(headers))
        self._table.setHorizontalHeaderLabels(headers)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.setMaximumHeight(120)
        layout.addWidget(self._table)
        btn_row = QHBoxLayout()
        add_btn = QPushButton("+ 行")
        add_btn.clicked.connect(self._on_add_row)
        btn_row.addWidget(add_btn)
        del_btn = QPushButton("- 行")
        del_btn.clicked.connect(self._on_remove_row)
        btn_row.addWidget(del_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    def _on_add_row(self) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        for col in range(len(self._headers)):
            self._table.setItem(row, col, QTableWidgetItem(""))

    def _on_remove_row(self) -> None:
        rows = set(idx.row() for idx in self._table.selectedIndexes())
        for row in sorted(rows, reverse=True):
            self._table.removeRow(row)

    def set_rows(self, rows: list[list[str]]) -> None:
        self._table.setRowCount(0)
        for row_data in rows:
            row = self._table.rowCount()
            self._table.insertRow(row)
            for col, text in enumerate(row_data[: len(self._headers)]):
                self._table.setItem(row, col, QTableWidgetItem(text))

    def rowCount(self) -> int:
        return self._table.rowCount()


# ── Helpers ────────────────────────────────────────────────────────────────

def _cell(table: QTableWidget, row: int, col: int) -> str:
    item = table.item(row, col)
    return item.text().strip() if item else ""


def _set_combo(layout: QHBoxLayout, value: str) -> None:
    """Set a combo box inside a labeled row layout by its text value."""
    for i in range(layout.count()):
        w = layout.itemAt(i).widget()
        if isinstance(w, QComboBox):
            idx = w.findText(value)
            if idx >= 0:
                w.setCurrentIndex(idx)
            return


def _combo_val(layout: QHBoxLayout) -> str:
    """Get the current text from a combo box inside a labeled row layout."""
    for i in range(layout.count()):
        w = layout.itemAt(i).widget()
        if isinstance(w, QComboBox):
            return w.currentText()
    return ""
```

- [ ] **Step 2: Verify the editor constructs without error**

```powershell
conda activate fourteen; python -c "
from PyQt6.QtWidgets import QApplication
import sys
app = QApplication(sys.argv)
from app.ui.bible_editor import BibleEditorView
v = BibleEditorView()
assert v._tabs.count() == 2
print('BibleEditorView constructed successfully')
"
```

Expected: `BibleEditorView constructed successfully`

- [ ] **Step 3: Commit**

```bash
git add app/ui/bible_editor.py
git commit -m "feat: Bible editor with World and Style tabs, Xianxia template button"
```

---

### Task 4: Wire Bible editor to MainWindow

**Files:**
- Modify: `app/ui/main_window.py`

- [ ] **Step 1: Update MainWindow to store project directory and pass to Bible editor**

The MainWindow needs to:
1. Store `self._current_project_dir` alongside `self._current_project`
2. Call `self.views["bible"].load_project_dir(proj_dir)` after create/open
3. Auto-save when navigating away from the Bible tab

Replace `app/ui/main_window.py` with the updated version:

```python
"""Main window with left sidebar navigation and stacked content views."""

from __future__ import annotations

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

    def _on_nav_changed(self, index: int) -> None:
        # Auto-save Bible editor when navigating away from it
        if self._previous_tab_index == 1:  # Bible tab index
            bible = self.views["bible"]
            if isinstance(bible, BibleEditorView) and bible._project_dir is not None:
                bible._on_save()

        self._previous_tab_index = index

        item = self.sidebar.item(index)
        if item is None:
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

        bible = self.views["bible"]
        if isinstance(bible, BibleEditorView):
            bible.load_project_dir(proj_dir)

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

        bible = self.views["bible"]
        if isinstance(bible, BibleEditorView):
            bible.load_project_dir(Path(dir_path))
```

- [ ] **Step 2: Verify MainWindow constructs and Bible editor wiring works**

```powershell
conda activate fourteen; python -c "
from PyQt6.QtWidgets import QApplication
import sys
app = QApplication(sys.argv)
from app.ui.main_window import MainWindow
w = MainWindow()
assert w._current_project_dir is None  # no project loaded yet
assert w.sidebar.count() == 4
print('MainWindow with Bible wiring OK')
"
```

Expected: `MainWindow with Bible wiring OK`

- [ ] **Step 3: Commit**

```bash
git add app/ui/main_window.py
git commit -m "feat: wire Bible editor to MainWindow with auto-save on tab switch"
```

---

### Task 5: Integration test — Bible editor save/load round-trip

**Files:**
- Create: `tests/test_bible_editor.py`

- [ ] **Step 1: Write integration test**

```python
"""Integration tests for Bible editor: load → edit → save → reload round-trip."""

import pytest

from app.storage.models import Project
from app.storage.project_files import (
    create_project,
    load_project,
    save_style_guide,
    save_world_setting,
)


def test_world_setting_save_load_round_trip(tmp_path):
    """Save a full WorldSetting, reload, verify all fields preserved."""
    from app.storage.project_files import _write_world_md

    project = Project(title="测试项目", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    from app.storage.models import PowerSystem, WorldSetting

    world = WorldSetting(
        geography="测试地理",
        power_system=PowerSystem(
            realms=["炼气", "筑基", "金丹"],
            abilities={"炼气": "灵气感知", "筑基": "御剑飞行", "金丹": "金丹领域"},
            limitations=["需要灵石"],
            costs=["消耗寿元"],
            rare_resources=["天火"],
            forbidden_methods=["血祭"],
        ),
        factions=[
            {"name": "青云宗", "description": "正道宗门", "goals": "维护和平"},
            {"name": "魔渊殿", "description": "魔道势力", "goals": "统治世界"},
        ],
        history="上古大战",
        rules=["规则一", "规则二"],
        taboos=["禁忌一"],
        technology_level="修仙文明",
        social_structure="宗门制",
        terminology={"灵石": "修炼货币", "秘境": "上古遗迹"},
    )

    save_world_setting(proj_dir, world)
    loaded = load_project(proj_dir)

    ws = loaded.world_setting
    assert ws.geography == "测试地理"
    assert ws.power_system is not None
    assert ws.power_system.realms == ["炼气", "筑基", "金丹"]
    assert ws.power_system.abilities == {"炼气": "灵气感知", "筑基": "御剑飞行", "金丹": "金丹领域"}
    assert ws.power_system.limitations == ["需要灵石"]
    assert ws.power_system.costs == ["消耗寿元"]
    assert ws.power_system.rare_resources == ["天火"]
    assert ws.power_system.forbidden_methods == ["血祭"]
    assert len(ws.factions) == 2
    assert ws.factions[0]["name"] == "青云宗"
    assert ws.factions[1]["description"] == "魔道势力"
    assert ws.history == "上古大战"
    assert ws.rules == ["规则一", "规则二"]
    assert ws.taboos == ["禁忌一"]
    assert ws.technology_level == "修仙文明"
    assert ws.social_structure == "宗门制"
    assert ws.terminology == {"灵石": "修炼货币", "秘境": "上古遗迹"}

    # Verify world.md contains key data
    md = (proj_dir / "world.md").read_text(encoding="utf-8")
    assert "测试地理" in md
    assert "青云宗" in md
    assert "炼气" in md
    assert "灵石" in md


def test_style_guide_save_load_round_trip(tmp_path):
    """Save a full StyleGuide, reload, verify all fields preserved."""
    project = Project(title="测试项目", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    from app.storage.models import StyleGuide

    style = StyleGuide(
        pacing="快节奏",
        dialogue_density="对白适中",
        description_style="简练",
        tone="热血",
        sentence_length="短句多",
        pov="第三人称",
        taboo_patterns=["禁忌一", "禁忌二"],
        preferred_patterns=["偏好一", "偏好二"],
        reference_passages=["段落一", "段落二"],
        freeform_notes="测试笔记内容",
    )

    save_style_guide(proj_dir, style)
    loaded = load_project(proj_dir)

    sg = loaded.style_guide
    assert sg.pacing == "快节奏"
    assert sg.dialogue_density == "对白适中"
    assert sg.description_style == "简练"
    assert sg.tone == "热血"
    assert sg.sentence_length == "短句多"
    assert sg.pov == "第三人称"
    assert sg.taboo_patterns == ["禁忌一", "禁忌二"]
    assert sg.preferred_patterns == ["偏好一", "偏好二"]
    assert sg.reference_passages == ["段落一", "段落二"]
    assert sg.freeform_notes == "测试笔记内容"

    # Verify style.yaml contains key data
    import yaml
    with open(proj_dir / "style.yaml", "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    assert raw["pacing"] == "快节奏"
    assert raw["tone"] == "热血"
    assert len(raw["reference_passages"]) == 2


def test_world_setting_empty_save_load(tmp_path):
    """Save an empty WorldSetting, verify it reloads with defaults."""
    project = Project(title="空项目", genre="科幻")
    proj_dir = create_project(tmp_path, project)

    from app.storage.models import WorldSetting

    world = WorldSetting()
    save_world_setting(proj_dir, world)
    loaded = load_project(proj_dir)

    assert loaded.world_setting.geography == ""
    assert loaded.world_setting.power_system is None
    assert loaded.world_setting.factions == []
    assert loaded.world_setting.rules == []


def test_style_guide_empty_save_load(tmp_path):
    """Save an empty StyleGuide, verify it reloads with defaults."""
    project = Project(title="空项目", genre="科幻")
    proj_dir = create_project(tmp_path, project)

    from app.storage.models import StyleGuide

    style = StyleGuide()
    save_style_guide(proj_dir, style)
    loaded = load_project(proj_dir)

    assert loaded.style_guide.pacing == ""
    assert loaded.style_guide.pov == ""
    assert loaded.style_guide.taboo_patterns == []


def test_world_md_without_power_system(tmp_path):
    """World markdown should not include power system section when None."""
    from app.storage.models import WorldSetting

    project = Project(title="无修炼", genre="都市")
    proj_dir = create_project(tmp_path, project)

    world = WorldSetting(geography="现代都市")
    save_world_setting(proj_dir, world)

    md = (proj_dir / "world.md").read_text(encoding="utf-8")
    assert "现代都市" in md
    assert "修炼体系" not in md  # No power system section
```

- [ ] **Step 2: Run integration tests**

```powershell
conda activate fourteen; python -m pytest tests/test_bible_editor.py -v
```

Expected: all 5 tests pass.

- [ ] **Step 3: Run full test suite to verify no regressions**

```powershell
conda activate fourteen; python -m pytest tests/ -v
```

Expected: all tests pass (existing + new).

- [ ] **Step 4: Commit**

```bash
git add tests/test_bible_editor.py
git commit -m "test: Bible editor save/load round-trip integration tests"
```

---

## Self-Review

### 1. Spec coverage

Issue #2 acceptance criteria mapped to tasks:

| Criterion | Task(s) |
|---|---|
| World editor tab: all fields editable, saved to `world.md` + structured fields in `project.yaml` | Task 1 (storage), Task 3 (UI) |
| Power system sub-form: realms list, abilities dict, limitations/costs/resources/forbidden fields | Task 3 (UI) |
| Terminology glossary: add/edit/remove term-definition pairs | Task 3 (_KeyValueTable widget) |
| Style editor tab: pacing slider, tone dropdown, dialogue density dropdown, sentence length selector, POV selector | Task 3 (UI) |
| Style editor: taboo patterns list, preferred patterns list, freeform notes textarea | Task 3 (UI) |
| Reference passages: paste area, passages stored in `style.yaml` | Task 3 (UI), Task 1 (storage) |
| Xianxia template: one-click pre-fill of cultivation realms, common faction types, tribulation mechanics, reviewer pacing rules | Task 2 |
| Save on edit; load on project open; round-trip verified | Task 4 (auto-save), Task 5 (integration tests) |

### 2. Placeholder scan

No TBDs, TODOs, "implement later", or abstract notes. Every step has concrete code or test assertions.

### 3. Type consistency

- `WorldSetting` and `StyleGuide` models already exist in `app/storage/models.py` — no model changes needed
- New `save_world_setting()` and `save_style_guide()` in `project_files.py` use the same model types
- `BibleEditorView._gather_world()` returns `WorldSetting`, `_gather_style()` returns `StyleGuide` — consistent with storage layer
- `MainWindow._current_project_dir` typed as `Path | None`

### 4. Dependency check

No new dependencies required. All widgets (`QTabWidget`, `QScrollArea`, `QTableWidget`, `QListWidget`, `QSlider`, `QComboBox`, `QTextEdit`) are built into PyQt6.

### 5. Simplicity check

The Bible editor is a single file (~300 lines). Reusable sub-widgets (`_StringListEditor`, `_KeyValueTable`) are internal private classes — no premature abstraction into a separate widgets module. Save logic is direct: gather → validate → write. No debouncing, no dirty-tracking, no undo stack.
