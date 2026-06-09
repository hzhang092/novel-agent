"""Tests for OllamaProvider with mocked OpenAI SDK responses."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.providers.ollama import OllamaProvider


class _TestSchema:
    """Minimal Pydantic-like schema for testing structured generation."""

    @staticmethod
    def model_json_schema():
        return {
            "description": "Test schema",
            "title": "TestSchema",
            "type": "object",
            "properties": {
                "name": {"type": "string", "title": "Name", "default": ""},
                "value": {"type": "integer", "title": "Value", "default": 0},
            },
        }

    @staticmethod
    def model_validate(data):
        return data


def _make_mock_completion(content: str, prompt_tokens: int = 10, completion_tokens: int = 5):
    """Build a mock ChatCompletion object shaped like the openai SDK response."""
    choice = MagicMock()
    choice.message.content = content
    mock = MagicMock()
    mock.choices = [choice]
    mock.usage.prompt_tokens = prompt_tokens
    mock.usage.completion_tokens = completion_tokens
    mock.usage.total_tokens = prompt_tokens + completion_tokens
    return mock


def _make_mock_stream_chunks(chunks: list[str]):
    """Build an async generator of mock stream chunks."""
    async def _gen():
        for text in chunks:
            chunk = MagicMock()
            delta = MagicMock()
            delta.content = text
            choice = MagicMock()
            choice.delta = delta
            chunk.choices = [choice]
            yield chunk
    return _gen()


@pytest.fixture
def ollama_provider():
    return OllamaProvider(host="http://fake-ollama:11434", model="qwen:14b")


class TestOllamaProvider:
    """OllamaProvider tests using mocked openai SDK client."""

    @pytest.mark.asyncio
    async def test_generate_text(self, ollama_provider):
        mock_create = AsyncMock(return_value=_make_mock_completion("Hello, world!"))

        with patch.object(ollama_provider._client.chat.completions, "create", mock_create):
            resp = await ollama_provider.generate_text([{"role": "user", "content": "Hi"}])

        assert resp.text == "Hello, world!"
        assert resp.usage["prompt_tokens"] == 10
        assert resp.usage["completion_tokens"] == 5
        assert resp.usage["total_tokens"] == 15

    @pytest.mark.asyncio
    async def test_generate_structured(self, ollama_provider):
        mock_create = AsyncMock(
            return_value=_make_mock_completion('{"name": "test", "value": 42}')
        )

        with patch.object(ollama_provider._client.chat.completions, "create", mock_create):
            resp = await ollama_provider.generate_structured(
                [{"role": "user", "content": "Give me JSON"}],
                _TestSchema,
            )

        assert resp.parsed is not None
        assert resp.parsed["name"] == "test"
        assert resp.parsed["value"] == 42

    @pytest.mark.asyncio
    async def test_generate_structured_passes_json_schema_format(self, ollama_provider):
        """Verify that extra_body includes the `format` field with cleaned schema."""
        captured_kwargs = {}

        async def _capture(**kwargs):
            captured_kwargs.update(kwargs)
            return _make_mock_completion('{"name": "x", "value": 1}')

        mock_create = AsyncMock(side_effect=_capture)

        with patch.object(ollama_provider._client.chat.completions, "create", mock_create):
            await ollama_provider.generate_structured(
                [{"role": "user", "content": "X"}],
                _TestSchema,
            )

        assert "extra_body" in captured_kwargs
        assert "format" in captured_kwargs["extra_body"]
        fmt = captured_kwargs["extra_body"]["format"]
        assert fmt.get("type") == "object"
        # Pydantic metadata keys (title, default, description) should be stripped
        assert "title" not in fmt
        assert "description" not in fmt
        prop = fmt.get("properties", {}).get("name", {})
        assert "title" not in prop

    @pytest.mark.asyncio
    async def test_generate_stream(self, ollama_provider):
        mock_create = AsyncMock(
            return_value=_make_mock_stream_chunks(["Hello", ", ", "world!"])
        )

        with patch.object(ollama_provider._client.chat.completions, "create", mock_create):
            tokens = []
            async for token in ollama_provider.generate_stream(
                [{"role": "user", "content": "Hi"}]
            ):
                tokens.append(token)

        assert tokens == ["Hello", ", ", "world!"]
