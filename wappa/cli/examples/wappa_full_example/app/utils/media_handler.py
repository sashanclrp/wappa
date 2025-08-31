"""
Media handling utilities for the Wappa Full Example application.

This module provides functions for downloading and uploading media files,
handling different media types, and managing local media storage.
"""

import os
import tempfile
from pathlib import Path

import aiohttp

from wappa.webhooks import IncomingMessageWebhook


class MediaHandler:
    """Utility class for handling media operations."""

    def __init__(self, temp_dir: str | None = None):
        """
        Initialize MediaHandler.

        Args:
            temp_dir: Optional temporary directory path for downloads
        """
        self.temp_dir = temp_dir or tempfile.gettempdir()
        self.session: aiohttp.ClientSession | None = None

    async def __aenter__(self):
        """Async context manager entry."""
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()

    async def get_media_info_from_webhook(
        self, webhook: IncomingMessageWebhook
    ) -> dict[str, str] | None:
        """
        Extract media information from webhook.

        Args:
            webhook: IncomingMessageWebhook containing media

        Returns:
            Dictionary with media info or None if no media found
        """
        message = webhook.message
        message_type = webhook.get_message_type_name().lower()

        if message_type not in [
            "image",
            "video",
            "audio",
            "voice",
            "document",
            "sticker",
        ]:
            return None

        media_info = {"type": message_type, "message_id": message.message_id}

        # Try to extract media ID (different field names possible)
        media_id = None
        for field_name in ["media_id", "id", f"{message_type}_id"]:
            if hasattr(message, field_name):
                media_id = getattr(message, field_name)
                if media_id:
                    break

        if not media_id:
            return None

        media_info["media_id"] = media_id

        # Extract additional metadata
        if hasattr(message, "mime_type"):
            media_info["mime_type"] = message.mime_type

        if hasattr(message, "file_size"):
            media_info["file_size"] = message.file_size

        if hasattr(message, "filename"):
            media_info["filename"] = message.filename

        if hasattr(message, "caption"):
            media_info["caption"] = message.caption

        # For images and videos, get dimensions
        if message_type in ["image", "video"]:
            if hasattr(message, "width"):
                media_info["width"] = message.width
            if hasattr(message, "height"):
                media_info["height"] = message.height

        # For audio and video, get duration
        if message_type in ["audio", "video", "voice"]:
            if hasattr(message, "duration"):
                media_info["duration"] = message.duration

        return media_info

    async def download_media_by_id(
        self, media_id: str, messenger, media_type: str = None
    ) -> tuple[str, dict[str, str]] | None:
        """
        Download media using media_id through WhatsApp API.

        Note: This is a placeholder implementation. The actual implementation
        would need to integrate with the WhatsApp Business API to download media.

        Args:
            media_id: Media ID from WhatsApp
            messenger: IMessenger instance for API calls
            media_type: Optional media type hint

        Returns:
            Tuple of (file_path, metadata) or None if failed
        """
        try:
            # This is a placeholder implementation
            # In a real implementation, you would:
            # 1. Use messenger or direct API calls to get media URL
            # 2. Download the media file
            # 3. Save to temporary location
            # 4. Return file path and metadata

            # For now, return None to indicate media download not implemented
            return None

        except Exception as e:
            print(f"Error downloading media {media_id}: {e}")
            return None

    async def upload_local_media(
        self, file_path: str, media_type: str = None
    ) -> str | None:
        """
        Upload local media file to get media_id for sending.

        Note: This is a placeholder implementation. The actual implementation
        would need to integrate with the WhatsApp Business API media upload endpoint.

        Args:
            file_path: Path to local media file
            media_type: Type of media (image, video, audio, document)

        Returns:
            Media ID if successful, None if failed
        """
        try:
            # This is a placeholder implementation
            # In a real implementation, you would:
            # 1. Upload the file to WhatsApp Business API
            # 2. Get the media_id from the response
            # 3. Return the media_id

            # For now, return the file path as a placeholder
            if os.path.exists(file_path):
                return f"local_{os.path.basename(file_path)}"

            return None

        except Exception as e:
            print(f"Error uploading media {file_path}: {e}")
            return None

    def get_local_media_path(self, filename: str, media_subdir: str = None) -> str:
        """
        Get path to local media file.

        Args:
            filename: Name of the media file
            media_subdir: Optional subdirectory within media folder

        Returns:
            Full path to media file
        """
        # Construct path relative to app directory
        base_dir = Path(__file__).parent.parent  # Go up to app directory
        media_dir = base_dir / "media"

        if media_subdir:
            media_dir = media_dir / media_subdir

        return str(media_dir / filename)

    def media_file_exists(self, filename: str, media_subdir: str = None) -> bool:
        """
        Check if local media file exists.

        Args:
            filename: Name of the media file
            media_subdir: Optional subdirectory within media folder

        Returns:
            True if file exists, False otherwise
        """
        file_path = self.get_local_media_path(filename, media_subdir)
        return os.path.exists(file_path)

    def get_media_type_from_extension(self, filename: str) -> str:
        """
        Determine media type from file extension.

        Args:
            filename: Name of the file

        Returns:
            Media type string
        """
        extension = Path(filename).suffix.lower()

        # Image extensions
        if extension in [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"]:
            return "image"

        # Video extensions
        elif extension in [".mp4", ".avi", ".mov", ".wmv", ".flv", ".webm"]:
            return "video"

        # Audio extensions
        elif extension in [".mp3", ".wav", ".aac", ".ogg", ".m4a", ".flac"]:
            return "audio"

        # Document extensions
        elif extension in [
            ".pdf",
            ".doc",
            ".docx",
            ".xls",
            ".xlsx",
            ".ppt",
            ".pptx",
            ".txt",
        ]:
            return "document"

        # Default
        else:
            return "document"

    async def send_media_by_file(
        self,
        messenger,
        recipient: str,
        file_path: str,
        caption: str = None,
        reply_to_message_id: str = None,
    ) -> dict[str, any]:
        """
        Send media file using appropriate messenger method.

        Args:
            messenger: IMessenger instance
            recipient: Recipient phone number
            file_path: Path to media file
            caption: Optional caption
            reply_to_message_id: Optional message to reply to

        Returns:
            Result dictionary with success status and details
        """
        try:
            if not os.path.exists(file_path):
                return {
                    "success": False,
                    "error": f"File not found: {file_path}",
                    "method": "file_not_found",
                }

            media_type = self.get_media_type_from_extension(file_path)

            # Send using appropriate method based on media type
            if media_type == "image":
                result = await messenger.send_image(
                    image_source=file_path,
                    recipient=recipient,
                    caption=caption,
                    reply_to_message_id=reply_to_message_id,
                )

            elif media_type == "video":
                result = await messenger.send_video(
                    video_source=file_path,
                    recipient=recipient,
                    caption=caption,
                    reply_to_message_id=reply_to_message_id,
                )

            elif media_type == "audio":
                result = await messenger.send_audio(
                    audio_source=file_path,
                    recipient=recipient,
                    reply_to_message_id=reply_to_message_id,
                )

            elif media_type == "document":
                filename = os.path.basename(file_path)
                result = await messenger.send_document(
                    document_source=file_path,
                    recipient=recipient,
                    filename=filename,
                    caption=caption,
                    reply_to_message_id=reply_to_message_id,
                )

            else:
                return {
                    "success": False,
                    "error": f"Unsupported media type: {media_type}",
                    "method": "unsupported_type",
                }

            return {
                "success": result.success,
                "message_id": result.message_id
                if hasattr(result, "message_id")
                else None,
                "error": result.error if hasattr(result, "error") else None,
                "method": f"send_{media_type}",
                "media_type": media_type,
                "file_path": file_path,
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Error sending media: {str(e)}",
                "method": "exception",
                "file_path": file_path,
            }

    async def send_media_by_id(
        self,
        messenger,
        recipient: str,
        media_id: str,
        media_type: str,
        caption: str = None,
        reply_to_message_id: str = None,
    ) -> dict[str, any]:
        """
        Send media using media_id (relay existing media).

        Args:
            messenger: IMessenger instance
            recipient: Recipient phone number
            media_id: Media ID to send
            media_type: Type of media
            caption: Optional caption
            reply_to_message_id: Optional message to reply to

        Returns:
            Result dictionary with success status and details
        """
        try:
            # For relaying media using media_id, we need to use the media_id as source
            # This assumes the messenger can handle media_id as source parameter

            if media_type == "image":
                result = await messenger.send_image(
                    image_source=media_id,  # Using media_id as source
                    recipient=recipient,
                    caption=caption,
                    reply_to_message_id=reply_to_message_id,
                )

            elif media_type == "video":
                result = await messenger.send_video(
                    video_source=media_id,
                    recipient=recipient,
                    caption=caption,
                    reply_to_message_id=reply_to_message_id,
                )

            elif media_type in ["audio", "voice"]:
                result = await messenger.send_audio(
                    audio_source=media_id,
                    recipient=recipient,
                    reply_to_message_id=reply_to_message_id,
                )

            elif media_type == "document":
                result = await messenger.send_document(
                    document_source=media_id,
                    recipient=recipient,
                    caption=caption,
                    reply_to_message_id=reply_to_message_id,
                )

            elif media_type == "sticker":
                result = await messenger.send_sticker(
                    sticker_source=media_id,
                    recipient=recipient,
                    reply_to_message_id=reply_to_message_id,
                )

            else:
                return {
                    "success": False,
                    "error": f"Unsupported media type for relay: {media_type}",
                    "method": "unsupported_relay_type",
                }

            return {
                "success": result.success,
                "message_id": result.message_id
                if hasattr(result, "message_id")
                else None,
                "error": result.error if hasattr(result, "error") else None,
                "method": f"relay_{media_type}",
                "media_type": media_type,
                "media_id": media_id,
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Error relaying media: {str(e)}",
                "method": "relay_exception",
                "media_id": media_id,
            }


# Convenience functions for direct use
async def extract_media_info(webhook: IncomingMessageWebhook) -> dict[str, str] | None:
    """
    Extract media information from webhook (convenience function).

    Args:
        webhook: IncomingMessageWebhook to process

    Returns:
        Media info dictionary or None
    """
    handler = MediaHandler()
    return await handler.get_media_info_from_webhook(webhook)


async def send_local_media_file(
    messenger,
    recipient: str,
    filename: str,
    media_subdir: str = None,
    caption: str = None,
    reply_to_message_id: str = None,
) -> dict[str, any]:
    """
    Send local media file (convenience function).

    Args:
        messenger: IMessenger instance
        recipient: Recipient phone number
        filename: Name of media file in media directory
        media_subdir: Optional subdirectory
        caption: Optional caption
        reply_to_message_id: Optional message to reply to

    Returns:
        Result dictionary
    """
    handler = MediaHandler()
    file_path = handler.get_local_media_path(filename, media_subdir)

    return await handler.send_media_by_file(
        messenger=messenger,
        recipient=recipient,
        file_path=file_path,
        caption=caption,
        reply_to_message_id=reply_to_message_id,
    )


async def relay_webhook_media(
    messenger,
    webhook: IncomingMessageWebhook,
    recipient: str,
    reply_to_message_id: str = None,
) -> dict[str, any]:
    """
    Relay media from webhook to recipient (convenience function).

    Args:
        messenger: IMessenger instance
        webhook: Original webhook with media
        recipient: Recipient phone number
        reply_to_message_id: Optional message to reply to

    Returns:
        Result dictionary
    """
    handler = MediaHandler()

    # Extract media info from webhook
    media_info = await handler.get_media_info_from_webhook(webhook)
    if not media_info:
        return {
            "success": False,
            "error": "No media found in webhook",
            "method": "no_media",
        }

    # Relay using media_id
    return await handler.send_media_by_id(
        messenger=messenger,
        recipient=recipient,
        media_id=media_info["media_id"],
        media_type=media_info["type"],
        caption=media_info.get("caption"),
        reply_to_message_id=reply_to_message_id,
    )
