"""
Media Processor for Echo Project

Handles media file operations including echoing media using WhatsApp media IDs,
sending sample media files, and extracting media metadata.

Features:
- Media echo using WhatsApp media IDs (preferred method)
- Sample media file sending for interactive lists
- Media metadata extraction and analysis
- Support for all WhatsApp media types
- Fallback handling for missing files
- Comprehensive error handling and logging
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional

from wappa.domain.interfaces.messaging_interface import IMessenger

from constants import (
    SUPPORTED_MEDIA_TYPES, MAX_MEDIA_SIZE_MB, MEDIA_ECHO_PREFIX,
    MEDIA_PATH_IMAGE, MEDIA_PATH_VIDEO, MEDIA_PATH_AUDIO, MEDIA_PATH_DOCUMENT,
    LIST_ROW_IMAGE, LIST_ROW_VIDEO, LIST_ROW_AUDIO, LIST_ROW_DOCUMENT
)


class MediaProcessor:
    """
    Processes media files for echo functionality and interactive features.
    
    Handles media echoing using WhatsApp media IDs, sending sample files,
    and extracting metadata from media messages.
    """
    
    def __init__(self, messenger: IMessenger, logger):
        """
        Initialize MediaProcessor with messenger and logger.
        
        Args:
            messenger: Wappa messaging interface
            logger: Logger instance for debugging
        """
        self.messenger = messenger
        self.logger = logger
        
    async def echo_media_by_id(self, webhook, user_id: str, media_type: str, 
                               reply_to_message_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Echo media back using WhatsApp media ID (preferred method).
        
        This uses the same media file that was sent by extracting the media_id
        from the webhook and sending it back without re-uploading.
        
        Args:
            webhook: IncomingMessageWebhook containing media data
            user_id: Recipient user ID
            media_type: Type of media (image, video, audio, document)
            reply_to_message_id: Optional message ID to reply to
            
        Returns:
            Dictionary with echo result
        """
        try:
            self.logger.info(f"🔄 Echoing {media_type} using media ID for {user_id}")
            
            # Extract media information from webhook
            media_info = self._extract_media_info(webhook, media_type)
            
            if not media_info.get("media_id"):
                self.logger.error(f"❌ No media ID found for {media_type} echo")
                return {
                    "success": False,
                    "error": "No media ID found in webhook",
                    "media_type": media_type
                }
                
            media_id = media_info["media_id"]
            caption = f"{MEDIA_ECHO_PREFIX}{media_type.upper()} echo - using media ID {media_id}"
            
            # Add metadata to caption if available
            if media_info.get("filename"):
                caption += f"\n📄 Original filename: {media_info['filename']}"
            if media_info.get("mime_type"):
                caption += f"\n🔍 MIME type: {media_info['mime_type']}"
                
            # Echo based on media type using media ID
            if media_type == "image":
                result = await self.messenger.send_image(
                    recipient=user_id,
                    media_id=media_id,
                    caption=caption,
                    reply_to_message_id=reply_to_message_id
                )
                
            elif media_type == "video":
                result = await self.messenger.send_video(
                    recipient=user_id,
                    media_id=media_id,
                    caption=caption,
                    reply_to_message_id=reply_to_message_id
                )
                
            elif media_type == "audio":
                result = await self.messenger.send_audio(
                    recipient=user_id,
                    media_id=media_id,
                    reply_to_message_id=reply_to_message_id
                )
                
            elif media_type == "document":
                result = await self.messenger.send_document(
                    recipient=user_id,
                    media_id=media_id,
                    filename=media_info.get("filename"),
                    caption=caption,
                    reply_to_message_id=reply_to_message_id
                )
                
            else:
                self.logger.error(f"❌ Unsupported media type for echo: {media_type}")
                return {
                    "success": False,
                    "error": f"Unsupported media type: {media_type}",
                    "media_type": media_type
                }
                
            if result.success:
                self.logger.info(f"✅ Media echo sent using ID {media_id}: {result.message_id}")
                return {
                    "success": True,
                    "message_id": result.message_id,
                    "media_id": media_id,
                    "media_type": media_type,
                    "echo_method": "media_id",
                    "original_media_info": media_info
                }
            else:
                self.logger.error(f"❌ Failed to echo {media_type} using media ID: {result.error}")
                return {
                    "success": False,
                    "error": result.error,
                    "media_id": media_id,
                    "media_type": media_type
                }
                
        except Exception as e:
            self.logger.error(f"❌ Error echoing media by ID for {user_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "media_type": media_type
            }
            
    async def send_sample_media(self, user_id: str, media_type: str, 
                                reply_to_message_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Send sample media file based on type (for interactive list responses).
        
        Args:
            user_id: Recipient user ID  
            media_type: Type of media to send (image, video, audio, document)
            reply_to_message_id: Optional message ID to reply to
            
        Returns:
            Dictionary with send result
        """
        try:
            self.logger.info(f"📁 Sending sample {media_type} to {user_id}")
            
            # Get sample file path based on media type
            media_path = self._get_sample_media_path(media_type)
            
            if not os.path.exists(media_path):
                self.logger.warning(f"⚠️ Sample {media_type} file not found: {media_path}")
                
                # Send fallback text message
                fallback_text = f"📁 Sample {media_type.upper()} file\n\n(File not found: {os.path.basename(media_path)})\n\nThis demonstrates how the interactive list would send media files."
                
                result = await self.messenger.send_text(
                    recipient=user_id,
                    text=fallback_text,
                    reply_to_message_id=reply_to_message_id
                )
                
                return {
                    "success": result.success,
                    "message_id": result.message_id if result.success else None,
                    "error": result.error if not result.success else None,
                    "media_type": media_type,
                    "fallback_used": True,
                    "media_path": media_path
                }
                
            # Send actual media file
            caption = f"📁 Sample {media_type.upper()} file from Echo Project"
            
            if media_type == "image":
                result = await self.messenger.send_image(
                    recipient=user_id,
                    image_path=media_path,
                    caption=caption,
                    reply_to_message_id=reply_to_message_id
                )
                
            elif media_type == "video":
                result = await self.messenger.send_video(
                    recipient=user_id,
                    video_path=media_path,
                    caption=caption,
                    reply_to_message_id=reply_to_message_id
                )
                
            elif media_type == "audio":
                result = await self.messenger.send_audio(
                    recipient=user_id,
                    audio_path=media_path,
                    reply_to_message_id=reply_to_message_id
                )
                
            elif media_type == "document":
                result = await self.messenger.send_document(
                    recipient=user_id,
                    document_path=media_path,
                    filename=os.path.basename(media_path),
                    caption=caption,
                    reply_to_message_id=reply_to_message_id
                )
                
            else:
                self.logger.error(f"❌ Unsupported sample media type: {media_type}")
                return {
                    "success": False,
                    "error": f"Unsupported media type: {media_type}",
                    "media_type": media_type
                }
                
            if result.success:
                self.logger.info(f"✅ Sample {media_type} sent to {user_id}: {result.message_id}")
                return {
                    "success": True,
                    "message_id": result.message_id,
                    "media_type": media_type,
                    "media_path": media_path,
                    "file_size_bytes": os.path.getsize(media_path),
                    "fallback_used": False
                }
            else:
                self.logger.error(f"❌ Failed to send sample {media_type}: {result.error}")
                return {
                    "success": False,
                    "error": result.error,
                    "media_type": media_type,
                    "media_path": media_path
                }
                
        except Exception as e:
            self.logger.error(f"❌ Error sending sample media for {user_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "media_type": media_type
            }
            
    def extract_media_metadata(self, webhook, media_type: str) -> Dict[str, Any]:
        """
        Extract comprehensive metadata from media webhook.
        
        Args:
            webhook: IncomingMessageWebhook containing media data
            media_type: Type of media (image, video, audio, document)
            
        Returns:
            Dictionary with extracted metadata
        """
        try:
            self.logger.debug(f"📊 Extracting {media_type} metadata")
            
            # Base metadata
            metadata = {
                "media_type": media_type,
                "supported_type": media_type in SUPPORTED_MEDIA_TYPES,
                "extraction_timestamp": webhook.get_webhook_timestamp() if hasattr(webhook, 'get_webhook_timestamp') else None
            }
            
            # Extract media-specific info
            media_info = self._extract_media_info(webhook, media_type)
            metadata.update(media_info)
            
            # Add file size analysis
            if metadata.get("file_size"):
                size_mb = metadata["file_size"] / (1024 * 1024)
                metadata["file_size_mb"] = round(size_mb, 2)
                metadata["within_size_limit"] = size_mb <= MAX_MEDIA_SIZE_MB
                
            # Add format analysis
            if metadata.get("mime_type"):
                metadata["format_supported"] = self._is_format_supported(metadata["mime_type"], media_type)
                
            self.logger.debug(f"📊 Extracted {len(metadata)} metadata fields for {media_type}")
            return metadata
            
        except Exception as e:
            self.logger.error(f"❌ Error extracting media metadata: {e}")
            return {
                "media_type": media_type,
                "error": str(e),
                "extraction_failed": True
            }
            
    def _extract_media_info(self, webhook, media_type: str) -> Dict[str, Any]:
        """Extract media information from webhook based on type."""
        try:
            media_info = {}
            
            # Try to extract from webhook message object
            if hasattr(webhook, 'message') and webhook.message:
                message = webhook.message
                
                # Common media fields
                if hasattr(message, 'media_id'):
                    media_info["media_id"] = message.media_id
                if hasattr(message, 'filename'):
                    media_info["filename"] = message.filename
                if hasattr(message, 'mime_type'):
                    media_info["mime_type"] = message.mime_type
                if hasattr(message, 'file_size'):
                    media_info["file_size"] = message.file_size
                if hasattr(message, 'sha256'):
                    media_info["sha256"] = message.sha256
                    
                # Media-specific fields
                if media_type == "image":
                    if hasattr(message, 'caption'):
                        media_info["caption"] = message.caption
                        
                elif media_type == "video":
                    if hasattr(message, 'caption'):
                        media_info["caption"] = message.caption
                        
                elif media_type == "audio":
                    if hasattr(message, 'voice'):
                        media_info["is_voice_message"] = message.voice
                        
                elif media_type == "document":
                    if hasattr(message, 'caption'):
                        media_info["caption"] = message.caption
                        
            # Try alternative extraction methods if needed
            if not media_info and hasattr(webhook, 'get_raw_webhook_data'):
                raw_data = webhook.get_raw_webhook_data()
                if raw_data and 'entry' in raw_data:
                    # Extract from raw webhook data structure
                    media_info.update(self._extract_from_raw_data(raw_data, media_type))
                    
            return media_info
            
        except Exception as e:
            self.logger.error(f"❌ Error extracting media info for {media_type}: {e}")
            return {"error": str(e)}
            
    def _extract_from_raw_data(self, raw_data: Dict[str, Any], media_type: str) -> Dict[str, Any]:
        """Extract media info from raw webhook data as fallback."""
        try:
            media_info = {}
            
            # Navigate webhook structure to find media data
            for entry in raw_data.get('entry', []):
                for change in entry.get('changes', []):
                    value = change.get('value', {})
                    for message in value.get('messages', []):
                        if media_type in message:
                            media_data = message[media_type]
                            media_info.update({
                                "media_id": media_data.get('id'),
                                "mime_type": media_data.get('mime_type'),
                                "sha256": media_data.get('sha256'),
                                "filename": media_data.get('filename'),
                                "file_size": media_data.get('file_size'),
                                "caption": media_data.get('caption')
                            })
                            break
                            
            return {k: v for k, v in media_info.items() if v is not None}
            
        except Exception as e:
            self.logger.error(f"❌ Error extracting from raw data: {e}")
            return {}
            
    def _get_sample_media_path(self, media_type: str) -> str:
        """Get path to sample media file based on type."""
        # Map media types to file paths
        path_map = {
            "image": MEDIA_PATH_IMAGE,
            "video": MEDIA_PATH_VIDEO, 
            "audio": MEDIA_PATH_AUDIO,
            "document": MEDIA_PATH_DOCUMENT
        }
        
        relative_path = path_map.get(media_type)
        if not relative_path:
            raise ValueError(f"No sample file path configured for media type: {media_type}")
            
        # Get echo_project directory (parent of this file)
        echo_project_dir = Path(__file__).parent
        
        # Join with relative path
        absolute_path = echo_project_dir / relative_path
        
        return str(absolute_path)
        
    def _is_format_supported(self, mime_type: str, media_type: str) -> bool:
        """Check if media format is supported based on MIME type."""
        # WhatsApp supported formats (basic check)
        supported_formats = {
            "image": ["image/jpeg", "image/png", "image/webp"],
            "video": ["video/mp4", "video/3gpp", "video/quicktime"],
            "audio": ["audio/aac", "audio/mp3", "audio/mpeg", "audio/ogg", "audio/wav"],
            "document": [
                "application/pdf", "application/msword", 
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "text/plain", "application/vnd.ms-excel",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ]
        }
        
        return mime_type in supported_formats.get(media_type, [])
        
    def get_media_capabilities(self) -> Dict[str, Any]:
        """Get current media processing capabilities."""
        try:
            capabilities = {
                "supported_media_types": SUPPORTED_MEDIA_TYPES,
                "max_file_size_mb": MAX_MEDIA_SIZE_MB,
                "echo_by_media_id": True,
                "sample_media_files": {},
                "messenger_capabilities": {}
            }
            
            # Check sample file availability
            for media_type in SUPPORTED_MEDIA_TYPES:
                try:
                    sample_path = self._get_sample_media_path(media_type)
                    capabilities["sample_media_files"][media_type] = {
                        "available": os.path.exists(sample_path),
                        "path": sample_path,
                        "size_bytes": os.path.getsize(sample_path) if os.path.exists(sample_path) else None
                    }
                except Exception as e:
                    capabilities["sample_media_files"][media_type] = {
                        "available": False,
                        "error": str(e)
                    }
                    
            # Check messenger capabilities
            capabilities["messenger_capabilities"] = {
                "send_image": hasattr(self.messenger, 'send_image'),
                "send_video": hasattr(self.messenger, 'send_video'),
                "send_audio": hasattr(self.messenger, 'send_audio'),
                "send_document": hasattr(self.messenger, 'send_document'),
                "media_id_support": True  # Assume supported by messenger interface
            }
            
            return capabilities
            
        except Exception as e:
            self.logger.error(f"❌ Error getting media capabilities: {e}")
            return {
                "error": str(e),
                "capabilities_check_failed": True
            }