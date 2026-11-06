"""Platform scope is never assumed to be WhatsApp (0.34 audit regressions)."""

from __future__ import annotations

from typing import Any

import pytest

from wappa.core.expiry import parse_expiry_notification
from wappa.domain.inbox.identity import InboxRef
from wappa.persistence.redis.pubsub_subscriber import build_channel, build_pattern
from wappa.schemas.core.types import PlatformType

IG = InboxRef(platform=PlatformType.INSTAGRAM, inbox_id="17841457247424017")
WA = InboxRef.whatsapp("1014417365082534")


@pytest.mark.parametrize("inbox", [IG, WA])
def test_expiry_keys_parse_back_to_their_own_platform(inbox: InboxRef) -> None:
    """The key carries a qualified namespace, on every Platform."""
    key = f"{inbox.cache_namespace}:EXPTRIGGER:reminder:USER1"

    notification = parse_expiry_notification({"type": "message", "data": key})

    assert notification is not None
    assert notification.inbox_ref == inbox


def test_pubsub_channels_take_the_platform_from_an_inbox_ref() -> None:
    assert "instagram__17841457247424017" in build_channel(IG, "u", "bot_reply")
    assert "instagram__17841457247424017" in build_pattern(IG)
    assert "whatsapp__1014417365082534" in build_pattern(WA)


async def test_api_notifications_publish_on_the_event_platform(monkeypatch) -> None:
    from wappa.core.pubsub import handlers
    from wappa.domain.events.api_message_event import APIMessageEvent

    published: list[dict[str, Any]] = []

    async def fake_publish(**kwargs: Any) -> int:
        published.append(kwargs)
        return 1

    monkeypatch.setattr(handlers, "publish_notification", fake_publish)
    event = APIMessageEvent.model_construct(
        inbox_id=IG.inbox_id,
        user_id="u1",
        recipient="u1",
        platform="instagram",
        message_id="mid.1",
        message_type="text",
        response_success=True,
        request_payload={},
    )

    await handlers.publish_api_notification(event)

    assert published[0]["platform"] == "instagram"


def test_evict_inbox_targets_the_given_platform() -> None:
    from wappa.messaging.outbound_runtime import OutboundRuntime

    evicted: list[InboxRef] = []
    runtime = OutboundRuntime.__new__(OutboundRuntime)
    runtime._messenger_factory = type(  # type: ignore[attr-defined]
        "F", (), {"evict": lambda self, ref: evicted.append(ref)}
    )()

    runtime.evict_inbox(IG)
    runtime.evict_inbox(WA)

    assert evicted == [IG, WA]
