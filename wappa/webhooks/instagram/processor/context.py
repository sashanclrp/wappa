"""Pure value builders shared by the Instagram translation lanes."""

from __future__ import annotations

from datetime import UTC, datetime

from wappa.webhooks.core.webhook_interfaces.conversation_webhooks import (
    EntryPointKind,
    EntryReferral,
)
from wappa.webhooks.instagram.message_types import InstagramMessageContext
from wappa.webhooks.instagram.models import InstagramMessage, InstagramReferral


def native_timestamp(value: int | None) -> datetime:
    if not value:
        return datetime.now(UTC)
    # Messaging uses milliseconds; change entries commonly use seconds.
    seconds = value / 1000 if value > 10**11 else value
    return datetime.fromtimestamp(seconds, tz=UTC)


def entry_referral(native: InstagramReferral | None) -> EntryReferral | None:
    if native is None:
        return None
    ads = native.ads_context_data
    source = (native.source or "").upper()
    if native.ad_id or source == "ADS":
        kind = EntryPointKind.AD
    elif native.ref is not None or source in {"SHORTLINK", "IGME", "LINK"}:
        kind = EntryPointKind.LINK
    else:
        kind = EntryPointKind.OTHER
    return EntryReferral(
        kind=kind,
        source=native.source,
        ref=native.ref,
        ad_id=native.ad_id,
        post_id=ads.post_id if ads else None,
        product_id=ads.product_id if ads else None,
        headline=ads.ad_title if ads else None,
        image_url=ads.photo_url if ads else None,
        video_url=ads.video_url if ads else None,
    )


def message_context(message: InstagramMessage) -> InstagramMessageContext | None:
    reply = message.reply_to
    if reply is None:
        return None
    story = reply.story
    return InstagramMessageContext(
        reply_to_message_id=reply.mid,
        story_id=story.id if story else None,
        story_url=story.url if story else None,
    )
