"""Interactive message models for WhatsApp messaging."""

from enum import Enum

from pydantic import BaseModel, Field, field_validator

from wappa.schemas.core.recipient import RecipientRequest


class HeaderType(Enum):
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    DOCUMENT = "document"


class InteractiveMessage(RecipientRequest):
    body: str = Field(
        ..., min_length=1, max_length=4096, description="Main message text"
    )
    reply_to_message_id: str | None = Field(
        None, description="Optional message ID for replies"
    )


class ReplyButton(BaseModel):
    id: str = Field(..., max_length=256, description="Unique button identifier")
    title: str = Field(..., max_length=20, description="Button display text")


class InteractiveHeader(BaseModel):
    type: HeaderType = Field(
        ..., description="Header type (text, image, video, document)"
    )
    text: str | None = Field(
        None, max_length=60, description="Header text (for text headers)"
    )
    image: dict[str, str] | None = Field(
        None, description="Image header with 'id' or 'link' key"
    )
    video: dict[str, str] | None = Field(
        None, description="Video header with 'id' or 'link' key"
    )
    document: dict[str, str] | None = Field(
        None, description="Document header with 'id' or 'link' key"
    )

    @field_validator("text")
    @classmethod
    def validate_text_header(cls, v, info):
        if info.data.get("type") == HeaderType.TEXT and not v:
            raise ValueError("Text header must include 'text' field")
        return v

    @field_validator("image", "video", "document")
    @classmethod
    def validate_media_header(cls, v, info):
        if v and not (v.get("id") or v.get("link")):
            raise ValueError("Media header must include either 'id' or 'link'")
        return v


class ButtonMessage(InteractiveMessage):
    buttons: list[ReplyButton] = Field(
        ..., min_length=1, max_length=3, description="List of reply buttons (max 3)"
    )
    header: InteractiveHeader | None = Field(
        None, description="Optional header with text/media content"
    )
    footer: str | None = Field(None, max_length=60, description="Optional footer text")

    @field_validator("buttons")
    @classmethod
    def validate_button_uniqueness(cls, v):
        button_ids = [button.id for button in v]
        if len(button_ids) != len(set(button_ids)):
            raise ValueError("Button IDs must be unique")
        return v


class ListRow(BaseModel):
    id: str = Field(..., max_length=200, description="Unique row identifier")
    title: str = Field(..., max_length=24, description="Row title")
    description: str | None = Field(
        None, max_length=72, description="Optional row description"
    )


class ListSection(BaseModel):
    title: str = Field(..., max_length=24, description="Section title")
    rows: list[ListRow] = Field(
        ...,
        min_length=1,
        max_length=10,
        description="List of rows in this section (max 10)",
    )

    @field_validator("rows")
    @classmethod
    def validate_row_uniqueness(cls, v):
        row_ids = [row.id for row in v]
        if len(row_ids) != len(set(row_ids)):
            raise ValueError("Row IDs must be unique within section")
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
    def validate_global_row_uniqueness(cls, v):
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


def validate_list_menu_limits(sections: list[ListSection]) -> None:
    """Validate list menu constraints based on WhatsApp API limits."""
    if len(sections) > 10:
        raise ValueError("Maximum of 10 sections allowed")

    for section in sections:
        if len(section.title) > 24:
            raise ValueError(f"Section title '{section.title}' exceeds 24 characters")

        if len(section.rows) > 10:
            raise ValueError(f"Section '{section.title}' has more than 10 rows")

        for row in section.rows:
            if len(row.id) > 200:
                raise ValueError(f"Row ID '{row.id}' exceeds 200 characters")
            if len(row.title) > 24:
                raise ValueError(f"Row title '{row.title}' exceeds 24 characters")
            if row.description and len(row.description) > 72:
                raise ValueError(
                    f"Row description for '{row.title}' exceeds 72 characters"
                )


def validate_header_constraints(
    header: InteractiveHeader | None, footer: str | None
) -> None:
    """Validate header and footer constraints."""
    if header:
        valid_header_types = {
            HeaderType.TEXT,
            HeaderType.IMAGE,
            HeaderType.VIDEO,
            HeaderType.DOCUMENT,
        }
        if header.type not in valid_header_types:
            raise ValueError(
                f"Header type must be one of {[t.value for t in valid_header_types]}"
            )

    if footer and len(footer) > 60:
        raise ValueError("Footer text cannot exceed 60 characters")
