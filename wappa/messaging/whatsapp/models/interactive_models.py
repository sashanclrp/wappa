"""
Interactive message models for WhatsApp messaging.

Pydantic schemas for interactive messaging operations based on WhatsApp Cloud API 2025
specifications and existing interactive_message.py implementation patterns.

Supports three types of interactive messages:
1. Button Messages - Quick reply buttons (max 3)
2. List Messages - Sectioned lists with rows (max 10 sections, 10 rows each)
3. Call-to-Action Messages - URL buttons with external links
"""

from enum import Enum

from pydantic import BaseModel, Field, field_validator


class InteractiveType(Enum):
    """Supported interactive message types for WhatsApp."""

    BUTTON = "button"
    LIST = "list"
    CTA_URL = "cta_url"


class HeaderType(Enum):
    """Supported header types for interactive messages."""

    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    DOCUMENT = "document"


class InteractiveMessage(BaseModel):
    """Base interactive message schema for interactive operations.

    Common fields for all interactive message types based on existing
    WhatsAppServiceInteractive implementation patterns.
    """

    recipient: str = Field(
        ..., pattern=r"^\d{10,15}$", description="Recipient phone number"
    )
    body: str = Field(
        ..., min_length=1, max_length=4096, description="Main message text"
    )
    reply_to_message_id: str | None = Field(
        None, description="Optional message ID for replies"
    )


class ReplyButton(BaseModel):
    """Reply button for button messages."""

    id: str = Field(..., max_length=256, description="Unique button identifier")
    title: str = Field(..., max_length=20, description="Button display text")


class InteractiveHeader(BaseModel):
    """Header for interactive messages with media support."""

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
        """Validate text header is provided for text type."""
        if info.data and info.data.get("type") == HeaderType.TEXT and not v:
            raise ValueError("Text header must include 'text' field")
        return v

    @field_validator("image", "video", "document")
    @classmethod
    def validate_media_header(cls, v, info):
        """Validate media headers have id or link."""
        if v and not (v.get("id") or v.get("link")):
            raise ValueError("Media header must include either 'id' or 'link'")
        return v


class ButtonMessage(InteractiveMessage):
    """Button message schema for send_button_message operations.

    Supports up to 3 quick reply buttons with text headers and footers.
    Based on existing send_buttons_menu() implementation.
    """

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
        """Validate button IDs are unique."""
        button_ids = [button.id for button in v]
        if len(button_ids) != len(set(button_ids)):
            raise ValueError("Button IDs must be unique")
        return v


class ListRow(BaseModel):
    """Row within a list section."""

    id: str = Field(..., max_length=200, description="Unique row identifier")
    title: str = Field(..., max_length=24, description="Row title")
    description: str | None = Field(
        None, max_length=72, description="Optional row description"
    )


class ListSection(BaseModel):
    """Section within a list message."""

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
        """Validate row IDs are unique within section."""
        row_ids = [row.id for row in v]
        if len(row_ids) != len(set(row_ids)):
            raise ValueError("Row IDs must be unique within section")
        return v


class ListMessage(InteractiveMessage):
    """List message schema for send_list_message operations.

    Supports sectioned lists with up to 10 sections and 10 rows per section.
    Based on existing send_list_menu() implementation.
    """

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
        """Validate row IDs are unique across all sections."""
        all_row_ids = []
        for section in v:
            for row in section.rows:
                all_row_ids.append(row.id)

        if len(all_row_ids) != len(set(all_row_ids)):
            raise ValueError("Row IDs must be unique across all sections")
        return v


class CTAMessage(InteractiveMessage):
    """Call-to-Action message schema for send_cta_message operations.

    Supports URL buttons for external links.
    Based on existing send_cta_button() implementation.
    """

    button_text: str = Field(
        ..., min_length=1, description="Text to display on the button"
    )
    button_url: str = Field(
        ..., pattern=r"^https?://", description="URL to load when button is tapped"
    )
    header: str | None = Field(None, description="Optional header text")
    footer: str | None = Field(None, description="Optional footer text")

    @field_validator("button_url")
    @classmethod
    def validate_url_format(cls, v):
        """Validate URL format is http:// or https://."""
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("button_url must start with http:// or https://")
        return v


# Validation utility functions for use in handlers
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
