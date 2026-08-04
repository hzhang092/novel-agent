from app.storage.models import (
    ChapterCardEditPreview,
    ChapterCardProjection,
    ChapterCardStatus,
    QuickStoryProjection,
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
        return ChapterCardEditPreview(chapter_id=chapter_id, changed_fields=list(values), **values)

    def apply_card_edit(self, preview):
        self.calls.append(("apply_card_edit", preview.chapter_id))
        self.card = self.card.model_copy(update={"title": preview.title, "summary": preview.summary, "ending_hook": preview.ending_hook})
        return self.card

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


def test_quick_outline_hides_brief_drift_and_replanning_controls(qtbot):
    view = QuickOutlineView()
    qtbot.addWidget(view)
    service = FakeQuickPlanning()
    view.bind_application(service)

    assert not hasattr(view, "drift_label")
    assert not hasattr(view, "replan_button")
    assert not any("重规划" in button.text() for button in view.findChildren(type(view.save_button)))
