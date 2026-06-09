"""OllamaProvider — connects to local Ollama via HTTP API."""

from __future__ import annotations

import json
from typing import AsyncGenerator

import httpx
from pydantic import BaseModel

from app.providers.base import LLMProvider, ProviderResponse


class OllamaProvider(LLMProvider):
    """Async Ollama client using httpx.

    Uses Ollama's `format` field to pass JSON schema for structured generation.
    """

    def __init__(self, host: str = "http://localhost:11434", model: str = "qwen:14b") -> None:
        self.host = host.rstrip("/")
        self.model = model
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(120.0))
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def generate_text(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> ProviderResponse:
        client = await self._get_client()
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_ctx": 16384,
                "presence_penalty": 0.0,
            },
        }
        resp = await client.post(f"{self.host}/api/chat", json=payload)
        try:
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            await resp.aread()  # consume body to prevent httpcore cleanup warnings
            raise
        text = data["message"]["content"]
        return ProviderResponse(
            text=text,
            usage={
                "prompt_tokens": data.get("prompt_eval_count", 0),
                "completion_tokens": data.get("eval_count", 0),
                "total_tokens": data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
            },
        )

    async def generate_structured(
        self,
        messages: list[dict[str, str]],
        schema: type[BaseModel],
        temperature: float = 0.3,
    ) -> ProviderResponse:
        client = await self._get_client()
        json_schema = _clean_schema(schema.model_json_schema())
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "format": json_schema,
            "options": {
                "temperature": temperature,
                "num_predict": 4096,
                "num_ctx": 16384,
                "presence_penalty": 0.0,
            },
        }
        resp = await client.post(f"{self.host}/api/chat", json=payload)
        try:
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            await resp.aread()  # consume body to prevent httpcore cleanup warnings
            raise
        text = data["message"]["content"]
        parsed = json.loads(text)
        model = schema.model_validate(parsed)
        return ProviderResponse(
            text=text,
            model=model,
            parsed=parsed,
            usage={
                "prompt_tokens": data.get("prompt_eval_count", 0),
                "completion_tokens": data.get("eval_count", 0),
                "total_tokens": data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
            },
        )

    async def generate_stream(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        client = await self._get_client()
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_ctx": 16384,
                "presence_penalty": 0.0,
            },
        }
        async with client.stream("POST", f"{self.host}/api/chat", json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if chunk.get("done", False):
                    break
                content = chunk.get("message", {}).get("content", "")
                if content:
                    yield content


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
