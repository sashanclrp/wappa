"""
Metadata extraction utilities for webhook processing.

This module provides functions to extract comprehensive metadata from
IncomingMessageWebhook objects based on message type.
"""

import time

from wappa.webhooks import IncomingMessageWebhook

from ..models.webhook_metadata import (
    ContactMessageMetadata,
    InteractiveMessageMetadata,
    LocationMessageMetadata,
    MediaMessageMetadata,
    MessageType,
    TextMessageMetadata,
    UnknownMessageMetadata,
    WebhookMetadata,
)


class MetadataExtractor:
    """Utility class for extracting metadata from webhooks."""

    @staticmethod
    def extract_metadata(
        webhook: IncomingMessageWebhook, start_time: float = None
    ) -> WebhookMetadata:
        """
        Extract appropriate metadata from webhook based on message type.

        Args:
            webhook: IncomingMessageWebhook to extract metadata from
            start_time: Optional start time for processing time calculation

        Returns:
            WebhookMetadata object with extracted information
        """
        # Calculate processing time if start_time provided
        processing_time_ms = None
        if start_time is not None:
            processing_time_ms = int((time.time() - start_time) * 1000)

        # Get message type from webhook
        message_type_name = webhook.get_message_type_name().lower()

        try:
            # Map message type string to enum
            message_type = MessageType(message_type_name)
        except ValueError:
            # Handle unknown message types
            return UnknownMessageMetadata.from_webhook(webhook, processing_time_ms)

        # Extract metadata based on message type
        if message_type == MessageType.TEXT:
            return TextMessageMetadata.from_webhook(webhook, processing_time_ms)

        elif message_type in [
            MessageType.IMAGE,
            MessageType.VIDEO,
            MessageType.AUDIO,
            MessageType.VOICE,
            MessageType.DOCUMENT,
            MessageType.STICKER,
        ]:
            return MediaMessageMetadata.from_webhook(
                webhook, message_type, processing_time_ms
            )

        elif message_type == MessageType.LOCATION:
            return LocationMessageMetadata.from_webhook(webhook, processing_time_ms)

        elif message_type in [MessageType.CONTACT, MessageType.CONTACTS]:
            return ContactMessageMetadata.from_webhook(webhook, processing_time_ms)

        elif message_type == MessageType.INTERACTIVE:
            return InteractiveMessageMetadata.from_webhook(webhook, processing_time_ms)

        else:
            # Fallback for unsupported types
            return UnknownMessageMetadata.from_webhook(webhook, processing_time_ms)

    @staticmethod
    def format_metadata_for_user(metadata: WebhookMetadata) -> str:
        """
        Format metadata for display to user.

        Args:
            metadata: WebhookMetadata object to format

        Returns:
            Formatted string for user display
        """
        lines = []
        lines.append("📊 *Message Metadata*")
        lines.append("─" * 30)

        # Basic information
        lines.append(f"🆔 Message ID: `{metadata.message_id[:20]}...`")
        # Handle both enum and string values for message_type
        message_type_str = (
            metadata.message_type.value
            if hasattr(metadata.message_type, "value")
            else str(metadata.message_type)
        )
        lines.append(f"📱 Message Type: `{message_type_str}`")
        lines.append(f"👤 User: {metadata.user_name or metadata.user_id}")
        lines.append(
            f"🕐 Timestamp: {metadata.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
        )
        lines.append(f"🏢 Tenant: `{metadata.tenant_id}`")
        lines.append(f"🌐 Platform: `{metadata.platform}`")

        # Processing metadata
        if metadata.processing_time_ms:
            lines.append(f"⚡ Processing Time: {metadata.processing_time_ms}ms")

        if metadata.cache_hit:
            lines.append("💾 Cache: Hit ✅")

        # Type-specific metadata
        if isinstance(metadata, TextMessageMetadata):
            lines.append("")
            lines.append("📝 *Text Message Details:*")
            lines.append(f"📏 Length: {metadata.text_length} characters")
            if metadata.has_urls:
                lines.append("🔗 Contains URLs: Yes")
            if metadata.has_mentions:
                lines.append("👥 Contains Mentions: Yes")
            if metadata.is_forwarded:
                lines.append("↪️ Forwarded: Yes")

        elif isinstance(metadata, MediaMessageMetadata):
            lines.append("")
            lines.append(f"🎬 *{metadata.media_type.title()} Media Details:*")
            lines.append(f"🆔 Media ID: `{metadata.media_id[:20]}...`")
            if metadata.mime_type:
                lines.append(f"📄 MIME Type: `{metadata.mime_type}`")
            if metadata.file_size:
                lines.append(
                    f"📦 File Size: {MetadataExtractor._format_file_size(metadata.file_size)}"
                )
            if metadata.caption:
                lines.append(
                    f"💬 Caption: {metadata.caption[:50]}{'...' if len(metadata.caption) > 50 else ''}"
                )
            if metadata.width and metadata.height:
                lines.append(f"📐 Dimensions: {metadata.width}x{metadata.height}")
            if metadata.duration:
                lines.append(f"⏱️ Duration: {metadata.duration}s")
            if metadata.filename:
                lines.append(f"📎 Filename: `{metadata.filename}`")
            if metadata.is_forwarded:
                lines.append("↪️ Forwarded: Yes")

        elif isinstance(metadata, LocationMessageMetadata):
            lines.append("")
            lines.append("📍 *Location Details:*")
            lines.append(f"🌍 Coordinates: {metadata.latitude}, {metadata.longitude}")
            if metadata.location_name:
                lines.append(f"🏷️ Name: {metadata.location_name}")
            if metadata.location_address:
                lines.append(f"🏠 Address: {metadata.location_address}")
            if metadata.is_forwarded:
                lines.append("↪️ Forwarded: Yes")

        elif isinstance(metadata, ContactMessageMetadata):
            lines.append("")
            lines.append("👥 *Contact Details:*")
            lines.append(f"📇 Contact Count: {metadata.contacts_count}")
            if metadata.contact_names:
                lines.append(
                    f"👤 Names: {', '.join(metadata.contact_names[:3])}{'...' if len(metadata.contact_names) > 3 else ''}"
                )
            if metadata.has_phone_numbers:
                lines.append("📞 Has Phone Numbers: Yes")
            if metadata.has_emails:
                lines.append("✉️ Has Emails: Yes")
            if metadata.is_forwarded:
                lines.append("↪️ Forwarded: Yes")

        elif isinstance(metadata, InteractiveMessageMetadata):
            lines.append("")
            lines.append("🔘 *Interactive Details:*")
            lines.append(f"⚡ Type: {metadata.interaction_type}")
            lines.append(f"🆔 Selection ID: `{metadata.selection_id}`")
            if metadata.selection_title:
                lines.append(f"🏷️ Selection: {metadata.selection_title}")
            if metadata.context_message_id:
                lines.append(
                    f"💬 Context Message: `{metadata.context_message_id[:20]}...`"
                )

        elif isinstance(metadata, UnknownMessageMetadata):
            lines.append("")
            lines.append("❓ *Unknown Message Type*")
            lines.append("🔍 Raw data captured for debugging")

        return "\n".join(lines)

    @staticmethod
    def get_metadata_summary(metadata: WebhookMetadata) -> dict:
        """
        Get a summary of metadata for logging/analytics.

        Args:
            metadata: WebhookMetadata object to summarize

        Returns:
            Dictionary with metadata summary
        """
        # Handle both enum and string values for message_type
        message_type_value = (
            metadata.message_type.value
            if hasattr(metadata.message_type, "value")
            else str(metadata.message_type)
        )

        summary = {
            "message_id": metadata.message_id,
            "message_type": message_type_value,
            "user_id": metadata.user_id,
            "timestamp": metadata.timestamp.isoformat(),
            "processing_time_ms": metadata.processing_time_ms,
            "cache_hit": metadata.cache_hit,
        }

        # Add type-specific summary data
        if isinstance(metadata, TextMessageMetadata):
            summary.update(
                {
                    "text_length": metadata.text_length,
                    "has_urls": metadata.has_urls,
                    "has_mentions": metadata.has_mentions,
                    "is_forwarded": metadata.is_forwarded,
                }
            )

        elif isinstance(metadata, MediaMessageMetadata):
            summary.update(
                {
                    "media_id": metadata.media_id,
                    "media_type": metadata.media_type,
                    "file_size": metadata.file_size,
                    "has_caption": bool(metadata.caption),
                    "is_forwarded": metadata.is_forwarded,
                }
            )

        elif isinstance(metadata, LocationMessageMetadata):
            summary.update(
                {
                    "latitude": metadata.latitude,
                    "longitude": metadata.longitude,
                    "has_name": bool(metadata.location_name),
                    "has_address": bool(metadata.location_address),
                    "is_forwarded": metadata.is_forwarded,
                }
            )

        elif isinstance(metadata, ContactMessageMetadata):
            summary.update(
                {
                    "contacts_count": metadata.contacts_count,
                    "has_phone_numbers": metadata.has_phone_numbers,
                    "has_emails": metadata.has_emails,
                    "is_forwarded": metadata.is_forwarded,
                }
            )

        elif isinstance(metadata, InteractiveMessageMetadata):
            summary.update(
                {
                    "interaction_type": metadata.interaction_type,
                    "selection_id": metadata.selection_id,
                    "has_title": bool(metadata.selection_title),
                }
            )

        return summary

    @staticmethod
    def _format_file_size(size_bytes: int) -> str:
        """Format file size in human-readable format."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


# Convenience functions for direct use
def extract_webhook_metadata(
    webhook: IncomingMessageWebhook, start_time: float = None
) -> WebhookMetadata:
    """
    Extract metadata from webhook (convenience function).

    Args:
        webhook: IncomingMessageWebhook to process
        start_time: Optional start time for processing measurement

    Returns:
        WebhookMetadata object
    """
    return MetadataExtractor.extract_metadata(webhook, start_time)


def format_metadata_message(metadata: WebhookMetadata) -> str:
    """
    Format metadata for user display (convenience function).

    Args:
        metadata: WebhookMetadata to format

    Returns:
        Formatted string for user
    """
    return MetadataExtractor.format_metadata_for_user(metadata)


def get_processing_summary(metadata: WebhookMetadata) -> dict:
    """
    Get processing summary (convenience function).

    Args:
        metadata: WebhookMetadata to summarize

    Returns:
        Summary dictionary
    """
    return MetadataExtractor.get_metadata_summary(metadata)
