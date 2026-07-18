"""Tests for CharacterHistoryWidget."""
import tempfile
from pathlib import Path

from app.storage.character_events import append_events
from app.storage.models import CharacterStateEvent, CharacterStoredChange


def test_history_widget_creation(qtbot):
    """History widget can be created and set with a character."""
    from app.ui.widgets.character_history import CharacterHistoryWidget
    widget = CharacterHistoryWidget()
    qtbot.addWidget(widget)

    with tempfile.TemporaryDirectory() as td:
        char_dir = Path(td)
        # Add some events
        append_events(char_dir, [
            CharacterStateEvent(
                event_id=1, scene_id="scene_001", character_id="char-1",
                changes=[CharacterStoredChange(type="set_field", field="goal", value="avenge", old="")],
            ),
        ])
        widget.set_character(char_dir, "scene_001")
        # Should render without error


def test_history_labels_initial_event_as_story_start(qtbot):
    from PySide6.QtWidgets import QLabel
    from app.ui.widgets.character_history import CharacterHistoryWidget

    widget = CharacterHistoryWidget()
    qtbot.addWidget(widget)

    with tempfile.TemporaryDirectory() as td:
        char_dir = Path(td)
        append_events(
            char_dir,
            [CharacterStateEvent(event_id=1, scene_id="", source="user")],
        )
        widget.set_character(char_dir)
        widget._switch_view("timeline")

        assert any("故事起点" in label.text() for label in widget.findChildren(QLabel))
