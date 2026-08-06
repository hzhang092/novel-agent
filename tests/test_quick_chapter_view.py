from app.ui.quick_chapter_view import QuickChapterView


def _configure(view):
    view.set_chapter("chapter-1", "scene-1")
    view.show_plan(
        {
            "scene_id": "scene-1",
            "scene_goal": "找到失踪的钥匙",
            "required_beats": ["进入档案室", "发现血迹"],
            "emotional_arc": "从笃定到不安",
            "ending_hook": "门后传来脚步声",
        }
    )
    view.set_length("standard", 3000, "当前目标与故事节奏匹配")
    view.set_revisions(["v1", "v2"], "v2", "v1")
    view.show_review(False, "节奏很好，但线索解释不足")
    view.show_memory(
        [{"text": "钥匙在档案室"}],
        [{"text": "主角开始怀疑同伴"}],
    )
    view.set_context_summary("本章承接第一幕")
    view.set_status("草稿")


def test_companion_shows_plan_review_memory_and_advanced_information(qtbot):
    view = QuickChapterView()
    qtbot.addWidget(view)
    _configure(view)

    assert view.goal_edit.text() == "找到失踪的钥匙"
    assert view.key_events_edit.toPlainText() == "进入档案室\n发现血迹"
    assert view.emotional_turn_edit.text() == "从笃定到不安"
    assert view.hook_edit.text() == "门后传来脚步声"
    assert view.length_combo.currentData() == "standard"
    assert view.length_warning_label.text() == "当前目标与故事节奏匹配"
    assert view.revision_combo.currentText() == "v2"
    assert "v1" in view.published_label.text()
    assert "节奏很好，但线索解释不足" in view.review_summary_label.text()
    assert view.status_label.text() == "草稿"
    assert "本章承接第一幕" in view.context_label.text()
    assert "线索解释不足" in view.review_label.text()
    assert not view.fact_checks[0].isChecked()
    assert not view.change_checks[0].isChecked()
    assert view.goal_edit.isReadOnly()
    assert view.plan()["required_beats"] == ["进入档案室", "发现血迹"]
    assert not hasattr(view, "prose_edit")


def test_companion_shows_chapter_identity_and_previous_summary(qtbot):
    view = QuickChapterView()
    qtbot.addWidget(view)

    view.set_chapter_metadata(4, "第一次交锋", "发现仙门印记")

    assert "第 4 章" in view.chapter_identity_label.text()
    assert "第一次交锋" in view.chapter_identity_label.text()
    assert "发现仙门印记" in view.previous_chapter_label.text()
    assert not view.previous_chapter_label.isHidden()


def test_revision_review_and_memory_sections_are_hidden_until_relevant(qtbot):
    view = QuickChapterView()
    qtbot.addWidget(view)

    assert view.revision_section.isHidden()
    assert view.prose_section.isHidden()
    assert view.review_section.isHidden()
    assert view.memory_section.isHidden()
    assert view.approval_section.isHidden()

    view.set_revisions(["v1"], "v1", "")
    assert not view.revision_section.isHidden()
    assert not view.prose_section.isHidden()
    assert not view.approval_section.isHidden()

    view.show_review(False, "需要复核")
    view.show_memory([{"text": "事实"}], [])
    assert not view.review_section.isHidden()
    assert not view.memory_section.isHidden()

    view.show_review(True, "")
    view.show_memory([], [])
    assert view.review_section.isHidden()
    assert view.memory_section.isHidden()


def test_programmatic_revision_selection_does_not_emit(qtbot):
    view = QuickChapterView()
    qtbot.addWidget(view)
    selected = []
    view.revision_selected.connect(selected.append)
    view.set_revisions(["v2", "v1"], "v2", "v1")

    assert view.select_revision("v1") is True
    assert view.selected_revision == "v1"
    assert selected == []


def test_reset_scene_state_clears_all_chapter_specific_presentation(qtbot):
    view = QuickChapterView()
    qtbot.addWidget(view)
    view.set_chapter("chapter-1", "scene-1")
    view.show_plan(
        {
            "scene_id": "scene-1",
            "scene_goal": "找到出口",
            "required_beats": ["开门"],
            "emotional_arc": "希望到恐惧",
            "ending_hook": "警报响起",
        }
    )
    view.begin_plan_adjustment()
    view.show_review(False, "需要复核")
    view.show_memory([{"description": "事实"}], [])
    view.set_revisions(["v1"], "v1", "")
    view.set_context_summary("旧上下文")
    view.set_status("旧状态")

    view.reset_scene_state()

    assert view.plan()["scene_goal"] == ""
    assert view.goal_edit.isReadOnly()
    assert view.revision_section.isHidden()
    assert view.review_section.isHidden()
    assert view.memory_section.isHidden()
    assert view.context_label.text() == ""
    assert view.status_label.text() == ""


def test_workflow_state_disables_conflicting_quick_actions(qtbot):
    view = QuickChapterView()
    qtbot.addWidget(view)
    view.set_chapter("chapter-1", "scene-1")
    view.set_revisions(["v1"], "v1", "")
    view.set_workflow_state(
        has_scene=True,
        generating=True,
        waiting_for_plan=False,
        has_revision=True,
        publication_ready=True,
    )

    for control in (
        view.start_button,
        view.adjust_button,
        view.regenerate_button,
        view.revision_instruction_button,
        view.revision_combo,
        view.approve_button,
        view.approve_next_button,
    ):
        assert not control.isEnabled()

    view.set_workflow_state(
        has_scene=True,
        generating=False,
        waiting_for_plan=False,
        has_revision=True,
        publication_ready=True,
    )

    assert not view.start_button.isEnabled()
    assert view.regenerate_button.isEnabled()
    assert view.revision_instruction_button.isEnabled()
    assert view.approve_button.isEnabled()

    view.set_workflow_state(
        has_scene=True,
        generating=False,
        waiting_for_plan=True,
        has_revision=True,
        publication_ready=True,
    )
    assert view.start_button.isEnabled()

    view.set_workflow_state(
        has_scene=True,
        generating=False,
        waiting_for_plan=False,
        has_revision=False,
        publication_ready=False,
    )
    assert view.start_button.isEnabled()


def test_plan_adjustment_preserves_hidden_fields_and_cancel_restores(qtbot):
    view = QuickChapterView()
    qtbot.addWidget(view)
    plan = {
        "scene_id": "scene-1",
        "scene_goal": "找到失踪的钥匙",
        "required_beats": ["进入档案室", "发现血迹"],
        "conflict": "守卫正在巡逻",
        "emotional_arc": "从笃定到不安",
        "ending_hook": "门后传来脚步声",
        "continuity_constraints": ["主角仍然受伤"],
    }
    view.show_plan(plan)
    cancellations = []
    view.adjustment_cancelled.connect(lambda: cancellations.append(True))

    view.begin_plan_adjustment()
    assert not view.goal_edit.isReadOnly()
    assert not view.key_events_edit.isReadOnly()
    assert not view.emotional_turn_edit.isReadOnly()
    assert not view.hook_edit.isReadOnly()

    view.goal_edit.setText("拿到钥匙")
    view.key_events_edit.setPlainText("躲开守卫\n打开保险柜")
    assert view.plan() == plan | {
        "scene_goal": "拿到钥匙",
        "required_beats": ["躲开守卫", "打开保险柜"],
    }

    view.adjust_button.click()

    assert cancellations == [True]
    assert view.goal_edit.isReadOnly()
    assert view.plan() == plan


def test_actions_emit_and_share_workflow_revision_selection(qtbot):
    view = QuickChapterView()
    qtbot.addWidget(view)
    _configure(view)
    starts, adjusts, saves, regenerates, instructions, lengths, revisions = (
        [], [], [], [], [], [], []
    )
    view.start_requested.connect(lambda chapter, scene: starts.append((chapter, scene)))
    view.adjust_requested.connect(adjusts.append)
    view.save_requested.connect(lambda: saves.append(True))
    view.regenerate_requested.connect(lambda: regenerates.append(True))
    view.revision_instruction_requested.connect(instructions.append)
    view.length_changed.connect(lambda mode, words: lengths.append((mode, words)))
    view.revision_selected.connect(revisions.append)

    view.start_button.click()
    view.adjust_button.click()
    view.save_button.click()
    view.regenerate_button.click()
    view.revision_instruction_edit.setText("加强不安感")
    view.revision_instruction_button.click()
    view.revision_combo.setCurrentText("v1")
    view.length_combo.setCurrentText("长 5000")

    assert starts == [("chapter-1", "scene-1")]
    assert adjusts == ["chapter-1"]
    assert saves == [True]
    assert regenerates == [True]
    assert instructions == ["加强不安感"]
    assert lengths == [("long", 5000)]
    assert revisions == ["v1"]


def test_review_memory_approval_and_deep_links_are_explicit(qtbot):
    view = QuickChapterView()
    qtbot.addWidget(view)
    _configure(view)
    fixes, details, overrides, approvals, nexts, links = [], [], [], [], [], []
    view.ai_fix_requested.connect(lambda: fixes.append(True))
    view.details_requested.connect(lambda: details.append(True))
    view.override_requested.connect(lambda: overrides.append(True))
    view.approve_requested.connect(lambda: approvals.append(True))
    view.approve_next_requested.connect(lambda: nexts.append(True))
    view.deep_control_requested.connect(links.append)

    view.ai_fix_button.click()
    view.details_button.click()
    view.override_button.click()
    view.fact_checks[0].setChecked(True)
    view.change_checks[0].setChecked(True)
    facts, changes = view.memory_selections()
    view.approve_button.click()
    view.approve_next_button.click()
    for action in view._advanced_actions.values():
        action.trigger()

    assert fixes == [True]
    assert details == [True]
    assert overrides == [True]
    assert approvals == [True]
    assert nexts == [True]
    assert links == ["context", "review", "memory", "status"]
    assert facts == [{"text": "钥匙在档案室"}]
    assert changes == [{"text": "主角开始怀疑同伴"}]
