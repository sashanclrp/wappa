"""Each accepted part describes only the structure that reached its own send."""

import json
from unittest.mock import AsyncMock

import pytest
from test_interactive_header import BUTTONS, IG_DM, SECTIONS, WA_DM, _ig, _wa
from test_messenger_parameter_reach import _card

from wappa.domain.interactive import InteractiveHeader
from wappa.domain.results import MessageResult, OperationOutcome
from wappa.messaging.meta.graph import GraphResponse


@pytest.mark.parametrize("platform", ["whatsapp", "instagram"])
@pytest.mark.parametrize(
    "family", ["text", "buttons", "list", "carousel", "media", "cta"]
)
async def test_shared_part_content_is_typed_serializable_and_describes_the_actual_part(
    platform, family
):
    ig, client, _ = _ig()
    wa, _ = _wa()
    messenger, target = (wa, WA_DM) if platform == "whatsapp" else (ig, IG_DM)
    try:
        if family == "text":
            result = await messenger.send_text("hello", target)
        elif family == "buttons":
            result = await messenger.send_button_message(BUTTONS, target, "Pick")
        elif family == "list":
            result = await messenger.send_list_message(SECTIONS, target, "Pick", "Open")
        elif family == "carousel":
            result = await messenger.send_carousel(
                [_card(1), _card(2)], target, "Intro"
            )
        elif family == "cta":
            result = await messenger.send_cta_message(
                "Open", "https://example.com", target, "Body"
            )
        else:
            result = await messenger.send_image(
                "https://example.com/a.jpg", target, caption="Caption"
            )
        assert result.success
        serialized = json.loads(result.model_dump_json())
        restored = MessageResult.model_validate_json(result.model_dump_json())
        assert restored.parts == result.parts
        assert len(serialized["parts"]) == len(result.parts)
        assert [
            part["content"] for part in result.platform_response["wappa_parts"]["parts"]
        ] == [
            part.content.model_dump(mode="json", exclude_none=True)
            if part.content
            else None
            for part in result.parts
        ]
        if family == "text":
            assert result.parts[0].content is None
        elif family in {"buttons", "cta"}:
            content = result.parts[0].content
            assert len(content.buttons) == 1
            if family == "buttons":
                assert content.buttons[0].id == BUTTONS[0].id
                assert content.buttons[0].title == BUTTONS[0].title
            else:
                assert content.buttons[0].type == "url"
                assert content.buttons[0].url == (
                    "https://example.com/"
                    if platform == "instagram"
                    else "https://example.com"
                )
        elif family == "list":
            if platform == "instagram":
                assert (
                    result.parts[-1].content.quick_replies[0].id
                    == SECTIONS[0].rows[0].id
                )
            else:
                assert (
                    result.parts[0].content.sections[0].rows[0].id
                    == SECTIONS[0].rows[0].id
                )
        elif family == "carousel":
            cards = result.parts[-1].content.elements
            assert len(cards) == 2
            assert cards[0].media.url == str(_card(1).header.url)
            assert len(cards[0].buttons) == len(_card(1).buttons)
            if platform == "instagram":
                assert result.parts[0].content is None  # plain intro
        else:
            assert result.parts[0].content.media.url == "https://example.com/a.jpg"
            if platform == "instagram":
                assert result.parts[1].text == "Caption"
                assert result.parts[1].content is None
    finally:
        await client.aclose()


async def test_partial_instagram_cta_history_never_claims_the_refused_buttons_arrived():
    ig, client, _ = _ig()
    ig._graph.request = AsyncMock(
        side_effect=[
            GraphResponse(
                outcome=OperationOutcome.ACCEPTED, body={"message_id": "header"}
            ),
            GraphResponse(outcome=OperationOutcome.REJECTED, error_code="100/33"),
        ]
    )
    try:
        result = await ig.send_cta_message(
            "Open",
            "https://example.com",
            IG_DM,
            "Body",
            header=InteractiveHeader.of_image(url="https://example.com/header.jpg"),
        )
        accepted = [part for part in result.parts if part.outcome == "accepted"]
        assert len(accepted) == 1
        assert accepted[0].content.media.url == "https://example.com/header.jpg"
        assert accepted[0].content.buttons is None
        assert result.parts[1].content.buttons[0].title == "Open"
        assert result.parts[1].outcome == "rejected"
        assert result.aggregate_outcome.value == "partially_accepted"
    finally:
        await client.aclose()


@pytest.mark.parametrize("platform", ["whatsapp", "instagram"])
async def test_media_evidence_uses_the_selected_id_and_not_the_original_source(
    platform,
):
    ig, client, _ = _ig()
    wa, _ = _wa()
    try:
        messenger, target = (wa, WA_DM) if platform == "whatsapp" else (ig, IG_DM)
        result = await messenger.send_image("stored-media-id", target)
        media = result.parts[0].content.media
        assert media.type == "image" and media.id == "stored-media-id"
        assert media.url is None
    finally:
        await client.aclose()
