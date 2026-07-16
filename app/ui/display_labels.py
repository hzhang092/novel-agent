"""Localized labels for stable storage values."""

from app.storage.models import CharacterTier


CHARACTER_TIER_LABELS = {
    CharacterTier.MAJOR: "主要角色",
    CharacterTier.SUPPORTING: "配角",
    CharacterTier.BACKGROUND: "背景角色",
}


def character_tier_label(tier: CharacterTier) -> str:
    return CHARACTER_TIER_LABELS.get(tier, tier.value)
