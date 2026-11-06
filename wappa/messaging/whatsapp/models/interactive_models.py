"""Interactive message models for WhatsApp messaging."""

from pydantic import Field, field_validator

from wappa.domain.interactive import ButtonHeader, ListSection, ReplyButton
from wappa.schemas.core.recipient import DeliveryRequest


class InteractiveMessage(DeliveryRequest):
    body: str = Field(
        ..., min_length=1, max_length=4096, description="Main message text"
    )
    reply_to_message_id: str | None = Field(
        None, description="Optional message ID for replies"
    )


class ButtonMessage(InteractiveMessage):
    buttons: list[ReplyButton] = Field(
        ..., min_length=1, max_length=3, description="List of reply buttons (max 3)"
    )
    header: ButtonHeader | None = Field(
        None, description="Optional header: text, or an image by URL or media ID"
    )
    footer: str | None = Field(None, max_length=60, description="Optional footer text")

    @field_validator("buttons")
    @classmethod
    def validate_button_uniqueness(cls, v: list[ReplyButton]) -> list[ReplyButton]:
        button_ids = [button.id for button in v]
        if len(button_ids) != len(set(button_ids)):
            raise ValueError("Button IDs must be unique")
        return v


class ListMessage(InteractiveMessage):
    button_text: str = Field(
        ..., max_length=20, description="Text for the button that opens the list"
    )
    sections: list[ListSection] = Field(
        ..., min_length=1, max_length=10, description="List of sections (max 10)"
    )
    header: str | None = Field(
        None, max_length=60, description="Optional header text (text only for lists)"
    )
    footer: str | None = Field(None, max_length=60, description="Optional footer text")

    @field_validator("sections")
    @classmethod
    def validate_global_row_uniqueness(cls, v: list[ListSection]) -> list[ListSection]:
        all_row_ids = [row.id for section in v for row in section.rows]
        if len(all_row_ids) != len(set(all_row_ids)):
            raise ValueError("Row IDs must be unique across all sections")
        return v


class CTAMessage(InteractiveMessage):
    button_text: str = Field(
        ..., min_length=1, description="Text to display on the button"
    )
    button_url: str = Field(
        ..., pattern=r"^https?://", description="URL to load when button is tapped"
    )
    header: str | None = Field(None, description="Optional header text")
    footer: str | None = Field(None, description="Optional footer text")


def validate_buttons_menu_limits(buttons: list[ReplyButton]) -> None:
    """Validate button menu constraints based on WhatsApp API limits."""
    if len(buttons) > 3:
        raise ValueError("Maximum of 3 buttons allowed")

    for button in buttons:
        if len(button.title) > 20:
            raise ValueError(f"Button title '{button.title}' exceeds 20 characters")
        if len(button.id) > 256:
            raise ValueError(f"Button ID '{button.id}' exceeds 256 characters")
