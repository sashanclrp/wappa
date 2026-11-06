"""Shared typed surface of the WhatsApp processor mixins.

Every lane mixin inherits ``_ProcessorBase`` so mypy sees the attributes and
the cross-lane helpers it calls through ``self``. The stubs exist only for
type checking; the real implementations live in the lane modules.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from wappa.core.logging.logger import ContextLogger
from wappa.schemas.core.types import MessageType, PlatformType
from wappa.webhooks.core.base_message import BaseMessage

if TYPE_CHECKING:
    from wappa.core.events.field_registry import FieldHandlerRegistry
    from wappa.webhooks.core.webhook_interfaces import (
        BusinessContextBase,
        ConversationBase,
        EntryReferral,
        ErrorDetailBase,
        ForwardContextBase,
        InboxBase,
        MessageUpdateWebhook,
        SystemWebhook,
        UserBase,
    )
    from wappa.webhooks.whatsapp.message_types.system import WhatsAppSystemMessage
    from wappa.webhooks.whatsapp.models.coexistence import CoexistenceMessage
    from wappa.webhooks.whatsapp.models.status import WhatsAppMessageStatus
    from wappa.webhooks.whatsapp.models.webhook import WhatsAppWebhook


class _ProcessorBase:
    """Attributes and cross-lane helpers the processor mixins rely on."""

    logger: ContextLogger
    _field_registry: FieldHandlerRegistry | None
    _message_type_handlers: dict[str, Callable[..., BaseMessage]]

    @property
    def platform(self) -> PlatformType:
        raise NotImplementedError

    if TYPE_CHECKING:

        def _create_message_from_data(
            self,
            message_data: dict[str, Any],
            message_type: MessageType,
            **kwargs: Any,
        ) -> BaseMessage: ...

        def _create_system_message(
            self, message_data: dict[str, Any], **kwargs: Any
        ) -> WhatsAppSystemMessage: ...

        def _create_unsupported_message(
            self, message_data: dict[str, Any], **kwargs: Any
        ) -> BaseMessage: ...

        def _create_message_update_webhook(
            self,
            webhook: WhatsAppWebhook,
            message: BaseMessage,
            inbox_base: InboxBase,
        ) -> MessageUpdateWebhook: ...

        def _typed_coexistence_message(
            self, raw: CoexistenceMessage
        ) -> tuple[BaseMessage | None, MessageType | None]: ...

        def _create_status_from_data(
            self, status_data: dict[str, Any]
        ) -> WhatsAppMessageStatus: ...

        def _create_unmodelled_status_webhook(
            self,
            webhook: WhatsAppWebhook,
            inbox_base: InboxBase,
            raw_status: dict[str, Any],
        ) -> SystemWebhook: ...

        def _create_user_base_from_contacts(
            self, webhook: WhatsAppWebhook, sender_id: str
        ) -> UserBase: ...

        def _create_status_user_from_contacts(
            self, webhook: WhatsAppWebhook, recipient_id: str
        ) -> UserBase | None: ...

        def _extract_business_context(
            self, message_data: dict[str, Any]
        ) -> BusinessContextBase | None: ...

        def _extract_forward_context(
            self, message_data: dict[str, Any]
        ) -> ForwardContextBase | None: ...

        def _extract_entry_referral(
            self, message_data: dict[str, Any]
        ) -> EntryReferral | None: ...

        def _extract_conversation_context(
            self, status_data: Any
        ) -> ConversationBase | None: ...

        def _extract_status_errors(
            self, status_data: Any
        ) -> list[ErrorDetailBase] | None: ...
