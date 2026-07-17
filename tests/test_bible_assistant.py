import asyncio

import pytest
from pydantic import ValidationError

from app.pipeline.agents.bible_assistant import BibleAssistantAgent
from app.pipeline.bible_suggestions import (
    AddCharacterRelationSuggestion,
    AddElementRelationSuggestion,
    BibleSuggestionResponse,
    CreateElementSuggestion,
    UpdateElementSuggestion,
)
from app.providers.base import MockProvider, ProviderResponse
from app.storage.bible_models import FactionElement
from app.storage.models import CharacterCore


@pytest.mark.asyncio
async def test_assistant_returns_structured_proposals_and_records_usage():
    response = BibleSuggestionResponse(
        proposals=[
            CreateElementSuggestion(
                proposal_id="new-sect",
                confidence=0.9,
                source_excerpt="赤云宗统治北谷。",
                element_type="faction",
                name="赤云宗",
                summary="统治北谷的宗门",
            )
        ]
    )
    agent = BibleAssistantAgent()

    proposals = await agent.generate(
        MockProvider(structured_response=response),
        "赤云宗统治北谷。",
    )

    assert proposals == response.proposals
    assert agent.last_usage == {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }


@pytest.mark.asyncio
async def test_assistant_parses_all_proposal_actions_from_provider_fallback():
    class ParsedProvider(MockProvider):
        async def generate_structured(self, messages, schema, temperature=0.3):
            return ProviderResponse(
                text="",
                parsed={
                    "proposals": [
                        {
                            "proposal_id": "update-sect",
                            "action": "update_element",
                            "confidence": 0.8,
                            "target_element_id": "sect-id",
                            "summary": "统治北谷",
                        },
                        {
                            "proposal_id": "new-mine",
                            "action": "create_element",
                            "confidence": 0.9,
                            "element_type": "location",
                            "name": "北谷灵矿",
                        },
                        {
                            "proposal_id": "sect-controls-mine",
                            "action": "add_element_relation",
                            "confidence": 0.9,
                            "source_ref": "sect-id",
                            "kind": "controls",
                            "target_ref": "new-mine",
                        },
                        {
                            "proposal_id": "hero-member",
                            "action": "add_character_relation",
                            "confidence": 0.75,
                            "character_id": "hero-id",
                            "kind": "member_of",
                            "target_ref": "sect-id",
                        },
                    ]
                },
                usage={"total_tokens": 12},
            )

    proposals = await BibleAssistantAgent().generate(ParsedProvider(), "正文")

    assert [type(proposal) for proposal in proposals] == [
        UpdateElementSuggestion,
        CreateElementSuggestion,
        AddElementRelationSuggestion,
        AddCharacterRelationSuggestion,
    ]


def test_prompt_identifies_existing_elements_and_characters_for_reuse():
    prompt = BibleAssistantAgent().build_prompt(
        "赤云宗收林风为弟子。",
        existing_elements=[
            FactionElement(id="sect-id", name="赤云宗", aliases=["赤云门"])
        ],
        characters=[CharacterCore(id="hero-id", name="林风")],
    )

    assert '"id": "sect-id"' in prompt
    assert '"name": "赤云宗"' in prompt
    assert '"id": "hero-id"' in prompt
    assert "赤云宗收林风为弟子。" in prompt


def test_response_rejects_ambiguous_duplicate_temporary_refs():
    proposal = CreateElementSuggestion(
        proposal_id="same-ref",
        confidence=0.8,
        element_type="faction",
        name="赤云宗",
    )

    with pytest.raises(ValidationError, match="proposal IDs must be unique"):
        BibleSuggestionResponse(proposals=[proposal, proposal])


@pytest.mark.asyncio
async def test_assistant_returns_an_empty_proposal_result():
    proposals = await BibleAssistantAgent().generate(
        MockProvider(structured_response=BibleSuggestionResponse()), "没有新设定。"
    )

    assert proposals == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "message"),
    [
        (RuntimeError("provider failed"), "provider failed"),
        (asyncio.CancelledError(), ""),
    ],
)
async def test_assistant_propagates_provider_failure_and_cancellation(error, message):
    class FailingProvider(MockProvider):
        async def generate_structured(self, messages, schema, temperature=0.3):
            raise error

    expected = asyncio.CancelledError if isinstance(error, asyncio.CancelledError) else RuntimeError
    with pytest.raises(expected, match=message or None):
        await BibleAssistantAgent().generate(FailingProvider(), "正文")
