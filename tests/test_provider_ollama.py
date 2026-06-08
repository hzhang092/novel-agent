"""Tests for OllamaProvider with mocked HTTP responses."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.providers.ollama import OllamaProvider


class _TestSchema:
    """Minimal Pydantic-like schema for testing structured generation."""

    @staticmethod
    def model_json_schema():
        return {"type": "object", "properties": {"name": {"type": "string"}, "value": {"type": "integer"}}}

    @staticmethod
    def model_validate(data):
        return data


@pytest.fixture
def ollama_provider():
    return OllamaProvider(host="http://fake-ollama:11434", model="qwen:14b")


class TestOllamaProvider:
    """OllamaProvider integration points, tested with mocked httpx."""

    @pytest.mark.asyncio
    async def test_generate_text(self, ollama_provider):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "model": "qwen:14b",
            "message": {"role": "assistant", "content": "Hello, world!"},
            "done": True,
            "prompt_eval_count": 10,
            "eval_count": 5,
        }
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp

        with patch.object(ollama_provider, "_get_client", return_value=mock_client):
            resp = await ollama_provider.generate_text([{"role": "user", "content": "Hi"}])
            assert resp.text == "Hello, world!"
            assert resp.usage["prompt_tokens"] == 10
            assert resp.usage["completion_tokens"] == 5
            assert resp.usage["total_tokens"] == 15

    @pytest.mark.asyncio
    async def test_generate_structured(self, ollama_provider):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "model": "qwen:14b",
            "message": {"role": "assistant", "content": '{"name": "test", "value": 42}'},
            "done": True,
            "prompt_eval_count": 10,
            "eval_count": 5,
        }
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp

        with patch.object(ollama_provider, "_get_client", return_value=mock_client):
            resp = await ollama_provider.generate_structured(
                [{"role": "user", "content": "Give me JSON"}],
                _TestSchema,
            )
            assert resp.parsed is not None
            assert resp.parsed["name"] == "test"
            assert resp.parsed["value"] == 42

    @pytest.mark.asyncio
    async def test_generate_structured_passes_json_schema_format(self, ollama_provider):
        """Verify that the Ollama API `format` field receives the JSON schema."""
        last_payload = {}

        async def capture_post(url, json=None, **kwargs):
            nonlocal last_payload
            last_payload.update(json)
            mock_resp = MagicMock()
            mock_resp.json.return_value = {
                "model": "qwen:14b",
                "message": {"role": "assistant", "content": '{"name": "x", "value": 1}'},
                "done": True,
                "prompt_eval_count": 0,
                "eval_count": 0,
            }
            mock_resp.raise_for_status = MagicMock()
            return mock_resp

        mock_client = AsyncMock()
        mock_client.post = capture_post

        with patch.object(ollama_provider, "_get_client", return_value=mock_client):
            await ollama_provider.generate_structured(
                [{"role": "user", "content": "X"}],
                _TestSchema,
            )
            assert "format" in last_payload
            assert last_payload["format"].get("type") == "object"

    @pytest.mark.asyncio
    async def test_generate_stream(self, ollama_provider):
        async def stream_lines():
            for line in [
                json.dumps({"message": {"content": "Hello"}, "done": False}),
                json.dumps({"message": {"content": ", "}, "done": False}),
                json.dumps({"message": {"content": "world!"}, "done": False}),
                json.dumps({"done": True}),
            ]:
                yield line

        class _MockStreamResponse:
            async def aiter_lines(self):
                async for line in stream_lines():
                    yield line

            def raise_for_status(self):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        mock_client = MagicMock()
        mock_client.stream = MagicMock(return_value=_MockStreamResponse())

        with patch.object(ollama_provider, "_get_client", return_value=mock_client):
            tokens = []
            async for token in ollama_provider.generate_stream([{"role": "user", "content": "Hi"}]):
                tokens.append(token)
            assert tokens == ["Hello", ", ", "world!"]
