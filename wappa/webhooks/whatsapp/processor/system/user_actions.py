"""System family: user interaction events (marketing link clicks) -> USER_ACTION."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from wappa.webhooks.core.webhook_interfaces import SystemEventDetail, SystemEventType
from wappa.webhooks.whatsapp.processor.system.parts import SystemParts

if TYPE_CHECKING:
    from wappa.webhooks.whatsapp.models.webhook import WhatsAppWebhook
    from wappa.webhooks.whatsapp.processor._base import _ProcessorBase


def build_user_action_event(
    processor: _ProcessorBase, webhook: WhatsAppWebhook
) -> SystemParts:
    # User interaction events (marketing message link clicks) ride
    # the messages field with no messages and no contacts, so there
    # is no User to attach — the event is Inbox-scoped.
    from wappa.webhooks.core.webhook_interfaces import UserAction

    action = webhook.get_user_actions()[0]
    click = action.marketing_messages_link_click_data

    system_event_type = SystemEventType.USER_ACTION
    event_detail = SystemEventDetail(
        action_type=action.action_type,
        user_action=UserAction(
            action_type=action.action_type,
            timestamp=action.timestamp_int,
            click_component=click.click_component if click else None,
            click_id=click.click_id if click else None,
            tracking_token=click.tracking_token if click else None,
            product_id=click.product_id if click else None,
            client_user_agent=click.client_user_agent if click else None,
        ),
    )
    event_timestamp = datetime.fromtimestamp(action.timestamp_int, tz=UTC)
    return SystemParts(system_event_type, event_detail, event_timestamp, None)
