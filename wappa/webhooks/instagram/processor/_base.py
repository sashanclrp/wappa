"""Shared typed state and cross-lane signatures for the Instagram processor mixins."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from wappa.domain.inbox.identity import InboxRef
from wappa.webhooks.core.base_message import BaseMessage
from wappa.webhooks.core.webhook_interfaces.base_components import (
    SystemEventDetail,
    UserBase,
)
from wappa.webhooks.core.webhook_interfaces.universal_webhooks import (
    SystemEventType,
    SystemWebhook,
    UniversalWebhook,
)
from wappa.webhooks.instagram.models import (
    InstagramChange,
    InstagramEntry,
    InstagramMessage,
    InstagramMessagingEvent,
)

if TYPE_CHECKING:
    from wappa.core.events.field_registry import FieldHandlerRegistry
    from wappa.core.logging.logger import ContextLogger
    from wappa.schemas.core.types import PlatformType


class InstagramProcessorBase:
    """Attributes and lane signatures every Instagram processor mixin relies on."""

    logger: ContextLogger
    _field_registry: FieldHandlerRegistry | None

    @property
    def platform(self) -> PlatformType:
        raise NotImplementedError

    def _message(
        self,
        entry: InstagramEntry,
        event: InstagramMessagingEvent,
        message: InstagramMessage,
        user_id: str,
    ) -> BaseMessage | None:
        raise NotImplementedError

    def _echo(
        self,
        entry: InstagramEntry,
        event: InstagramMessagingEvent,
        message: InstagramMessage,
        user: UserBase,
        meta: dict[str, Any],
    ) -> UniversalWebhook:
        raise NotImplementedError

    def _comment(
        self, change: InstagramChange, ref: InboxRef, meta: dict[str, Any]
    ) -> UniversalWebhook:
        raise NotImplementedError

    def _mention(
        self, change: InstagramChange, ref: InboxRef, meta: dict[str, Any]
    ) -> UniversalWebhook:
        raise NotImplementedError

    def _system(
        self,
        meta: dict[str, Any],
        user: UserBase | None,
        event: InstagramMessagingEvent | InstagramChange,
        kind: SystemEventType,
        detail: str,
    ) -> SystemWebhook:
        raw = event.model_dump(mode="json", exclude_none=True, by_alias=True)
        if isinstance(event, InstagramMessagingEvent):
            mid = event.message.mid if event.message else None
            webhook_id = f"{kind.value}:{mid or 'event'}:{event.timestamp}"
        else:
            webhook_id = f"{kind.value}:{event.field}:{meta['timestamp'].timestamp()}"
        return SystemWebhook(
            **meta,
            webhook_id=webhook_id,
            user=user,
            system_event_type=kind,
            event_detail=SystemEventDetail(platform_event=raw, detail=detail),
        )
