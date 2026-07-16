"""Tests for ProviderConfig, factory, and per-step routing."""

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


class TestProviderConfig:
    def test_defaults(self):
        cfg = ProviderConfig()
        assert cfg.ollama_host == "http://localhost:11434"
        assert cfg.ollama_model == "qwen:14b"
        assert cfg.deepseek_model == "deepseek-chat"
        assert cfg.deepseek_api_key == ""
        assert cfg.routing["planner"] == "ollama"
        assert cfg.routing["writer"] == "ollama"
        assert cfg.routing["state_updater"] == "ollama"
        assert len(cfg.routing) == 6  # all 6 steps

    def test_custom_routing(self):
        cfg = ProviderConfig(
            routing={
                "planner": "ollama",
                "characters": "ollama",
                "writer": "deepseek",
                "reviewer": "ollama",
                "fact_extractor": "ollama",
                "state_updater": "ollama",
            }
        )
        assert cfg.routing["writer"] == "deepseek"


class TestCreateProvider:
    def test_create_ollama(self):
        cfg = ProviderConfig(ollama_host="http://localhost:11434", ollama_model="qwen:14b")
        provider = create_provider("ollama", cfg)
        assert isinstance(provider, OllamaProvider)
        assert provider.host == "http://localhost:11434"
        assert provider.model == "qwen:14b"

    def test_create_deepseek(self):
        cfg = ProviderConfig(
            deepseek_model="deepseek-chat",
            deepseek_api_key="sk-test",
            deepseek_base_url="https://api.deepseek.com/v1",
        )
        provider = create_provider("deepseek", cfg)
        assert isinstance(provider, DeepSeekProvider)
        assert provider.model == "deepseek-chat"

    def test_create_mock(self):
        cfg = ProviderConfig()
        provider = create_provider("mock", cfg)
        assert isinstance(provider, MockProvider)

    def test_create_unknown_raises(self):
        cfg = ProviderConfig()
        with pytest.raises(ValueError, match="Unknown provider type"):
            create_provider("unknown", cfg)


class TestGetProviderForStep:
    def test_default_routing_all_ollama(self):
        cfg = ProviderConfig()
        for step in [
            "planner",
            "characters",
            "writer",
            "reviewer",
            "fact_extractor",
            "state_updater",
        ]:
            provider = get_provider_for_step(step, cfg)
            assert isinstance(provider, OllamaProvider)

    def test_custom_writer_routing(self):
        cfg = ProviderConfig(
            deepseek_api_key="sk-test",
            routing={
                "planner": "ollama",
                "characters": "ollama",
                "writer": "deepseek",
                "reviewer": "ollama",
                "fact_extractor": "ollama",
                "state_updater": "ollama",
            },
        )
        writer = get_provider_for_step("writer", cfg)
        assert isinstance(writer, DeepSeekProvider)

        planner = get_provider_for_step("planner", cfg)
        assert isinstance(planner, OllamaProvider)

    def test_unknown_step_falls_back(self):
        cfg = ProviderConfig()
        provider = get_provider_for_step("nonexistent", cfg)
        assert isinstance(provider, OllamaProvider)


class TestConfigSerialization:
    def test_legacy_config_adds_state_updater_from_fact_extractor(self):
        cfg = ProviderConfig.model_validate({
            "routing": {
                "planner": "ollama",
                "characters": "ollama",
                "writer": "ollama",
                "reviewer": "ollama",
                "fact_extractor": "deepseek",
            }
        })

        assert cfg.routing["state_updater"] == "deepseek"

    def test_round_trip_excludes_api_key(self):
        cfg = ProviderConfig(
            ollama_model="qwen:32b",
            deepseek_api_key="sk-secret",
            routing={
                "planner": "deepseek",
                "characters": "deepseek",
                "writer": "deepseek",
                "reviewer": "ollama",
                "fact_extractor": "ollama",
                "state_updater": "ollama",
            },
        )
        data = cfg.model_dump(mode="json")
        restored = ProviderConfig.model_validate(data)
        assert restored.ollama_model == "qwen:32b"
        assert restored.deepseek_api_key == ""
        assert restored.routing["planner"] == "deepseek"


class TestSecureConfigStorage:
    def test_save_keeps_api_key_out_of_qsettings(self):
        config = ProviderConfig(deepseek_api_key="sk-secret")

        with (
            patch("PyQt6.QtCore.QSettings") as qsettings,
            patch("app.providers.config.keyring.set_password") as set_password,
        ):
            save_provider_config(config)

        set_password.assert_called_once_with("NovelForge", "DeepSeek API key", "sk-secret")
        saved = qsettings.return_value.setValue.call_args.args[1]
        assert "deepseek_api_key" not in saved

    def test_load_migrates_legacy_api_key(self):
        with (
            patch("PyQt6.QtCore.QSettings") as qsettings,
            patch("app.providers.config.keyring.get_password", return_value=None),
            patch("app.providers.config.keyring.set_password") as set_password,
        ):
            qsettings.return_value.value.return_value = {"deepseek_api_key": "sk-legacy"}
            config = load_provider_config()

        assert config.deepseek_api_key == "sk-legacy"
        set_password.assert_called_once_with("NovelForge", "DeepSeek API key", "sk-legacy")
        saved = qsettings.return_value.setValue.call_args.args[1]
        assert "deepseek_api_key" not in saved

    def test_save_empty_key_removes_stored_credential(self):
        with (
            patch("PyQt6.QtCore.QSettings"),
            patch("app.providers.config.keyring.delete_password") as delete_password,
        ):
            save_provider_config(ProviderConfig())

        delete_password.assert_called_once_with("NovelForge", "DeepSeek API key")
