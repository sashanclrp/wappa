"""Shared identity for every Instagram User message."""

from __future__ import annotations

from typing import Any

from pydantic import ConfigDict, PositiveInt

from wappa.schemas.core.types import PlatformType, UniversalMessageData
from wappa.webhooks.core.base_message import BaseMessage, BaseMessageContext

from .context import InstagramMessageContext


class InstagramMessageBase(BaseMessage):
    """Shared identity for every Instagram User message."""

    model_config = ConfigDict(extra="allow", str_strip_whitespace=False)
    id: str
    sender: str
    account_id: str
    timestamp_ms: PositiveInt
    context: InstagramMessageContext | None = None

    @classmethod
    def from_platform_data(cls, data: dict[str, Any], **kwargs: Any) -> Any:
        return cls.model_validate(data)

    @property
    def platform(self) -> PlatformType:
        return PlatformType.INSTAGRAM

    @property
    def message_id(self) -> str:
        return self.id

    @property
    def sender_id(self) -> str:
        return self.sender

    @property
    def timestamp(self) -> int:
        return self.timestamp_ms // 1000

    @property
    def conversation_id(self) -> str:
        return self.sender

    def has_context(self) -> bool:
        return self.context is not None

    def get_context(self) -> BaseMessageContext | None:
        return self.context

    def get_platform_data(self) -> dict[str, Any]:
        return self.model_dump()

    def _universal(self, **extra: Any) -> UniversalMessageData:
        data: dict[str, Any] = {
            "platform": self.platform.value,
            "message_type": self.message_type.value,
            "message_id": self.id,
            "sender_id": self.sender,
            "timestamp": self.timestamp,
            **{k: v for k, v in extra.items() if v is not None},
        }
        return data
