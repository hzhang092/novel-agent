"""Integration tests for the export module."""

import tempfile
from pathlib import Path

import pytest

from app.export import export_markdown, export_epub
from app.storage.models import (
    Project,
    VolumeOutline,
    ChapterOutline,
    SceneOutline,
)
from app.storage.project_files import (
    create_project,
    save_volume_outline,
)


@pytest.fixture
def project_dir():
    """Create a minimal project with two chapters, one with generated prose."""
    with tempfile.TemporaryDirectory() as tmp:
        proj = Project(title="TestExport", genre="玄幻", llm_provider="mock")
        proj_dir = create_project(Path(tmp), proj)

        scene1 = SceneOutline(
            id="scene-1",
            title="开场",
            location="青云山",
        )
        scene2 = SceneOutline(
            id="scene-2",
            title="初遇",
            location="山脚小镇",
        )
        ch1 = ChapterOutline(id="ch-1", title="第一章", scenes=[scene1])
        ch2 = ChapterOutline(id="ch-2", title="第二章", scenes=[scene2])
        vol = VolumeOutline(id="vol-1", title="第一卷", chapters=[ch1, ch2])
        save_volume_outline(proj_dir, vol)

        # Write some prose for scene 1
        ch_dir = proj_dir / "scenes" / "ch-1"
        ch_dir.mkdir(parents=True, exist_ok=True)
        (ch_dir / "scene-1.v2.md").write_text("云海翻涌，一道剑光划破长空。\n\n林轩睁开双眼。", encoding="utf-8")
        (ch_dir / "scene-1.v1.md").write_text("旧版本", encoding="utf-8")

        # Write prose for scene 2
        ch2_dir = proj_dir / "scenes" / "ch-2"
        ch2_dir.mkdir(parents=True, exist_ok=True)
        (ch2_dir / "scene-2.md").write_text("小镇炊烟袅袅。", encoding="utf-8")

        yield proj_dir


class TestMarkdownExport:
    def test_exports_valid_markdown(self, project_dir: Path) -> None:
        path = export_markdown(project_dir, "TestExport")
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "# TestExport" in content
        assert "## 第一章" in content
        assert "### 开场" in content
        assert "云海翻涌" in content
        assert "## 第二章" in content
        assert "炊烟袅袅" in content

    def test_empty_scene_placeholder(self, project_dir: Path) -> None:
        """Scene without prose should get a placeholder."""
        path = export_markdown(project_dir, "TestExport")
        content = path.read_text(encoding="utf-8")
        # scene-2 has prose so no placeholder expected
        assert "尚未生成" not in content

    def test_raises_on_empty_outline(self, tmp_path: Path) -> None:
        proj = Project(title="Empty", genre="玄幻", llm_provider="mock")
        proj_dir = create_project(tmp_path, proj)
        with pytest.raises(ValueError, match="No outline"):
            export_markdown(proj_dir, "Empty")


class TestEpubExport:
    def test_exports_valid_epub(self, project_dir: Path) -> None:
        path = export_epub(project_dir, "TestExport", author="测试作者")
        assert path.exists()
        assert path.suffix == ".epub"
        assert path.stat().st_size > 0

    def test_raises_on_no_prose(self, tmp_path: Path) -> None:
        """EPUB export should raise if there's no generated prose at all."""
        proj = Project(title="NoProse", genre="玄幻", llm_provider="mock")
        proj_dir = create_project(tmp_path, proj)
        scene = SceneOutline(id="s-1", title="空场景")
        ch = ChapterOutline(id="ch-1", title="空章", scenes=[scene])
        vol = VolumeOutline(id="vol-1", title="空卷", chapters=[ch])
        save_volume_outline(proj_dir, vol)
        with pytest.raises(ValueError, match="No generated"):
            export_epub(proj_dir, "NoProse")
