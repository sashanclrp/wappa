"""
WhatsApp document message schema.

This module contains Pydantic models for processing WhatsApp document messages,
including PDFs, Office documents, and other file types sent via Click-to-WhatsApp ads.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from wappa.schemas.core.types import (
    MediaType,
    MessageType,
    UniversalMessageData,
)
from wappa.webhooks.core.base_message import BaseDocumentMessage, BaseMessageContext
from wappa.webhooks.whatsapp.models.base import (
    AdReferral,
    MessageContext,
)

from ._base import WhatsAppMessageBase


class DocumentContent(BaseModel):
    """Document message content."""

    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)

    caption: str | None = Field(None, description="Document caption text (optional)")
    filename: str | None = Field(
        None,
        description=(
            "Original filename as the User's client sent it. Untrusted: sanitize "
            "it before using it as a path"
        ),
    )
    mime_type: str = Field(
        ..., description="MIME type of the document (e.g., 'application/pdf')"
    )
    sha256: str = Field(..., description="SHA-256 hash of the document file")
    id: str = Field(..., description="Media asset ID for retrieving the document file")
    url: str | None = Field(
        None,
        description="Direct download URL for the document (temporary, requires authentication)",
    )

    @field_validator("caption")
    @classmethod
    def validate_caption(cls, v: str | None) -> str | None:
        """Validate document caption if present."""
        if v is not None:
            v = v.strip()
            if not v:
                return None
        return v

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, v: str | None) -> str | None:
        """Keep the name Meta delivered (inbound is never rejected, ADR-0023)."""
        return v.strip() or None if v is not None else None

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


class WhatsAppDocumentMessage(WhatsAppMessageBase, BaseDocumentMessage):
    """
    WhatsApp document message model.

    Supports various document message scenarios:
    - PDF documents
    - Office documents (Word, Excel, PowerPoint)
    - Text files
    - Click-to-WhatsApp ad document messages
    """

    model_config = ConfigDict(
        extra="allow", str_strip_whitespace=True, validate_assignment=True
    )

    # Standard message fields (BSUID support v24.0+)
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
    def media_id(self) -> str:
        """Get the media asset ID for downloading the document file."""
        return self.document.id

    @property
    def mime_type(self) -> str:
        """Get the document MIME type."""
        return self.document.mime_type

    @property
    def filename(self) -> str | None:
        """The original filename (untrusted; sanitize before using as a path)."""
        return self.document.filename

    @property
    def file_extension(self) -> str | None:
        """Get the file extension from the filename."""
        name = self.document.filename
        if name and "." in name:
            return name.split(".")[-1].lower()
        return None

    @property
    def file_hash(self) -> str:
        """Get the SHA-256 hash of the document file."""
        return self.document.sha256

    @property
    def caption(self) -> str | None:
        """Get the document caption."""
        return self.document.caption

    def get_file_extension(self) -> str | None:
        """
        Get the file extension from the filename.

        Returns:
            File extension (without dot) or None if no extension found.
        """
        return self.file_extension

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

    def to_summary_dict(self) -> dict[str, str | bool | int | None]:
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
    def message_type(self) -> MessageType:
        return MessageType.DOCUMENT

    def has_context(self) -> bool:
        return self.context is not None

    def get_context(self) -> BaseMessageContext | None:
        from .context import WhatsAppMessageContext

        return WhatsAppMessageContext(self.context) if self.context else None

    def to_universal_dict(self) -> UniversalMessageData:
        from wappa.webhooks.core.base_message.projections import media_projection

        return media_projection(self)

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

    # Abstract methods already implemented above

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
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "WhatsAppDocumentMessage":
        return cls.model_validate(data)
