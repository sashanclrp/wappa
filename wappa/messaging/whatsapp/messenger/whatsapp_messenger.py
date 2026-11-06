# Unified WhatsApp implementation of IMessenger.

from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from typing import Any, cast

from wappa.core.logging.logger import get_logger
from wappa.domain.contacts import ContactCard
from wappa.domain.factories.media_factory import WhatsAppMediaFactory
from wappa.domain.factories.message_factory import WhatsAppMessageFactory
from wappa.domain.inbox.identity import InboxRef
from wappa.domain.interactive import (
    ButtonHeader,
    ListSection,
    MessageCard,
    ReplyButton,
    UrlButton,
)
from wappa.domain.interfaces.media_library import IMediaLibrary
from wappa.domain.interfaces.messaging_interface import IMessenger
from wappa.domain.interfaces.template_messaging import ITemplateMessaging
from wappa.domain.media_renditions import MediaRenditions, pick_rendition
from wappa.domain.messaging_targets import (
    DirectMessage,
    MessageTarget,
    require_direct_message,
)
from wappa.domain.results import MessageResult
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
from wappa.messaging.whatsapp.media_library import WhatsAppMediaLibrary
from wappa.messaging.whatsapp.models.basic_models import message_result_from_payload
from wappa.messaging.whatsapp.models.media_models import MediaType
from wappa.messaging.whatsapp.models.template_models import (
    WhatsAppTemplateMediaType,
    WhatsAppTemplateType,
)
from wappa.messaging.whatsapp.utils.error_helpers import (
    ADDRESS_REJECTION_CODES,
    BSUID_ERROR_TAG,
    handle_whatsapp_error,
)
from wappa.schemas.core.recipient import (
    apply_recipient_to_payload,
    whatsapp_delivery_order,
)
from wappa.schemas.core.types import PlatformType


class WhatsAppMessenger(IMessenger, ITemplateMessaging):
    def __init__(
        self,
        client: WhatsAppClient,
        media_handler: WhatsAppMediaHandler,
        interactive_handler: WhatsAppInteractiveHandler,
        template_handler: WhatsAppTemplateHandler,
        specialized_handler: WhatsAppSpecializedHandler,
        inbox_id: str,
        message_factory: WhatsAppMessageFactory | None = None,
        media_factory: WhatsAppMediaFactory | None = None,
    ):
        self.client = client
        self.media_handler = media_handler
        self.interactive_handler = interactive_handler
        self.template_handler = template_handler
        self.specialized_handler = specialized_handler
        self._inbox_id = inbox_id
        # Factories default to new instances so the constructor stays ergonomic
        # for library users while still allowing DI in FastAPI routes.
        self._message_factory = message_factory or WhatsAppMessageFactory()
        self._media_factory = media_factory or WhatsAppMediaFactory()
        self.logger = get_logger(__name__)

    def capability[C](self, kind: Callable[..., C]) -> C | None:
        """Focused capabilities: Templates (WhatsApp-only) and the Media Library."""
        if kind is ITemplateMessaging:
            return cast(C, self)
        if kind is IMediaLibrary:
            return cast(C, WhatsAppMediaLibrary(self.media_handler, self._inbox_id))
        return None

    @property
    def supported_operations(self) -> frozenset[str]:
        return frozenset(
            [
                "send_text",
                "mark_as_read",
                "send_image",
                "send_video",
                "send_audio",
                "send_document",
                "send_sticker",
                "send_button_message",
                "send_list_message",
                "send_cta_message",
                "send_carousel",
                "send_contact_request",
                "send_contact",
                "send_location",
                "send_location_request",
            ]
        )

    @property
    def platform(self) -> PlatformType:
        return PlatformType.WHATSAPP

    @property
    def inbox_id(self) -> str:
        return self._inbox_id

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
            inbox_id=self._inbox_id,
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

    # Delivery Addresses (ADR-0019)

    async def _deliver(
        self,
        target: DirectMessage,
        send: Callable[[str], Awaitable[MessageResult]],
        *,
        phone_only: bool = False,
    ) -> MessageResult:
        """Send to the User's addresses in WhatsApp order, falling back once
        per address only when Meta rejects the address itself.

        Order: phone (``wa_id``) first, then BSUID, as Meta recommends. A
        rejection that is not about the address (window, rate limit, content,
        timeouts) is returned as-is: retrying could not help or could send
        twice. ``phone_only`` covers authentication Templates, which Meta
        does not deliver to BSUIDs.
        """
        addresses = whatsapp_delivery_order(
            target.resolve_all(InboxRef.whatsapp(self._inbox_id)),
            phone_only=phone_only,
        )
        if not addresses:
            return self._error_result(
                "No phone number known for a message that requires one",
                BSUID_ERROR_TAG,
                recipient=target.address,
            )
        attempted: list[str] = []
        result: MessageResult | None = None
        for address in addresses:
            attempted.append(address)
            result = await send(address)
            if result.success or result.error_code not in ADDRESS_REJECTION_CODES:
                break
            if address != addresses[-1]:
                self.logger.warning(
                    "Delivery Address %s rejected (%s); trying the next known address",
                    address,
                    result.error_code,
                )
        assert result is not None
        if len(attempted) > 1:
            result = result.model_copy(
                update={"attempted_recipients": tuple(attempted)}
            )
        return result

    # Basic

    async def send_text(
        self,
        text: str,
        target: MessageTarget,
        reply_to_message_id: str | None = None,
        disable_preview: bool = False,
    ) -> MessageResult:
        return await self._deliver(
            require_direct_message(target, "WhatsApp send_text"),
            lambda recipient: self._send_text_to(
                recipient, text, reply_to_message_id, disable_preview
            ),
        )

    async def _send_text_to(
        self,
        recipient: str,
        text: str,
        reply_to_message_id: str | None,
        disable_preview: bool,
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
            result = message_result_from_payload(
                response,
                inbox_id=self._inbox_id,
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
                inbox_id=self._inbox_id,
                logger=self.logger,
            )

    async def mark_as_read(
        self,
        message_id: str,
        target: DirectMessage,
        *,
        typing: bool = False,
    ) -> MessageResult:
        # The read receipt is addressed by message ID; ``target`` is only
        # checked against this Inbox.
        require_direct_message(target, "WhatsApp mark_as_read").resolve(
            InboxRef.whatsapp(self._inbox_id)
        )
        try:
            # Cloud API: typing_indicator rides on the read receipt itself and
            # needs only the inbound message ID.
            read_payload = self._message_factory.create_read_status_message(
                message_id=message_id, typing=typing
            )

            self.logger.debug(f"Marking message {message_id} as read")
            await self.client.post_request(read_payload)

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
                inbox_id=self._inbox_id,
            )

        except Exception as e:
            return handle_whatsapp_error(
                error=e,
                operation=(
                    "mark as read with typing indicator" if typing else "mark as read"
                ),
                recipient=message_id,
                inbox_id=self._inbox_id,
                logger=self.logger,
            )

    # Media

    async def send_image(
        self,
        image_source: str | Path,
        target: DirectMessage,
        caption: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        media_cache: dict[str, Any] = {}  # upload once across fallback attempts
        return await self._deliver(
            target,
            lambda recipient: self._send_media(
                image_source,
                MediaType.IMAGE,
                recipient,
                media_cache=media_cache,
                caption=caption,
                reply_to_message_id=reply_to_message_id,
            ),
        )

    async def send_video(
        self,
        video_source: str | Path,
        target: DirectMessage,
        caption: str | None = None,
        reply_to_message_id: str | None = None,
        transcript: str | None = None,
    ) -> MessageResult:
        media_cache: dict[str, Any] = {}  # upload once across fallback attempts
        return await self._deliver(
            target,
            lambda recipient: self._send_media(
                video_source,
                MediaType.VIDEO,
                recipient,
                media_cache=media_cache,
                caption=caption,
                reply_to_message_id=reply_to_message_id,
                transcript=transcript,
            ),
        )

    async def send_audio(
        self,
        audio_source: MediaRenditions,
        target: DirectMessage,
        reply_to_message_id: str | None = None,
        transcript: str | None = None,
        is_voice: bool = False,
    ) -> MessageResult:
        # A voice note (waveform) needs OGG/Opus mono; audio has no caption.
        audio_source = pick_rendition(
            audio_source,
            WHATSAPP_VOICE_SUFFIXES if is_voice else WHATSAPP_AUDIO_SUFFIXES,
            what="WhatsApp voice note" if is_voice else "WhatsApp audio",
        )
        media_cache: dict[str, Any] = {}  # upload once across fallback attempts
        return await self._deliver(
            target,
            lambda recipient: self._send_media(
                audio_source,
                MediaType.AUDIO,
                recipient,
                media_cache=media_cache,
                reply_to_message_id=reply_to_message_id,
                transcript=transcript,
                is_voice=is_voice,
            ),
        )

    async def send_document(
        self,
        document_source: str | Path,
        target: DirectMessage,
        filename: str | None = None,
        caption: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        media_cache: dict[str, Any] = {}  # upload once across fallback attempts
        return await self._deliver(
            target,
            lambda recipient: self._send_media(
                document_source,
                MediaType.DOCUMENT,
                recipient,
                media_cache=media_cache,
                caption=caption,
                filename=filename,
                reply_to_message_id=reply_to_message_id,
            ),
        )

    async def send_sticker(
        self,
        sticker_source: MediaRenditions,
        target: DirectMessage,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        # WhatsApp stickers must be WebP. Meta accepts a PNG link with 200 and
        # only fails later (status 131053), so pick or reject up front.
        sticker_source = pick_rendition(
            sticker_source, WHATSAPP_STICKER_SUFFIXES, what="WhatsApp sticker"
        )
        media_cache: dict[str, Any] = {}  # upload once across fallback attempts
        return await self._deliver(
            target,
            lambda recipient: self._send_media(
                sticker_source,
                MediaType.STICKER,
                recipient,
                media_cache=media_cache,
                reply_to_message_id=reply_to_message_id,
            ),
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
                upload_result.error_code or "MEDIA_UPLOAD_FAILED",
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
        media_cache: dict[str, Any] | None = None,
    ) -> MessageResult:
        try:
            if media_cache is not None and "media_obj" in media_cache:
                media_obj = media_cache["media_obj"]
            else:
                media_obj, error = await self._resolve_media_object(
                    media_source, media_type, recipient
                )
                if error is not None:
                    return error
                assert media_obj is not None
                if media_cache is not None:
                    media_cache["media_obj"] = media_obj

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
            result = message_result_from_payload(
                response,
                inbox_id=self._inbox_id,
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
                inbox_id=self._inbox_id,
                logger=self.logger,
            )

    # Interactive

    async def send_button_message(
        self,
        buttons: list[ReplyButton],
        target: DirectMessage,
        body: str,
        header: ButtonHeader | None = None,
        footer: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        return await self._deliver(
            target,
            lambda recipient: self.interactive_handler.send_buttons_menu(
                recipient=recipient,
                body=body,
                buttons=buttons,
                header=header,
                footer_text=footer,
                reply_to_message_id=reply_to_message_id,
            ),
        )

    async def send_list_message(
        self,
        sections: list[ListSection],
        target: DirectMessage,
        body: str,
        button_text: str,
        header: ButtonHeader | None = None,
        footer: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        return await self._deliver(
            target,
            lambda recipient: self.interactive_handler.send_list_menu(
                recipient=recipient,
                body=body,
                button_text=button_text,
                sections=sections,
                header=header,
                footer_text=footer,
                reply_to_message_id=reply_to_message_id,
            ),
        )

    async def send_cta_message(
        self,
        button_text: str,
        button_url: str,
        target: DirectMessage,
        body: str,
        header: str | None = None,
        footer: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        return await self._deliver(
            target,
            lambda recipient: self.interactive_handler.send_cta_button(
                recipient=recipient,
                body=body,
                button_text=button_text,
                button_url=button_url,
                header_text=header,
                footer_text=footer,
                reply_to_message_id=reply_to_message_id,
            ),
        )

    async def send_carousel(
        self,
        cards: Sequence[MessageCard],
        target: DirectMessage,
        body: str,
    ) -> MessageResult:
        """Interactive media carousel (2–10 cards, outside Templates).

        Each card needs ``image_url``; ``title`` + ``subtitle`` become the card
        body (≤ 160). Buttons are one ``UrlButton`` or 1–2 ``ReplyButton`` and
        must match in kind and count across cards (Meta rule). A reply-button
        tap arrives as an interactive ``button_reply`` with the button ``id``.
        """
        target.resolve_all(InboxRef.whatsapp(self._inbox_id))
        interactive = {
            "type": "carousel",
            "body": {"text": _wa_check(body, 1024, "WhatsApp carousel body")},
            "action": {"cards": _wa_cards(cards)},
        }
        return await self._deliver(
            require_direct_message(target, "WhatsApp send_carousel"),
            lambda recipient: self._send_carousel_to(recipient, interactive),
        )

    async def _send_carousel_to(
        self, recipient: str, interactive: dict[str, Any]
    ) -> MessageResult:
        payload: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "type": "interactive",
            "interactive": interactive,
        }
        try:
            apply_recipient_to_payload(payload, recipient)
            response = await self.client.post_request(payload)
            return message_result_from_payload(
                response, inbox_id=self._inbox_id, fallback_recipient=recipient
            )
        except Exception as e:
            return handle_whatsapp_error(
                error=e,
                operation="send carousel",
                recipient=recipient,
                inbox_id=self._inbox_id,
                logger=self.logger,
            )

    async def send_contact_request(
        self,
        body: str,
        target: DirectMessage,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        """Request a user's phone number through Meta's contact-info flow."""
        return await self._deliver(
            target,
            lambda recipient: self.interactive_handler.send_contact_request(
                recipient=recipient,
                body=body,
                reply_to_message_id=reply_to_message_id,
            ),
        )

    # Templates

    async def send_text_template(
        self,
        template_name: str,
        target: DirectMessage,
        body_parameters: list[dict] | None = None,
        language_code: str = "es",
        *,
        template_type: str,
        routing_policy: str = "category_default",
        authentication_method: str | None = None,
        authentication_button_index: int = 0,
    ) -> MessageResult:
        target.resolve_all(InboxRef.whatsapp(self._inbox_id))
        template_type_enum = self._parse_template_type(template_type)
        if template_type_enum is None:
            return self._error_result(
                f"Invalid template type: {template_type}", "INVALID_TEMPLATE_TYPE"
            )
        return await self._deliver(
            target,
            lambda recipient: self.template_handler.send_text_template(
                recipient=recipient,
                template_name=template_name,
                body_parameters=self._convert_body_parameters(body_parameters),
                language_code=language_code,
                template_type=template_type_enum,
                routing_policy=routing_policy,
                authentication_method=authentication_method,
                authentication_button_index=authentication_button_index,
            ),
            phone_only=template_type_enum is WhatsAppTemplateType.AUTHENTICATION,
        )

    async def send_media_template(
        self,
        template_name: str,
        target: DirectMessage,
        media_type: str,
        media_id: str | None = None,
        media_url: str | None = None,
        body_parameters: list[dict] | None = None,
        language_code: str = "es",
        *,
        template_type: str,
        routing_policy: str = "category_default",
    ) -> MessageResult:
        target.resolve_all(InboxRef.whatsapp(self._inbox_id))
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

        return await self._deliver(
            target,
            lambda recipient: self.template_handler.send_media_template(
                recipient=recipient,
                template_name=template_name,
                media_type=media_type_enum,
                media_id=media_id,
                media_url=media_url,
                body_parameters=self._convert_body_parameters(body_parameters),
                language_code=language_code,
                template_type=template_type_enum,
                routing_policy=routing_policy,
            ),
        )

    async def send_location_template(
        self,
        template_name: str,
        target: DirectMessage,
        latitude: str,
        longitude: str,
        name: str,
        address: str,
        body_parameters: list[dict] | None = None,
        language_code: str = "es",
        *,
        template_type: str,
        routing_policy: str = "category_default",
    ) -> MessageResult:
        target.resolve_all(InboxRef.whatsapp(self._inbox_id))
        template_type_enum = self._parse_template_type(template_type)
        if template_type_enum is None:
            return self._error_result(
                f"Invalid template type: {template_type}", "INVALID_TEMPLATE_TYPE"
            )
        return await self._deliver(
            target,
            lambda recipient: self.template_handler.send_location_template(
                recipient=recipient,
                template_name=template_name,
                latitude=latitude,
                longitude=longitude,
                name=name,
                address=address,
                body_parameters=self._convert_body_parameters(body_parameters),
                language_code=language_code,
                template_type=template_type_enum,
                routing_policy=routing_policy,
            ),
        )

    # Specialized

    async def send_contact(
        self,
        contact: ContactCard,
        target: DirectMessage,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        target.resolve_all(InboxRef.whatsapp(self._inbox_id))
        return await self._deliver(
            target,
            lambda recipient: self.specialized_handler.send_contact_card(
                recipient=recipient,
                contact=contact,
                reply_to_message_id=reply_to_message_id,
            ),
        )

    async def send_location(
        self,
        latitude: float,
        longitude: float,
        target: DirectMessage,
        name: str | None = None,
        address: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        return await self._deliver(
            target,
            lambda recipient: self.specialized_handler.send_location(
                recipient=recipient,
                latitude=latitude,
                longitude=longitude,
                name=name,
                address=address,
                reply_to_message_id=reply_to_message_id,
            ),
        )

    async def send_location_request(
        self, body: str, target: DirectMessage, reply_to_message_id: str | None = None
    ) -> MessageResult:
        return await self._deliver(
            target,
            lambda recipient: self.specialized_handler.send_location_request(
                recipient=recipient, body=body, reply_to_message_id=reply_to_message_id
            ),
        )


def _wa_check(value: str, limit: int, what: str) -> str:
    if not value or not value.strip():
        raise ValueError(f"{what} must not be empty")
    if len(value) > limit:
        raise ValueError(f"{what} is {len(value)} characters; limit is {limit}")
    return value


WHATSAPP_STICKER_SUFFIXES = frozenset({".webp"})
WHATSAPP_AUDIO_SUFFIXES = frozenset({".aac", ".amr", ".mp3", ".m4a", ".ogg"})
WHATSAPP_VOICE_SUFFIXES = frozenset({".ogg"})


def _wa_cards(cards: Sequence[MessageCard]) -> list[dict[str, Any]]:
    if not 2 <= len(cards) <= 10:
        raise ValueError(
            "Carousels need 2–10 cards; for one card use send_button_message "
            "with an image header"
        )
    shapes = {
        (
            isinstance(c.buttons[0], UrlButton) if c.buttons else None,
            len(c.buttons),
        )
        for c in cards
    }
    if len(shapes) != 1:
        raise ValueError(
            "WhatsApp carousel cards must all use the same button kind and count"
        )
    out: list[dict[str, Any]] = []
    for index, card in enumerate(cards):
        if card.image_url is None:
            raise ValueError("WhatsApp carousel cards need image_url")
        text = "\n".join(p for p in (card.title, card.subtitle) if p)
        url_buttons = [b for b in card.buttons if isinstance(b, UrlButton)]
        replies = [b for b in card.buttons if isinstance(b, ReplyButton)]
        if url_buttons and (replies or len(url_buttons) > 1):
            raise ValueError(
                "A WhatsApp carousel card has one URL button or reply buttons"
            )
        if not card.buttons:
            raise ValueError("WhatsApp carousel cards need at least one button")
        element: dict[str, Any] = {
            "card_index": index,
            # Meta requires type on every card and documents "cta_url" for
            # quick-reply cards too; omitting it is a 400 (code 100).
            "type": "cta_url",
            "header": {"type": "image", "image": {"link": str(card.image_url)}},
            "body": {"text": _wa_check(text, 160, "WhatsApp carousel card text")},
        }
        if url_buttons:
            element["action"] = {
                "name": "cta_url",
                "parameters": {
                    "display_text": url_buttons[0].title,
                    "url": str(url_buttons[0].url),
                },
            }
        else:
            if len(replies) > 2:
                raise ValueError(
                    "WhatsApp carousel cards allow at most 2 reply buttons"
                )
            element["action"] = {
                "buttons": [
                    {
                        "type": "quick_reply",
                        "quick_reply": {"id": b.id, "title": b.title},
                    }
                    for b in replies
                ]
            }
        out.append(element)
    return out
