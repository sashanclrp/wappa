"""
List Prompt Logic

Handles prompting users to select valid list options when they
send invalid responses while in list state.
"""

from typing import Any, Dict

from wappa.domain.interfaces.messaging_interface import IMessenger

from ..constants import LIST_SELECTION_PROMPT


async def handle_list_prompt(webhook, user_id: str, list_state, messenger: IMessenger,
                             reason: str = "Invalid selection") -> Dict[str, Any]:
    """
    Prompt user to select valid list option.
    
    Called when user sends invalid response while in list state.
    Provides guidance on valid selections and maintains state.
    
    Args:
        webhook: IncomingMessageWebhook
        user_id: User identifier
        list_state: Active list state object
        messenger: Messaging interface
        reason: Reason for prompting
        
    Returns:
        Dictionary with prompt result
    """
    try:
        message_id = webhook.message.message_id
        
        # Build prompt message with available options
        list_context = list_state.context.get("options", {})
        
        prompt_text = f"⚠️ {reason}\n\n{LIST_SELECTION_PROMPT}\n\n"
        prompt_text += "📋 **Available Options:**\n"
        
        for option_id, option_info in list_context.items():
            option_title = option_info.get("title", option_id)
            option_description = option_info.get("description", "")
            
            prompt_text += f"• **{option_title}**"
            if option_description:
                prompt_text += f" - {option_description}"
            prompt_text += "\n"
            
        # Add timing information
        time_remaining = list_state.time_remaining_seconds()
        if time_remaining > 0:
            minutes_remaining = max(1, time_remaining // 60)
            prompt_text += f"\n⏰ List session expires in {minutes_remaining} minute(s)."
        else:
            prompt_text += "\n⏰ List session has expired. Please use /list to start again."
            
        # Send prompt message
        prompt_result = await messenger.send_text(
            recipient=user_id,
            text=prompt_text,
            reply_to_message_id=message_id
        )
        
        return {
            "success": True,
            "handler": "list_prompt",
            "user_id": user_id,
            "reason": reason,
            "prompt_sent": prompt_result.success if prompt_result else False,
            "available_options": list(list_context.keys()),
            "time_remaining_seconds": time_remaining,
            "state_maintained": True
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "handler": "list_prompt",
            "user_id": user_id,
            "reason": reason
        }