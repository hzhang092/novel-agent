"""DeepSeekProvider — OpenAI-compatible API client for DeepSeek."""

from __future__ import annotations

import json
from typing import AsyncGenerator

from openai import AsyncOpenAI
from pydantic import BaseModel

from app.providers.base import LLMProvider, ProviderResponse


class DeepSeekProvider(LLMProvider):
    """Async DeepSeek client using the openai SDK (OpenAI-compatible API)."""

    def __init__(
        self,
        api_key: str,
        model: str = "deepseek-chat",
        base_url: str = "https://api.deepseek.com/v1",
    ) -> None:
        self.model = model
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)

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
        json_schema = schema.model_json_schema()
        json_instruction = {
            "role": "system",
            "content": (
                "You must respond with a JSON object matching this schema:\n"
                f"{json.dumps(json_schema, ensure_ascii=False)}\n"
                "Respond with ONLY the JSON, no markdown fences, no extra text."
            ),
        }
        full_messages = [json_instruction] + messages

        resp = await self._client.chat.completions.create(
            model=self.model,
            messages=full_messages,  # type: ignore[arg-type]
            temperature=temperature,
            max_tokens=4096,
            response_format={"type": "json_object"},
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
        )
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
