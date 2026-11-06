"""Platform webhook lanes of ``WappaEventHandler``: the handle_* template and process_* hooks."""

from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING

from ._state import _HandlerState

if TYPE_CHECKING:
    from wappa.webhooks import (
        CallWebhook,
        ErrorWebhook,
        HistorySyncWebhook,
        InboundMessageWebhook,
        InboxConnectionWebhook,
        IncomingCommentWebhook,
        MentionWebhook,
        MessageUpdateWebhook,
        OutboundEchoWebhook,
        StatusWebhook,
        SystemWebhook,
    )


class _WebhookLanes(_HandlerState):
    """Platform webhook lanes of ``WappaEventHandler``: the handle_* template and process_* hooks."""

    async def handle_message(self, webhook: InboundMessageWebhook) -> None:
        """
        Handle incoming message webhook using Template Method pattern.

        This method provides a structured flow:
        1. Pre-processing: Default logging (non-optional framework infrastructure)
        2. User processing: Custom business logic (implemented in process_message)
        3. Post-processing: Optional cleanup/metrics

        Args:
            webhook: InboundMessageWebhook containing the message data
        """
        # 1. Pre-processing: Framework logging (always happens)
        await self._default_message_handler.log_incoming_message(webhook)

        # 2. User processing: Custom business logic
        await self.process_message(webhook)

        # 3. Post-processing: Framework cleanup (future extensibility)
        await self._default_message_handler.post_process_message(webhook)

    @abstractmethod
    async def process_message(self, webhook: InboundMessageWebhook) -> None:
        """
        Process incoming message webhook with custom business logic.

        This is where users implement their message processing logic.
        The framework handles logging automatically before calling this method.

        Args:
            webhook: InboundMessageWebhook containing the message data
        """
        pass

    async def handle_status(self, webhook: StatusWebhook) -> None:
        """
        Handle message status updates using Template Method pattern.

        This method provides a structured flow:
        1. Pre-processing: Default logging (non-optional framework infrastructure)
        2. User processing: Custom status logic (implemented in process_status)
        3. Post-processing: Framework cleanup (future extensibility)

        Args:
            webhook: StatusWebhook containing the status update
        """
        # 1. Pre-processing: Framework logging (always happens)
        await self._default_status_handler.handle_status(webhook)

        # 2. User processing: Custom business logic (optional)
        await self.process_status(webhook)

    async def process_status(self, webhook: StatusWebhook) -> None:
        """
        Process status webhook with custom business logic.

        Optional method - override if you need custom status processing.
        The framework handles logging automatically before calling this method.

        Args:
            webhook: StatusWebhook containing the status update
        """
        _ = webhook
        return None

    async def handle_error(self, webhook: ErrorWebhook) -> None:
        """
        Handle platform errors using Template Method pattern.

        This method provides a structured flow:
        1. Pre-processing: Default logging and escalation (non-optional framework infrastructure)
        2. User processing: Custom error handling (implemented in process_error)
        3. Post-processing: Framework cleanup (future extensibility)

        Args:
            webhook: ErrorWebhook containing error information
        """
        # 1. Pre-processing: Framework logging and escalation (always happens)
        await self._default_error_handler.handle_error(webhook)

        # 2. User processing: Custom business logic (optional)
        await self.process_error(webhook)

    async def process_error(self, webhook: ErrorWebhook) -> None:
        """
        Process error webhook with custom business logic.

        Optional method - override if you need custom error processing.
        The framework handles logging and escalation automatically before calling this method.

        Args:
            webhook: ErrorWebhook containing error information
        """
        _ = webhook
        return None

    # =========== SYSTEM WEBHOOK HANDLING ===========

    async def handle_system(self, webhook: SystemWebhook) -> None:
        """
        Handle platform-level system events using Template Method pattern.

        This method provides a structured flow:
        1. Pre-processing: Default logging (non-optional framework infrastructure)
        2. User processing: Custom system event logic (implemented in process_system_webhook)

        Args:
            webhook: SystemWebhook containing system event data
        """
        # 1. Pre-processing: Framework logging (always happens)
        await self._default_system_handler.handle_system(webhook)

        # 2. User processing: Custom business logic (optional)
        await self.process_system_webhook(webhook)

    async def process_system_webhook(self, webhook: SystemWebhook) -> None:
        """
        Process system webhook with custom business logic.

        Optional method - override to handle phone number changes,
        BSUID updates, or marketing preference changes.

        The framework handles logging automatically before calling this method.

        Args:
            webhook: SystemWebhook containing system event data

        Example:
            async def process_system_webhook(self, webhook: SystemWebhook) -> None:
                match webhook.system_event_type:
                    case SystemEventType.NUMBER_CHANGE:
                        # Update user records with new phone number
                        ...
                    case SystemEventType.USER_ID_CHANGE:
                        # Update user records with new BSUID
                        ...
                    case SystemEventType.MARKETING_PREFERENCE:
                        # Update marketing opt-in/out status
                        ...
        """
        _ = webhook
        return None

    # =========== CONVERSATION LANES (optional overrides) ===========

    async def handle_message_update(self, webhook: MessageUpdateWebhook) -> None:
        """Template Method: default log, then ``process_message_update``."""
        await self._default_conversation_handler.log_event(webhook)
        await self.process_message_update(webhook)

    async def process_message_update(self, webhook: MessageUpdateWebhook) -> None:
        """Override to react to edits/deletions of an earlier User message.

        Updates never arrive as ``process_message`` or ``process_status``.
        """
        _ = webhook
        return None

    async def handle_comment(self, webhook: IncomingCommentWebhook) -> None:
        """Template Method: default log, then ``process_comment``."""
        await self._default_conversation_handler.log_event(webhook)
        await self.process_comment(webhook)

    async def process_comment(self, webhook: IncomingCommentWebhook) -> None:
        """Override to handle public Comments (regular and Live).

        Wappa does not filter by source/placement/author: decide here. Use
        ``webhook.is_own_comment`` to avoid replying to your own replies.
        """
        _ = webhook
        return None

    async def handle_mention(self, webhook: MentionWebhook) -> None:
        """Template Method: default log, then ``process_mention``."""
        await self._default_conversation_handler.log_event(webhook)
        await self.process_mention(webhook)

    async def process_mention(self, webhook: MentionWebhook) -> None:
        """Override to handle public account mentions (media or comment)."""
        _ = webhook
        return None

    async def handle_history_sync(self, webhook: HistorySyncWebhook) -> None:
        """Template Method: default log, then ``process_history_sync``."""
        await self._default_conversation_handler.log_event(webhook)
        await self.process_history_sync(webhook)

    async def process_history_sync(self, webhook: HistorySyncWebhook) -> None:
        """Override to store past conversations the Platform pushed.

        Pull-only Platforms (Instagram) offer the same ``HistoryThread`` via
        ``self.instagram.history.read_history(...)``.
        """
        _ = webhook
        return None

    async def handle_inbox_connection(self, webhook: InboxConnectionWebhook) -> None:
        """Template Method: default log, then ``process_inbox_connection``."""
        await self._default_conversation_handler.log_event(webhook)
        await self.process_inbox_connection(webhook)

    async def process_inbox_connection(self, webhook: InboxConnectionWebhook) -> None:
        """Override to deactivate or restore an Inbox when its connection changes."""
        _ = webhook
        return None

    async def handle_outbound_echo(self, webhook: OutboundEchoWebhook) -> None:
        """Template Method: default log, then ``process_outbound_echo``."""
        await self._default_conversation_handler.log_event(webhook)
        await self.process_outbound_echo(webhook)

    async def process_outbound_echo(self, webhook: OutboundEchoWebhook) -> None:
        """Override to react to messages the business itself sent.

        Same lane on every Platform (WhatsApp Coexistence, Instagram).
        ``webhook.is_from_business_app`` means a person answered from the
        Platform's own app, e.g. to pause automation for a human takeover.
        Echoes never arrive as ``process_message``.
        """
        _ = webhook
        return None

    async def handle_call(self, webhook: CallWebhook) -> None:
        """Dispatch a WhatsApp Calling event to the host hook."""
        await self.process_call(webhook)

    async def process_call(self, webhook: CallWebhook) -> None:
        """Override to handle connected, terminated, and call-status events."""
        _ = webhook
        return None
