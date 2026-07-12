from app.ui.widgets.fact_approval import FactApprovalPanel


def test_confirm_emits_source_scene_id(qtbot):
    panel = FactApprovalPanel()
    qtbot.addWidget(panel)

    got = []
    panel.approval_batch_approved.connect(
        lambda scene_id, revision_id, facts, changes: got.append(
            (scene_id, revision_id, facts, changes)
        )
    )

    fact = {"description": "sect exists", "category": "world"}
    change = {
        "character_id": "c1",
        "character_name": "Lin",
        "changes": [{"type": "set_field", "field": "location", "value": "market"}],
    }

    panel.show_items("scene-a", "rev-a", [fact], [change])
    panel._on_confirm()

    assert got == [("scene-a", "rev-a", [fact], [change])]
