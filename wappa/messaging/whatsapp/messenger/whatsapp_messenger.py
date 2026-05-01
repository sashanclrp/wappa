# Unified WhatsApp implementation of IMessenger.

from pathlib import Path
from typing import Any

from wappa.core.logging.logger import get_logger
from wappa.domain.factories.media_factory import WhatsAppMediaFactory
from wappa.domain.factories.message_factory import WhatsAppMessageFactory
from wappa.domain.interfaces.messaging_interface import IMessenger
from wappa.messaging.whatsapp.client.whatsapp_client import WhatsAppClient
from wappa.messaging.whatsapp.handlers.whatsapp_interactive_handler import (
    WhatsAppInteractiveHandler,
)
from wappa.messaging.whatsapp.handlers.whatsapp_media_handler import (
    WhatsAppMediaHandler,
)
from wappa.messaging.whatsapp.handlers.whatsapp_specialized_handler import (
    WhatsAppSpecializedHandler,
)
from wappa.messaging.whatsapp.handlers.whatsapp_template_handler import (
    WhatsAppTemplateHandler,
)
from wappa.messaging.whatsapp.models.basic_models import MessageResult
from wappa.messaging.whatsapp.models.interactive_models import (
    InteractiveHeader,
    ListSection,
    ReplyButton,
)
from wappa.messaging.whatsapp.models.media_models import MediaType
from wappa.messaging.whatsapp.models.template_models import (
    WhatsAppTemplateMediaType,
    WhatsAppTemplateType,
)
from wappa.messaging.whatsapp.utils.error_helpers import handle_whatsapp_error
from wappa.schemas.core.types import PlatformType


class WhatsAppMessenger(IMessenger):
    def __init__(
        self,
        client: WhatsAppClient,
        media_handler: WhatsAppMediaHandler,
        interactive_handler: WhatsAppInteractiveHandler,
        template_handler: WhatsAppTemplateHandler,
        specialized_handler: WhatsAppSpecializedHandler,
        tenant_id: str,
        message_factory: WhatsAppMessageFactory | None = None,
        media_factory: WhatsAppMediaFactory | None = None,
    ):
        self.client = client
        self.media_handler = media_handler
        self.interactive_handler = interactive_handler
        self.template_handler = template_handler
        self.specialized_handler = specialized_handler
        self._tenant_id = tenant_id
        # Factories default to new instances so the constructor stays ergonomic
        # for library users while still allowing DI in FastAPI routes.
        self._message_factory = message_factory or WhatsAppMessageFactory()
        self._media_factory = media_factory or WhatsAppMediaFactory()
        self.logger = get_logger(__name__)

    @property
    def platform(self) -> PlatformType:
        return PlatformType.WHATSAPP

    @property
    def tenant_id(self) -> str:
        return self._tenant_id

    def _error_result(
        self, error: str, error_code: str, recipient: str | None = None
    ) -> MessageResult:
        return MessageResult(
            success=False,
            platform=PlatformType.WHATSAPP,
            recipient=recipient,
            recipient_bsuid=None,
            recipient_phone=None,
            error=error,
            error_code=error_code,
            tenant_id=self._tenant_id,
            api_response=None,
        )

    def _convert_body_parameters(
        self, body_parameters: list[dict] | None
    ) -> list | None:
        if not body_parameters:
            return None

        from wappa.messaging.whatsapp.models.template_models import (
            TemplateParameter,
            TemplateParameterType,
        )

        result = []
        for p in body_parameters:
            if not isinstance(p, dict):
                continue
            if p.get("type") == "text":
                result.append(
                    TemplateParameter(
                        type=TemplateParameterType.TEXT,
                        text=p.get("text"),
                        parameter_name=p.get("parameter_name"),
                    )
                )
            else:
                self.logger.warning(
                    "Skipping unsupported template body parameter type '%s' in "
                    "WhatsAppMessenger._convert_body_parameters",
                    p.get("type"),
                )
        return result

    def _parse_template_type(self, template_type: str) -> WhatsAppTemplateType | None:
        try:
            return WhatsAppTemplateType(template_type)
        except ValueError:
            return None

    def _parse_template_enums(
        self, template_type: str, media_type: str
    ) -> tuple[WhatsAppTemplateType | None, WhatsAppTemplateMediaType | None]:
        template_type_enum = self._parse_template_type(template_type)
        if template_type_enum is None:
            return None, None
        try:
            media_type_enum = WhatsAppTemplateMediaType(media_type)
        except ValueError:
            return template_type_enum, None
        return template_type_enum, media_type_enum

    # Basic

    async def send_text(
        self,
        text: str,
        recipient: str,
        reply_to_message_id: str | None = None,
        disable_preview: bool = False,
    ) -> MessageResult:
        try:
            payload = self._message_factory.create_text_message(
                text=text,
                recipient=recipient,
                reply_to_message_id=reply_to_message_id,
                disable_preview=disable_preview,
            )

            self.logger.debug(f"Sending text message to {recipient}: {text[:50]}...")
            response = await self.client.post_request(payload)
            result = MessageResult.from_response_payload(
                response,
                tenant_id=self._tenant_id,
                fallback_recipient=recipient,
            )
            self.logger.info(
                f"Text message sent successfully to {result.recipient}, id: {result.message_id}"
            )
            return result

        except Exception as e:
            return handle_whatsapp_error(
                error=e,
                operation="send text message",
                recipient=recipient,
                tenant_id=self._tenant_id,
                logger=self.logger,
            )

    async def mark_as_read(
        self, message_id: str, typing: bool = False
    ) -> MessageResult:
        # WhatsApp Business API: typing indicator requires recipient WA ID (not tracked here).
        try:
            read_payload = self._message_factory.create_read_status_message(
                message_id=message_id, typing=False
            )

            self.logger.debug(f"Marking message {message_id} as read")
            await self.client.post_request(read_payload)

            if typing:
                # TODO: proper typing indicator needs recipient WhatsApp ID
                self.logger.debug(
                    "Typing indicator requested but skipped (requires recipient ID)"
                )

            action_msg = (
                "marked as read with typing indicator" if typing else "marked as read"
            )
            self.logger.info(f"Message {message_id} {action_msg}")

            return MessageResult(
                success=True,
                message_id=message_id,
                recipient=None,
                recipient_bsuid=None,
                recipient_phone=None,
                platform=PlatformType.WHATSAPP,
                tenant_id=self._tenant_id,
                api_response=None,
            )

        except Exception as e:
            return handle_whatsapp_error(
                error=e,
                operation=(
                    "mark as read with typing indicator" if typing else "mark as read"
                ),
                recipient=message_id,
                tenant_id=self._tenant_id,
                logger=self.logger,
            )

    # Media

    async def send_image(
        self,
        image_source: str | Path,
        recipient: str,
        caption: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        return await self._send_media(
            image_source,
            MediaType.IMAGE,
            recipient,
            caption=caption,
            reply_to_message_id=reply_to_message_id,
        )

    async def send_video(
        self,
        video_source: str | Path,
        recipient: str,
        caption: str | None = None,
        reply_to_message_id: str | None = None,
        transcript: str | None = None,
    ) -> MessageResult:
        return await self._send_media(
            video_source,
            MediaType.VIDEO,
            recipient,
            caption=caption,
            reply_to_message_id=reply_to_message_id,
            transcript=transcript,
        )

    async def send_audio(
        self,
        audio_source: str | Path,
        recipient: str,
        reply_to_message_id: str | None = None,
        transcript: str | None = None,
        is_voice: bool = False,
    ) -> MessageResult:
        # Voice messages require OGG/OPUS mono; regular audio has no caption support.
        return await self._send_media(
            audio_source,
            MediaType.AUDIO,
            recipient,
            reply_to_message_id=reply_to_message_id,
            transcript=transcript,
            is_voice=is_voice,
        )

    async def send_document(
        self,
        document_source: str | Path,
        recipient: str,
        filename: str | None = None,
        caption: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        return await self._send_media(
            document_source,
            MediaType.DOCUMENT,
            recipient,
            caption=caption,
            filename=filename,
            reply_to_message_id=reply_to_message_id,
        )

    async def send_sticker(
        self,
        sticker_source: str | Path,
        recipient: str,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        return await self._send_media(
            sticker_source,
            MediaType.STICKER,
            recipient,
            reply_to_message_id=reply_to_message_id,
        )

    async def _resolve_media_object(
        self,
        media_source: str | Path,
        media_type: MediaType,
        recipient: str,
    ) -> tuple[dict[str, Any] | None, MessageResult | None]:
        # Returns (media_obj, None) on success or (None, error_result) on failure.
        if isinstance(media_source, str) and (
            media_source.startswith("http://") or media_source.startswith("https://")
        ):
            self.logger.debug(f"Using media URL for {media_type.value}: {media_source}")
            return {"link": media_source}, None

        # Heuristic: short string without slashes is treated as an existing media ID.
        if (
            isinstance(media_source, str)
            and len(media_source) < 100
            and "/" not in media_source
        ):
            self.logger.debug(
                f"Using existing media ID for {media_type.value}: {media_source}"
            )
            return {"id": media_source}, None

        media_path = Path(media_source)
        if not media_path.exists():
            return None, self._error_result(
                f"Media file not found: {media_path}",
                "FILE_NOT_FOUND",
                recipient=recipient,
            )

        self.logger.debug(
            f"Uploading media file for {media_type.value}: {media_path.name}"
        )
        upload_result = await self.media_handler.upload_media(media_path)
        if not upload_result.success:
            return None, self._error_result(
                f"Failed to upload media: {upload_result.error}",
                upload_result.error_code,
                recipient=recipient,
            )
        if not upload_result.media_id:
            return None, self._error_result(
                "Failed to upload media: missing media ID",
                "MEDIA_ID_MISSING",
                recipient=recipient,
            )

        self.logger.debug(
            f"Using uploaded media ID for {media_type.value}: {upload_result.media_id}"
        )
        return {"id": upload_result.media_id}, None

    async def _send_media(
        self,
        media_source: str | Path,
        media_type: MediaType,
        recipient: str,
        caption: str | None = None,
        filename: str | None = None,
        reply_to_message_id: str | None = None,
        transcript: str | None = None,  # noqa: ARG002 - internal metadata, not sent to WhatsApp
        is_voice: bool = False,
    ) -> MessageResult:
        try:
            media_obj, error = await self._resolve_media_object(
                media_source, media_type, recipient
            )
            if error is not None:
                return error
            assert media_obj is not None

            # Unpack the resolved media into (reference, is_url) for the factory.
            is_url = "link" in media_obj
            media_reference = media_obj["link"] if is_url else media_obj["id"]

            match media_type:
                case MediaType.IMAGE:
                    payload = self._media_factory.create_image_message(
                        media_reference=media_reference,
                        recipient=recipient,
                        caption=caption,
                        reply_to_message_id=reply_to_message_id,
                        is_url=is_url,
                    )
                case MediaType.VIDEO:
                    payload = self._media_factory.create_video_message(
                        media_reference=media_reference,
                        recipient=recipient,
                        caption=caption,
                        reply_to_message_id=reply_to_message_id,
                        is_url=is_url,
                    )
                case MediaType.AUDIO:
                    payload = self._media_factory.create_audio_message(
                        media_reference=media_reference,
                        recipient=recipient,
                        reply_to_message_id=reply_to_message_id,
                        is_url=is_url,
                    )
                case MediaType.DOCUMENT:
                    payload = self._media_factory.create_document_message(
                        media_reference=media_reference,
                        recipient=recipient,
                        filename=filename,
                        reply_to_message_id=reply_to_message_id,
                        is_url=is_url,
                    )
                case MediaType.STICKER:
                    payload = self._media_factory.create_sticker_message(
                        media_reference=media_reference,
                        recipient=recipient,
                        reply_to_message_id=reply_to_message_id,
                        is_url=is_url,
                    )
                case _:
                    return self._error_result(
                        f"Unsupported media type: {media_type}",
                        "INVALID_MEDIA_TYPE",
                        recipient=recipient,
                    )

            # Voice-note flag is WhatsApp-specific and not part of the factory contract.
            if media_type is MediaType.AUDIO and is_voice:
                payload[media_type.value]["voice"] = True

            self.logger.debug(f"Sending {media_type.value} message to {recipient}")
            response = await self.client.post_request(payload)
            result = MessageResult.from_response_payload(
                response,
                tenant_id=self._tenant_id,
                fallback_recipient=recipient,
            )
            self.logger.info(
                f"{media_type.value.title()} message sent successfully to "
                f"{result.recipient}, id: {result.message_id}"
            )
            return result

        except Exception as e:
            return handle_whatsapp_error(
                error=e,
                operation=f"send {media_type.value}",
                recipient=recipient,
                tenant_id=self._tenant_id,
                logger=self.logger,
            )

    # Interactive

    async def send_button_message(
        self,
        buttons: list[ReplyButton],
        recipient: str,
        body: str,
        header: InteractiveHeader | None = None,
        footer: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        return await self.interactive_handler.send_buttons_menu(
            recipient=recipient,
            body=body,
            buttons=buttons,
            header=header,
            footer_text=footer,
            reply_to_message_id=reply_to_message_id,
        )

    async def send_list_message(
        self,
        sections: list[ListSection],
        recipient: str,
        body: str,
        button_text: str,
        header: str | None = None,
        footer: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        return await self.interactive_handler.send_list_menu(
            recipient=recipient,
            body=body,
            button_text=button_text,
            sections=sections,
            header=header,
            footer_text=footer,
            reply_to_message_id=reply_to_message_id,
        )

    async def send_cta_message(
        self,
        button_text: str,
        button_url: str,
        recipient: str,
        body: str,
        header: str | None = None,
        footer: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        return await self.interactive_handler.send_cta_button(
            recipient=recipient,
            body=body,
            button_text=button_text,
            button_url=button_url,
            header_text=header,
            footer_text=footer,
            reply_to_message_id=reply_to_message_id,
        )

    # Templates

    async def send_text_template(
        self,
        template_name: str,
        recipient: str,
        body_parameters: list[dict] | None = None,
        language_code: str = "es",
        *,
        template_type: str,
        override: bool | None = None,
    ) -> MessageResult:
        template_type_enum = self._parse_template_type(template_type)
        if template_type_enum is None:
            return self._error_result(
                f"Invalid template type: {template_type}", "INVALID_TEMPLATE_TYPE"
            )
        return await self.template_handler.send_text_template(
            recipient=recipient,
            template_name=template_name,
            body_parameters=self._convert_body_parameters(body_parameters),
            language_code=language_code,
            template_type=template_type_enum,
            override=override,
        )

    async def send_media_template(
        self,
        template_name: str,
        recipient: str,
        media_type: str,
        media_id: str | None = None,
        media_url: str | None = None,
        body_parameters: list[dict] | None = None,
        language_code: str = "es",
        *,
        template_type: str,
        override: bool | None = None,
    ) -> MessageResult:
        template_type_enum, media_type_enum = self._parse_template_enums(
            template_type, media_type
        )
        if template_type_enum is None:
            return self._error_result(
                f"Invalid template type: {template_type}", "INVALID_TEMPLATE_TYPE"
            )
        if media_type_enum is None:
            return self._error_result(
                f"Invalid media type: {media_type}", "INVALID_MEDIA_TYPE"
            )

        return await self.template_handler.send_media_template(
            recipient=recipient,
            template_name=template_name,
            media_type=media_type_enum,
            media_id=media_id,
            media_url=media_url,
            body_parameters=self._convert_body_parameters(body_parameters),
            language_code=language_code,
            template_type=template_type_enum,
            override=override,
        )

    async def send_location_template(
        self,
        template_name: str,
        recipient: str,
        latitude: str,
        longitude: str,
        name: str,
        address: str,
        body_parameters: list[dict] | None = None,
        language_code: str = "es",
        *,
        template_type: str,
        override: bool | None = None,
    ) -> MessageResult:
        template_type_enum = self._parse_template_type(template_type)
        if template_type_enum is None:
            return self._error_result(
                f"Invalid template type: {template_type}", "INVALID_TEMPLATE_TYPE"
            )
        return await self.template_handler.send_location_template(
            recipient=recipient,
            template_name=template_name,
            latitude=latitude,
            longitude=longitude,
            name=name,
            address=address,
            body_parameters=self._convert_body_parameters(body_parameters),
            language_code=language_code,
            template_type=template_type_enum,
            override=override,
        )

    # Specialized

    async def send_contact(
        self, contact: dict, recipient: str, reply_to_message_id: str | None = None
    ) -> MessageResult:
        from wappa.messaging.whatsapp.models.specialized_models import ContactCard

        if isinstance(contact, dict):
            try:
                contact_card = ContactCard(**contact)
            except Exception as e:
                return self._error_result(
                    f"Invalid contact format: {e}", "INVALID_CONTACT_FORMAT"
                )
        else:
            contact_card = contact

        return await self.specialized_handler.send_contact_card(
            recipient=recipient,
            contact=contact_card,
            reply_to_message_id=reply_to_message_id,
        )

    async def send_location(
        self,
        latitude: float,
        longitude: float,
        recipient: str,
        name: str | None = None,
        address: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        return await self.specialized_handler.send_location(
            recipient=recipient,
            latitude=latitude,
            longitude=longitude,
            name=name,
            address=address,
            reply_to_message_id=reply_to_message_id,
        )

    async def send_location_request(
        self, body: str, recipient: str, reply_to_message_id: str | None = None
    ) -> MessageResult:
        return await self.specialized_handler.send_location_request(
            recipient=recipient, body=body, reply_to_message_id=reply_to_message_id
        )
