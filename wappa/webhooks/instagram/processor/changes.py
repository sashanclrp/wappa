"""Instagram ``changes[]`` dispatch: comments, mentions, extension fields, unsupported."""

from __future__ import annotations

from typing import Any

from wappa.domain.inbox.identity import InboxRef
from wappa.schemas.core.types import PlatformType
from wappa.webhooks.core.webhook_interfaces.base_components import InboxBase
from wappa.webhooks.core.webhook_interfaces.universal_webhooks import (
    CustomWebhook,
    SystemEventType,
    UniversalWebhook,
)
from wappa.webhooks.instagram.models import InstagramChange, InstagramEntry

from ._base import InstagramProcessorBase
from .context import native_timestamp


class ChangesLaneMixin(InstagramProcessorBase):
    """Translate one ``entry.changes[]`` item."""

    def _from_change(
        self,
        entry: InstagramEntry,
        change: InstagramChange,
        inbox: InboxBase,
        payload: dict[str, Any],
    ) -> UniversalWebhook:
        ref = InboxRef(platform=PlatformType.INSTAGRAM, inbox_id=entry.id)
        meta: dict[str, Any] = {
            "inbox": inbox,
            "timestamp": native_timestamp(entry.time),
            "platform": self.platform,
            "raw_webhook_data": payload,
        }
        if change.field in ("comments", "live_comments"):
            return self._comment(change, ref, meta)
        if change.field == "mentions":
            return self._mention(change, ref, meta)
        spec = (
            self._field_registry.get(change.field, PlatformType.INSTAGRAM)
            if self._field_registry
            else None
        )
        if spec is not None:
            return CustomWebhook(
                **meta,
                webhook_id=f"{change.field}:{entry.time or 'event'}",
                field_name=change.field,
                parsed=spec.parser(change.value),
                raw_value=change.value,
            )
        return self._system(
            meta,
            None,
            change,
            SystemEventType.UNSUPPORTED_EVENT,
            f"Instagram change field '{change.field}' is not implemented",
        )
