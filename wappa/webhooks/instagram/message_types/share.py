"""Instagram shared post, Reel or story, and story mentions delivered as a DM."""

from __future__ import annotations

from pydantic import ConfigDict

from wappa.schemas.core.types import MessageType, UniversalMessageData

from ._attachment import InstagramAttachmentMessage


class InstagramShareMessage(InstagramAttachmentMessage):
    """Shared post/Reel/story or a story mention delivered as a DM.

    ``shared_media_id`` is set only when the provider supplied it; a URL-only
    share stays processable and is not resolved here.
    """

    model_config = ConfigDict(extra="allow", str_strip_whitespace=False)

    @property
    def message_type(self) -> MessageType:
        if self.attachment_type == "story_mention":
            return MessageType.STORY_MENTION
        return MessageType.SHARE

    @property
    def is_story_mention(self) -> bool:
        return self.attachment_type == "story_mention"

    @property
    def shared_media_id(self) -> str | None:
        payload = self.primary.payload
        if payload is None:
            return None
        return payload.ig_post_media_id or payload.reel_video_id

    @property
    def title(self) -> str | None:
        return self.primary.payload.title if self.primary.payload else None

    def to_universal_dict(self) -> UniversalMessageData:
        return self._universal(
            attachment_type=self.attachment_type,
            url=self.url,
            shared_media_id=self.shared_media_id,
            text=self.text,
        )
