from __future__ import annotations

import importlib
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import BaseModel

from wappa.core.events.field_registry import FieldHandlerRegistry
from wappa.processors.base_processor import ProcessorError
from wappa.processors.whatsapp_processor import WhatsAppWebhookProcessor
from wappa.schemas.core.types import MessageType, PlatformType
from wappa.webhooks.core.base_message import BaseMessage, BaseMessageContext
from wappa.webhooks.core.webhook_interfaces import (
    CustomWebhook,
    ErrorWebhook,
    InboundMessageWebhook,
    InboxBase,
    StatusWebhook,
    SystemEventType,
    SystemWebhook,
    UserBase,
)


def _metadata() -> dict[str, str]:
    return {
        "display_phone_number": "573232821994",
        "phone_number_id": "508386009032748",
    }


def _payload(field: str, value: dict[str, Any]) -> dict[str, Any]:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "535497026314662",
                "changes": [{"field": field, "value": value}],
            }
        ],
    }


def test_schemas_package_exposes_only_shared_primitives() -> None:
    assert importlib.import_module("wappa.schemas.core.types")
    assert importlib.import_module("wappa.schemas.core.recipient")

    removed_modules = [
        "wappa.schemas.factory",
        "wappa.schemas.core.base_message",
        "wappa.schemas.core.base_status",
        "wappa.schemas.core.base_webhook",
        "wappa.schemas.whatsapp.base_models",
        "wappa.schemas.whatsapp.webhook_container",
        "wappa.schemas.whatsapp.status_models",
        "wappa.schemas.whatsapp.message_types.text",
        "wappa.schemas.whatsapp.message_types.interactive",
    ]

    for module_name in removed_modules:
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(module_name)


@pytest.mark.asyncio
async def test_whatsapp_message_payload_parses_to_pydantic_universal_model() -> None:
    processor = WhatsAppWebhookProcessor()
    webhook = await processor.create_universal_webhook(
        _payload(
            "messages",
            {
                "messaging_product": "whatsapp",
                "metadata": _metadata(),
                "contacts": [
                    {
                        "profile": {"name": "Sasha Nicolai Canal"},
                        "wa_id": "573168227670",
                        "user_id": "CO.2186878922080769",
                    }
                ],
                "messages": [
                    {
                        "from": "573168227670",
                        "from_user_id": "CO.2186878922080769",
                        "id": "wamid.test-message-001",
                        "timestamp": "1776696189",
                        "text": {"body": "Hola"},
                        "type": "text",
                    }
                ],
            },
        )
    )

    assert isinstance(webhook, InboundMessageWebhook)
    assert isinstance(webhook, BaseModel)
    assert webhook.user.user_id == "CO.2186878922080769"
    assert webhook.message.message_type == MessageType.TEXT


@pytest.mark.asyncio
async def test_whatsapp_status_payload_parses_to_pydantic_universal_model() -> None:
    processor = WhatsAppWebhookProcessor()
    webhook = await processor.create_universal_webhook(
        _payload(
            "messages",
            {
                "messaging_product": "whatsapp",
                "metadata": _metadata(),
                "statuses": [
                    {
                        "id": "wamid.test-status-001",
                        "status": "delivered",
                        "timestamp": "1776696189",
                        "recipient_id": "573168227670",
                        "recipient_user_id": "CO.2186878922080769",
                    }
                ],
            },
        )
    )

    assert isinstance(webhook, StatusWebhook)
    assert isinstance(webhook, BaseModel)
    assert webhook.user_id == "CO.2186878922080769"
    assert webhook.recipient_phone_id == "573168227670"


@pytest.mark.asyncio
async def test_whatsapp_error_payload_parses_to_pydantic_universal_model() -> None:
    processor = WhatsAppWebhookProcessor()
    webhook = await processor.create_universal_webhook(
        _payload(
            "messages",
            {
                "messaging_product": "whatsapp",
                "metadata": _metadata(),
                "errors": [
                    {
                        "code": 131000,
                        "title": "Temporary service issue",
                        "message": "The platform could not process the webhook.",
                        "error_data": {"details": "Retry later."},
                    }
                ],
            },
        )
    )

    assert isinstance(webhook, ErrorWebhook)
    assert isinstance(webhook, BaseModel)
    assert webhook.get_primary_error().error_code == 131000


@pytest.mark.asyncio
async def test_whatsapp_system_payload_parses_to_pydantic_universal_model() -> None:
    processor = WhatsAppWebhookProcessor()
    webhook = await processor.create_universal_webhook(
        _payload(
            "user_preferences",
            {
                "messaging_product": "whatsapp",
                "metadata": _metadata(),
                "user_preferences": [
                    {
                        "wa_id": "573168227670",
                        "user_id": "CO.2186878922080769",
                        "detail": "User opted in to marketing messages.",
                        "category": "marketing_messages",
                        "value": "opt-in",
                        "timestamp": 1776696189,
                    }
                ],
            },
        )
    )

    assert isinstance(webhook, SystemWebhook)
    assert isinstance(webhook, BaseModel)
    assert webhook.event_detail.user_id == "CO.2186878922080769"


@pytest.mark.asyncio
async def test_whatsapp_custom_field_payload_parses_to_pydantic_universal_model() -> (
    None
):
    class TemplateStatusUpdate(BaseModel):
        event: str
        message_template_id: str

    async def handler(webhook: CustomWebhook) -> None:
        assert webhook.field_name == "message_template_status_update"

    registry = FieldHandlerRegistry()
    registry.register(
        "message_template_status_update",
        parser=TemplateStatusUpdate,
        handler=handler,
    )

    processor = WhatsAppWebhookProcessor()
    processor.set_field_registry(registry)
    webhook = await processor.create_universal_webhook(
        _payload(
            "message_template_status_update",
            {
                "event": "APPROVED",
                "message_template_id": "template-123",
            },
        ),
        inbox_id="508386009032748",
    )

    assert isinstance(webhook, CustomWebhook)
    assert isinstance(webhook, BaseModel)
    assert isinstance(webhook.parsed, TemplateStatusUpdate)


class FakePlatformTextMessage(BaseMessage):
    id: str
    sender: str
    sent_at: int
    text: str
    conversation: str

    @property
    def platform(self) -> PlatformType:
        return PlatformType.TELEGRAM

    @property
    def message_type(self) -> MessageType:
        return MessageType.TEXT

    @property
    def message_id(self) -> str:
        return self.id

    @property
    def sender_id(self) -> str:
        return self.sender

    @property
    def timestamp(self) -> int:
        return self.sent_at

    @property
    def conversation_id(self) -> str:
        return self.conversation

    def has_context(self) -> bool:
        return False

    def get_context(self) -> BaseMessageContext | None:
        return None

    def to_universal_dict(self) -> dict[str, str | int | bool | None | dict | list]:
        return {
            "id": self.message_id,
            "type": self.message_type.value,
            "sender": self.sender_id,
            "text": self.text,
        }

    def get_platform_data(self) -> dict[str, Any]:
        return {"source": "fake-platform"}

    @classmethod
    def from_platform_data(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> FakePlatformTextMessage:
        return cls(
            id=data["event_id"],
            sender=data["chat"]["user_id"],
            sent_at=data["timestamp"],
            text=data["body"]["text"],
            conversation=data["chat"]["id"],
        )


def test_future_platform_payload_can_map_to_same_universal_model_shape() -> None:
    payload: dict[str, Any] = {
        "event_id": "future-event-001",
        "bot_id": "telegram-bot-123",
        "account_id": "telegram-account-456",
        "chat": {"id": "chat-789", "user_id": "telegram-user-001"},
        "timestamp": 1776696189,
        "body": {"text": "Hola desde otro platform"},
    }
    chat = payload["chat"]
    body = payload["body"]
    assert isinstance(chat, dict)
    assert isinstance(body, dict)

    universal = InboundMessageWebhook(
        inbox=InboxBase(
            inbox_id=str(payload["bot_id"]),
            display_address="@wappa_bot",
            platform_account_id=str(payload["account_id"]),
        ),
        user=UserBase(phone_number="", username=str(chat["user_id"])),
        message=FakePlatformTextMessage.from_platform_data(payload),
        timestamp=datetime.fromtimestamp(int(payload["timestamp"]), tz=UTC),
        platform=PlatformType.TELEGRAM,
        webhook_id=str(payload["event_id"]),
    )

    assert isinstance(universal, BaseModel)
    assert universal.platform == PlatformType.TELEGRAM
    assert universal.message.message_type == MessageType.TEXT
    assert universal.get_message_text() == ""
    assert universal.inbox.inbox_id == "telegram-bot-123"


@pytest.mark.asyncio
async def test_whatsapp_account_offboarded_parses_to_system_webhook() -> None:
    """Coexistence account_offboarded → SystemWebhook (WABA-scoped, no user)."""
    processor = WhatsAppWebhookProcessor()
    webhook = await processor.create_universal_webhook(
        _payload(
            "account_offboarded",
            {
                "waba_id": "2068060904064070",
                "reason": "USER_INITIATED",
                "timestamp": 1655913600,
            },
        )
    )

    assert isinstance(webhook, SystemWebhook)
    assert webhook.system_event_type == SystemEventType.ACCOUNT_OFFBOARDED
    assert webhook.event_detail.waba_id == "2068060904064070"
    assert webhook.event_detail.reason == "USER_INITIATED"
    # Account event has no user context.
    assert webhook.user is None


@pytest.mark.asyncio
async def test_whatsapp_account_reconnected_parses_to_system_webhook() -> None:
    """Coexistence account_reconnected → SystemWebhook with phone_number_id."""
    processor = WhatsAppWebhookProcessor()
    webhook = await processor.create_universal_webhook(
        _payload(
            "account_reconnected",
            {
                "waba_id": "2068060904064070",
                "phone_number_id": "123456789012345",
                "timestamp": 1655914000,
            },
        )
    )

    assert isinstance(webhook, SystemWebhook)
    assert webhook.system_event_type == SystemEventType.ACCOUNT_RECONNECTED
    assert webhook.event_detail.waba_id == "2068060904064070"
    assert webhook.event_detail.phone_number_id == "123456789012345"
    assert webhook.user is None


@pytest.mark.asyncio
async def test_account_event_value_is_strictly_validated() -> None:
    """A malformed account payload (missing required waba_id) is rejected.

    Account events route through the strict ``AccountWebhookValue`` model, so a
    missing required field surfaces as a validation error at parse time rather
    than slipping through a permissive container.
    """
    processor = WhatsAppWebhookProcessor()
    with pytest.raises(ProcessorError):
        await processor.create_universal_webhook(
            _payload(
                "account_offboarded",
                {"reason": "USER_INITIATED", "timestamp": 1655913600},
            )
        )
