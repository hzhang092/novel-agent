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
    assert not panel.isHidden()
    assert panel._facts == [fact]
    assert panel._state_changes == [change]


def test_state_changes_can_be_edited_and_approved_individually(qtbot):
    panel = FactApprovalPanel()
    qtbot.addWidget(panel)
    got = []
    panel.approval_batch_approved.connect(
        lambda scene_id, revision_id, facts, changes: got.append(changes)
    )
    panel.show_items(
        "scene-a",
        "rev-a",
        [],
        [
            {
                "character_id": "c1",
                "character_name": "Lin",
                "changes": [
                    {"type": "set_field", "field": "location", "value": "market"},
                    {"type": "knowledge_add", "fact": "hidden door"},
                ],
            }
        ],
    )

    panel._change_editors[0].setText("temple")
    panel._change_checkboxes[1].setChecked(False)
    panel._on_confirm()

    assert got == [
        [
            {
                "character_id": "c1",
                "character_name": "Lin",
                "changes": [
                    {"type": "set_field", "field": "location", "value": "temple"}
                ],
            }
        ]
    ]
