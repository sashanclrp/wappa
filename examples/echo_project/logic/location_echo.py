"""
Location Echo Logic

Handles location message echoing with comprehensive metadata extraction
and location information processing.
"""

from typing import Any, Dict

from wappa.domain.interfaces.messaging_interface import IMessenger

from ..constants import LOCATION_ECHO_ENABLED, LOCATION_METADATA_ENABLED


async def handle_location_echo(webhook, user_id: str, messenger: IMessenger,
                               metadata_extractor) -> Dict[str, Any]:
    """
    Handle location message echo with metadata and location processing.
    
    Echoes the location information and extracts comprehensive
    metadata about the location data and message context.
    
    Args:
        webhook: IncomingMessageWebhook
        user_id: User identifier
        messenger: Messaging interface
        metadata_extractor: Metadata extraction utilities
        
    Returns:
        Dictionary with echo result
    """
    try:
        message = webhook.message
        message_id = message.message_id
        
        # Extract location data
        if not hasattr(message, 'location') or not message.location:
            return {
                "success": False,
                "error": "No location data found in message",
                "handler": "location_echo",
                "user_id": user_id
            }
            
        location_data = message.location
        
        # Prepare echo result
        result = {
            "success": True,
            "handler": "location_echo",
            "user_id": user_id,
            "message_type": "location",
            "original_message_id": message_id
        }
        
        # Extract location details
        latitude = getattr(location_data, 'latitude', None)
        longitude = getattr(location_data, 'longitude', None)
        name = getattr(location_data, 'name', None)
        address = getattr(location_data, 'address', None)
        url = getattr(location_data, 'url', None)
        
        # Build location echo response
        if LOCATION_ECHO_ENABLED:
            echo_text = "📍 **Location Echo**\n\n"
            
            if name:
                echo_text += f"🏷️ **Name:** {name}\n"
            if address:
                echo_text += f"🏠 **Address:** {address}\n"
            if latitude and longitude:
                echo_text += f"🌍 **Coordinates:** {latitude}, {longitude}\n"
                # Create Google Maps link
                maps_url = f"https://www.google.com/maps?q={latitude},{longitude}"
                echo_text += f"🗺️ **Map:** {maps_url}\n"
            if url:
                echo_text += f"🔗 **URL:** {url}\n"
            
            echo_text += "\n✅ Location received and echoed back!"
            
            echo_result = await messenger.send_text(
                recipient=user_id,
                text=echo_text,
                reply_to_message_id=message_id
            )
            
            result.update({
                "echo_sent": echo_result.success if echo_result else False,
                "echo_message_id": echo_result.message_id if echo_result else None,
                "echo_text_length": len(echo_text),
                "echo_error": None if echo_result and echo_result.success else "Failed to send echo"
            })
        else:
            result["echo_sent"] = False
            result["echo_disabled"] = True
            
        # Extract and include metadata if enabled
        if LOCATION_METADATA_ENABLED:
            try:
                metadata = await metadata_extractor.extract_message_metadata(webhook)
                
                # Add location-specific metadata
                location_metadata = {
                    "latitude": latitude,
                    "longitude": longitude,
                    "name": name,
                    "address": address,
                    "url": url
                }
                
                # Filter out None values
                location_metadata = {k: v for k, v in location_metadata.items() if v is not None}
                
                result.update({
                    "metadata_extracted": True,
                    "general_metadata": metadata,
                    "location_metadata": location_metadata
                })
                
                # Send metadata response
                metadata_response = await metadata_extractor.build_metadata_response(
                    metadata, message_type="location", media_metadata=location_metadata
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
            "handler": "location_echo",
            "user_id": user_id
        }