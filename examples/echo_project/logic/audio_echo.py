"""
Audio Echo Logic

Handles audio message echoing with comprehensive metadata extraction
and media processing using WhatsApp media IDs.
"""

from typing import Any, Dict

from wappa.domain.interfaces.messaging_interface import IMessenger

from ..constants import MEDIA_ECHO_ENABLED, MEDIA_METADATA_ENABLED


async def handle_audio_echo(webhook, user_id: str, messenger: IMessenger,
                            media_processor, metadata_extractor) -> Dict[str, Any]:
    """
    Handle audio message echo with metadata and media processing.
    
    Echoes the audio using WhatsApp media ID and extracts comprehensive
    metadata about the audio file and message context.
    
    Args:
        webhook: IncomingMessageWebhook
        user_id: User identifier
        messenger: Messaging interface
        media_processor: MediaProcessor instance
        metadata_extractor: Metadata extraction utilities
        
    Returns:
        Dictionary with echo result
    """
    try:
        message = webhook.message
        message_id = message.message_id
        
        # Extract audio data (handles both audio and voice messages)
        audio_data = None
        message_type = None
        
        if hasattr(message, 'audio') and message.audio:
            audio_data = message.audio
            message_type = "audio"
        elif hasattr(message, 'voice') and message.voice:
            audio_data = message.voice
            message_type = "voice"
            
        if not audio_data:
            return {
                "success": False,
                "error": "No audio or voice data found in message",
                "handler": "audio_echo",
                "user_id": user_id
            }
        
        # Prepare echo result
        result = {
            "success": True,
            "handler": "audio_echo",
            "user_id": user_id,
            "message_type": message_type,
            "original_message_id": message_id
        }
        
        # Echo audio using media ID if enabled
        if MEDIA_ECHO_ENABLED:
            echo_result = await media_processor.echo_media_by_id(
                user_id=user_id,
                media_type=message_type,
                media_id=getattr(audio_data, 'id', None),
                mime_type=getattr(audio_data, 'mime_type', None),
                sha256=getattr(audio_data, 'sha256', None),
                caption=None,  # Audio messages don't have captions
                reply_to_message_id=message_id
            )
            
            result.update({
                "echo_sent": echo_result.get("success", False),
                "echo_message_id": echo_result.get("message_id"),
                "echo_method": "media_id",
                "echo_error": echo_result.get("error") if not echo_result.get("success") else None
            })
        else:
            result["echo_sent"] = False
            result["echo_disabled"] = True
            
        # Extract and include metadata if enabled
        if MEDIA_METADATA_ENABLED:
            try:
                metadata = await metadata_extractor.extract_message_metadata(webhook)
                
                # Add audio-specific metadata
                audio_metadata = {
                    "media_id": getattr(audio_data, 'id', None),
                    "mime_type": getattr(audio_data, 'mime_type', None),
                    "sha256": getattr(audio_data, 'sha256', None),
                    "file_size": getattr(audio_data, 'file_size', None)
                }
                
                # Add voice-specific metadata
                if message_type == "voice":
                    audio_metadata.update({
                        "duration": getattr(audio_data, 'duration', None)
                    })
                
                # Filter out None values
                audio_metadata = {k: v for k, v in audio_metadata.items() if v is not None}
                
                result.update({
                    "metadata_extracted": True,
                    "general_metadata": metadata,
                    "audio_metadata": audio_metadata
                })
                
                # Send metadata response
                metadata_response = await metadata_extractor.build_metadata_response(
                    metadata, message_type=message_type, media_metadata=audio_metadata
                )
                
                if metadata_response:
                    metadata_result = await messenger.send_text(
                        recipient=user_id,
                        text=metadata_response,
                        reply_to_message_id=message_id
                    )
                    
                    result["metadata_response_sent"] = metadata_result.success if metadata_result else False
                    
            except Exception as metadata_error:
                result.update({
                    "metadata_extracted": False,
                    "metadata_error": str(metadata_error)
                })
        else:
            result["metadata_extraction_disabled"] = True
            
        return result
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "handler": "audio_echo",
            "user_id": user_id
        }