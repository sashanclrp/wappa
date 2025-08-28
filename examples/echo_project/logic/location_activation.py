"""
Location Activation Logic

Handles the /location command to request location sharing.
This is stateless - no state management needed.
"""

from typing import Any, Dict

from wappa.domain.interfaces.messaging_interface import IMessenger

from ..constants import LOCATION_REQUEST_BODY


async def handle_location_activation(webhook, user_id: str, messenger: IMessenger) -> Dict[str, Any]:
    """
    Handle location activation command (/location).
    
    Sends location request message. This is stateless.
    
    Args:
        webhook: IncomingMessageWebhook
        user_id: User identifier
        messenger: Messaging interface
        
    Returns:
        Dictionary with activation result
    """
    try:
        message_id = webhook.message.message_id
        
        # Send location request message
        location_result = await messenger.send_text(
            recipient=user_id,
            text=LOCATION_REQUEST_BODY,
            reply_to_message_id=message_id
        )
        
        if location_result.success:
            return {
                "success": True,
                "command": "/location",
                "user_id": user_id,
                "location_request_sent": True,
                "location_request_message_id": location_result.message_id,
                "interaction_type": "stateless",
                "next_step": "Share your location using the WhatsApp location sharing feature"
            }
        else:
            return {
                "success": False,
                "error": f"Failed to send location request: {location_result.error}",
                "command": "/location",
                "user_id": user_id
            }
            
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "command": "/location",
            "user_id": user_id
        }