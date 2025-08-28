"""
Button Activation Logic

Handles the /button command to activate interactive button mode.
Creates button state with 10-minute TTL and sends interactive button message.
"""

from typing import Any, Dict

from wappa.domain.interfaces.messaging_interface import IMessenger

from ..constants import BUTTON_STATE_TTL_SECONDS, STATE_TYPE_BUTTON


async def handle_button_activation(webhook, user_id: str, messenger: IMessenger,
                                   state_manager, interactive_builder) -> Dict[str, Any]:
    """
    Handle button activation command (/button).
    
    Creates button state and sends interactive button message with
    two options that will trigger different image responses.
    
    Args:
        webhook: IncomingMessageWebhook
        user_id: User identifier
        messenger: Messaging interface
        state_manager: StateManager instance
        interactive_builder: InteractiveBuilder instance
        
    Returns:
        Dictionary with activation result
    """
    try:
        message_id = webhook.message.message_id
        
        # Clean up any existing button state first
        await state_manager.delete_user_state(user_id, STATE_TYPE_BUTTON)
        
        # Send interactive button message
        button_result = await interactive_builder.send_button_message(
            user_id=user_id,
            reply_to_message_id=message_id
        )
        
        if not button_result.get("success"):
            return {
                "success": False,
                "error": f"Failed to send button message: {button_result.get('error')}",
                "command": "/button",
                "user_id": user_id
            }
            
        # Create button state with context
        button_context = button_result.get("button_context", {})
        button_context.update({
            "activation_message_id": message_id,
            "button_message_id": button_result.get("message_id"),
            "activated_at": webhook.get_webhook_timestamp() if hasattr(webhook, 'get_webhook_timestamp') else None,
            "expires_in_seconds": BUTTON_STATE_TTL_SECONDS
        })
        
        state_created = await state_manager.create_button_state(user_id, button_context)
        
        if not state_created:
            # Button message was sent but state creation failed
            # Send warning but don't fail completely
            await messenger.send_text(
                recipient=user_id,
                text="⚠️ Button message sent but state management failed. Manual cleanup may be needed.",
                reply_to_message_id=message_id
            )
            
        return {
            "success": True,
            "command": "/button",
            "user_id": user_id,
            "button_message_sent": True,
            "button_message_id": button_result.get("message_id"),
            "state_created": state_created,
            "state_ttl_seconds": BUTTON_STATE_TTL_SECONDS,
            "available_buttons": list(button_context.get("buttons", {}).keys()) if "buttons" in button_context else [],
            "next_step": "Select one of the buttons to receive a special image"
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "command": "/button",
            "user_id": user_id
        }