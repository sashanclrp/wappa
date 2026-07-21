"""WhatsApp edit and revoke message webhook models."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from wappa.schemas.core.types import (
    ConversationType,
    MessageType,
    PlatformType,
    UniversalMessageData,
)
from wappa.webhooks.core.base_message import BaseMessage, BaseMessageContext
from wappa.webhooks.whatsapp.base_models import WhatsAppMessageIdentity


class RevokeContent(BaseMessageContext):
    """Reference to the message removed by the user."""

    original_id: str = Field(alias="original_message_id")

    @property
    def original_message_id(self) -> str:
        return self.original_id

    @property
    def original_sender_id(self) -> None:
        return None

    @property
    def is_reply(self) -> bool:
        return False

    @property
    def is_forward(self) -> bool:
        return False

    def to_universal_dict(self) -> dict[str, Any]:
        return {"original_message_id": self.original_id}


class EditedMessageContext(BaseMessageContext):
    """Context carried by the replacement message inside an edit."""

    id: str

    @property
    def original_message_id(self) -> str:
        return self.id

    @property
    def original_sender_id(self) -> None:
        return None

    @property
    def is_reply(self) -> bool:
        return True

    @property
    def is_forward(self) -> bool:
        return False

    def to_universal_dict(self) -> dict[str, Any]:
        return {"original_message_id": self.id}


class EditedMessage(BaseModel):
    """Replacement message nested inside Meta's edit object."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    context: EditedMessageContext | None = None
    type: str
    text: dict[str, Any] | None = None
    image: dict[str, Any] | None = None
    audio: dict[str, Any] | None = None
    video: dict[str, Any] | None = None
    document: dict[str, Any] | None = None
    sticker: dict[str, Any] | None = None
    contacts: list[dict[str, Any]] | None = None
    location: dict[str, Any] | None = None
    interactive: dict[str, Any] | None = None


class EditContent(BaseMessageContext):
    """Original ID and replacement content for an edited message."""

    original_id: str = Field(alias="original_message_id")
    message: EditedMessage

    @property
    def original_message_id(self) -> str:
        return self.original_id

    @property
    def original_sender_id(self) -> None:
        return None

    @property
    def is_reply(self) -> bool:
        return False

    @property
    def is_forward(self) -> bool:
        return False

    def to_universal_dict(self) -> dict[str, Any]:
        return {
            "original_message_id": self.original_id,
            "message": self.message.model_dump(),
        }


class WhatsAppLifecycleMessage(WhatsAppMessageIdentity, BaseMessage):
    """Shared implementation for consumer edit and revoke webhooks."""

    from_: str | None = Field(default=None, alias="from")
    from_bsuid: str | None = Field(default=None, alias="from_user_id")
    id: str
    timestamp_str: str = Field(alias="timestamp")
    type: Literal["edit", "revoke"]
    edit: EditContent | None = None
    revoke: RevokeContent | None = None

    @model_validator(mode="after")
    def require_matching_content(self) -> "WhatsAppLifecycleMessage":
        if self.type == "edit" and (self.edit is None or self.revoke is not None):
            raise ValueError("edit messages require only an edit object")
        if self.type == "revoke" and (self.revoke is None or self.edit is not None):
            raise ValueError("revoke messages require only a revoke object")
        return self

    @property
    def platform(self) -> PlatformType:
        return PlatformType.WHATSAPP

    @property
    def message_type(self) -> MessageType:
        return MessageType(self.type)

    @property
    def message_id(self) -> str:
        return self.id

    @property
    def sender_id(self) -> str:
        return self.from_bsuid or self.from_ or ""

    @property
    def timestamp(self) -> int:
        return int(self.timestamp_str)

    @property
    def conversation_id(self) -> str:
        return self.group_id or self.sender_id

    @property
    def conversation_type(self) -> ConversationType:
        return ConversationType.GROUP if self.group_id else ConversationType.PRIVATE

    def has_context(self) -> bool:
        return self.edit is not None or self.revoke is not None

    def get_context(self) -> BaseMessageContext | None:
        return self.edit or self.revoke

    def to_universal_dict(self) -> UniversalMessageData:
        content = self.edit or self.revoke
        return {
            "message_id": self.id,
            "message_type": self.type,
            "sender_id": self.sender_id,
            "timestamp": self.timestamp,
            "content": content.to_universal_dict() if content else None,
            "whatsapp_data": self.get_platform_data(),
        }

    def get_platform_data(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, exclude={"processed_at"})

    @classmethod
    def from_platform_data(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "WhatsAppLifecycleMessage":
        return cls.model_validate(data)
