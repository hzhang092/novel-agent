"""Provider configuration, per-step routing, and factory."""

from __future__ import annotations

import keyring
from keyring.errors import PasswordDeleteError

from app.providers.base import LLMProvider
from app.storage.models import ProviderConfig

_CREDENTIAL_SERVICE = "NovelForge"
_CREDENTIAL_ACCOUNT = "DeepSeek API key"


def _get_default_config() -> ProviderConfig:
    return ProviderConfig()


def load_provider_config() -> ProviderConfig:
    """Load provider config from QSettings, falling back to defaults."""
    from PySide6.QtCore import QSettings

    settings = QSettings()
    raw = settings.value("providers/config")
    if raw is None:
        config = _get_default_config()
    else:
        try:
            config = ProviderConfig.model_validate(raw)
        except Exception:
            config = _get_default_config()

    legacy_key = config.deepseek_api_key
    stored_key = keyring.get_password(_CREDENTIAL_SERVICE, _CREDENTIAL_ACCOUNT)
    if legacy_key:
        if stored_key is None:
            keyring.set_password(_CREDENTIAL_SERVICE, _CREDENTIAL_ACCOUNT, legacy_key)
            stored_key = legacy_key
        settings.setValue("providers/config", config.model_dump(mode="json"))
    config.deepseek_api_key = stored_key or ""
    return config


def save_provider_config(config: ProviderConfig) -> None:
    """Persist non-secret config to QSettings and the API key to keyring."""
    from PySide6.QtCore import QSettings

    if config.deepseek_api_key:
        keyring.set_password(
            _CREDENTIAL_SERVICE,
            _CREDENTIAL_ACCOUNT,
            config.deepseek_api_key,
        )
    else:
        try:
            keyring.delete_password(_CREDENTIAL_SERVICE, _CREDENTIAL_ACCOUNT)
        except PasswordDeleteError:
            pass

    settings = QSettings()
    settings.setValue("providers/config", config.model_dump(mode="json"))


def create_provider(provider_type: str, config: ProviderConfig) -> LLMProvider:
    """Factory: create a provider instance from type string and config.

    Args:
        provider_type: "ollama", "deepseek", or "mock"
        config: ProviderConfig with host, model, API key, etc.

    Returns:
        Concrete LLMProvider instance.

    Raises:
        ValueError: If provider_type is unknown.
    """
    if provider_type == "ollama":
        from app.providers.ollama import OllamaProvider

        return OllamaProvider(host=config.ollama_host, model=config.ollama_model)
    elif provider_type == "deepseek":
        from app.providers.deepseek import DeepSeekProvider

        return DeepSeekProvider(
            api_key=config.deepseek_api_key,
            model=config.deepseek_model,
            base_url=config.deepseek_base_url,
        )
    elif provider_type == "mock":
        from app.providers.base import MockProvider

        return MockProvider()
    else:
        raise ValueError(f"Unknown provider type: {provider_type}")


def get_provider_for_step(step_id: str, config: ProviderConfig) -> LLMProvider:
    """Resolve the right provider for a pipeline step.

    Args:
        step_id: One of "planner", "characters", "writer", "reviewer",
            "fact_extractor", "state_updater"
        config: ProviderConfig with routing map.

    Returns:
        LLMProvider instance for this step.
    """
    provider_type = config.routing.get(step_id, "ollama")
    return create_provider(provider_type, config)
