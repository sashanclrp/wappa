"""Contract tests for Meta's ``user_actions`` webhook payload.

Meta delivers user interaction events (marketing message link clicks) on the
``messages`` field, in a ``value`` that carries neither ``messages`` nor
``contacts``. Before these were modeled, ``WebhookValue``'s ``extra="forbid"``
turned every such delivery into a 400, which Meta retries and eventually
penalises the webhook for.
"""

import pytest

from wappa.processors.whatsapp_processor import WhatsAppWebhookProcessor
from wappa.schemas.core.types import WebhookType
from wappa.webhooks.core.webhook_interfaces import SystemEventType, SystemWebhook
from wappa.webhooks.whatsapp.webhook_container import WhatsAppWebhook


def _payload(user_actions: list[dict]) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "535497026314662",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "573232821994",
                                "phone_number_id": "508386009032748",
                            },
                            "user_actions": user_actions,
                        },
                    }
                ],
            }
        ],
    }


_LINK_CLICK = {
    "action_type": "marketing_messages_link_click",
    "timestamp": "1753000000",
    "marketing_messages_link_click_data": {
        "click_component": "cta",
        "product_id": "sku_id",
        "click_id": "click_id",
        "tracking_token": "example_token",
    },
}


def test_documented_link_click_parses_as_a_system_event() -> None:
    webhook = WhatsAppWebhook.model_validate(_payload([_LINK_CLICK]))

    assert webhook.is_user_action is True
    assert webhook.is_system_event is True
    assert webhook.is_incoming_message is False
    assert webhook.webhook_type is WebhookType.SYSTEM_EVENTS

    action = webhook.get_user_actions()[0]
    assert action.action_type == "marketing_messages_link_click"
    assert action.timestamp_int == 1753000000
    assert action.marketing_messages_link_click_data.click_component == "cta"
    assert action.marketing_messages_link_click_data.tracking_token == "example_token"


def test_undocumented_action_type_is_tolerated_without_contract_drift() -> None:
    """Meta ships new action types unannounced — they must not 400."""
    webhook = WhatsAppWebhook.model_validate(
        _payload(
            [
                {
                    "action_type": "some_unannounced_action",
                    "timestamp": 1753000001,
                    "some_unannounced_action_data": {
                        "device": {"agent": "(Android 15)"}
                    },
                }
            ]
        )
    )

    action = webhook.get_user_actions()[0]
    assert action.action_type == "some_unannounced_action"
    assert action.model_extra["some_unannounced_action_data"] == {
        "device": {"agent": "(Android 15)"}
    }


def test_link_click_data_tolerates_undocumented_client_user_agent() -> None:
    """Meta started sending ``client_user_agent`` on this sub-object unannounced.

    Production hit a 400 (``extra_forbidden``) on this exact field in 2026-07,
    since the nested model used to be ``extra="forbid"``.
    """
    payload = _payload(
        [
            {
                **_LINK_CLICK,
                "marketing_messages_link_click_data": {
                    **_LINK_CLICK["marketing_messages_link_click_data"],
                    "client_user_agent": "(Android 14)",
                },
            }
        ]
    )

    webhook = WhatsAppWebhook.model_validate(payload)

    action = webhook.get_user_actions()[0]
    assert action.marketing_messages_link_click_data.client_user_agent == "(Android 14)"


def test_undocumented_click_data_field_logs_a_warning(caplog) -> None:
    """A genuinely new field on the tolerated model must still surface — as a
    warning, not a silent drop — even though the model no longer 400s on it."""
    payload = _payload(
        [
            {
                **_LINK_CLICK,
                "marketing_messages_link_click_data": {
                    **_LINK_CLICK["marketing_messages_link_click_data"],
                    "brand_new_meta_field": "surprise",
                },
            }
        ]
    )

    with caplog.at_level("WARNING"):
        WhatsAppWebhook.model_validate(payload)

    [record] = [
        r for r in caplog.records if "WHATSAPP_WEBHOOK_UNDOCUMENTED_FIELDS" in r.message
    ]
    assert "marketing_messages_link_click_data" in record.message
    assert "brand_new_meta_field" in record.message
    assert "surprise" in record.message


def test_unknown_top_level_value_key_still_reports_contract_drift() -> None:
    """Tolerance stops at the action entry — ``value`` stays strict."""
    payload = _payload([_LINK_CLICK])
    payload["entry"][0]["changes"][0]["value"]["brand_new_field"] = [{"a": 1}]

    with pytest.raises(ValueError, match="brand_new_field"):
        WhatsAppWebhookProcessor().parse_webhook_container(payload)


@pytest.mark.asyncio
async def test_link_click_dispatches_as_inbox_scoped_user_action() -> None:
    webhook = await WhatsAppWebhookProcessor().create_universal_webhook(
        _payload([_LINK_CLICK]), inbox_id="508386009032748"
    )

    assert isinstance(webhook, SystemWebhook)
    assert webhook.system_event_type is SystemEventType.USER_ACTION
    assert webhook.event_detail.action_type == "marketing_messages_link_click"
    assert webhook.event_detail.user_action["marketing_messages_link_click_data"] == {
        "click_component": "cta",
        "product_id": "sku_id",
        "click_id": "click_id",
        "tracking_token": "example_token",
    }
    assert webhook.timestamp.timestamp() == 1753000000
    # No contacts arrive with the payload, so there is no User to attach.
    assert webhook.user is None


def test_user_actions_alongside_messages_keeps_the_message_path() -> None:
    """A value carrying both must still be delivered as an inbound message."""
    payload = _payload([_LINK_CLICK])
    value = payload["entry"][0]["changes"][0]["value"]
    value["contacts"] = [{"profile": {"name": "Sasha"}, "wa_id": "573001234567"}]
    value["messages"] = [
        {
            "from": "573001234567",
            "id": "wamid.user-action-coexist",
            "timestamp": "1753000000",
            "type": "text",
            "text": {"body": "hi"},
        }
    ]

    webhook = WhatsAppWebhook.model_validate(payload)

    assert webhook.is_user_action is False
    assert webhook.is_system_event is False
    assert webhook.webhook_type is WebhookType.INCOMING_MESSAGES
    # The actions are still parsed and reachable, just not the routing signal.
    assert len(webhook.get_user_actions()) == 1
