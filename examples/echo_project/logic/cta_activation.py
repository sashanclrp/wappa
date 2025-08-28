"""
CTA Activation Logic

Handles the /cta command to send call-to-action button message.
This is stateless - no state management needed.
"""

from typing import Any, Dict

from wappa.domain.interfaces.messaging_interface import IMessenger


async def handle_cta_activation(webhook, user_id: str, messenger: IMessenger,
                                interactive_builder) -> Dict[str, Any]:
    """
    Handle CTA activation command (/cta).
    
    Sends call-to-action message with URL button. This is stateless.
    
    Args:
        webhook: IncomingMessageWebhook
        user_id: User identifier
        messenger: Messaging interface
        interactive_builder: InteractiveBuilder instance
        
    Returns:
        Dictionary with activation result
    """
    try:
        message_id = webhook.message.message_id
        
        # Send CTA message
        cta_result = await interactive_builder.send_cta_message(
            user_id=user_id,
            reply_to_message_id=message_id
        )
        
        if cta_result.get("success"):
            return {
                "success": True,
                "command": "/cta",
                "user_id": user_id,
                "cta_message_sent": True,
                "cta_message_id": cta_result.get("message_id"),
                "button_url": cta_result.get("button_url"),
                "interaction_type": "stateless",
                "next_step": "Click the button to open the external link"
            }
        else:
            return {
                "success": False,
                "error": f"Failed to send CTA message: {cta_result.get('error')}",
                "command": "/cta",
                "user_id": user_id
            }
            
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "command": "/cta",
            "user_id": user_id
        }