"""System lane: one dispatch method over the per-family builders."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from wappa.core.inbound.errors import ProcessorError
from wappa.schemas.core.types import ErrorCode, PlatformType
from wappa.webhooks.core.webhook_interfaces import SystemWebhook
from wappa.webhooks.whatsapp.processor._base import _ProcessorBase
from wappa.webhooks.whatsapp.processor.system.account_events import (
    build_app_state_sync_event,
    build_business_username_event,
)
from wappa.webhooks.whatsapp.processor.system.groups import build_group_event
from wappa.webhooks.whatsapp.processor.system.identity import (
    build_user_id_update_event,
)
from wappa.webhooks.whatsapp.processor.system.number_changes import (
    build_system_message_event,
)
from wappa.webhooks.whatsapp.processor.system.parts import SystemParts
from wappa.webhooks.whatsapp.processor.system.preferences import (
    build_preference_event,
)
from wappa.webhooks.whatsapp.processor.system.user_actions import (
    build_user_action_event,
)

if TYPE_CHECKING:
    from wappa.webhooks.core.webhook_interfaces import InboxBase
    from wappa.webhooks.whatsapp.models.webhook import WhatsAppWebhook


class _SystemMixin(_ProcessorBase):
    """Builds ``SystemWebhook`` from the system-event fields."""

    async def _create_system_webhook(
        self, webhook: WhatsAppWebhook, inbox_base: InboxBase, **kwargs: Any
    ) -> SystemWebhook:
        # Handles direct fields and system messages carried by messages[].
        # - field: "user_preferences"           → MARKETING_PREFERENCE
        # - field: "user_id_update"             → USER_ID_CHANGE
        # - field: "messages" (type=="system")  → NUMBER_CHANGE or USER_ID_CHANGE
        # - field: "messages" (user_actions)    → USER_ACTION
        field = webhook.entry[0].changes[0].field

        parts: SystemParts | None = None
        match field:
            case "user_preferences":
                parts = build_preference_event(self, webhook)
            case "user_id_update":
                parts = build_user_id_update_event(self, webhook)
            case "business_username_updates":
                parts = build_business_username_event(self, webhook)
            case "group_participants_update":
                parts = build_group_event(self, webhook)
            case "smb_app_state_sync":
                parts = build_app_state_sync_event(self, webhook, field)
            case "messages" if webhook.is_user_action:
                parts = build_user_action_event(self, webhook)
            case "messages":
                parts = build_system_message_event(self, webhook)

        if parts is None:
            raise ProcessorError(
                f"Unsupported system webhook field '{field}'",
                ErrorCode.PROCESSING_ERROR,
                PlatformType.WHATSAPP,
            )

        return SystemWebhook(
            inbox=inbox_base,
            system_event_type=parts.event_type,
            event_detail=parts.detail,
            user=parts.user,
            timestamp=parts.timestamp,
            platform=PlatformType.WHATSAPP,
            webhook_id=webhook.get_webhook_id(),
        )
