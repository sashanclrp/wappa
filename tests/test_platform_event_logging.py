"""Default logs use shared identity and omit absent Platform-specific evidence."""

from datetime import UTC, datetime
from unittest.mock import Mock

import pytest

from wappa.core.events.default_handlers import (
    DefaultStatusHandler,
    DefaultSystemHandler,
)
from wappa.schemas.core.types import MessageStatus, PlatformType
from wappa.webhooks import StatusWebhook, SystemEventType, SystemWebhook
from wappa.webhooks.core.webhook_interfaces.base_components import (
    InboxBase,
    SystemEventDetail,
    UserBase,
)


def inbox():
    return InboxBase(
        inbox_id="account-1", platform_account_id="account-1", display_address=None
    )


@pytest.mark.parametrize(
    ("platform", "user", "detail", "expected_user"),
    [
        (
            PlatformType.INSTAGRAM,
            UserBase(platform_user_id="ig-sender"),
            SystemEventDetail(),
            "ig-sender",
        ),
        (
            PlatformType.WHATSAPP,
            UserBase(bsuid="CO.sender"),
            SystemEventDetail(wa_id="573001112233"),
            "CO.sender",
        ),
        (
            PlatformType.WHATSAPP,
            None,
            SystemEventDetail(user_id="CO.sender"),
            "CO.sender",
        ),
        (
            PlatformType.WHATSAPP,
            None,
            SystemEventDetail(wa_id="573001112233"),
            "573001112233",
        ),
        (PlatformType.WHATSAPP, None, SystemEventDetail(waba_id="account-1"), None),
    ],
)
async def test_system_logging_uses_available_identity_without_empty_wa_fields(
    platform, user, detail, expected_user
):
    webhook = SystemWebhook(
        inbox=inbox(),
        user=user,
        event_detail=detail,
        system_event_type=SystemEventType.UNSUPPORTED_EVENT
        if platform is PlatformType.INSTAGRAM
        else SystemEventType.BUSINESS_USERNAME_UPDATE,
        platform=platform,
        timestamp=datetime.now(UTC),
        webhook_id="event-1",
    )
    handler = DefaultSystemHandler()
    handler.logger = Mock()
    result = await handler.handle_system(webhook)
    message = handler.logger.info.call_args.args[0]
    assert f"platform: {platform.value}" in message
    assert "inbox: account-1" in message
    assert (
        "None" not in message and "wa_id:" not in message and "user_id:" not in message
    )
    if expected_user:
        assert f"user: {expected_user}" in message
    else:
        assert "user:" not in message
    assert result["success"] is True


def test_instagram_status_logs_native_message_and_recipient_without_phone_evidence():
    webhook = StatusWebhook(
        inbox=inbox(),
        message_id="ig-message",
        status=MessageStatus.READ,
        recipient_platform_id="ig-sender",
        user_id="ig-sender",
        platform=PlatformType.INSTAGRAM,
        timestamp=datetime.now(UTC),
        webhook_id="read-1",
    )
    message = DefaultStatusHandler()._format_status_message(webhook)
    assert "platform: instagram" in message
    assert "message: ig-message" in message
    assert "recipient: ig-sender" in message
    assert "None" not in message
    assert webhook.recipient_phone_id == ""
