"""Tests for Xianxia template data validity."""

from app.utils.xianxia_template import get_xianxia_template


def test_template_returns_valid_models():
    world, style = get_xianxia_template()

    # WorldSetting fields
    assert world.geography != ""
    assert world.power_system is not None
    assert len(world.power_system.realms) == 9
    assert len(world.power_system.abilities) == 9
    assert len(world.factions) >= 3
    assert len(world.rules) >= 2
    assert len(world.taboos) >= 2
    assert len(world.terminology) >= 4

    # StyleGuide fields
    assert style.pacing != ""
    assert style.tone != ""
    assert style.pov != ""
    assert len(style.taboo_patterns) >= 3
    assert len(style.preferred_patterns) >= 3
    assert style.freeform_notes != ""
