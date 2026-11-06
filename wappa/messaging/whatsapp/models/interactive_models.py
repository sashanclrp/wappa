"""Interactive message models for WhatsApp messaging."""

from typing import Self

from pydantic import Field, model_validator

from wappa.domain.interactive import (
    BUTTON_BODY_MAX,
    BUTTONS_MAX,
    FOOTER_MAX,
    HEADER_TEXT_MAX,
    LIST_BODY_MAX,
    LIST_BUTTON_TEXT_MAX,
    LIST_SECTIONS_MAX,
    InteractiveHeader,
    ListSection,
    ReplyButton,
    check_button_message,
    check_list_message,
)
from wappa.schemas.core.recipient import DeliveryRequest


class InteractiveMessage(DeliveryRequest):
    body: str = Field(
        ..., min_length=1, max_length=4096, description="Main message text"
    )
    reply_to_message_id: str | None = Field(
        None, description="Optional message ID for replies"
    )


class ButtonMessage(InteractiveMessage):
    body: str = Field(..., min_length=1, max_length=BUTTON_BODY_MAX)
    buttons: list[ReplyButton] = Field(
        ..., min_length=1, max_length=BUTTONS_MAX, description="Reply buttons (1–3)"
    )
    header: InteractiveHeader | None = Field(
        None,
        description=(
            'Optional header: {"kind": "text", "text": ...} or an image, video or '
            'document by {"media": {"url": ...}} or {"media": {"media_id": ...}}'
        ),
    )
    footer: str | None = Field(None, max_length=FOOTER_MAX)

    @model_validator(mode="after")
    def _shared_limits(self) -> Self:
        check_button_message(self.buttons, self.body, self.footer)
        return self


class ListMessage(InteractiveMessage):
    body: str = Field(..., min_length=1, max_length=LIST_BODY_MAX)
    button_text: str = Field(
        ...,
        min_length=1,
        max_length=LIST_BUTTON_TEXT_MAX,
        description="Text for the button that opens the list",
    )
    sections: list[ListSection] = Field(
        ..., min_length=1, max_length=LIST_SECTIONS_MAX, description="Sections (1–10)"
    )
    header: str | None = Field(
        None, max_length=HEADER_TEXT_MAX, description="Optional header text"
    )
    footer: str | None = Field(None, max_length=FOOTER_MAX)

    @model_validator(mode="after")
    def _shared_limits(self) -> Self:
        check_list_message(
            self.sections, self.body, self.button_text, self.header, self.footer
        )
        return self


class CTAMessage(InteractiveMessage):
    button_text: str = Field(
        ..., min_length=1, description="Text to display on the button"
    )
    button_url: str = Field(
        ..., pattern=r"^https?://", description="URL to load when button is tapped"
    )
    header: str | None = Field(None, description="Optional header text")
    footer: str | None = Field(None, description="Optional footer text")
