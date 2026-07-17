from app.domain.story_usage import (
    ElementUsageSummary,
    SceneUsage,
    StoryUsageKind,
)
from app.ui.story_usage_panel import StoryUsagePanel


def test_usage_panel_groups_scene_usage_and_emits_selected_scene(qtbot):
    panel = StoryUsagePanel()
    qtbot.addWidget(panel)
    selected = []
    panel.scene_requested.connect(selected.append)

    panel.set_usage(ElementUsageSummary("sect", (
        SceneUsage(
            "scene-1", "chapter-1", 2, "Gate visit",
            frozenset({
                StoryUsageKind.EXPLICIT_OUTLINE,
                StoryUsageKind.GENERATION_CONTEXT,
                StoryUsageKind.PROSE_MENTION,
            }),
            selection_reasons=("explicit_scene_reference",),
            matched_alias="Cloud Sect",
            generated_element_revision=1,
            current_element_revision=2,
        ),
    )))

    groups = [
        panel._tree.topLevelItem(index).text(0)
        for index in range(panel._tree.topLevelItemCount())
    ]
    assert groups == ["Explicit outline (1)", "Generation context (1)", "Mentioned in prose (1)"]
    generated = panel._tree.topLevelItem(1).child(0)
    assert "revision changed (1 → 2)" in generated.text(0)
    assert "explicit scene reference" in generated.toolTip(0)

    panel._tree.setCurrentItem(generated)
    panel._tree.itemActivated.emit(generated, 0)
    assert selected == ["scene-1"]


def test_panel_displays_character_location_and_inference_reason(qtbot):
    panel = StoryUsagePanel(title="Scene presence")
    qtbot.addWidget(panel)
    panel.set_usage(ElementUsageSummary("character-1", (
        SceneUsage(
            "scene-1", "chapter-1", 2, "Arrival",
            frozenset({StoryUsageKind.CHARACTER_PRESENCE}),
            location_label="Cloud Peak",
            location_reason="Explicit location element",
        ),
    )))

    item = panel._tree.topLevelItem(0).child(0)
    assert "Cloud Peak" in item.text(0)
    assert "Explicit location element" in item.toolTip(0)
