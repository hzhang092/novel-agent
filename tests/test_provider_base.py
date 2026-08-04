"""Tests for MockProvider's LLMProvider contract."""

import asyncio

import pytest
from pydantic import BaseModel

from app.providers.base import MockProvider


class _TestSchema(BaseModel):
    name: str
    value: int


def test_mock_provider_happy_path_contract():
    schema = _TestSchema(name="test", value=42)
    provider = MockProvider(
        text_response="Hello, world!",
        structured_response=schema,
        stream_tokens=["Hello", ", ", "world!"],
    )

    text = asyncio.run(provider.generate_text([{"role": "user", "content": "Hi"}]))
    structured = asyncio.run(
        provider.generate_structured(
            [{"role": "user", "content": "Give me JSON"}],
            _TestSchema,
        )
    )

    async def collect(current_provider):
        return [
            token
            async for token in current_provider.generate_stream(
                [{"role": "user", "content": "Hi"}]
            )
        ]

    assert text.text == "Hello, world!"
    assert text.usage is not None
    assert "total_tokens" in text.usage
    assert structured.model == schema
    assert asyncio.run(collect(provider)) == ["Hello", ", ", "world!"]
    assert asyncio.run(collect(MockProvider(stream_tokens=[]))) == []


def test_generate_structured_requires_a_response():
    with pytest.raises(ValueError, match="structured_response not set"):
        asyncio.run(
            MockProvider().generate_structured(
                [{"role": "user", "content": "Hi"}],
                _TestSchema,
            )
        )
