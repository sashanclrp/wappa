"""Instagram audio message."""

from __future__ import annotations

from pydantic import ConfigDict

from wappa.schemas.core.types import MediaType
from wappa.webhooks.core.base_message import BaseAudioMessage

from ._attachment import InstagramAttachmentMessage


class InstagramAudioMessage(InstagramAttachmentMessage, BaseAudioMessage):
    model_config = ConfigDict(extra="allow", str_strip_whitespace=False)

    @property
    def media_type(self) -> MediaType:
        return MediaType.AUDIO_AAC

    @property
    def is_voice_message(self) -> bool:
        return True

    @property
    def duration(self) -> int | None:
        return None
