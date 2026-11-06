"""Platform-neutral Interactive Message values (ADR-0025).

``ReplyButton`` is the one "choose this option" value on every Platform. A tap
returns as an ``InboundMessageWebhook`` whose ``get_interactive_selection()`` is
the button ``id``: a WhatsApp ``button_reply``, or an Instagram postback.
``UrlButton`` opens a page and produces no webhook. ``MessageCard`` is one card
of ``send_carousel``, headed by a ``CardMedia`` image or video.
``InteractiveHeader`` heads a button or CTA message (text, or an image, video
or document by URL or media ID, as in the WhatsApp Cloud API), and
``ListSection``/``ListRow`` are the options of ``send_list_message``; a row tap
returns its ``id`` as the selection.

The shape follows WhatsApp; every structured limit is the most restrictive across the
installed Platforms (the constants below) and is enforced when the value is
built, so a value that constructs is deliverable on every Platform. Plain
``body``/``footer``/``sections``/``cards`` arguments are checked by
``check_button_message``, ``check_list_message``, ``check_cta_message`` and
``check_carousel`` before any Platform call, and free-form text by
``check_text`` / ``check_caption`` (WhatsApp's limit; a stricter Platform splits).
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
BUTTON_TITLE_MAX = 20  # WhatsApp reply title and CTA display_text 20; Instagram 20
BUTTON_ID_MAX = 256  # WhatsApp reply id 256; Instagram postback payload 1000
BUTTONS_MAX = 3  # WhatsApp 3 reply buttons; Instagram button template 3
HEADER_TEXT_MAX = 60  # WhatsApp header text 60; Instagram folded
FOOTER_MAX = 60  # WhatsApp footer 60; Instagram folded
BUTTON_BODY_MAX = 640  # WhatsApp button/CTA body 1024; Instagram button template 640
LIST_BODY_MAX = 1000  # WhatsApp list body 4096; Instagram text 1000 UTF-8 bytes
LIST_BUTTON_TEXT_MAX = 20  # WhatsApp list opener 20; Instagram not shown
LIST_SECTIONS_MAX = 10  # WhatsApp 10 sections; Instagram flattens to quick replies
LIST_ROWS_MAX = 10  # WhatsApp 10 rows in total; Instagram 13 quick replies
SECTION_TITLE_MAX = 24  # WhatsApp section title 24; Instagram folded into the text
ROW_ID_MAX = 200  # WhatsApp row id 200; Instagram quick-reply payload 1000
ROW_TITLE_MAX = 20  # WhatsApp row title 24; Instagram quick-reply title 20
ROW_DESCRIPTION_MAX = 72  # WhatsApp row description 72; Instagram folded into the text
CAROUSEL_CARDS_MIN = 2  # WhatsApp carousel 2; Instagram generic template 1
CAROUSEL_CARDS_MAX = 10  # WhatsApp carousel 10; Instagram generic template 10
CAROUSEL_BODY_MAX = 1000  # WhatsApp carousel body 1024; Instagram intro text 1000 bytes
CARD_TITLE_MAX = 80  # WhatsApp card body (title + subtitle) 160; Instagram title 80
CARD_SUBTITLE_MAX = 80  # WhatsApp card body (title + subtitle) 160; Instagram 80
CARD_TEXT_MAX = (
    160  # WhatsApp card body (title, newline, subtitle) 160; Instagram 2 slots
)
CARD_BUTTONS_MAX = 2  # WhatsApp 2 reply buttons (or 1 URL button); Instagram 3

# ── Free-form text limits: WhatsApp's, not the minimum (ADR-0028 rule 3) ────
# Divisible content keeps WhatsApp's limit; a stricter Platform splits it
# (Instagram: 1000 UTF-8 bytes per message). Checked by every adapter before
# any I/O with ``check_text`` / ``check_caption``.
TEXT_MAX = 4096  # WhatsApp text body 4096; Instagram splits
CAPTION_MAX = 1024  # WhatsApp media caption 1024; Instagram splits (sent as text)


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


class MediaRef(BaseModel):
    """One media file by public ``url``, by ``media_id``, or both.

    A ``media_id`` is issued by the Inbox's own Platform (WhatsApp media
    upload, Instagram ``attachment_id`` from ``IMediaLibrary.upload``); it does
    not exist on another Platform. WhatsApp sends ``media_id`` when set and
    falls back to ``url``; Instagram prefers ``url``. Set both to serve one
    value on several Platforms.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    url: HttpUrl | None = None
    media_id: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _at_least_one(self) -> Self:
        if self.url is None and self.media_id is None:
            raise ValueError("MediaRef needs a url, a media_id or both")
        return self


class CardMedia(BaseModel):
    """The image or video heading a carousel card, by public ``url`` only.

    Meta documents WhatsApp carousel card headers as a public ``link`` (no
    Media ID), so card media is URL-only on every Platform. WhatsApp sends
    ``url`` as the card header link and ignores ``poster_url``. An Instagram
    card has an image slot only: an image shows ``url``; a video shows
    ``poster_url`` and opens ``url`` on tap, so Instagram rejects a video
    without ``poster_url`` before any call.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["image", "video"]
    url: HttpUrl
    poster_url: HttpUrl | None = None

    @classmethod
    def image(cls, *, url: str) -> Self:
        return cls.model_validate({"kind": "image", "url": url})

    @classmethod
    def video(cls, *, url: str, poster_url: str | None = None) -> Self:
        return cls.model_validate(
            {
                "kind": "video",
                "url": url,
                **({"poster_url": poster_url} if poster_url else {}),
            }
        )


class MessageCard(BaseModel):
    """One carousel card: media header, title, optional subtitle and buttons.

    Shaped like a WhatsApp carousel card: ``header`` is required and the card
    has one URL button or 1-``CARD_BUTTONS_MAX`` reply buttons, never a mix.
    WhatsApp renders ``title`` + ``subtitle`` as the card body; Instagram
    shows them as card title and subtitle. ``default_url`` (tap on the card
    itself) is Instagram-only presentation and is ignored where unsupported.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    header: CardMedia
    title: str = Field(min_length=1, max_length=CARD_TITLE_MAX)
    subtitle: str | None = Field(
        default=None, min_length=1, max_length=CARD_SUBTITLE_MAX
    )
    default_url: HttpUrl | None = None
    buttons: tuple[CardButton, ...] = Field(min_length=1, max_length=CARD_BUTTONS_MAX)

    _check = field_validator("title")(_nonblank)

    @model_validator(mode="after")
    def _card_text(self) -> Self:
        text = "\n".join(p for p in (self.title, self.subtitle) if p)
        _check_len(text, CARD_TEXT_MAX, "Card title + subtitle")
        url_buttons = sum(isinstance(b, UrlButton) for b in self.buttons)
        if url_buttons and len(self.buttons) > 1:
            raise ValueError("A carousel card has one URL button or reply buttons")
        return self


type HeaderKind = Literal["text", "image", "video", "document"]


class InteractiveHeader(BaseModel):
    """Header of a button or CTA message, shaped like the WhatsApp Cloud API header.

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


def check_text(text: str) -> None:
    """Shared limit of a ``send_text`` body; ``ValueError`` before any I/O."""
    _check_len(text, TEXT_MAX, "Text")


def check_caption(caption: str | None) -> None:
    """Shared limit of a media caption; ``ValueError`` before any I/O."""
    _check_len(caption, CAPTION_MAX, "Caption")


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


def check_cta_message(
    button_text: str, button_url: str, body: str, footer: str | None
) -> None:
    """Shared limits of ``send_cta_message``; ``ValueError`` before any I/O."""
    UrlButton.model_validate({"title": button_text, "url": button_url})
    _nonblank(body)
    _check_len(body, BUTTON_BODY_MAX, "CTA message body")
    _check_len(footer, FOOTER_MAX, "Footer")


def check_carousel(cards: Sequence[MessageCard], body: str) -> None:
    """Shared limits of ``send_carousel``; ``ValueError`` before any I/O."""
    if not CAROUSEL_CARDS_MIN <= len(cards) <= CAROUSEL_CARDS_MAX:
        raise ValueError(
            f"Carousels need {CAROUSEL_CARDS_MIN}–{CAROUSEL_CARDS_MAX} cards; for "
            "one card use send_button_message with a media header"
        )
    shapes = {(isinstance(c.buttons[0], UrlButton), len(c.buttons)) for c in cards}
    if len(shapes) != 1:
        raise ValueError("Carousel cards must all use the same button kind and count")
    if len({c.header.kind for c in cards}) != 1:
        # WhatsApp rejects a carousel whose cards differ in structure (131009,
        # "must have the same structure for all cards"): all image or all video.
        raise ValueError("Carousel cards must all use the same header kind")
    _nonblank(body)
    _check_len(body, CAROUSEL_BODY_MAX, "Carousel body")


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
    "CAPTION_MAX",
    "CARD_BUTTONS_MAX",
    "CARD_SUBTITLE_MAX",
    "CARD_TEXT_MAX",
    "CARD_TITLE_MAX",
    "CAROUSEL_BODY_MAX",
    "CAROUSEL_CARDS_MAX",
    "CAROUSEL_CARDS_MIN",
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
    "TEXT_MAX",
    "CardButton",
    "CardMedia",
    "HeaderKind",
    "InteractiveHeader",
    "ListRow",
    "ListSection",
    "MediaRef",
    "MessageCard",
    "ReplyButton",
    "UrlButton",
    "check_button_message",
    "check_caption",
    "check_carousel",
    "check_cta_message",
    "check_list_message",
    "check_text",
]
