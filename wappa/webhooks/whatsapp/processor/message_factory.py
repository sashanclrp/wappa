"""Message factory: the ``_create_*_message`` table, one Wappa message model per type."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from wappa.core.inbound.errors import UnsupportedMessageTypeError
from wappa.schemas.core.types import MessageType
from wappa.webhooks.core.base_message import BaseMessage
from wappa.webhooks.core.schema_drift import report_schema_drift, report_unmodelled
from wappa.webhooks.whatsapp.processor._base import _ProcessorBase

if TYPE_CHECKING:
    from wappa.webhooks.whatsapp.message_types.system import WhatsAppSystemMessage
    from wappa.webhooks.whatsapp.processor._base import _ProcessorBase


class _MessageFactoryMixin(_ProcessorBase):
    """Message factory: the ``_create_*_message`` table, one Wappa message model per type."""

    def _create_message_from_data(
        self,
        message_data: dict[str, Any],
        message_type: MessageType,
        **kwargs: Any,
    ) -> BaseMessage:
        message_type_str = message_type.value
        handler = self._message_type_handlers.get(message_type_str)
        if handler is None:
            raise UnsupportedMessageTypeError(message_type_str, self.platform)

        message = handler(message_data, **kwargs)
        report_schema_drift(message, platform="whatsapp", logger=self.logger)
        return message

    def _create_text_message(
        self, message_data: dict[str, Any], **kwargs: Any
    ) -> BaseMessage:
        from wappa.webhooks.whatsapp.message_types.text import WhatsAppTextMessage

        return WhatsAppTextMessage.model_validate(message_data)

    def _create_interactive_message(
        self, message_data: dict[str, Any], **kwargs: Any
    ) -> BaseMessage:
        from wappa.webhooks.whatsapp.message_types.interactive import (
            KNOWN_INTERACTIVE_REPLY_TYPES,
            WhatsAppInteractiveMessage,
        )

        interactive = message_data.get("interactive") or {}
        reply_type = interactive.get("type")
        if reply_type not in KNOWN_INTERACTIVE_REPLY_TYPES:
            # A reply type Wappa does not model: deliver it as Unsupported with
            # a 200 instead of a 400 that Meta retries and drops (ADR-0023).
            report_unmodelled(
                [f"InteractiveContent.type={reply_type}"],
                platform="whatsapp",
                logger=self.logger,
            )
            return self._create_unsupported_message(
                {
                    **{k: v for k, v in message_data.items() if k != "interactive"},
                    "type": "unsupported",
                    "unsupported": {"type": "interactive", "interactive": interactive},
                    "errors": [
                        {
                            "code": 131051,
                            "title": "Unsupported message type",
                            "message": (
                                f"Interactive reply type '{reply_type}' is not "
                                "modelled by Wappa"
                            ),
                            "error_data": {
                                "details": "Read the reply from unsupported.interactive"
                            },
                        }
                    ],
                }
            )
        return WhatsAppInteractiveMessage.model_validate(message_data)

    def _create_image_message(
        self, message_data: dict[str, Any], **kwargs: Any
    ) -> BaseMessage:
        from wappa.webhooks.whatsapp.message_types.image import WhatsAppImageMessage

        return WhatsAppImageMessage.model_validate(message_data)

    def _create_audio_message(
        self, message_data: dict[str, Any], **kwargs: Any
    ) -> BaseMessage:
        from wappa.webhooks.whatsapp.message_types.audio import WhatsAppAudioMessage

        return WhatsAppAudioMessage.model_validate(message_data)

    def _create_video_message(
        self, message_data: dict[str, Any], **kwargs: Any
    ) -> BaseMessage:
        from wappa.webhooks.whatsapp.message_types.video import WhatsAppVideoMessage

        return WhatsAppVideoMessage.model_validate(message_data)

    def _create_document_message(
        self, message_data: dict[str, Any], **kwargs: Any
    ) -> BaseMessage:
        from wappa.webhooks.whatsapp.message_types.document import (
            WhatsAppDocumentMessage,
        )

        return WhatsAppDocumentMessage.model_validate(message_data)

    def _create_contact_message(
        self, message_data: dict[str, Any], **kwargs: Any
    ) -> BaseMessage:
        from wappa.webhooks.whatsapp.message_types.contact import WhatsAppContactMessage

        return WhatsAppContactMessage.model_validate(message_data)

    def _create_location_message(
        self, message_data: dict[str, Any], **kwargs: Any
    ) -> BaseMessage:
        from wappa.webhooks.whatsapp.message_types.location import (
            WhatsAppLocationMessage,
        )

        return WhatsAppLocationMessage.model_validate(message_data)

    def _create_sticker_message(
        self, message_data: dict[str, Any], **kwargs: Any
    ) -> BaseMessage:
        from wappa.webhooks.whatsapp.message_types.sticker import WhatsAppStickerMessage

        return WhatsAppStickerMessage.model_validate(message_data)

    def _create_system_message(
        self, message_data: dict[str, Any], **kwargs: Any
    ) -> WhatsAppSystemMessage:
        from wappa.webhooks.whatsapp.message_types.system import WhatsAppSystemMessage

        return WhatsAppSystemMessage.model_validate(message_data)

    def _create_unsupported_message(
        self, message_data: dict[str, Any], **kwargs: Any
    ) -> BaseMessage:
        from wappa.webhooks.whatsapp.message_types.unsupported import (
            WhatsAppUnsupportedMessage,
        )

        return WhatsAppUnsupportedMessage.model_validate(message_data)

    def _create_reaction_message(
        self, message_data: dict[str, Any], **kwargs: Any
    ) -> BaseMessage:
        from wappa.webhooks.whatsapp.message_types.reaction import (
            WhatsAppReactionMessage,
        )

        return WhatsAppReactionMessage.model_validate(message_data)

    def _create_button_message(
        self, message_data: dict[str, Any], **kwargs: Any
    ) -> BaseMessage:
        from wappa.webhooks.whatsapp.message_types.button import WhatsAppButtonMessage

        return WhatsAppButtonMessage.model_validate(message_data)

    def _create_order_message(
        self, message_data: dict[str, Any], **kwargs: Any
    ) -> BaseMessage:
        from wappa.webhooks.whatsapp.message_types.order import WhatsAppOrderMessage

        return WhatsAppOrderMessage.model_validate(message_data)

    def _create_lifecycle_message(
        self, message_data: dict[str, Any], **kwargs: Any
    ) -> BaseMessage:
        from wappa.webhooks.whatsapp.message_types.lifecycle import (
            WhatsAppLifecycleMessage,
        )

        return WhatsAppLifecycleMessage.model_validate(message_data)
