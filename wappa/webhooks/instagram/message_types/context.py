"""Instagram reply context: an earlier message or a story the User replied to."""

from __future__ import annotations

from typing import Any

from pydantic import ConfigDict

from wappa.webhooks.core.base_message import BaseMessageContext


class InstagramMessageContext(BaseMessageContext):
    """Reply context: an earlier message or a story the User replied to."""

    model_config = ConfigDict(extra="allow")
    reply_to_message_id: str | None = None
    story_id: str | None = None
    story_url: str | None = None

    @property
    def original_message_id(self) -> str | None:
        return self.reply_to_message_id

    @property
    def original_sender_id(self) -> str | None:
        return None

    @property
    def is_reply(self) -> bool:
        return self.reply_to_message_id is not None or self.story_id is not None

    @property
    def is_forward(self) -> bool:
        return False

    @property
    def is_story_reply(self) -> bool:
        return self.story_id is not None or self.story_url is not None

    def to_universal_dict(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)
