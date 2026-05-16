"""Media handling utilities for the Wappa Full Example application."""

import os
import tempfile
from pathlib import Path

import httpx

from wappa.webhooks import IncomingMessageWebhook


class MediaHandler:
    """Utility class for handling media operations."""

    def __init__(self, temp_dir: str | None = None) -> None:
        self.temp_dir = temp_dir or tempfile.gettempdir()
        self.session: httpx.AsyncClient | None = None

    async def __aenter__(self):
        self.session = httpx.AsyncClient()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.aclose()

    async def get_media_info_from_webhook(
        self, webhook: IncomingMessageWebhook
    ) -> dict[str, str] | None:
        """Extract media information from a webhook, or None if no media present."""
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
        if message_type in ["audio", "video", "voice"] and hasattr(message, "duration"):
            media_info["duration"] = message.duration

        return media_info

    async def download_media_by_id(
        self, media_id: str, messenger, media_type: str = None
    ) -> tuple[str, dict[str, str]] | None:
        """Placeholder — integrate with WhatsApp Business API to implement."""
        return None

    async def upload_local_media(
        self, file_path: str, media_type: str = None
    ) -> str | None:
        """Placeholder — integrate with WhatsApp Business API media upload to implement."""
        if os.path.exists(file_path):
            return f"local_{os.path.basename(file_path)}"
        return None

    def get_local_media_path(self, filename: str, media_subdir: str = None) -> str:
        base_dir = Path(__file__).parent.parent
        media_dir = base_dir / "media"
        if media_subdir:
            media_dir = media_dir / media_subdir
        return str(media_dir / filename)

    def media_file_exists(self, filename: str, media_subdir: str = None) -> bool:
        return os.path.exists(self.get_local_media_path(filename, media_subdir))

    def get_media_type_from_extension(self, filename: str) -> str:
        extension = Path(filename).suffix.lower()
        if extension in {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}:
            return "image"
        if extension in {".mp4", ".avi", ".mov", ".wmv", ".flv", ".webm"}:
            return "video"
        if extension in {".mp3", ".wav", ".aac", ".ogg", ".m4a", ".flac"}:
            return "audio"
        return "document"

    async def send_media_by_file(
        self,
        messenger,
        recipient: str,
        file_path: str,
        caption: str = None,
        reply_to_message_id: str = None,
    ) -> dict[str, any]:
        """Send a local media file using the appropriate messenger method."""
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
        """Relay existing media by ID using the appropriate messenger method."""
        try:
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


async def extract_media_info(webhook: IncomingMessageWebhook) -> dict[str, str] | None:
    """Extract media information from a webhook."""
    return await MediaHandler().get_media_info_from_webhook(webhook)


async def send_local_media_file(
    messenger,
    recipient: str,
    filename: str,
    media_subdir: str = None,
    caption: str = None,
    reply_to_message_id: str = None,
) -> dict[str, any]:
    """Send a local media file from the app's media directory."""
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
    """Relay media from an incoming webhook to a recipient."""
    handler = MediaHandler()
    media_info = await handler.get_media_info_from_webhook(webhook)
    if not media_info:
        return {
            "success": False,
            "error": "No media found in webhook",
            "method": "no_media",
        }
    return await handler.send_media_by_id(
        messenger=messenger,
        recipient=recipient,
        media_id=media_info["media_id"],
        media_type=media_info["type"],
        caption=media_info.get("caption"),
        reply_to_message_id=reply_to_message_id,
    )
