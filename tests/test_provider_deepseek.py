"""Tests for DeepSeekProvider with mocked openai SDK."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.providers.deepseek import DeepSeekProvider


class _TestSchema:
    """Minimal Pydantic-like schema for testing structured generation."""

    @staticmethod
    def model_json_schema():
        return {"type": "object", "properties": {"name": {"type": "string"}, "value": {"type": "integer"}}}

    @staticmethod
    def model_validate(data):
        return data


@pytest.fixture
def deepseek_provider():
    return DeepSeekProvider(
        api_key="sk-test",
        model="deepseek-chat",
        base_url="https://api.deepseek.com/v1",
    )


class TestDeepSeekProvider:
    """DeepSeekProvider integration points, tested with mocked openai SDK."""

    @pytest.mark.asyncio
    async def test_generate_text(self, deepseek_provider):
        mock_choice = MagicMock()
        mock_choice.message.content = "Hello, world!"

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 10
        mock_usage.completion_tokens = 5
        mock_usage.total_tokens = 15

        mock_resp = MagicMock()
        mock_resp.choices = [mock_choice]
        mock_resp.usage = mock_usage

        with patch.object(
            deepseek_provider._client.chat.completions, "create", new=AsyncMock(return_value=mock_resp)
        ):
            resp = await deepseek_provider.generate_text([{"role": "user", "content": "Hi"}])
            assert resp.text == "Hello, world!"
            assert resp.usage["prompt_tokens"] == 10
            assert resp.usage["completion_tokens"] == 5
            assert resp.usage["total_tokens"] == 15

    @pytest.mark.asyncio
    async def test_generate_structured(self, deepseek_provider):
        json_str = json.dumps({"name": "test", "value": 42}, ensure_ascii=False)
        mock_choice = MagicMock()
        mock_choice.message.content = json_str

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 12
        mock_usage.completion_tokens = 8
        mock_usage.total_tokens = 20

        mock_resp = MagicMock()
        mock_resp.choices = [mock_choice]
        mock_resp.usage = mock_usage

        with patch.object(
            deepseek_provider._client.chat.completions, "create", new=AsyncMock(return_value=mock_resp)
        ):
            resp = await deepseek_provider.generate_structured(
                [{"role": "user", "content": "Give me JSON"}],
                _TestSchema,
            )
            assert resp.parsed is not None
            assert resp.parsed["name"] == "test"
            assert resp.parsed["value"] == 42

    @pytest.mark.asyncio
    async def test_generate_structured_uses_json_object_format(self, deepseek_provider):
        """Verify response_format is set to json_object."""
        json_str = json.dumps({"name": "x", "value": 1}, ensure_ascii=False)

        mock_choice = MagicMock()
        mock_choice.message.content = json_str

        mock_resp = MagicMock()
        mock_resp.choices = [mock_choice]
        mock_resp.usage = None

        mock_create = AsyncMock(return_value=mock_resp)
        with patch.object(deepseek_provider._client.chat.completions, "create", new=mock_create):
            await deepseek_provider.generate_structured(
                [{"role": "user", "content": "X"}],
                _TestSchema,
            )
            call_kwargs = mock_create.call_args.kwargs
            assert call_kwargs["response_format"] == {"type": "json_object"}

    @pytest.mark.asyncio
    async def test_generate_stream(self, deepseek_provider):
        async def mock_stream():
            for content in ["Hello", ", ", "world!"]:
                chunk = MagicMock()
                chunk.choices = [MagicMock()]
                chunk.choices[0].delta.content = content
                yield chunk

        mock_create = AsyncMock(return_value=mock_stream())
        with patch.object(deepseek_provider._client.chat.completions, "create", new=mock_create):
            tokens = []
            async for token in deepseek_provider.generate_stream([{"role": "user", "content": "Hi"}]):
                tokens.append(token)
            assert tokens == ["Hello", ", ", "world!"]

    @pytest.mark.asyncio
    async def test_generate_stream_empty(self, deepseek_provider):
        async def mock_stream():
            if False:
                yield

        mock_create = AsyncMock(return_value=mock_stream())
        with patch.object(deepseek_provider._client.chat.completions, "create", new=mock_create):
            tokens = []
            async for token in deepseek_provider.generate_stream([{"role": "user", "content": "Hi"}]):
                tokens.append(token)
            assert tokens == []
