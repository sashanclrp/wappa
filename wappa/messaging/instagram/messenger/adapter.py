"""Inbox-bound Instagram Messenger (Unified Login, Graph v26.0).

Native wire formats (``POST /{ig-account-id}/messages``):

- text: ``{"recipient": {"id"}, "message": {"text"}}`` (≤ 1000 UTF-8 bytes)
- private reply: ``{"recipient": {"comment_id"}, "message": {"text"}}``
- media: ``message.attachment = {"type": image|audio|video|file,
  "payload": {"url"}}`` or ``{"attachment_id"}`` after upload
Contract mappings (ADR-0025: one Messenger method per action):

- ``send_text`` → text over 1000 UTF-8 bytes is split into several messages,
  on a word boundary when possible
- ``send_button_message`` → ``template_type = button`` with ``postback``
  buttons (text ≤ 640, 1–3); a media header is sent first as its own
  attachment
- ``send_list_message`` → ``message.quick_replies[]`` on the (last) text;
  section titles and row descriptions fold into the text as a numbered menu
- ``send_cta_message`` → ``template_type = button`` with one ``web_url``; a
  media header is sent first as its own attachment
- ``send_carousel`` → intro text, then ``template_type = generic`` (2–10); a
  video card shows its poster image and opens the video on tap
- ``mark_as_read`` → ``sender_action`` ``mark_seen`` then ``typing_on``
- ``resolve_platform_user_profile`` → ``GET /{igsid}?fields=name,username,
  profile_pic`` merged over the webhook evidence; a failure returns the
  evidence with the failure outcome
- media by http(s) URL, by ``IMediaLibrary.upload`` attachment_id, or a
  ``Path`` (uploaded first, under ``filename`` for a document); a document
  URL whose format Instagram does not take is sent as a text with the file
  name and the link, while an audio or video URL Instagram cannot play raises
  ``ValueError`` before any call (as on WhatsApp)
- ``send_location`` / ``send_contact`` → text (maps link / one block per card);
  ``send_sticker`` → image
- ``IUserDataRequests`` (location / phone-number requests) → not provided
  (``self.whatsapp`` is ``None`` here; a text prompt would not return the data)
- reply: top-level ``reply_to: {"mid"}``

Known local constraints are rejected before I/O; provider refusals and
unknown outcomes are returned, never retried.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
from pydantic import SecretStr

from wappa.domain.inbox.identity import InboxRef
from wappa.domain.interfaces.conversation_capabilities import (
    ICommentControls,
    IConversationContentReader,
)
from wappa.domain.interfaces.history_reader import IConversationHistoryReader
from wappa.domain.interfaces.media_library import IMediaLibrary
from wappa.domain.interfaces.messaging_interface import IMessenger
from wappa.domain.interfaces.sent_message_registry import ISentMessageRegistry
from wappa.schemas.core.types import PlatformType

from ..capabilities.comments import InstagramCommentControls
from ..capabilities.content import InstagramContentReader
from ..capabilities.history import InstagramHistoryReader
from ..client import InstagramClient
from ..media.library import InstagramMediaLibrary
from ..media.transport import InstagramAttachmentReader
from .delivery import _DeliveryMixin
from .interactive import _InteractiveMixin
from .media import _MediaMixin
from .profile import _ProfileMixin
from .receipts import _ReceiptsMixin
from .specialized import _SpecializedMixin
from .text import _TextMixin


class InstagramMessengerAdapter(
    _TextMixin,
    _MediaMixin,
    _InteractiveMixin,
    _SpecializedMixin,
    _ReceiptsMixin,
    _ProfileMixin,
    _DeliveryMixin,
    IMessenger,
):
    """One professional account; lifecycle-owned HTTP and no automatic retries."""

    """One professional account; lifecycle-owned HTTP and no automatic retries."""

    _OPERATIONS = frozenset(
        {
            "send_text",
            "send_text:private_reply",
            "send_image",
            "send_audio",
            "send_video",
            "send_document",
            "send_button_message",
            "send_list_message",
            "send_cta_message",
            "send_carousel",
            "mark_as_read",
            "send_sticker",
            "send_location",
            "send_contact",
            "resolve_platform_user_profile",
        }
    )

    CAPABILITY_TYPES = frozenset(
        {
            ICommentControls,
            IConversationContentReader,
            IMediaLibrary,
            IConversationHistoryReader,
        }
    )

    def __init__(
        self,
        *,
        inbox_ref: InboxRef,
        access_token: SecretStr,
        session_provider: Callable[[], httpx.AsyncClient],
        graph_api_version: str,
        graph_base_url: str,
        media_download_client_provider: Callable[[], httpx.AsyncClient] | None = None,
        sent_registry: ISentMessageRegistry | None = None,
    ) -> None:
        if inbox_ref.platform is not PlatformType.INSTAGRAM:
            raise ValueError("InstagramMessengerAdapter requires an Instagram Inbox")
        self._inbox_ref = inbox_ref
        # Instagram echoes Wappa's own sends; recording them lets the Inbound
        # Runtime drop those echoes (ADR-0023).
        self._sent_registry = sent_registry
        self._graph = InstagramClient(
            inbox_ref=inbox_ref,
            access_token=access_token,
            session_provider=session_provider,
            graph_api_version=graph_api_version,
            graph_base_url=graph_base_url,
        )
        self._media = InstagramMediaLibrary(
            self._graph,
            InstagramAttachmentReader(
                media_download_client_provider or session_provider
            ),
        )
        # Instagram-only actions (ADR-0025 exceptions), capability-gated.
        self._capabilities = {
            ICommentControls: InstagramCommentControls(self._graph),
            IConversationContentReader: InstagramContentReader(self._graph),
            IMediaLibrary: self._media,
            IConversationHistoryReader: InstagramHistoryReader(self._graph),
        }

    # ── identity / discovery ────────────────────────────────────────────

    @property
    def platform(self) -> PlatformType:
        return PlatformType.INSTAGRAM

    @property
    def inbox_id(self) -> str:
        return self._inbox_ref.inbox_id

    @property
    def inbox_ref(self) -> InboxRef:
        return self._inbox_ref

    @property
    def supported_operations(self) -> frozenset[str]:
        return self._OPERATIONS
