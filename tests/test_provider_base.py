"""Tests for MockProvider and LLMProvider ABC contract."""

import pytest
from pydantic import BaseModel

from app.providers.base import MockProvider


class _TestSchema(BaseModel):
    name: str
    value: int


class TestMockProvider:
    """MockProvider must satisfy the full LLMProvider contract."""

    def test_generate_text_returns_canned_response(self):
        provider = MockProvider(text_response="Hello, world!")
        import asyncio

        resp = asyncio.run(provider.generate_text([{"role": "user", "content": "Hi"}]))
        assert resp.text == "Hello, world!"
        assert resp.usage is not None

    def test_generate_structured_returns_validated_model(self):
        schema = _TestSchema(name="test", value=42)
        provider = MockProvider(structured_response=schema)
        import asyncio

        resp = asyncio.run(
            provider.generate_structured(
                [{"role": "user", "content": "Give me JSON"}],
                _TestSchema,
            )
        )
        assert resp.model is not None
        assert resp.model.name == "test"
        assert resp.model.value == 42

    def test_generate_structured_raises_when_no_response_set(self):
        provider = MockProvider()
        import asyncio

        with pytest.raises(ValueError, match="structured_response not set"):
            asyncio.run(
                provider.generate_structured(
                    [{"role": "user", "content": "Hi"}],
                    _TestSchema,
                )
            )

    def test_generate_stream_yields_tokens(self):
        provider = MockProvider(stream_tokens=["Hello", ", ", "world!"])
        import asyncio

        async def collect():
            tokens = []
            async for token in provider.generate_stream(
                [{"role": "user", "content": "Hi"}]
            ):
                tokens.append(token)
            return tokens

        tokens = asyncio.run(collect())
        assert tokens == ["Hello", ", ", "world!"]

    def test_generate_stream_empty_tokens(self):
        provider = MockProvider(stream_tokens=[])
        import asyncio

        async def collect():
            tokens = []
            async for token in provider.generate_stream(
                [{"role": "user", "content": "Hi"}]
            ):
                tokens.append(token)
            return tokens

        tokens = asyncio.run(collect())
        assert tokens == []

    def test_provider_response_usage(self):
        provider = MockProvider(text_response="Hello")
        import asyncio

        resp = asyncio.run(provider.generate_text([{"role": "user", "content": "Hi"}]))
        assert resp.usage is not None
        assert "total_tokens" in resp.usage
