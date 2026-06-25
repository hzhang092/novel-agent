"""Tests for character state snapshot and replay I/O."""
import tempfile
from pathlib import Path

import pytest

from app.storage.character_state import (
    load_snapshot,
    save_snapshot,
    build_snapshot,
    load_or_build_snapshot,
    map_character_state_to_snapshot,
    map_snapshot_to_character_state,
    save_checkpoint,
    load_checkpoint,
)
from app.storage.character_events import append_events
from app.storage.models import (
    CharacterState,
    CharacterStateEvent,
    CharacterStoredChange,
    CharacterStateSnapshot,
    SceneStateCheckpoint,
)


class TestSnapshotSaveAndLoad:
    def test_save_and_load_round_trip(self):
        with tempfile.TemporaryDirectory() as td:
            char_dir = Path(td)
            snap = CharacterStateSnapshot(
                character_id="char-1",
                last_event_id=5,
                emotion="angry",
                goal="revenge",
                location="temple",
                power_level="qi_refining_3",
                knowledge=["secret door"],
                secrets=["hidden identity"],
                relationships={"ally": "friend"},
            )
            save_snapshot(char_dir, snap)
            loaded = load_snapshot(char_dir)
            assert loaded.character_id == "char-1"
            assert loaded.emotion == "angry"
            assert loaded.last_event_id == 5
            assert loaded.knowledge == ["secret door"]

    def test_load_snapshot_missing_returns_default(self):
        with tempfile.TemporaryDirectory() as td:
            snap = load_snapshot(Path(td))
            assert snap.character_id == ""
            assert snap.last_event_id == 0
            assert snap.goal == ""

    def test_load_snapshot_empty_returns_default(self):
        with tempfile.TemporaryDirectory() as td:
            char_dir = Path(td)
            (char_dir / "state.yaml").write_text("", encoding="utf-8")

            snap = load_snapshot(char_dir)

            assert snap.character_id == ""
            assert snap.last_event_id == 0

    def test_load_snapshot_corrupt_yaml_raises_value_error(self):
        with tempfile.TemporaryDirectory() as td:
            char_dir = Path(td)
            path = char_dir / "state.yaml"
            path.write_text("[", encoding="utf-8")

            with pytest.raises(ValueError) as exc:
                load_snapshot(char_dir)

            assert str(path) in str(exc.value)

    def test_load_snapshot_invalid_model_data_raises_value_error(self):
        with tempfile.TemporaryDirectory() as td:
            char_dir = Path(td)
            path = char_dir / "state.yaml"
            path.write_text("- not\n- a mapping\n", encoding="utf-8")

            with pytest.raises(ValueError) as exc:
                load_snapshot(char_dir)

            assert str(path) in str(exc.value)


class TestBuildFromEvents:
    def test_build_snapshot_replays_set_field_events(self):
        with tempfile.TemporaryDirectory() as td:
            char_dir = Path(td)
            append_events(char_dir, [
                CharacterStateEvent(
                    event_id=1, scene_id="s1", character_id="char-1",
                    changes=[CharacterStoredChange(type="set_field", field="goal", value="avenge", old="")],
                ),
                CharacterStateEvent(
                    event_id=2, scene_id="s2", character_id="char-1",
                    changes=[CharacterStoredChange(type="set_field", field="emotion", value="calm", old="")],
                ),
            ])
            snap = build_snapshot(char_dir, character_id="char-1")
            assert snap.goal == "avenge"
            assert snap.emotion == "calm"
            assert snap.last_event_id == 2

    def test_build_snapshot_skips_invalidated_events(self):
        with tempfile.TemporaryDirectory() as td:
            char_dir = Path(td)
            append_events(char_dir, [
                CharacterStateEvent(
                    event_id=1, scene_id="s1", character_id="char-1",
                    changes=[CharacterStoredChange(type="set_field", field="goal", value="old_goal")],
                ),
                CharacterStateEvent(
                    event_id=2, scene_id="s2", character_id="char-1", invalidated=True,
                    changes=[CharacterStoredChange(type="set_field", field="goal", value="should_not_apply")],
                ),
            ])
            snap = build_snapshot(char_dir, character_id="char-1")
            assert snap.goal == "old_goal"

    def test_build_snapshot_knowledge_add_remove(self):
        with tempfile.TemporaryDirectory() as td:
            char_dir = Path(td)
            append_events(char_dir, [
                CharacterStateEvent(
                    event_id=1, scene_id="s1", character_id="char-1",
                    changes=[
                        CharacterStoredChange(type="knowledge_add", fact="secret door"),
                        CharacterStoredChange(type="knowledge_add", fact="hidden key"),
                    ],
                ),
                CharacterStateEvent(
                    event_id=2, scene_id="s2", character_id="char-1",
                    changes=[CharacterStoredChange(type="knowledge_remove", fact="secret door")],
                ),
            ])
            snap = build_snapshot(char_dir, character_id="char-1")
            assert snap.knowledge == ["hidden key"]

    def test_build_snapshot_relationships(self):
        with tempfile.TemporaryDirectory() as td:
            char_dir = Path(td)
            append_events(char_dir, [
                CharacterStateEvent(
                    event_id=1, scene_id="s1", character_id="char-1",
                    changes=[
                        CharacterStoredChange(type="relationship_change", target_character_id="bob", relationship="friend"),
                        CharacterStoredChange(type="relationship_change", target_character_id="alice", relationship="rival"),
                    ],
                ),
                CharacterStateEvent(
                    event_id=2, scene_id="s2", character_id="char-1",
                    changes=[CharacterStoredChange(type="relationship_change", target_character_id="bob", relationship="enemy", old="friend")],
                ),
            ])
            snap = build_snapshot(char_dir, character_id="char-1")
            assert snap.relationships == {"bob": "enemy", "alice": "rival"}


class TestLoadOrBuild:
    def test_load_or_build_rebuilds_when_cache_is_behind_events(self):
        with tempfile.TemporaryDirectory() as td:
            char_dir = Path(td)
            # Pre-populate a snapshot
            snap = CharacterStateSnapshot(character_id="char-1", emotion="sad", last_event_id=3)
            save_snapshot(char_dir, snap)
            # Simulate a crash after event append but before snapshot save.
            append_events(char_dir, [
                CharacterStateEvent(
                    event_id=4, scene_id="s4", character_id="char-1",
                    changes=[CharacterStoredChange(type="set_field", field="emotion", value="happy")],
                ),
            ])
            result = load_or_build_snapshot(char_dir, character_id="char-1")
            assert result.emotion == "happy"
            assert result.last_event_id == 4
            assert load_snapshot(char_dir).last_event_id == 4

    def test_load_or_build_builds_when_no_cache(self):
        with tempfile.TemporaryDirectory() as td:
            char_dir = Path(td)
            append_events(char_dir, [
                CharacterStateEvent(
                    event_id=1, scene_id="s1", character_id="char-1",
                    changes=[CharacterStoredChange(type="set_field", field="goal", value="revenge")],
                ),
            ])
            result = load_or_build_snapshot(char_dir, character_id="char-1")
            assert result.goal == "revenge"

    def test_load_or_build_recovers_corrupt_snapshot_from_events(self):
        with tempfile.TemporaryDirectory() as td:
            char_dir = Path(td)
            (char_dir / "state.yaml").write_text("[", encoding="utf-8")
            append_events(char_dir, [
                CharacterStateEvent(
                    event_id=1, scene_id="s1", character_id="char-1",
                    changes=[CharacterStoredChange(type="set_field", field="goal", value="revenge")],
                ),
            ])

            result = load_or_build_snapshot(char_dir, character_id="char-1")

            assert result.goal == "revenge"
            assert load_snapshot(char_dir).goal == "revenge"

    def test_load_or_build_corrupt_snapshot_without_events_raises(self):
        with tempfile.TemporaryDirectory() as td:
            char_dir = Path(td)
            path = char_dir / "state.yaml"
            path.write_text("[", encoding="utf-8")

            with pytest.raises(ValueError) as exc:
                load_or_build_snapshot(char_dir, character_id="char-1")

            assert str(path) in str(exc.value)


class TestStateMapping:
    def test_map_character_state_to_snapshot(self):
        state = CharacterState(
            character_id="char-1",
            current_goal="become elder",
            current_emotion="nervous",
            current_location="dojo",
            current_power_level="qi_refining_5",
            current_status="injured",
            current_relationships={"master": "respect"},
            current_knowledge=["hidden technique"],
            current_secrets=["true identity"],
            last_updated_scene="scene_001",
        )
        snap = map_character_state_to_snapshot(state)
        assert snap.goal == "become elder"
        assert snap.emotion == "nervous"
        assert snap.power_level == "qi_refining_5"
        assert snap.relationships == {"master": "respect"}
        assert snap.knowledge == ["hidden technique"]

    def test_map_snapshot_to_character_state(self):
        snap = CharacterStateSnapshot(
            character_id="char-1",
            goal="revenge",
            emotion="angry",
            location="temple",
            power_level="qi_refining_7",
            relationships={"ally": "trust"},
            knowledge=["secret"],
            secrets=["hidden"],
            status="wounded",
            last_scene_id="scene_042",
        )
        state = map_snapshot_to_character_state(snap)
        assert state.character_id == "char-1"
        assert state.current_goal == "revenge"
        assert state.current_emotion == "angry"
        assert state.current_power_level == "qi_refining_7"
        assert state.current_relationships == {"ally": "trust"}
        assert state.last_updated_scene == "scene_042"


class TestCheckpoints:
    def test_save_and_load_checkpoint(self):
        with tempfile.TemporaryDirectory() as td:
            char_dir = Path(td)
            snap = CharacterStateSnapshot(character_id="char-1", goal="mid_checkpoint", last_event_id=7)
            cp = SceneStateCheckpoint(
                scene_id="scene_001",
                checkpoint_id="cp-1",
                event_id=7,
                character_id="char-1",
                snapshot=snap,
            )
            save_checkpoint(char_dir, cp)
            loaded = load_checkpoint(char_dir, "scene_001")
            assert loaded is not None
            assert loaded.scene_id == "scene_001"
            assert loaded.snapshot.goal == "mid_checkpoint"

    def test_load_checkpoint_missing_returns_none(self):
        with tempfile.TemporaryDirectory() as td:
            result = load_checkpoint(Path(td), "nonexistent")
            assert result is None
