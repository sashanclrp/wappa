"""Platform-neutral Interactive Message values (ADR-0016).

``ReplyButton`` is the one "choose this option" value on every Platform. A tap
returns as an ``InboundMessageWebhook`` whose ``get_interactive_selection()`` is
the button ``id``: a WhatsApp ``button_reply``, or an Instagram postback.
``UrlButton`` opens a page and produces no webhook. ``MessageCard`` is one card
of ``send_carousel``. Each adapter validates its own native limits before I/O
and rejects what it cannot deliver; nothing here is a wire format.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


def _nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("value must not be blank")
    return value


class ReplyButton(BaseModel):
    """A tappable option: ``title`` is shown, ``id`` returns as the selection."""

    id: str = Field(..., max_length=256, description="Unique button identifier")
    title: str = Field(..., max_length=20, description="Button display text")


class UrlButton(BaseModel):
    """A button that opens a web page; it produces no webhook on tap."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["web_url"] = "web_url"
    title: str = Field(min_length=1, max_length=20)
    url: HttpUrl

    _check = field_validator("title")(_nonblank)


CardButton = ReplyButton | UrlButton


class MessageCard(BaseModel):
    """One carousel card: image, title, optional subtitle and buttons.

    WhatsApp requires ``image_url`` and renders ``title`` + ``subtitle`` as the
    card body (≤ 160 chars); Instagram shows them as card title and subtitle
    (≤ 80 each). ``default_url`` (tap on the card itself) is Instagram-only
    presentation and is ignored where unsupported.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    title: str = Field(min_length=1)
    subtitle: str | None = None
    image_url: HttpUrl | None = None
    default_url: HttpUrl | None = None
    buttons: tuple[CardButton, ...] = ()

    _check = field_validator("title")(_nonblank)


__all__ = ["CardButton", "MessageCard", "ReplyButton", "UrlButton"]
