"""Instagram text message, including story replies."""

from __future__ import annotations

from pydantic import ConfigDict

from wappa.schemas.core.types import UniversalMessageData
from wappa.webhooks.core.base_message import BaseTextMessage

from ._base import InstagramMessageBase


class InstagramTextMessage(InstagramMessageBase, BaseTextMessage):
    """Text, including story replies (``context.is_story_reply``)."""

    model_config = ConfigDict(extra="allow", str_strip_whitespace=False)

    text: str

    @property
    def text_content(self) -> str:
        return self.text

    @property
    def is_reply(self) -> bool:
        return bool(self.context and self.context.is_reply)

    @property
    def is_forwarded(self) -> bool:
        return False

    def get_reply_context(self) -> tuple[str | None, str | None]:
        if self.context is None:
            return None, None
        return self.context.reply_to_message_id, None

    def to_universal_dict(self) -> UniversalMessageData:
        from wappa.webhooks.core.base_message.projections import text_projection

        return text_projection(self)
