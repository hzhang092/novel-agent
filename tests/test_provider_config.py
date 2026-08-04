"""Tests for ProviderConfig, factory, routing, and secure storage."""

from unittest.mock import patch

import pytest

from app.providers.base import MockProvider
from app.providers.config import (
    create_provider,
    get_provider_for_step,
    load_provider_config,
    save_provider_config,
)
from app.providers.deepseek import DeepSeekProvider
from app.providers.ollama import OllamaProvider
from app.storage.models import ProviderConfig
from app.ui.settings_dialog import STEP_LABELS


def test_provider_config_defaults_and_custom_routing():
    defaults = ProviderConfig()
    custom = ProviderConfig(routing={**defaults.routing, "writer": "deepseek"})

    assert defaults.ollama_host == "http://localhost:11434"
    assert defaults.ollama_model == "qwen:14b"
    assert defaults.deepseek_model == "deepseek-chat"
    assert defaults.deepseek_api_key == ""
    assert set(defaults.routing.values()) == {"ollama"}
    assert set(defaults.routing) == set(STEP_LABELS)
    assert custom.routing["writer"] == "deepseek"


def test_create_supported_providers():
    config = ProviderConfig(
        ollama_host="http://localhost:11434",
        ollama_model="qwen:14b",
        deepseek_model="deepseek-chat",
        deepseek_api_key="sk-test",
        deepseek_base_url="https://api.deepseek.com/v1",
    )

    ollama = create_provider("ollama", config)
    deepseek = create_provider("deepseek", config)

    assert isinstance(ollama, OllamaProvider)
    assert ollama.host == "http://localhost:11434"
    assert ollama.model == "qwen:14b"
    assert isinstance(deepseek, DeepSeekProvider)
    assert deepseek.model == "deepseek-chat"
    assert isinstance(create_provider("mock", config), MockProvider)


def test_create_unknown_provider_raises():
    with pytest.raises(ValueError, match="Unknown provider type"):
        create_provider("unknown", ProviderConfig())


def test_step_routing_covers_defaults_override_and_fallback():
    default = ProviderConfig()
    custom = ProviderConfig(
        deepseek_api_key="sk-test",
        routing={**default.routing, "writer": "deepseek"},
    )

    assert all(
        isinstance(get_provider_for_step(step, default), OllamaProvider)
        for step in default.routing
    )
    assert isinstance(get_provider_for_step("writer", custom), DeepSeekProvider)
    assert isinstance(get_provider_for_step("planner", custom), OllamaProvider)
    assert isinstance(get_provider_for_step("nonexistent", default), OllamaProvider)


def test_config_serialization_preserves_routing_but_excludes_secrets():
    legacy = ProviderConfig.model_validate(
        {
            "routing": {
                "planner": "ollama",
                "characters": "ollama",
                "writer": "ollama",
                "reviewer": "ollama",
                "fact_extractor": "deepseek",
            }
        }
    )
    config = ProviderConfig(
        ollama_model="qwen:32b",
        deepseek_api_key="sk-secret",
        routing={**ProviderConfig().routing, "planner": "deepseek"},
    )
    restored = ProviderConfig.model_validate(config.model_dump(mode="json"))

    assert legacy.routing["state_updater"] == "deepseek"
    assert legacy.routing["bible_assistant"] == "deepseek"
    assert legacy.routing["story_designer"] == "ollama"
    assert restored.ollama_model == "qwen:32b"
    assert restored.deepseek_api_key == ""
    assert restored.routing["planner"] == "deepseek"


def test_save_keeps_api_key_out_of_qsettings():
    with (
        patch("PySide6.QtCore.QSettings") as qsettings,
        patch("app.providers.config.keyring.set_password") as set_password,
    ):
        save_provider_config(ProviderConfig(deepseek_api_key="sk-secret"))

    set_password.assert_called_once_with("NovelForge", "DeepSeek API key", "sk-secret")
    saved = qsettings.return_value.setValue.call_args.args[1]
    assert "deepseek_api_key" not in saved


def test_load_migrates_legacy_api_key():
    with (
        patch("PySide6.QtCore.QSettings") as qsettings,
        patch("app.providers.config.keyring.get_password", return_value=None),
        patch("app.providers.config.keyring.set_password") as set_password,
    ):
        qsettings.return_value.value.return_value = {"deepseek_api_key": "sk-legacy"}
        config = load_provider_config()

    assert config.deepseek_api_key == "sk-legacy"
    set_password.assert_called_once_with("NovelForge", "DeepSeek API key", "sk-legacy")
    saved = qsettings.return_value.setValue.call_args.args[1]
    assert "deepseek_api_key" not in saved


def test_save_empty_key_removes_stored_credential():
    with (
        patch("PySide6.QtCore.QSettings"),
        patch("app.providers.config.keyring.delete_password") as delete_password,
    ):
        save_provider_config(ProviderConfig())

    delete_password.assert_called_once_with("NovelForge", "DeepSeek API key")
