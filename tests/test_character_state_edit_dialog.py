from PySide6.QtWidgets import QLineEdit

from app.storage.models import CharacterState


def test_state_override_dialog_edits_a_copy(qtbot):
    from app.ui.character_state_edit_dialog import CharacterStateEditDialog

    state = CharacterState(
        character_id="char-1",
        current_goal="旧目标",
        current_emotion="平静",
        current_location="山门",
        current_power_level="炼气",
        current_relationships={"ally": "朋友"},
        current_knowledge=["线索"],
        current_secrets=["秘密"],
        current_status="健康",
        last_updated_scene="scene-1",
    )
    dialog = CharacterStateEditDialog(state)
    qtbot.addWidget(dialog)

    dialog.findChild(QLineEdit, "current_goal").setText("新目标")
    gathered = dialog.gathered_state()

    assert state.current_goal == "旧目标"
    assert gathered == state.model_copy(update={"current_goal": "新目标"})
