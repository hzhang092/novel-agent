from app.ui.widgets.planner_checkpoint import PlannerCheckpointWidget


def test_approval_emits_edited_plan(qtbot):
    widget = PlannerCheckpointWidget()
    qtbot.addWidget(widget)
    widget.show_plan(
        {
            "scene_id": "scene-1",
            "scene_goal": "旧目标",
            "required_beats": ["旧节拍"],
            "conflict": "旧冲突",
            "emotional_arc": "旧情绪",
            "ending_hook": "旧钩子",
            "continuity_constraints": ["旧约束"],
        }
    )

    widget._scene_goal_edit.setText("新目标")
    widget._required_beats_edit.setPlainText("第一拍\n第二拍")
    widget._continuity_constraints_edit.setPlainText("约束一\n约束二")
    approved = []
    widget.approved.connect(approved.append)

    widget._on_approve()

    assert approved[0]["scene_id"] == "scene-1"
    assert approved[0]["scene_goal"] == "新目标"
    assert approved[0]["required_beats"] == ["第一拍", "第二拍"]
    assert approved[0]["continuity_constraints"] == ["约束一", "约束二"]
