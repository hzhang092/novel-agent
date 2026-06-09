"""OllamaProvider — connects to local Ollama via OpenAI-compatible API."""

from __future__ import annotations

import json
from typing import AsyncGenerator

from openai import AsyncOpenAI
from pydantic import BaseModel

from app.providers.base import LLMProvider, ProviderResponse


class OllamaProvider(LLMProvider):
    """Async Ollama client using the openai SDK for OpenAI-compatible API.

    Ollama exposes an OpenAI-compatible endpoint at /v1, so we can use
    AsyncOpenAI with base_url pointed at the Ollama host.  Ollama-specific
    parameters (num_ctx, format, etc.) are passed via extra_body.
    """

    def __init__(self, host: str = "http://localhost:11434", model: str = "qwen:14b") -> None:
        self.host = host.rstrip("/")
        self.model = model
        self._client = AsyncOpenAI(
            api_key="ollama",  # dummy key, Ollama doesn't require auth
            base_url=f"{self.host}/v1",
        )

    async def close(self) -> None:
        await self._client.close()

    async def generate_text(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> ProviderResponse:
        resp = await self._client.chat.completions.create(
            model=self.model,
            messages=messages,  # type: ignore[arg-type]
            temperature=temperature,
            max_tokens=max_tokens,
            extra_body={
                "options": {
                    "num_ctx": 16384,
                    "presence_penalty": 0.0,
                },
            },
        )
        choice = resp.choices[0]
        return ProviderResponse(
            text=choice.message.content or "",
            usage={
                "prompt_tokens": resp.usage.prompt_tokens if resp.usage else 0,
                "completion_tokens": resp.usage.completion_tokens if resp.usage else 0,
                "total_tokens": resp.usage.total_tokens if resp.usage else 0,
            },
        )

    async def generate_structured(
        self,
        messages: list[dict[str, str]],
        schema: type[BaseModel],
        temperature: float = 0.3,
    ) -> ProviderResponse:
        json_schema = _clean_schema(schema.model_json_schema())
        resp = await self._client.chat.completions.create(
            model=self.model,
            messages=messages,  # type: ignore[arg-type]
            temperature=temperature,
            max_tokens=4096,
            extra_body={
                "format": json_schema,
                "options": {
                    "num_ctx": 16384,
                    "presence_penalty": 0.0,
                },
            },
        )
        choice = resp.choices[0]
        text = choice.message.content or ""
        parsed = json.loads(text)
        model = schema.model_validate(parsed)
        return ProviderResponse(
            text=text,
            model=model,
            parsed=parsed,
            usage={
                "prompt_tokens": resp.usage.prompt_tokens if resp.usage else 0,
                "completion_tokens": resp.usage.completion_tokens if resp.usage else 0,
                "total_tokens": resp.usage.total_tokens if resp.usage else 0,
            },
        )

    async def generate_stream(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        stream = await self._client.chat.completions.create(
            model=self.model,
            messages=messages,  # type: ignore[arg-type]
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            extra_body={
                "options": {
                    "num_ctx": 16384,
                    "presence_penalty": 0.0,
                },
            },
        )
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content


def _clean_schema(schema: dict) -> dict:
    """Strip Pydantic-specific keys (title, default, description) for Ollama compat."""
    if isinstance(schema, dict):
        return {
            k: _clean_schema(v)
            for k, v in schema.items()
            if k not in ("title", "default", "description")
        }
    if isinstance(schema, list):
        return [_clean_schema(item) for item in schema]
    return schema
