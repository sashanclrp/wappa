"""
WhatsApp document message schema.

This module contains Pydantic models for processing WhatsApp document messages,
including PDFs, Office documents, and other file types sent via Click-to-WhatsApp ads.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from wappa.schemas.core.base_message import BaseDocumentMessage, BaseMessageContext
from wappa.schemas.core.types import (
    ConversationType,
    MediaType,
    MessageType,
    PlatformType,
    UniversalMessageData,
)
from wappa.schemas.whatsapp.base_models import AdReferral, MessageContext


class DocumentContent(BaseModel):
    """Document message content."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    caption: str | None = Field(None, description="Document caption text (optional)")
    filename: str = Field(..., description="Original filename of the document")
    mime_type: str = Field(
        ..., description="MIME type of the document (e.g., 'application/pdf')"
    )
    sha256: str = Field(..., description="SHA-256 hash of the document file")
    id: str = Field(..., description="Media asset ID for retrieving the document file")

    @field_validator("caption")
    @classmethod
    def validate_caption(cls, v: str | None) -> str | None:
        """Validate document caption if present."""
        if v is not None:
            v = v.strip()
            if not v:
                return None
            if len(v) > 1024:  # WhatsApp caption limit
                raise ValueError("Document caption cannot exceed 1024 characters")
        return v

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, v: str) -> str:
        """Validate document filename."""
        if not v.strip():
            raise ValueError("Document filename cannot be empty")

        # Check for basic filename validation
        filename = v.strip()
        if len(filename) > 255:
            raise ValueError("Document filename cannot exceed 255 characters")

        # Basic security check - no path traversal
        if ".." in filename or "/" in filename or "\\" in filename:
            raise ValueError("Document filename contains invalid characters")

        return filename

    @field_validator("mime_type")
    @classmethod
    def validate_mime_type(cls, v: str) -> str:
        """Validate document MIME type format."""
        # Common document MIME types
        valid_prefixes = [
            "application/",  # PDFs, Office docs, etc.
            "text/",  # Text files
            "image/",  # Images as documents
        ]

        mime_lower = v.lower()
        if not any(mime_lower.startswith(prefix) for prefix in valid_prefixes):
            raise ValueError(
                "Document MIME type must start with application/, text/, or image/"
            )
        return mime_lower

    @field_validator("id")
    @classmethod
    def validate_media_id(cls, v: str) -> str:
        """Validate media asset ID."""
        if not v or len(v) < 10:
            raise ValueError("Media asset ID must be at least 10 characters")
        return v


class WhatsAppDocumentMessage(BaseDocumentMessage):
    """
    WhatsApp document message model.

    Supports various document message scenarios:
    - PDF documents
    - Office documents (Word, Excel, PowerPoint)
    - Text files
    - Click-to-WhatsApp ad document messages
    """

    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, validate_assignment=True
    )

    # Standard message fields
    from_: str = Field(
        ..., alias="from", description="WhatsApp user phone number who sent the message"
    )
    id: str = Field(..., description="Unique WhatsApp message ID")
    timestamp_str: str = Field(
        ..., alias="timestamp", description="Unix timestamp when the message was sent"
    )
    type: Literal["document"] = Field(
        ..., description="Message type, always 'document' for document messages"
    )

    # Document content
    document: DocumentContent = Field(
        ..., description="Document message content and metadata"
    )

    # Optional context fields
    context: MessageContext | None = Field(
        None,
        description="Context for forwards (documents don't support replies typically)",
    )
    referral: AdReferral | None = Field(
        None, description="Click-to-WhatsApp ad referral information"
    )

    @field_validator("from_")
    @classmethod
    def validate_from_phone(cls, v: str) -> str:
        """Validate sender phone number format."""
        if not v or len(v) < 8:
            raise ValueError("Sender phone number must be at least 8 characters")
        # Remove common prefixes and validate numeric
        phone = v.replace("+", "").replace("-", "").replace(" ", "")
        if not phone.isdigit():
            raise ValueError("Phone number must contain only digits (and +)")
        return v

    @field_validator("id")
    @classmethod
    def validate_message_id(cls, v: str) -> str:
        """Validate WhatsApp message ID format."""
        if not v or len(v) < 10:
            raise ValueError("WhatsApp message ID must be at least 10 characters")
        # WhatsApp message IDs typically start with 'wamid.'
        if not v.startswith("wamid."):
            raise ValueError("WhatsApp message ID should start with 'wamid.'")
        return v

    @field_validator("timestamp_str")
    @classmethod
    def validate_timestamp(cls, v: str) -> str:
        """Validate Unix timestamp format."""
        if not v.isdigit():
            raise ValueError("Timestamp must be numeric")
        # Validate reasonable timestamp range (after 2020, before 2100)
        timestamp_int = int(v)
        if timestamp_int < 1577836800 or timestamp_int > 4102444800:
            raise ValueError("Timestamp must be a valid Unix timestamp")
        return v

    @property
    def has_caption(self) -> bool:
        """Check if this document has a caption."""
        return (
            self.document.caption is not None and len(self.document.caption.strip()) > 0
        )

    @property
    def is_ad_message(self) -> bool:
        """Check if this document message came from a Click-to-WhatsApp ad."""
        return self.referral is not None

    @property
    def is_pdf(self) -> bool:
        """Check if this is a PDF document."""
        return self.document.mime_type == "application/pdf"

    @property
    def is_office_document(self) -> bool:
        """Check if this is a Microsoft Office document."""
        office_types = [
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # .docx
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # .xlsx
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",  # .pptx
            "application/msword",  # .doc
            "application/vnd.ms-excel",  # .xls
            "application/vnd.ms-powerpoint",  # .ppt
        ]
        return self.document.mime_type in office_types

    @property
    def is_text_file(self) -> bool:
        """Check if this is a text file."""
        return self.document.mime_type.startswith("text/")

    @property
    def sender_phone(self) -> str:
        """Get the sender's phone number (clean accessor)."""
        return self.from_

    @property
    def media_id(self) -> str:
        """Get the media asset ID for downloading the document file."""
        return self.document.id

    @property
    def mime_type(self) -> str:
        """Get the document MIME type."""
        return self.document.mime_type

    @property
    def filename(self) -> str:
        """Get the document filename."""
        return self.document.filename

    @property
    def file_extension(self) -> str | None:
        """Get the file extension from the filename."""
        if "." in self.document.filename:
            return self.document.filename.split(".")[-1].lower()
        return None

    @property
    def file_hash(self) -> str:
        """Get the SHA-256 hash of the document file."""
        return self.document.sha256

    @property
    def caption(self) -> str | None:
        """Get the document caption."""
        return self.document.caption

    @property
    def unix_timestamp(self) -> int:
        """Get the timestamp as an integer."""
        return self.timestamp

    def get_file_extension(self) -> str | None:
        """
        Get the file extension from the filename.

        Returns:
            File extension (without dot) or None if no extension found.
        """
        if "." in self.filename:
            return self.filename.split(".")[-1].lower()
        return None

    def get_ad_context(self) -> tuple[str | None, str | None]:
        """
        Get ad context information for Click-to-WhatsApp document messages.

        Returns:
            Tuple of (ad_id, ad_click_id) if this came from an ad,
            (None, None) otherwise.
        """
        if self.is_ad_message and self.referral:
            return (self.referral.source_id, self.referral.ctwa_clid)
        return (None, None)

    def to_summary_dict(self) -> dict[str, str | bool | int]:
        """
        Create a summary dictionary for logging and analysis.

        Returns:
            Dictionary with key message information for structured logging.
        """
        return {
            "message_id": self.id,
            "sender": self.sender_phone,
            "timestamp": self.unix_timestamp,
            "type": self.type,
            "media_id": self.media_id,
            "mime_type": self.mime_type,
            "filename": self.filename,
            "file_extension": self.get_file_extension(),
            "has_caption": self.has_caption,
            "caption_length": len(self.caption) if self.caption else 0,
            "is_pdf": self.is_pdf,
            "is_office_document": self.is_office_document,
            "is_text_file": self.is_text_file,
            "is_ad_message": self.is_ad_message,
        }

    # Implement abstract methods from BaseMessage

    @property
    def platform(self) -> PlatformType:
        return PlatformType.WHATSAPP

    @property
    def message_type(self) -> MessageType:
        return MessageType.DOCUMENT

    @property
    def message_id(self) -> str:
        return self.id

    @property
    def sender_id(self) -> str:
        return self.from_

    @property
    def timestamp(self) -> int:
        return int(self.timestamp_str)

    @property
    def conversation_id(self) -> str:
        return self.from_

    @property
    def conversation_type(self) -> ConversationType:
        return ConversationType.PRIVATE

    def has_context(self) -> bool:
        return self.context is not None

    def get_context(self) -> BaseMessageContext | None:
        from .text import WhatsAppMessageContext

        return WhatsAppMessageContext(self.context) if self.context else None

    def to_universal_dict(self) -> UniversalMessageData:
        return {
            "platform": self.platform.value,
            "message_type": self.message_type.value,
            "message_id": self.message_id,
            "sender_id": self.sender_id,
            "conversation_id": self.conversation_id,
            "conversation_type": self.conversation_type.value,
            "timestamp": self.timestamp,
            "processed_at": self.processed_at.isoformat(),
            "has_context": self.has_context(),
            "media_id": self.media_id,
            "media_type": self.media_type.value,
            "file_size": self.file_size,
            "caption": self.caption,
            "filename": self.filename,
            "whatsapp_data": {
                "whatsapp_id": self.id,
                "from": self.from_,
                "timestamp_str": self.timestamp_str,
                "type": self.type,
                "document_content": self.document.model_dump(),
                "context": self.context.model_dump() if self.context else None,
                "referral": self.referral.model_dump() if self.referral else None,
            },
        }

    def get_platform_data(self) -> dict[str, Any]:
        return {
            "whatsapp_message_id": self.id,
            "from_phone": self.from_,
            "timestamp_str": self.timestamp_str,
            "message_type": self.type,
            "document_content": self.document.model_dump(),
            "context": self.context.model_dump() if self.context else None,
            "referral": self.referral.model_dump() if self.referral else None,
            "suggested_filename": f"{self.filename}",
            "document_properties": {
                "is_pdf": self.is_pdf,
                "is_office_document": self.is_office_document,
                "is_text_file": self.is_text_file,
            },
        }

    # Implement abstract methods from BaseMediaMessage

    @property
    def media_id(self) -> str:
        return self.document.id

    @property
    def media_type(self) -> MediaType:
        mime_str = self.document.mime_type
        try:
            return MediaType(mime_str)
        except ValueError:
            # Fallback based on common document types
            if self.is_pdf:
                return MediaType.DOCUMENT_PDF
            elif self.is_office_document:
                return MediaType.DOCUMENT_DOCX
            else:
                return MediaType.DOCUMENT_PDF

    @property
    def file_size(self) -> int | None:
        return None  # WhatsApp doesn't provide file size in webhooks

    @property
    def caption(self) -> str | None:
        return self.document.caption

    def get_download_info(self) -> dict[str, Any]:
        return {
            "media_id": self.media_id,
            "mime_type": self.media_type.value,
            "sha256": self.document.sha256,
            "platform": "whatsapp",
            "requires_auth": True,
            "download_method": "whatsapp_media_api",
            "filename": self.filename,
        }

    # Implement abstract methods from BaseDocumentMessage
    # Note: filename and file_extension properties are implemented above

    @classmethod
    def from_platform_data(
        cls, data: dict[str, Any], **kwargs
    ) -> "WhatsAppDocumentMessage":
        return cls.model_validate(data)
