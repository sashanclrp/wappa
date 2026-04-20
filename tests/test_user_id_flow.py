"""
Tests for v0.3.3 user_id field — outbound endpoints and status webhooks.

Covers:
  - RecipientRequest.user_id field presence and default (None)
  - APIMessageEvent.user_id populated from decorator with correct fallback
  - api_event_dispatcher context binding prefers user_id over recipient
  - StatusWebhook.user_id field populated from processor
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from wappa.domain.events.api_message_event import APIMessageEvent
from wappa.messaging.whatsapp.models.basic_models import BasicTextMessage
from wappa.schemas.core.recipient import RecipientRequest
from wappa.schemas.core.types import PlatformType
from wappa.webhooks.core.webhook_interfaces import StatusWebhook

# ──────────────────────────────────────────────
# RecipientRequest — base schema
# ──────────────────────────────────────────────


def test_recipient_request_user_id_defaults_to_none() -> None:
    req = RecipientRequest(recipient="+573001234567")
    assert req.user_id is None


def test_recipient_request_accepts_explicit_user_id() -> None:
    req = RecipientRequest(recipient="+573001234567", user_id="CO.13491208655302741918")
    assert req.user_id == "CO.13491208655302741918"


def test_basic_text_message_inherits_user_id() -> None:
    msg = BasicTextMessage(
        text="hello",
        recipient="+573001234567",
        user_id="CO.13491208655302741918",
    )
    assert msg.user_id == "CO.13491208655302741918"


def test_basic_text_message_user_id_optional() -> None:
    msg = BasicTextMessage(text="hello", recipient="+573001234567")
    assert msg.user_id is None


# ──────────────────────────────────────────────
# APIMessageEvent — user_id field
# ──────────────────────────────────────────────


def _make_event(recipient: str, user_id: str) -> APIMessageEvent:
    return APIMessageEvent(
        message_type="text",
        message_id="wamid.test",
        recipient=recipient,
        user_id=user_id,
        request_payload={"recipient": recipient, "text": "hi"},
        response_success=True,
        tenant_id="test-tenant",
        platform="whatsapp",
    )


def test_api_message_event_stores_user_id() -> None:
    event = _make_event("+573001234567", "+573001234567")
    assert event.user_id == "+573001234567"
    assert event.recipient == "+573001234567"


def test_api_message_event_user_id_distinct_from_recipient() -> None:
    event = _make_event("+573001234567", "CO.13491208655302741918")
    assert event.recipient == "+573001234567"
    assert event.user_id == "CO.13491208655302741918"


# ──────────────────────────────────────────────
# APIEventDispatcher — context binding
# ──────────────────────────────────────────────


def test_api_event_dispatcher_binds_user_id_when_distinct() -> None:
    from wappa.core.events.api_event_dispatcher import APIEventDispatcher

    handler = MagicMock()
    cloned = MagicMock()
    cloned.handle_api_message = AsyncMock()
    cloned.db = None
    handler.with_context.return_value = cloned

    dispatcher = APIEventDispatcher(handler)

    event = _make_event("+573001234567", "CO.13491208655302741918")

    import asyncio

    asyncio.get_event_loop().run_until_complete(dispatcher.dispatch(event))

    handler.with_context.assert_called_once()
    call_kwargs = handler.with_context.call_args.kwargs
    assert call_kwargs["user_id"] == "CO.13491208655302741918"


def test_api_event_dispatcher_falls_back_to_recipient_when_same() -> None:
    from wappa.core.events.api_event_dispatcher import APIEventDispatcher

    handler = MagicMock()
    cloned = MagicMock()
    cloned.handle_api_message = AsyncMock()
    cloned.db = None
    handler.with_context.return_value = cloned

    dispatcher = APIEventDispatcher(handler)
    event = _make_event("+573001234567", "+573001234567")

    import asyncio

    asyncio.get_event_loop().run_until_complete(dispatcher.dispatch(event))

    call_kwargs = handler.with_context.call_args.kwargs
    assert call_kwargs["user_id"] == "+573001234567"


# ──────────────────────────────────────────────
# StatusWebhook.user_id — inbound status
# ──────────────────────────────────────────────


def _make_tenant():
    from wappa.webhooks.core.webhook_interfaces import TenantBase

    return TenantBase(
        business_phone_number_id="12345",
        display_phone_number="+571234567",
        platform_tenant_id="12345",
    )


def test_status_webhook_user_id_set_to_bsuid_when_present() -> None:
    status = StatusWebhook(
        tenant=_make_tenant(),
        message_id="wamid.abc",
        status="delivered",
        recipient_phone_id="+573001234567",
        recipient_bsuid="CO.13491208655302741918",
        user_id="CO.13491208655302741918",
        timestamp=datetime.now(UTC),
        platform=PlatformType.WHATSAPP,
        webhook_id="evt-001",
    )
    assert status.user_id == "CO.13491208655302741918"
    assert status.recipient_phone_id == "+573001234567"


def test_status_webhook_user_id_falls_back_to_phone_when_no_bsuid() -> None:
    status = StatusWebhook(
        tenant=_make_tenant(),
        message_id="wamid.abc",
        status="read",
        recipient_phone_id="+573001234567",
        recipient_bsuid=None,
        user_id="+573001234567",
        timestamp=datetime.now(UTC),
        platform=PlatformType.WHATSAPP,
        webhook_id="evt-002",
    )
    assert status.user_id == "+573001234567"


def test_status_webhook_user_id_can_be_overridden_after_enrichment() -> None:
    """Simulate controller enriching user_id after phone→BSUID lookup."""
    status = StatusWebhook(
        tenant=_make_tenant(),
        message_id="wamid.abc",
        status="sent",
        recipient_phone_id="+573001234567",
        recipient_bsuid=None,
        user_id="+573001234567",
        timestamp=datetime.now(UTC),
        platform=PlatformType.WHATSAPP,
        webhook_id="evt-003",
    )

    # Simulate enrichment
    status.user_id = "CO.13491208655302741918"

    assert status.user_id == "CO.13491208655302741918"
    assert status.recipient_phone_id == "+573001234567"


def test_status_webhook_user_id_none_when_no_identifiers() -> None:
    """No phone and no BSUID — user_id stays None."""
    status = StatusWebhook(
        tenant=_make_tenant(),
        message_id="wamid.abc",
        status="failed",
        recipient_phone_id="",
        recipient_bsuid=None,
        user_id=None,
        timestamp=datetime.now(UTC),
        platform=PlatformType.WHATSAPP,
        webhook_id="evt-004",
    )
    assert status.user_id is None
