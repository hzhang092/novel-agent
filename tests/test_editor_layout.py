import pytest

from app.storage import editor_layout
from app.storage.editor_layout import BibleEditorLayout, EditorLayoutStore


def test_missing_file_returns_default_layout(tmp_path):
    store = EditorLayoutStore(tmp_path)

    assert store.layout == BibleEditorLayout()
    assert not (tmp_path / ".novel-agent").exists()


def test_layout_round_trip_preserves_settings(tmp_path):
    store = EditorLayoutStore(tmp_path)
    store.layout.selected_tab = "characters"
    store.layout.world.selected_item_id = "faction-1"
    store.layout.world.type_filter = "faction"
    store.layout.world.tag_filters = ["正道"]
    store.layout.world.overview_visible_sections = ["geography", "rules"]
    store.layout.world.overview_collapsed_sections = ["geography"]
    store.layout.world.collapsed_type_groups = ["terminology"]
    store.layout.style.collapsed_sections = ["advanced"]
    character = store.character_layout("446d5a19")
    character.visible_fields = ["personality", "long_term_goal"]
    character.collapsed_sections = ["capabilities"]
    character.initialized_for_tier = "major"
    character.visibility_customized = True

    store.save()

    assert (tmp_path / ".novel-agent" / "editor-layout.yaml").exists()
    assert EditorLayoutStore(tmp_path).layout == store.layout


def test_failed_atomic_replace_preserves_previous_layout(tmp_path, monkeypatch):
    store = EditorLayoutStore(tmp_path)
    store.layout.selected_tab = "world"
    store.save()
    store.layout.selected_tab = "style"

    def fail_replace(source, destination):
        raise OSError("disk failure")

    monkeypatch.setattr(editor_layout.os, "replace", fail_replace)

    with pytest.raises(OSError, match="disk failure"):
        store.save()

    assert EditorLayoutStore(tmp_path).layout.selected_tab == "world"


def test_corrupt_layout_is_backed_up_and_regenerated(tmp_path, caplog):
    state_dir = tmp_path / ".novel-agent"
    state_dir.mkdir()
    layout_path = state_dir / "editor-layout.yaml"
    layout_path.write_text(": invalid: yaml:", encoding="utf-8")

    store = EditorLayoutStore(tmp_path)

    assert store.layout == BibleEditorLayout()
    assert EditorLayoutStore(tmp_path).layout == BibleEditorLayout()
    backups = list(state_dir.glob("editor-layout.broken-*.yaml"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == ": invalid: yaml:"
    assert "Failed to load editor layout" in caplog.text


def test_invalid_layout_data_is_backed_up_and_regenerated(tmp_path):
    state_dir = tmp_path / ".novel-agent"
    state_dir.mkdir()
    (state_dir / "editor-layout.yaml").write_text(
        "schema_version: not-an-integer\n", encoding="utf-8"
    )

    store = EditorLayoutStore(tmp_path)

    assert store.layout == BibleEditorLayout()
    assert len(list(state_dir.glob("editor-layout.broken-*.yaml"))) == 1


def test_recovery_io_failures_do_not_block_opening(tmp_path, monkeypatch):
    state_dir = tmp_path / ".novel-agent"
    state_dir.mkdir()
    (state_dir / "editor-layout.yaml").write_text("world: [", encoding="utf-8")

    def fail_backup(*_args):
        raise OSError("backup failed")

    def fail_save(*_args):
        raise OSError("save failed")

    monkeypatch.setattr(editor_layout.Path, "replace", fail_backup)
    monkeypatch.setattr(EditorLayoutStore, "save", fail_save)

    store = EditorLayoutStore(tmp_path)

    assert store.layout == BibleEditorLayout()
    assert store.recovered_from_error is True


def test_schedule_save_debounces_repeated_requests(tmp_path, qtbot, monkeypatch):
    store = EditorLayoutStore(tmp_path)
    save_calls = 0
    original_save = store.save

    def counted_save():
        nonlocal save_calls
        save_calls += 1
        original_save()

    monkeypatch.setattr(store, "save", counted_save)

    store.schedule_save()
    store.schedule_save()

    qtbot.waitUntil(lambda: save_calls == 1, timeout=1000)
    qtbot.wait(200)
    assert save_calls == 1


def test_first_layout_save_appends_gitignore_entry_without_rewriting_content(tmp_path):
    gitignore = tmp_path / ".gitignore"
    gitignore.write_bytes(b"custom/\r\nkeep-this")
    store = EditorLayoutStore(tmp_path)

    store.save()
    store.save()

    assert gitignore.read_bytes() == b"custom/\r\nkeep-this\n.novel-agent/\n"


def test_unknown_layout_ids_do_not_prevent_loading(tmp_path):
    state_dir = tmp_path / ".novel-agent"
    state_dir.mkdir()
    (state_dir / "editor-layout.yaml").write_text(
        "schema_version: 2\nworld:\n  overview_visible_sections:\n    - future-section\n"
        "characters:\n  future-character:\n    visible_fields:\n      - future-field\n",
        encoding="utf-8",
    )

    store = EditorLayoutStore(tmp_path)

    assert store.layout.world.overview_visible_sections == ["future-section"]
    assert store.character_layout("future-character").visible_fields == ["future-field"]


def test_layout_save_does_not_rewrite_project_yaml(tmp_path):
    project_yaml = tmp_path / "project.yaml"
    original = b"title: untouched\r\nupdated_at: fixed\r\n"
    project_yaml.write_bytes(original)

    EditorLayoutStore(tmp_path).save()

    assert project_yaml.read_bytes() == original


def test_schema_v1_world_layout_is_explicitly_migrated_to_overview(tmp_path):
    state_dir = tmp_path / ".novel-agent"
    state_dir.mkdir()
    (state_dir / "editor-layout.yaml").write_text(
        "schema_version: 1\n"
        "selected_tab: world\n"
        "world:\n"
        "  visible_sections: [geography, society, history, factions, rules, taboos, terminology, power_system]\n"
        "  collapsed_sections: [geography, history, rules, power_system]\n"
        "style:\n"
        "  collapsed_sections: [advanced]\n"
        "characters:\n"
        "  char-1:\n"
        "    visible_fields: [personality]\n",
        encoding="utf-8",
    )

    layout = EditorLayoutStore(tmp_path).layout

    assert layout.schema_version == 2
    assert layout.selected_tab == "world"
    assert layout.world.selected_item_id == "overview"
    assert layout.world.overview_visible_sections == [
        "geography", "society", "rules", "taboos"
    ]
    assert layout.world.overview_collapsed_sections == ["geography", "rules"]
    assert layout.style.collapsed_sections == ["advanced"]
    assert layout.characters["char-1"].visible_fields == ["personality"]
