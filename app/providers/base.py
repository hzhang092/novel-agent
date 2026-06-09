"""LLMProvider abstract base class and MockProvider for testing."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncGenerator

from pydantic import BaseModel


@dataclass
class ProviderResponse:
    """Wrapper for structured generation results."""
    text: str
    model: BaseModel | None = None
    parsed: dict | None = None
    usage: dict | None = None  # {"prompt_tokens": N, "completion_tokens": N, "total_tokens": N}


class LLMProvider(ABC):
    """Unified interface for Ollama, DeepSeek, and mock providers."""

    async def close(self) -> None:
        """Release provider resources (connections, sessions, etc.)."""
        pass

    @abstractmethod
    async def generate_text(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> ProviderResponse:
        """Generate free-text output (used by Writer agent)."""
        ...

    @abstractmethod
    async def generate_structured(
        self,
        messages: list[dict[str, str]],
        schema: type[BaseModel],
        temperature: float = 0.3,
    ) -> ProviderResponse:
        """Generate Pydantic model output via JSON schema (used by Planner, Characters, Reviewer, FactExtractor)."""
        ...

    @abstractmethod
    async def generate_stream(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        """Stream tokens for real-time prose display (used by Writer agent)."""
        ...


class MockProvider(LLMProvider):
    """Returns canned responses for all three methods. Used in tests."""

    def __init__(
        self,
        text_response: str = "",
        structured_response: BaseModel | None = None,
        stream_tokens: list[str] | None = None,
    ) -> None:
        self.text_response = text_response
        self.structured_response = structured_response
        self.stream_tokens = stream_tokens or []

    async def generate_text(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> ProviderResponse:
        return ProviderResponse(
            text=self.text_response,
            usage={"prompt_tokens": 0, "completion_tokens": len(self.text_response), "total_tokens": len(self.text_response)},
        )

    async def generate_structured(
        self,
        messages: list[dict[str, str]],
        schema: type[BaseModel],
        temperature: float = 0.3,
    ) -> ProviderResponse:
        if self.structured_response is None:
            raise ValueError("MockProvider.structured_response not set")
        return ProviderResponse(
            text=self.structured_response.model_dump_json(),
            model=self.structured_response,
            parsed=self.structured_response.model_dump(),
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        )

    async def generate_stream(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        for token in self.stream_tokens:
            yield token
