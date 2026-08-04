"""Static and lightweight runtime smoke checks for the Windows package."""

import ast
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest
from app.export import export_markdown
from app.storage.models import ChapterOutline, Project, SceneOutline, VolumeOutline
from app.storage.project_files import create_project, load_project, save_volume_outline
from app.ui.main_window import MainWindow


ROOT = Path(__file__).parents[1]


def test_pyinstaller_spec_uses_the_desktop_entry_and_windowed_exe():
    spec = (ROOT / "NovelForge-v0.1.0.spec").read_text(encoding="utf-8")
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "['app\\\\main.py']" in spec
    assert "pathex=['.']" in spec
    assert "name='NovelForge-v0.1.0'" in spec
    assert "console=False" in spec
    assert "upx=False" in spec
    assert "!NovelForge-v0.1.0.spec" in gitignore


def test_readme_documents_the_windows_build_and_smoke_commands():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "pyinstaller --clean --noconfirm NovelForge-v0.1.0.spec" in readme
    assert "python -m pytest -q tests/test_slice8_packaging.py" in readme


def test_desktop_entry_constructs_main_window_and_has_module_guard():
    source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    assert "MainWindow" in source
    assert any(
        isinstance(node, ast.If)
        and isinstance(node.test, ast.Compare)
        and any(
            isinstance(part, ast.Constant) and part.value == "__main__"
            for part in ast.walk(node.test)
        )
        for node in ast.walk(tree)
    )


def test_window_composes_generation_publication_export_and_reopen_seams(
    tmp_path, qtbot
):
    project_dir = create_project(tmp_path, Project(title="Smoke Story"))
    window = MainWindow(quick_creation_enabled=True)
    qtbot.addWidget(window)
    window._bind_project_application(project_dir)

    modes = {
        window._experience_switch.itemData(index)
        for index in range(window._experience_switch.count())
    }
    assert modes == {"deep", "quick"}
    assert window._application.scene_workflow is not None
    assert load_project(project_dir).title == "Smoke Story"
    file_menu = window.menuBar().actions()[0].menu()
    labels = [action.text() for action in file_menu.actions() if not action.isSeparator()]
    assert labels.count("导出 Markdown(&M)...") == 1
    assert labels.count("导出 EPUB(&E)...") == 1


def test_reopened_project_exports_published_prose(tmp_path):
    project_dir = create_project(tmp_path, Project(title="Published Smoke"))
    save_volume_outline(
        project_dir,
        VolumeOutline(
            id="v1",
            title="第一卷",
            chapters=[
                ChapterOutline(
                    id="c1",
                    title="第一章",
                    scenes=[SceneOutline(id="s1", title="开场")],
                )
            ],
        ),
    )
    scene_dir = project_dir / "scenes" / "c1"
    scene_dir.mkdir(parents=True)
    (scene_dir / "s1.md").write_text("已发布的烟火", encoding="utf-8")

    reopened = load_project(project_dir)
    export_path = export_markdown(project_dir, reopened.title)

    assert export_path.exists()
    assert "已发布的烟火" in export_path.read_text(encoding="utf-8")


@pytest.mark.skipif(sys.platform != "win32", reason="Windows release artifact")
def test_packaged_executable_starts():
    executable = ROOT / "dist" / "NovelForge-v0.1.0.exe"
    if not executable.exists():
        subprocess.run(
            [
                sys.executable,
                "-m",
                "PyInstaller",
                "--clean",
                "--noconfirm",
                "NovelForge-v0.1.0.spec",
            ],
            cwd=ROOT,
            check=True,
        )
    environment = os.environ.copy()
    environment["QT_QPA_PLATFORM"] = "offscreen"
    process = subprocess.Popen([executable], env=environment)
    try:
        time.sleep(8)
        assert process.poll() is None
    finally:
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            check=False,
            capture_output=True,
        )
