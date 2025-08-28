"""
Button Prompt Logic

Handles prompting users to select valid button options when they
send invalid responses while in button state.
"""

from typing import Any, Dict

from wappa.domain.interfaces.messaging_interface import IMessenger

from ..constants import BUTTON_SELECTION_PROMPT


async def handle_button_prompt(webhook, user_id: str, button_state, messenger: IMessenger,
                               reason: str = "Invalid selection") -> Dict[str, Any]:
    """
    Prompt user to select valid button option.
    
    Called when user sends invalid response while in button state.
    Provides guidance on valid selections and maintains state.
    
    Args:
        webhook: IncomingMessageWebhook
        user_id: User identifier
        button_state: Active button state object
        messenger: Messaging interface
        reason: Reason for prompting
        
    Returns:
        Dictionary with prompt result
    """
    try:
        message_id = webhook.message.message_id
        
        # Build prompt message with available options
        button_context = button_state.context.get("buttons", {})
        
        prompt_text = f"⚠️ {reason}\n\n{BUTTON_SELECTION_PROMPT}\n\n"
        prompt_text += "🔘 **Available Options:**\n"
        
        for button_id, button_info in button_context.items():
            button_title = button_info.get("title", button_id)
            button_action = button_info.get("action", "")
            prompt_text += f"• **{button_title}**"
            
            if button_action:
                action_desc = button_action.replace("_", " ").title()
                prompt_text += f" - {action_desc}"
            prompt_text += "\n"
            
        # Add timing information
        time_remaining = button_state.time_remaining_seconds()
        if time_remaining > 0:
            minutes_remaining = max(1, time_remaining // 60)
            prompt_text += f"\n⏰ Button session expires in {minutes_remaining} minute(s)."
        else:
            prompt_text += "\n⏰ Button session has expired. Please use /button to start again."
            
        # Send prompt message
        prompt_result = await messenger.send_text(
            recipient=user_id,
            text=prompt_text,
            reply_to_message_id=message_id
        )
        
        return {
            "success": True,
            "handler": "button_prompt",
            "user_id": user_id,
            "reason": reason,
            "prompt_sent": prompt_result.success if prompt_result else False,
            "available_buttons": list(button_context.keys()),
            "time_remaining_seconds": time_remaining,
            "state_maintained": True
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "handler": "button_prompt",
            "user_id": user_id,
            "reason": reason
        }