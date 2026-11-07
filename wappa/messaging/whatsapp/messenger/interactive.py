"""Interactive sends: reply buttons, list, CTA URL and media carousel."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from wappa.domain.inbox.identity import InboxRef
from wappa.domain.interactive import (
    InteractiveHeader,
    ListSection,
    MessageCard,
    ReplyButton,
    check_button_message,
    check_carousel,
    check_cta_message,
    check_list_message,
)
from wappa.domain.messaging_targets import DirectMessage, require_direct_message
from wappa.domain.results import MessageResult
from wappa.messaging.whatsapp.errors import handle_whatsapp_error
from wappa.messaging.whatsapp.media.rules import check_name
from wappa.messaging.whatsapp.messenger.delivery import _DeliveryMixin
from wappa.messaging.whatsapp.models.basic_models import message_result_from_payload
from wappa.messaging.whatsapp.payloads.interactive import (
    build_interactive_payload,
    buttons_interactive,
    carousel_interactive,
    cta_interactive,
    interactive_envelope,
    list_interactive,
    wa_header,
)
from wappa.schemas.core.recipient import apply_recipient_to_payload


class _InteractiveMixin(_DeliveryMixin):
    async def send_button_message(
        self,
        buttons: list[ReplyButton],
        target: DirectMessage,
        body: str,
        header: InteractiveHeader | None = None,
        footer: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        check_button_message(buttons, body, footer)
        return await self._deliver(
            target,
            lambda recipient: self._send_buttons_to(
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
        header: str | None = None,
        footer: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        check_list_message(sections, body, button_text, header, footer)
        return await self._deliver(
            target,
            lambda recipient: self._send_list_to(
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
        header: InteractiveHeader | None = None,
        footer: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        check_cta_message(button_text, button_url, body, footer)
        return await self._deliver(
            target,
            lambda recipient: self._send_cta_to(
                recipient=recipient,
                body=body,
                button_text=button_text,
                button_url=button_url,
                header=header,
                footer_text=footer,
                reply_to_message_id=reply_to_message_id,
            ),
        )

    async def send_carousel(
        self,
        cards: Sequence[MessageCard],
        target: DirectMessage,
        body: str,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        """Interactive media carousel (2–10 cards, outside Templates).

        Each card needs a ``header`` (image or video, by public ``url`` only:
        Meta documents carousel card headers as a ``link``, no Media ID);
        ``title`` + ``subtitle`` become the card body. Buttons are one
        ``UrlButton`` or 1–2 ``ReplyButton`` and must match in kind and count
        across cards (Meta rule). A reply-button tap arrives as an interactive
        ``button_reply`` with the button ``id``.
        """
        check_carousel(cards, body)
        for card in cards:  # one bad card fails the whole carousel (131053)
            check_name(str(card.header.url), card.header.kind)
        target.resolve_all(InboxRef.whatsapp(self._inbox_id))
        interactive = carousel_interactive(cards, body)
        return await self._deliver(
            require_direct_message(target, "WhatsApp send_carousel"),
            lambda recipient: self._send_carousel_to(
                recipient, interactive, reply_to_message_id
            ),
        )

    async def _send_carousel_to(
        self,
        recipient: str,
        interactive: dict[str, Any],
        reply_to_message_id: str | None,
    ) -> MessageResult:
        payload = interactive_envelope(interactive, reply_to_message_id)
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

    async def _send_buttons_to(
        self,
        recipient: str,
        body: str,
        buttons: list[ReplyButton],
        header: InteractiveHeader | None = None,
        footer_text: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        """Limits are checked by the neutral values and ``check_button_message``."""
        try:
            payload = build_interactive_payload(
                recipient=recipient,
                interactive_data=buttons_interactive(
                    body, buttons, header, footer_text
                ),
                reply_to_message_id=reply_to_message_id,
            )

            self.logger.debug(
                f"Sending interactive button menu with {len(buttons)} buttons"
            )
            result = await self._post_payload(payload, recipient)
            self.logger.info(
                f"Interactive button menu sent successfully, id: {result.message_id}"
            )
            return result

        except Exception as e:
            return handle_whatsapp_error(
                error=e,
                operation="send interactive button menu",
                recipient=recipient,
                inbox_id=self._inbox_id,
                logger=self.logger,
            )

    async def _send_list_to(
        self,
        recipient: str,
        body: str,
        button_text: str,
        sections: list[ListSection],
        header: str | None = None,
        footer_text: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        """Limits are checked by the neutral values and ``check_list_message``."""
        try:
            payload = build_interactive_payload(
                recipient=recipient,
                interactive_data=list_interactive(
                    body, button_text, sections, header, footer_text
                ),
                reply_to_message_id=reply_to_message_id,
            )
            self.logger.debug(
                f"Sending list menu message with {len(sections)} sections"
            )
            result = await self._post_payload(payload, recipient)
            self.logger.info(
                f"List menu message sent successfully, id: {result.message_id}"
            )
            return result

        except Exception as e:
            return handle_whatsapp_error(
                error=e,
                operation="send list menu",
                recipient=recipient,
                inbox_id=self._inbox_id,
                logger=self.logger,
                extra_context=f"button_text: '{button_text}', sections_count: {len(sections)}, body_length: {len(body)}",
                include_traceback=True,
            )

    async def _send_cta_to(
        self,
        recipient: str,
        body: str,
        button_text: str,
        button_url: str,
        header: InteractiveHeader | None = None,
        footer_text: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        """Limits are checked by ``check_cta_message`` before this call."""
        try:
            payload = build_interactive_payload(
                recipient=recipient,
                interactive_data=cta_interactive(body, button_text, button_url),
                reply_to_message_id=reply_to_message_id,
            )
            if header:
                payload["interactive"]["header"] = wa_header(header)
            if footer_text:
                payload["interactive"]["footer"] = {"text": footer_text}

            self.logger.debug(f"Sending CTA button message with URL: {button_url}")
            result = await self._post_payload(payload, recipient)
            self.logger.info(
                f"CTA button message sent successfully, id: {result.message_id}"
            )
            return result

        except Exception as e:
            return handle_whatsapp_error(
                error=e,
                operation="send CTA button message",
                recipient=recipient,
                inbox_id=self._inbox_id,
                logger=self.logger,
            )
