import asyncio

import pytest

from app.storage.models import (
    ChapterCardEditPreview,
    ChapterCardProjection,
    ChapterCardStatus,
    HiddenFieldPatch,
    QuickStoryProjection,
    ReplanPreview,
    StoryArcProjection,
)
from app.ui.quick_outline_view import QuickOutlineView


class FakeQuickPlanning:
    def __init__(self):
        self.calls = []
        self.card = ChapterCardProjection(
            id="chapter-1",
            volume_id="volume-1",
            scene_id="scene-1",
            title="第一章",
            summary="主角发现线索",
            ending_hook="门后有人",
            status=ChapterCardStatus.UNWRITTEN,
        )
        self.projection = QuickStoryProjection(
            arcs=[StoryArcProjection(id="volume-1", story_id="story-1", title="第一卷", summary="开端", chapter_cards=[self.card])]
        )

    def story_projection(self):
        self.calls.append(("story_projection",))
        return self.projection

    def chapter_card(self, chapter_id):
        self.calls.append(("chapter_card", chapter_id))
        return self.card

    def preview_card_edit(self, chapter_id, edits=None, **kwargs):
        self.calls.append(("preview_card_edit", chapter_id, edits or kwargs))
        values = {"title": self.card.title, "summary": self.card.summary, "ending_hook": self.card.ending_hook}
        values.update(edits or kwargs)
        preview = ChapterCardEditPreview(chapter_id=chapter_id, changed_fields=list(values), **values)
        if getattr(self, "advanced", False):
            preview.advanced_patch = [HiddenFieldPatch(path="/scene/pov", old_value="旧", new_value="新", reason="需要高级确认")]
        return preview

    def apply_card_edit(self, preview, *, accept_advanced=False):
        self.calls.append(("apply_card_edit", preview.chapter_id, accept_advanced))
        self.card = self.card.model_copy(update={"title": preview.title, "summary": preview.summary, "ending_hook": preview.ending_hook})
        return self.card

    def brief_drift(self):
        self.calls.append(("brief_drift",))
        return type("Drift", (), {"changed_fields": ["premise", "tone_tags"]})()

    async def generate_replan(self, instruction=""):
        self.calls.append(("generate_replan", instruction))
        return ReplanPreview(future_chapter_ids=["chapter-1"], changes=["第 1 章概要"], consequences=["影响后续节奏"])

    def apply_replan(self, preview, *, confirm_published=False):
        self.calls.append(("apply_replan", confirm_published))
        return preview

    def can_plan_next_arc(self, volume_id=None):
        self.calls.append(("can_plan_next_arc", volume_id))
        return True

    async def generate_later_arc(self, volume_id=None):
        self.calls.append(("generate_later_arc", volume_id))
        return type("LaterArc", (), {"title": "第二卷", "summary": "新的旅程", "direction_conflicts": [], "changes": ["新增第二卷"]})()


def test_quick_outline_renders_cards_and_emits_canonical_scene(qtbot):
    view = QuickOutlineView()
    qtbot.addWidget(view)
    service = FakeQuickPlanning()
    view.bind_application(service)
    selected = []
    view.scene_selected.connect(selected.append)

    assert "第一章" in view.card_list.itemText(0)
    assert "待写" in view.card_list.itemText(0)
    view.select_chapter("chapter-1")
    view.write_button.click()

    assert selected == ["scene-1"]


def test_quick_outline_edits_only_card_fields_and_requests_deep_outline(qtbot):
    view = QuickOutlineView()
    qtbot.addWidget(view)
    service = FakeQuickPlanning()
    view.bind_application(service)
    requested = []
    view.deep_outline_requested.connect(requested.append)
    view.select_chapter("chapter-1")
    view.title_edit.setText("新标题")
    view.summary_edit.setPlainText("新概要")
    view.ending_hook_edit.setText("新钩子")
    view.save_button.click()
    view.advanced_outline_button.click()

    assert any(call[0] == "preview_card_edit" for call in service.calls)
    assert any(call[0] == "apply_card_edit" for call in service.calls)
    assert requested == ["chapter-1"]


def test_quick_outline_requires_explicit_choice_for_advanced_patch(qtbot):
    view = QuickOutlineView()
    qtbot.addWidget(view)
    service = FakeQuickPlanning()
    service.advanced = True
    view.bind_application(service)
    view.save_button.click()

    assert "高级字段" in view.advanced_label.text()
    assert view.apply_advanced_button.isEnabled()
    assert view.save_card_only_button.isEnabled()
    view.save_card_only_button.click()
    assert "阻止生成" in view.advanced_label.text()
    assert any(call[0] == "apply_card_edit" and call[2] is False for call in service.calls)


@pytest.mark.asyncio
async def test_quick_outline_shows_drift_replan_and_unapplied_later_arc(qtbot):
    view = QuickOutlineView()
    qtbot.addWidget(view)
    service = FakeQuickPlanning()
    view.bind_application(service)

    assert "premise" in view.drift_label.text()
    view.replan_instruction.setText("调整未来冲突")
    view.replan_button.click()
    await asyncio.sleep(0)
    assert "第 1 章概要" in view.replan_label.text()
    view.apply_replan_button.click()
    view.next_arc_button.click()
    await asyncio.sleep(0)
    assert "第二卷" in view.next_arc_label.text()
    assert not any(call[0] == "apply_later_arc" for call in service.calls)
