"""
Button Selection Logic

Handles button click responses when user is in button state.
Processes button selections and sends appropriate image responses.
"""

from typing import Any, Dict

from wappa.domain.interfaces.messaging_interface import IMessenger

from ..constants import BUTTON_ID_NICE, BUTTON_ID_YOURS, STATE_TYPE_BUTTON


async def handle_button_selection(webhook, user_id: str, message_text: str, button_state,
                                  messenger: IMessenger, state_manager, interactive_builder) -> Dict[str, Any]:
    """
    Handle button selection when user is in active button state.
    
    Processes interactive button clicks and sends corresponding image responses.
    
    Args:
        webhook: IncomingMessageWebhook
        user_id: User identifier
        message_text: Text content (may be button response)
        button_state: Active button state object
        messenger: Messaging interface
        state_manager: StateManager instance
        interactive_builder: InteractiveBuilder instance
        
    Returns:
        Dictionary with selection result
    """
    try:
        message_id = webhook.message.message_id
        
        # Check if this is an interactive button response
        selected_button_id = None
        
        # Try to extract button ID from webhook
        if hasattr(webhook, 'message') and webhook.message:
            message = webhook.message
            
            # Check for interactive response
            if hasattr(message, 'interactive') and message.interactive:
                interactive = message.interactive
                if hasattr(interactive, 'button_reply') and interactive.button_reply:
                    selected_button_id = interactive.button_reply.id
                    
        # If no interactive response, check if message text matches button titles
        if not selected_button_id and message_text:
            button_context = button_state.context.get("buttons", {})
            
            for button_id, button_info in button_context.items():
                button_title = button_info.get("title", "").lower()
                if message_text.lower().strip() == button_title:
                    selected_button_id = button_id
                    break
                    
        # Validate button selection
        if not selected_button_id:
            from .button_prompt import handle_button_prompt
            return await handle_button_prompt(
                webhook=webhook,
                user_id=user_id,
                button_state=button_state,
                messenger=messenger,
                reason="Invalid button selection"
            )
            
        # Validate button ID is in expected options
        button_context = button_state.context.get("buttons", {})
        if selected_button_id not in button_context:
            from .button_prompt import handle_button_prompt
            return await handle_button_prompt(
                webhook=webhook,
                user_id=user_id,
                button_state=button_state,
                messenger=messenger,
                reason=f"Unknown button ID: {selected_button_id}"
            )
            
        # Process valid button selection
        button_info = button_context[selected_button_id]
        
        # Send button response image
        response_result = await interactive_builder.send_button_image_response(
            user_id=user_id,
            button_id=selected_button_id,
            reply_to_message_id=message_id
        )
        
        # Clean up button state (selection complete)
        await state_manager.delete_user_state(user_id, STATE_TYPE_BUTTON)
        
        # Send completion message
        completion_text = f"✅ Button selection complete!\n\nYou selected: **{button_info.get('title')}**"
        
        if response_result.get("success"):
            completion_text += f"\n📸 Image sent successfully!"
        else:
            completion_text += f"\n⚠️ Image sending failed: {response_result.get('error')}"
            
        completion_result = await messenger.send_text(
            recipient=user_id,
            text=completion_text,
            reply_to_message_id=message_id
        )
        
        return {
            "success": True,
            "handler": "button_selection",
            "user_id": user_id,
            "selected_button_id": selected_button_id,
            "selected_button_title": button_info.get("title"),
            "image_response": response_result,
            "state_cleaned": True,
            "completion_message_sent": completion_result.success if completion_result else False,
            "interaction_complete": True
        }
        
    except Exception as e:
        # Clean up state on error
        try:
            await state_manager.delete_user_state(user_id, STATE_TYPE_BUTTON)
        except:
            pass
            
        return {
            "success": False,
            "error": str(e),
            "handler": "button_selection",
            "user_id": user_id,
            "state_cleaned": True
        }