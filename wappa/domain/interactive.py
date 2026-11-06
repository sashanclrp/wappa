"""Platform-neutral Interactive Message values (ADR-0016).

``ReplyButton`` is the one "choose this option" value on every Platform. A tap
returns as an ``InboundMessageWebhook`` whose ``get_interactive_selection()`` is
the button ``id``: a WhatsApp ``button_reply``, or an Instagram postback.
``UrlButton`` opens a page and produces no webhook. ``MessageCard`` is one card
of ``send_carousel``. ``ButtonHeader`` heads a button or list message, and
``ListSection``/``ListRow`` are the options of ``send_list_message``; a row tap
returns its ``id`` as the selection. Each adapter validates its own native limits before I/O
and rejects what it cannot deliver; nothing here is a wire format.
"""

from typing import Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    field_validator,
    model_validator,
)


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


class ButtonHeader(BaseModel):
    """Header of a button or list message: text, or one image.

    Set exactly one of ``text``, ``image_url`` or ``image_media_id`` (a media
    ID the Inbox's own Platform issued). Each adapter maps the header to its
    wire shape and rejects a kind it cannot deliver; video and document
    headers are not neutral and are not offered here.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    text: str | None = Field(default=None, min_length=1)
    image_url: HttpUrl | None = None
    image_media_id: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _exactly_one(self) -> Self:
        chosen = [
            v for v in (self.text, self.image_url, self.image_media_id) if v is not None
        ]
        if len(chosen) != 1:
            raise ValueError(
                "ButtonHeader needs exactly one of text, image_url or image_media_id"
            )
        if self.text is not None:
            _nonblank(self.text)
        return self

    @property
    def kind(self) -> Literal["text", "image"]:
        return "text" if self.text is not None else "image"


class ListRow(BaseModel):
    """One selectable option of a list message; ``id`` returns as the selection."""

    id: str = Field(..., min_length=1, description="Unique row identifier")
    title: str = Field(..., min_length=1, description="Row title")
    description: str | None = Field(None, description="Optional row description")


class ListSection(BaseModel):
    """A titled group of rows; row IDs are unique within the section."""

    title: str = Field(..., description="Section title")
    rows: list[ListRow] = Field(..., min_length=1, description="Rows in the section")

    @field_validator("rows")
    @classmethod
    def _unique_row_ids(cls, v: list[ListRow]) -> list[ListRow]:
        row_ids = [row.id for row in v]
        if len(row_ids) != len(set(row_ids)):
            raise ValueError("Row IDs must be unique within section")
        return v


__all__ = [
    "ButtonHeader",
    "CardButton",
    "ListRow",
    "ListSection",
    "MessageCard",
    "ReplyButton",
    "UrlButton",
]
