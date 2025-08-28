"""
List Activation Logic

Handles the /list command to activate interactive list mode.
Creates list state with 10-minute TTL and sends interactive list message.
"""

from typing import Any, Dict

from wappa.domain.interfaces.messaging_interface import IMessenger

from ..constants import LIST_STATE_TTL_SECONDS, STATE_TYPE_LIST


async def handle_list_activation(webhook, user_id: str, messenger: IMessenger,
                                 state_manager, interactive_builder) -> Dict[str, Any]:
    """
    Handle list activation command (/list).
    
    Creates list state and sends interactive list message with
    media options (image, video, audio, document).
    
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
        
        # Clean up any existing list state first
        await state_manager.delete_user_state(user_id, STATE_TYPE_LIST)
        
        # Send interactive list message
        list_result = await interactive_builder.send_list_message(
            user_id=user_id,
            reply_to_message_id=message_id
        )
        
        if not list_result.get("success"):
            return {
                "success": False,
                "error": f"Failed to send list message: {list_result.get('error')}",
                "command": "/list",
                "user_id": user_id
            }
            
        # Create list state with context
        list_context = list_result.get("list_context", {})
        list_context.update({
            "activation_message_id": message_id,
            "list_message_id": list_result.get("message_id"),
            "activated_at": webhook.get_webhook_timestamp() if hasattr(webhook, 'get_webhook_timestamp') else None,
            "expires_in_seconds": LIST_STATE_TTL_SECONDS
        })
        
        state_created = await state_manager.create_list_state(user_id, list_context)
        
        if not state_created:
            # List message was sent but state creation failed
            # Send warning but don't fail completely
            await messenger.send_text(
                recipient=user_id,
                text="⚠️ List message sent but state management failed. Manual cleanup may be needed.",
                reply_to_message_id=message_id
            )
            
        return {
            "success": True,
            "command": "/list",
            "user_id": user_id,
            "list_message_sent": True,
            "list_message_id": list_result.get("message_id"),
            "state_created": state_created,
            "state_ttl_seconds": LIST_STATE_TTL_SECONDS,
            "available_options": list(list_context.get("options", {}).keys()) if "options" in list_context else [],
            "next_step": "Select one of the options from the list to receive a sample media file"
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "command": "/list",
            "user_id": user_id
        }