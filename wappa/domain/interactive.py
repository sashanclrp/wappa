"""Platform-neutral Interactive Message values (ADR-0016).

``ReplyButton`` is the one "choose this option" value on every Platform. A tap
returns as an ``InboundMessageWebhook`` whose ``get_interactive_selection()`` is
the button ``id``: a WhatsApp ``button_reply``, or an Instagram postback.
``UrlButton`` opens a page and produces no webhook. ``MessageCard`` is one card
of ``send_carousel``. ``InteractiveHeader`` heads a button message (text, or an
image, video or document by URL or media ID, as in the WhatsApp Cloud API), and
``ListSection``/``ListRow`` are the options of ``send_list_message``; a row tap
returns its ``id`` as the selection.

The shape follows WhatsApp; every limit is the most restrictive one across the
installed Platforms (the constants below) and is enforced when the value is
built, so a value that constructs is deliverable on every Platform. Plain
``body``/``footer``/``sections`` arguments are checked by
``check_button_message`` and ``check_list_message`` before any Platform call.
Nothing here is a wire format.
"""

from collections.abc import Sequence
from typing import Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    field_validator,
    model_validator,
)

# ── Interactive limits: the minimum across WhatsApp and Instagram ───────────
# Characters unless noted. "folded" means Instagram has no slot and joins the
# value into the message text; "not shown" means Instagram has no slot at all.
BUTTON_TITLE_MAX = 20  # WhatsApp reply title 20; Instagram postback title 20
BUTTON_ID_MAX = 256  # WhatsApp reply id 256; Instagram postback payload 1000
BUTTONS_MAX = 3  # WhatsApp 3 reply buttons; Instagram button template 3
HEADER_TEXT_MAX = 60  # WhatsApp header text 60; Instagram folded
FOOTER_MAX = 60  # WhatsApp footer 60; Instagram folded
BUTTON_BODY_MAX = 640  # WhatsApp button body 1024; Instagram button template text 640
LIST_BODY_MAX = 1000  # WhatsApp list body 4096; Instagram text 1000 UTF-8 bytes
LIST_BUTTON_TEXT_MAX = 20  # WhatsApp list opener 20; Instagram not shown
LIST_SECTIONS_MAX = 10  # WhatsApp 10 sections; Instagram flattens to quick replies
LIST_ROWS_MAX = 10  # WhatsApp 10 rows in total; Instagram 13 quick replies
SECTION_TITLE_MAX = 24  # WhatsApp section title 24; Instagram not shown
ROW_ID_MAX = 200  # WhatsApp row id 200; Instagram quick-reply payload 1000
ROW_TITLE_MAX = 20  # WhatsApp row title 24; Instagram quick-reply title 20
ROW_DESCRIPTION_MAX = 72  # WhatsApp row description 72; Instagram not shown


def _nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("value must not be blank")
    return value


def _check_len(value: str | None, limit: int, what: str) -> None:
    if value is not None and len(value) > limit:
        raise ValueError(f"{what} is {len(value)} characters; limit is {limit}")


class ReplyButton(BaseModel):
    """A tappable option: ``title`` is shown, ``id`` returns as the selection."""

    id: str = Field(..., min_length=1, max_length=BUTTON_ID_MAX)
    title: str = Field(..., min_length=1, max_length=BUTTON_TITLE_MAX)

    _check = field_validator("id", "title")(_nonblank)


class UrlButton(BaseModel):
    """A button that opens a web page; it produces no webhook on tap."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["web_url"] = "web_url"
    title: str = Field(min_length=1, max_length=BUTTON_TITLE_MAX)
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


class MediaRef(BaseModel):
    """One media file by public ``url`` or by ``media_id``; set exactly one.

    A ``media_id`` is issued by the Inbox's own Platform (WhatsApp media
    upload, Instagram ``attachment_id`` from ``IMediaLibrary.upload``); it does
    not exist on another Platform.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    url: HttpUrl | None = None
    media_id: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _exactly_one(self) -> Self:
        if (self.url is None) == (self.media_id is None):
            raise ValueError("MediaRef needs exactly one of url or media_id")
        return self


type HeaderKind = Literal["text", "image", "video", "document"]


class InteractiveHeader(BaseModel):
    """Header of a button message, shaped like the WhatsApp Cloud API header.

    ``kind="text"`` takes ``text`` (≤ ``HEADER_TEXT_MAX``); ``image``,
    ``video`` and ``document`` take ``media``; ``filename`` is for a document
    only. Build one with ``of_text``, ``of_image``, ``of_video`` or
    ``of_document``. Instagram folds a text header into the message text and
    sends a media header as its own message before the buttons.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: HeaderKind
    text: str | None = Field(default=None, min_length=1, max_length=HEADER_TEXT_MAX)
    media: MediaRef | None = None
    filename: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _matches_kind(self) -> Self:
        if self.kind == "text":
            if self.text is None or self.media is not None:
                raise ValueError("A text header needs text and no media")
            _nonblank(self.text)
        elif self.media is None or self.text is not None:
            raise ValueError(f"A {self.kind} header needs media and no text")
        if self.filename is not None and self.kind != "document":
            raise ValueError("filename is only for a document header")
        return self

    @classmethod
    def of_text(cls, text: str) -> Self:
        return cls(kind="text", text=text)

    @classmethod
    def of_image(cls, *, url: str | None = None, media_id: str | None = None) -> Self:
        return cls(kind="image", media=MediaRef.model_validate(_ref(url, media_id)))

    @classmethod
    def of_video(cls, *, url: str | None = None, media_id: str | None = None) -> Self:
        return cls(kind="video", media=MediaRef.model_validate(_ref(url, media_id)))

    @classmethod
    def of_document(
        cls,
        *,
        url: str | None = None,
        media_id: str | None = None,
        filename: str | None = None,
    ) -> Self:
        return cls(
            kind="document",
            media=MediaRef.model_validate(_ref(url, media_id)),
            filename=filename,
        )


def _ref(url: str | None, media_id: str | None) -> dict[str, str]:
    return {k: v for k, v in (("url", url), ("media_id", media_id)) if v is not None}


class ListRow(BaseModel):
    """One selectable option of a list message; ``id`` returns as the selection."""

    id: str = Field(..., min_length=1, max_length=ROW_ID_MAX)
    title: str = Field(..., min_length=1, max_length=ROW_TITLE_MAX)
    description: str | None = Field(
        default=None, min_length=1, max_length=ROW_DESCRIPTION_MAX
    )

    _check = field_validator("id", "title")(_nonblank)


class ListSection(BaseModel):
    """A group of rows. ``title`` is required once a list has several sections."""

    title: str | None = Field(default=None, min_length=1, max_length=SECTION_TITLE_MAX)
    rows: list[ListRow] = Field(..., min_length=1, max_length=LIST_ROWS_MAX)


def check_button_message(
    buttons: Sequence[ReplyButton], body: str, footer: str | None
) -> None:
    """Shared limits of ``send_button_message``; ``ValueError`` before any I/O."""
    if not 1 <= len(buttons) <= BUTTONS_MAX:
        raise ValueError(f"Button messages need 1–{BUTTONS_MAX} buttons")
    if len({b.id for b in buttons}) != len(buttons):
        raise ValueError("Button IDs must be unique")
    _nonblank(body)
    _check_len(body, BUTTON_BODY_MAX, "Button message body")
    _check_len(footer, FOOTER_MAX, "Footer")


def check_list_message(
    sections: Sequence[ListSection],
    body: str,
    button_text: str,
    header: str | None,
    footer: str | None,
) -> None:
    """Shared limits of ``send_list_message``; ``ValueError`` before any I/O."""
    if not 1 <= len(sections) <= LIST_SECTIONS_MAX:
        raise ValueError(f"List messages need 1–{LIST_SECTIONS_MAX} sections")
    if len(sections) > 1 and any(s.title is None for s in sections):
        raise ValueError("Every section needs a title when a list has several")
    row_ids = [row.id for section in sections for row in section.rows]
    if len(row_ids) > LIST_ROWS_MAX:
        raise ValueError(
            f"List messages allow {LIST_ROWS_MAX} rows in total; got {len(row_ids)}"
        )
    if len(set(row_ids)) != len(row_ids):
        raise ValueError("Row IDs must be unique across all sections")
    _nonblank(body)
    _check_len(body, LIST_BODY_MAX, "List message body")
    _nonblank(button_text)
    _check_len(button_text, LIST_BUTTON_TEXT_MAX, "List button text")
    if header is not None:
        _nonblank(header)
    _check_len(header, HEADER_TEXT_MAX, "Header")
    _check_len(footer, FOOTER_MAX, "Footer")


__all__ = [
    "BUTTONS_MAX",
    "BUTTON_BODY_MAX",
    "BUTTON_ID_MAX",
    "BUTTON_TITLE_MAX",
    "FOOTER_MAX",
    "HEADER_TEXT_MAX",
    "LIST_BODY_MAX",
    "LIST_BUTTON_TEXT_MAX",
    "LIST_ROWS_MAX",
    "LIST_SECTIONS_MAX",
    "ROW_DESCRIPTION_MAX",
    "ROW_ID_MAX",
    "ROW_TITLE_MAX",
    "SECTION_TITLE_MAX",
    "CardButton",
    "HeaderKind",
    "InteractiveHeader",
    "ListRow",
    "ListSection",
    "MediaRef",
    "MessageCard",
    "ReplyButton",
    "UrlButton",
    "check_button_message",
    "check_list_message",
]
