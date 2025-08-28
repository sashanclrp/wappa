"""
Image Echo Logic

Handles image message echoing with comprehensive metadata extraction
and media processing using WhatsApp media IDs.
"""

from typing import Any, Dict

from wappa.domain.interfaces.messaging_interface import IMessenger

from ..constants import MEDIA_ECHO_ENABLED, MEDIA_METADATA_ENABLED


async def handle_image_echo(webhook, user_id: str, messenger: IMessenger,
                            media_processor, metadata_extractor) -> Dict[str, Any]:
    """
    Handle image message echo with metadata and media processing.
    
    Echoes the image using WhatsApp media ID and extracts comprehensive
    metadata about the image file and message context.
    
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
        
        # Extract image data
        if not hasattr(message, 'image') or not message.image:
            return {
                "success": False,
                "error": "No image data found in message",
                "handler": "image_echo",
                "user_id": user_id
            }
            
        image_data = message.image
        
        # Prepare echo result
        result = {
            "success": True,
            "handler": "image_echo",
            "user_id": user_id,
            "message_type": "image",
            "original_message_id": message_id
        }
        
        # Echo image using media ID if enabled
        if MEDIA_ECHO_ENABLED:
            echo_result = await media_processor.echo_media_by_id(
                user_id=user_id,
                media_type="image",
                media_id=getattr(image_data, 'id', None),
                mime_type=getattr(image_data, 'mime_type', None),
                sha256=getattr(image_data, 'sha256', None),
                caption=getattr(image_data, 'caption', None),
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
                
                # Add image-specific metadata
                image_metadata = {
                    "media_id": getattr(image_data, 'id', None),
                    "mime_type": getattr(image_data, 'mime_type', None),
                    "sha256": getattr(image_data, 'sha256', None),
                    "caption": getattr(image_data, 'caption', None),
                    "file_size": getattr(image_data, 'file_size', None)
                }
                
                # Filter out None values
                image_metadata = {k: v for k, v in image_metadata.items() if v is not None}
                
                result.update({
                    "metadata_extracted": True,
                    "general_metadata": metadata,
                    "image_metadata": image_metadata
                })
                
                # Send metadata response
                metadata_response = await metadata_extractor.build_metadata_response(
                    metadata, message_type="image", media_metadata=image_metadata
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
            "handler": "image_echo",
            "user_id": user_id
        }