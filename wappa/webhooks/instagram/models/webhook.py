"""Instagram ``object: instagram`` callback envelope: change, entry and webhook.

The envelope carries ``entry[].messaging[]`` (DM events) and/or
``entry[].changes[]`` (``comments``, ``live_comments``, ``mentions`` and
extension fields). Provider extensions are retained but never promote an
event into a different lane (echo/deletion/edit/postback stay separate).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .messaging import InstagramMessagingEvent


class InstagramChange(BaseModel):
    """One ``changes[]`` item; ``value`` is parsed per field by the processor."""

    model_config = ConfigDict(extra="allow")
    field: str = Field(min_length=1)
    value: dict[str, Any]


class InstagramEntry(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str = Field(min_length=1)
    time: int | None = None
    messaging: list[InstagramMessagingEvent] = Field(default_factory=list)
    changes: list[InstagramChange] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _flat_change(cls, data: Any) -> Any:
        # The Instagram Login doc example shows field/value directly on entry.
        if isinstance(data, dict) and "field" in data and "value" in data:
            data = dict(data)
            change = {"field": data.pop("field"), "value": data.pop("value")}
            data["changes"] = [*data.get("changes", []), change]
        return data

    @model_validator(mode="after")
    def _has_events(self) -> InstagramEntry:
        if not self.messaging and not self.changes:
            raise ValueError("Instagram entry carries no messaging events or changes")
        return self


class InstagramWebhook(BaseModel):
    """The ``object: instagram`` callback envelope; no container ABC."""

    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, validate_assignment=True
    )

    object: Literal["instagram"]
    entry: list[InstagramEntry] = Field(min_length=1)
