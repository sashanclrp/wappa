from unittest.mock import AsyncMock

import pytest

from wappa.core.events.event_dispatcher import WappaEventDispatcher
from wappa.messaging.whatsapp.handlers.whatsapp_interactive_handler import (
    WhatsAppInteractiveHandler,
)
from wappa.processors.whatsapp_processor import WhatsAppWebhookProcessor
from wappa.webhooks.core.webhook_interfaces import (
    CallWebhook,
    InboundMessageWebhook,
    SystemEventType,
    SystemWebhook,
)
from wappa.webhooks.whatsapp.message_types.contact import WhatsAppContactMessage
from wappa.webhooks.whatsapp.message_types.interactive import (
    WhatsAppInteractiveMessage,
)


def _payload(value: dict) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "535497026314662",
                "changes": [{"field": "messages", "value": value}],
            }
        ],
    }


def _metadata() -> dict[str, str]:
    return {
        "display_phone_number": "573232821994",
        "phone_number_id": "508386009032748",
    }


@pytest.mark.asyncio
async def test_contact_request_webhook_accepts_origin_and_vcard_without_name() -> None:
    webhook = await WhatsAppWebhookProcessor().create_universal_webhook(
        _payload(
            {
                "messaging_product": "whatsapp",
                "metadata": _metadata(),
                "contacts": [
                    {
                        "profile": {
                            "name": "Sasha Nicolai Canal",
                            "username": "sashanicolai",
                        },
                        "user_id": "CO.2186878922080769",
                    }
                ],
                "messages": [
                    {
                        "from_user_id": "CO.2186878922080769",
                        "id": "wamid.contact-request-001",
                        "timestamp": "1776696189",
                        "type": "contacts",
                        "contacts": [
                            {
                                "vcard": "BEGIN:VCARD\nTEL:+573001112233\nEND:VCARD",
                                "origin": "other",
                                "phones": [
                                    {
                                        "phone": "+573001112233",
                                        "wa_id": "573001112233",
                                        "type": "CELL",
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        )
    )

    assert isinstance(webhook.message, WhatsAppContactMessage)
    assert webhook.message.contacts[0].origin == "other"
    assert webhook.message.contacts[0].vcard is not None
    assert webhook.message.contact_phone == "+573001112233"


@pytest.mark.asyncio
async def test_system_user_id_change_accepts_meta_and_parent_bsuids() -> None:
    webhook = await WhatsAppWebhookProcessor().create_universal_webhook(
        _payload(
            {
                "messaging_product": "whatsapp",
                "metadata": _metadata(),
                "messages": [
                    {
                        "from_user_id": "CO.1057044516887193",
                        "from_parent_user_id": "CO.ENT.1057044516887193",
                        "id": "wamid.user-id-change-001",
                        "timestamp": "1776696189",
                        "type": "system",
                        "system": {
                            "body": "User Sasha changed to a new business-scoped ID",
                            "user_id": "CO.2057044516887193",
                            "parent_user_id": "CO.ENT.2057044516887193",
                            "type": "user_changed_user_id",
                        },
                    }
                ],
            }
        )
    )

    assert isinstance(webhook, SystemWebhook)
    assert webhook.system_event_type == SystemEventType.USER_ID_CHANGE
    assert webhook.event_detail.user_id == "CO.2057044516887193"
    assert webhook.event_detail.parent_user_id == "CO.ENT.2057044516887193"


@pytest.mark.asyncio
async def test_contact_request_send_uses_bsuid_recipient_payload() -> None:
    client = AsyncMock()
    client.post_request.return_value = {
        "messaging_product": "whatsapp",
        "contacts": [
            {
                "input": "CO.2186878922080769",
                "user_id": "CO.2186878922080769",
            }
        ],
        "messages": [{"id": "wamid.contact-request-send-001"}],
    }
    handler = WhatsAppInteractiveHandler(client=client, inbox_id="508386009032748")

    result = await handler.send_contact_request(
        recipient="CO.2186878922080769",
        body="Share your phone number",
    )

    assert result.success is True
    client.post_request.assert_awaited_once_with(
        {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "recipient": "CO.2186878922080769",
            "type": "interactive",
            "interactive": {
                "type": "request_contact_info",
                "body": {"text": "Share your phone number"},
                "action": {"name": "request_contact_info"},
            },
        }
    )


@pytest.mark.asyncio
async def test_call_permission_reply_accepts_username_only_user() -> None:
    webhook = await WhatsAppWebhookProcessor().create_universal_webhook(
        _payload(
            {
                "messaging_product": "whatsapp",
                "metadata": _metadata(),
                "contacts": [
                    {
                        "profile": {
                            "name": "Sasha Nicolai Canal",
                            "username": "sashanicolai",
                        },
                        "user_id": "CO.2186878922080769",
                        "parent_user_id": "CO.ENT.2186878922080769",
                    }
                ],
                "messages": [
                    {
                        "context": {
                            "from": "573232821994",
                            "id": "wamid.call-permission-request-001",
                        },
                        "from_user_id": "CO.2186878922080769",
                        "from_parent_user_id": "CO.ENT.2186878922080769",
                        "id": "wamid.call-permission-reply-001",
                        "timestamp": "1776696189",
                        "type": "interactive",
                        "interactive": {
                            "type": "call_permission_reply",
                            "call_permission_reply": {
                                "response": "accept",
                                "expiration_timestamp": "1776699789",
                                "response_source": "user_action",
                            },
                        },
                    }
                ],
            }
        )
    )

    assert isinstance(webhook.message, WhatsAppInteractiveMessage)
    assert webhook.message.is_call_permission_reply is True
    assert webhook.message.selected_option_id == "accept"


@pytest.mark.asyncio
async def test_business_username_update_is_a_native_system_event() -> None:
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "535497026314662",
                "time": 1776696189,
                "changes": [
                    {
                        "field": "business_username_updates",
                        "value": {
                            "display_phone_number": "573232821994",
                            "username": "wappa_support",
                            "status": "approved",
                        },
                    }
                ],
            }
        ],
    }

    webhook = await WhatsAppWebhookProcessor().create_universal_webhook(
        payload, inbox_id="508386009032748"
    )

    assert isinstance(webhook, SystemWebhook)
    assert webhook.system_event_type == SystemEventType.BUSINESS_USERNAME_UPDATE
    assert webhook.user is None
    assert webhook.event_detail.username == "wappa_support"
    assert webhook.event_detail.username_status == "approved"
    assert int(webhook.timestamp.timestamp()) == 1776696189


@pytest.mark.asyncio
async def test_group_participant_update_preserves_bsuid_without_phone() -> None:
    webhook = await WhatsAppWebhookProcessor().create_universal_webhook(
        {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "535497026314662",
                    "changes": [
                        {
                            "field": "group_participants_update",
                            "value": {
                                "messaging_product": "whatsapp",
                                "metadata": _metadata(),
                                "groups": [
                                    {
                                        "timestamp": 1776696189,
                                        "group_id": "120363001234567890@g.us",
                                        "type": "group_participants_add",
                                        "reason": "invite_link",
                                        "added_participants": [
                                            {
                                                "user_id": "CO.2186878922080769",
                                                "parent_user_id": (
                                                    "CO.ENT.2186878922080769"
                                                ),
                                                "username": "sashanicolai",
                                            }
                                        ],
                                    }
                                ],
                            },
                        }
                    ],
                }
            ],
        }
    )

    assert isinstance(webhook, SystemWebhook)
    assert webhook.system_event_type == SystemEventType.GROUP_PARTICIPANTS_UPDATE
    assert webhook.event_detail.group_id == "120363001234567890@g.us"
    assert webhook.user is not None
    assert webhook.user.user_id == "CO.2186878922080769"
    assert webhook.user.parent_bsuid == "CO.ENT.2186878922080769"


@pytest.mark.asyncio
async def test_business_initiated_call_uses_to_bsuid_without_phone() -> None:
    webhook = await WhatsAppWebhookProcessor().create_universal_webhook(
        {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "535497026314662",
                    "changes": [
                        {
                            "field": "calls",
                            "value": {
                                "messaging_product": "whatsapp",
                                "metadata": _metadata(),
                                "contacts": [
                                    {
                                        "profile": {"username": "sashanicolai"},
                                        "user_id": "CO.2186878922080769",
                                        "parent_user_id": ("CO.ENT.2186878922080769"),
                                    }
                                ],
                                "calls": [
                                    {
                                        "id": "wacid.business-connect-001",
                                        "event": "connect",
                                        "timestamp": "1776696189",
                                        "direction": "BUSINESS_INITIATED",
                                        "from": "573232821994",
                                        "to_user_id": "CO.2186878922080769",
                                        "to_parent_user_id": (
                                            "CO.ENT.2186878922080769"
                                        ),
                                        "session": {
                                            "sdp_type": "answer",
                                            "sdp": "v=0",
                                        },
                                    }
                                ],
                            },
                        }
                    ],
                }
            ],
        }
    )

    assert isinstance(webhook, CallWebhook)
    assert webhook.user_id == "CO.2186878922080769"
    assert webhook.phone_number is None
    assert webhook.parent_bsuid == "CO.ENT.2186878922080769"
    assert webhook.event == "connect"

    handler = AsyncMock()
    handler.inbox_id = "508386009032748"
    handler.handle_call = AsyncMock()
    result = await WappaEventDispatcher(handler).dispatch_universal_webhook(webhook)

    assert result["success"] is True
    assert result["action"] == "call_processed"
    handler.handle_call.assert_awaited_once_with(webhook)


@pytest.mark.asyncio
async def test_history_sync_preserves_thread_identity_companions() -> None:
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "535497026314662",
                "changes": [
                    {
                        "field": "history",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": _metadata(),
                            "history": [
                                {
                                    "metadata": {
                                        "phase": 1,
                                        "chunk_order": 2,
                                        "progress": 50,
                                    },
                                    "threads": [
                                        {
                                            "context": {
                                                "user_id": "CO.2186878922080769",
                                                "parent_user_id": (
                                                    "CO.ENT.2186878922080769"
                                                ),
                                                "username": "sashanicolai",
                                            },
                                            "messages": [
                                                {
                                                    "from_user_id": (
                                                        "CO.2186878922080769"
                                                    ),
                                                    "from_parent_user_id": (
                                                        "CO.ENT.2186878922080769"
                                                    ),
                                                    "to": "573232821994",
                                                    "id": "wamid.history-001",
                                                    "timestamp": "1776696189",
                                                    "type": "text",
                                                    "text": {"body": "hello"},
                                                    "history_context": {
                                                        "status": "read"
                                                    },
                                                }
                                            ],
                                        }
                                    ],
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }

    webhook = await WhatsAppWebhookProcessor().create_universal_webhook(payload)

    assert isinstance(webhook, SystemWebhook)
    assert webhook.system_event_type == SystemEventType.HISTORY_SYNC
    history = webhook.event_detail.coexistence_payload["history"][0]
    assert history["threads"][0]["context"]["user_id"] == "CO.2186878922080769"
    assert (
        history["threads"][0]["messages"][0]["from_parent_user_id"]
        == "CO.ENT.2186878922080769"
    )


@pytest.mark.asyncio
async def test_smb_echo_and_app_state_sync_accept_username_only_user() -> None:
    processor = WhatsAppWebhookProcessor()
    echo_payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "535497026314662",
                "changes": [
                    {
                        "field": "smb_message_echoes",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": _metadata(),
                            "contacts": [
                                {
                                    "profile": {"username": "sashanicolai"},
                                    "user_id": "CO.2186878922080769",
                                    "parent_user_id": "CO.ENT.2186878922080769",
                                }
                            ],
                            "message_echoes": [
                                {
                                    "from": "573232821994",
                                    "to_user_id": "CO.2186878922080769",
                                    "to_parent_user_id": ("CO.ENT.2186878922080769"),
                                    "id": "wamid.echo-001",
                                    "timestamp": "1776696189",
                                    "type": "revoke",
                                    "revoke": {
                                        "original_message_id": "wamid.original-001"
                                    },
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }
    echo = await processor.create_universal_webhook(echo_payload)

    assert isinstance(echo, SystemWebhook)
    assert echo.system_event_type == SystemEventType.SMB_MESSAGE_ECHO
    assert echo.user is not None
    assert echo.user.user_id == "CO.2186878922080769"
    assert (
        echo.event_detail.coexistence_payload["message_echoes"][0]["to_parent_user_id"]
        == "CO.ENT.2186878922080769"
    )

    app_state_payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "535497026314662",
                "changes": [
                    {
                        "field": "smb_app_state_sync",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": _metadata(),
                            "state_sync": [
                                {
                                    "type": "contact",
                                    "contact": {
                                        "full_name": "Sasha Nicolai Canal",
                                        "first_name": "Sasha",
                                        "user_id": "CO.2186878922080769",
                                        "parent_user_id": ("CO.ENT.2186878922080769"),
                                        "username": "sashanicolai",
                                    },
                                    "action": "add",
                                    "metadata": {"timestamp": "1776696189"},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }
    app_state = await processor.create_universal_webhook(app_state_payload)

    assert isinstance(app_state, SystemWebhook)
    assert app_state.system_event_type == SystemEventType.SMB_APP_STATE_SYNC
    assert app_state.user is not None
    assert app_state.user.phone_number == ""
    assert app_state.user.bsuid == "CO.2186878922080769"


@pytest.mark.asyncio
@pytest.mark.parametrize("message_type", ["edit", "revoke"])
async def test_consumer_lifecycle_messages_preserve_bsuid(
    message_type: str,
) -> None:
    content = (
        {
            "original_message_id": "wamid.original-001",
            "message": {
                "context": {"id": "wamid.context-001"},
                "type": "image",
                "image": {"id": "media-001", "caption": "updated"},
            },
        }
        if message_type == "edit"
        else {"original_message_id": "wamid.original-001"}
    )
    webhook = await WhatsAppWebhookProcessor().create_universal_webhook(
        _payload(
            {
                "messaging_product": "whatsapp",
                "metadata": _metadata(),
                "contacts": [
                    {
                        "profile": {"username": "sashanicolai"},
                        "user_id": "CO.2186878922080769",
                        "parent_user_id": "CO.ENT.2186878922080769",
                    }
                ],
                "messages": [
                    {
                        "from_user_id": "CO.2186878922080769",
                        "from_parent_user_id": "CO.ENT.2186878922080769",
                        "id": f"wamid.{message_type}-001",
                        "timestamp": "1776696189",
                        "type": message_type,
                        message_type: content,
                    }
                ],
            }
        )
    )

    assert isinstance(webhook, InboundMessageWebhook)
    assert webhook.message.message_type.value == message_type
    assert webhook.message.sender_id == "CO.2186878922080769"
    assert webhook.message.get_context().original_message_id == "wamid.original-001"


@pytest.mark.asyncio
async def test_call_status_accepts_recipient_bsuid_without_phone() -> None:
    webhook = await WhatsAppWebhookProcessor().create_universal_webhook(
        {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "535497026314662",
                    "changes": [
                        {
                            "field": "calls",
                            "value": {
                                "messaging_product": "whatsapp",
                                "metadata": _metadata(),
                                "statuses": [
                                    {
                                        "id": "wacid.status-001",
                                        "type": "call",
                                        "status": "RINGING",
                                        "timestamp": "1776696189",
                                        "recipient_user_id": "CO.2186878922080769",
                                        "recipient_parent_user_id": (
                                            "CO.ENT.2186878922080769"
                                        ),
                                    }
                                ],
                            },
                        }
                    ],
                }
            ],
        }
    )

    assert isinstance(webhook, CallWebhook)
    assert webhook.event == "status"
    assert webhook.status == "RINGING"
    assert webhook.user_id == "CO.2186878922080769"


@pytest.mark.asyncio
async def test_user_preferences_preserves_parent_bsuid_without_phone() -> None:
    webhook = await WhatsAppWebhookProcessor().create_universal_webhook(
        {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "535497026314662",
                    "changes": [
                        {
                            "field": "user_preferences",
                            "value": {
                                "messaging_product": "whatsapp",
                                "metadata": _metadata(),
                                "contacts": [
                                    {
                                        "profile": {"username": "sashanicolai"},
                                        "user_id": "CO.2186878922080769",
                                        "parent_user_id": ("CO.ENT.2186878922080769"),
                                    }
                                ],
                                "user_preferences": [
                                    {
                                        "user_id": "CO.2186878922080769",
                                        "parent_user_id": ("CO.ENT.2186878922080769"),
                                        "detail": "Marketing messages disabled",
                                        "category": "marketing_messages",
                                        "value": "stop",
                                        "timestamp": 1776696189,
                                    }
                                ],
                            },
                        }
                    ],
                }
            ],
        }
    )

    assert isinstance(webhook, SystemWebhook)
    assert webhook.system_event_type == SystemEventType.MARKETING_PREFERENCE
    assert webhook.event_detail.user_id == "CO.2186878922080769"
    assert webhook.event_detail.parent_user_id == "CO.ENT.2186878922080769"
    assert webhook.user is not None
    assert webhook.user.phone_number == ""


@pytest.mark.asyncio
async def test_user_id_update_accepts_missing_phone_and_parent_transition() -> None:
    webhook = await WhatsAppWebhookProcessor().create_universal_webhook(
        {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "535497026314662",
                    "changes": [
                        {
                            "field": "user_id_update",
                            "value": {
                                "messaging_product": "whatsapp",
                                "metadata": _metadata(),
                                "contacts": [{"profile": {"username": "sashanicolai"}}],
                                "user_id_update": [
                                    {
                                        "detail": "User id has been updated.",
                                        "user_id": {
                                            "previous": "CO.1186878922080769",
                                            "current": "CO.2186878922080769",
                                        },
                                        "parent_user_id": {
                                            "previous": "CO.ENT.1186878922080769",
                                            "current": "CO.ENT.2186878922080769",
                                        },
                                        "timestamp": "1776696189",
                                    }
                                ],
                            },
                        }
                    ],
                }
            ],
        }
    )

    assert isinstance(webhook, SystemWebhook)
    assert webhook.event_detail.previous_user_id == "CO.1186878922080769"
    assert webhook.event_detail.current_user_id == "CO.2186878922080769"
    assert webhook.event_detail.current_parent_user_id == "CO.ENT.2186878922080769"
