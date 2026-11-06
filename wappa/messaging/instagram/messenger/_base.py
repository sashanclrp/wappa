"""Shared typed surface of the Instagram Messenger mixins (ADR-0016).

Each mixin inherits this class so mypy sees the attributes ``adapter.py`` sets
and the helpers the mixins call on one another; the real implementations live
in the mixin modules named beside each stub.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from wappa.domain.inbox.identity import InboxRef
from wappa.domain.interfaces.sent_message_registry import ISentMessageRegistry
from wappa.domain.messaging_targets import DirectMessage, MessageTarget
from wappa.domain.results import MessageResult
from wappa.schemas.core.types import PlatformType

from ..client import InstagramClient
from ..media.library import InstagramMediaLibrary


class _InstagramBase:
    _inbox_ref: InboxRef
    _sent_registry: ISentMessageRegistry | None
    _graph: InstagramClient
    _media: InstagramMediaLibrary

    if TYPE_CHECKING:

        @property
        def platform(self) -> PlatformType: ...

        @property
        def inbox_id(self) -> str: ...

        # delivery.py
        async def _send(
            self,
            target: MessageTarget,
            message: dict[str, Any],
            *,
            operation: str,
            reply_to_message_id: str | None = None,
        ) -> MessageResult: ...

        def _direct(self, target: DirectMessage, operation: str) -> DirectMessage: ...

        # text.py
        async def send_text(
            self,
            text: str,
            target: MessageTarget,
            reply_to_message_id: str | None = None,
            disable_preview: bool = False,
        ) -> MessageResult: ...

        async def _send_texts(
            self,
            text: str,
            direct: DirectMessage,
            reply_to_message_id: str | None,
            last: dict[str, Any] | None = None,
            operation: str = "Instagram text send",
        ) -> MessageResult: ...

        # media.py
        async def _send_media(
            self,
            family: str,
            source: str | Path,
            target: DirectMessage,
            reply_to_message_id: str | None,
            *,
            filename: str | None = None,
        ) -> MessageResult: ...
