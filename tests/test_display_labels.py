from app.storage.models import CharacterTier
from app.ui.display_labels import character_tier_label


def test_character_tier_label_localizes_each_stable_tier():
    assert character_tier_label(CharacterTier.MAJOR) == "主要角色"
    assert character_tier_label(CharacterTier.SUPPORTING) == "配角"
    assert character_tier_label(CharacterTier.BACKGROUND) == "背景角色"
