"""
List Selection Logic

Handles list item selection responses when user is in list state.
Processes list selections and sends appropriate sample media files.
"""

from typing import Any, Dict

from wappa.domain.interfaces.messaging_interface import IMessenger

from ..constants import (
    LIST_ROW_IMAGE, LIST_ROW_VIDEO, LIST_ROW_AUDIO, LIST_ROW_DOCUMENT,
    STATE_TYPE_LIST
)


async def handle_list_selection(webhook, user_id: str, message_text: str, list_state,
                                messenger: IMessenger, state_manager, media_processor) -> Dict[str, Any]:
    """
    Handle list selection when user is in active list state.
    
    Processes interactive list selections and sends corresponding sample media files.
    
    Args:
        webhook: IncomingMessageWebhook
        user_id: User identifier
        message_text: Text content (may be list response)
        list_state: Active list state object
        messenger: Messaging interface
        state_manager: StateManager instance
        media_processor: MediaProcessor instance
        
    Returns:
        Dictionary with selection result
    """
    try:
        message_id = webhook.message.message_id
        
        # Check if this is an interactive list response
        selected_option_id = None
        
        # Try to extract option ID from webhook
        if hasattr(webhook, 'message') and webhook.message:
            message = webhook.message
            
            # Check for interactive response
            if hasattr(message, 'interactive') and message.interactive:
                interactive = message.interactive
                if hasattr(interactive, 'list_reply') and interactive.list_reply:
                    selected_option_id = interactive.list_reply.id
                    
        # If no interactive response, check if message text matches option titles
        if not selected_option_id and message_text:
            list_context = list_state.context.get("options", {})
            
            for option_id, option_info in list_context.items():
                option_title = option_info.get("title", "").lower()
                option_description = option_info.get("description", "").lower()
                message_lower = message_text.lower().strip()
                
                if (message_lower == option_title or
                    message_lower in option_description or
                    option_title in message_lower):
                    selected_option_id = option_id
                    break
                    
        # Validate option selection
        if not selected_option_id:
            from .list_prompt import handle_list_prompt
            return await handle_list_prompt(
                webhook=webhook,
                user_id=user_id,
                list_state=list_state,
                messenger=messenger,
                reason="Invalid list selection"
            )
            
        # Validate option ID is in expected options
        list_context = list_state.context.get("options", {})
        if selected_option_id not in list_context:
            from .list_prompt import handle_list_prompt
            return await handle_list_prompt(
                webhook=webhook,
                user_id=user_id,
                list_state=list_state,
                messenger=messenger,
                reason=f"Unknown option ID: {selected_option_id}"
            )
            
        # Process valid list selection
        option_info = list_context[selected_option_id]
        
        # Determine media type from option ID
        media_type_map = {
            LIST_ROW_IMAGE: "image",
            LIST_ROW_VIDEO: "video",
            LIST_ROW_AUDIO: "audio",
            LIST_ROW_DOCUMENT: "document"
        }
        
        media_type = media_type_map.get(selected_option_id)
        
        if not media_type:
            return {
                "success": False,
                "error": f"Unknown media type for option: {selected_option_id}",
                "handler": "list_selection",
                "user_id": user_id
            }
            
        # Send sample media file
        media_result = await media_processor.send_sample_media(
            user_id=user_id,
            media_type=media_type,
            reply_to_message_id=message_id
        )
        
        # Clean up list state (selection complete)
        await state_manager.delete_user_state(user_id, STATE_TYPE_LIST)
        
        # Send completion message
        completion_text = f"✅ List selection complete!\n\nYou selected: **{option_info.get('title')}**"
        completion_text += f"\n📄 {option_info.get('description', '')}"
        
        if media_result.get("success"):
            if media_result.get("fallback_used"):
                completion_text += f"\n⚠️ Sample {media_type} file not found, sent fallback message."
            else:
                completion_text += f"\n📁 Sample {media_type} file sent successfully!"
        else:
            completion_text += f"\n❌ Failed to send sample {media_type}: {media_result.get('error')}"
            
        completion_result = await messenger.send_text(
            recipient=user_id,
            text=completion_text,
            reply_to_message_id=message_id
        )
        
        return {
            "success": True,
            "handler": "list_selection",
            "user_id": user_id,
            "selected_option_id": selected_option_id,
            "selected_option_title": option_info.get("title"),
            "media_type": media_type,
            "media_response": media_result,
            "state_cleaned": True,
            "completion_message_sent": completion_result.success if completion_result else False,
            "interaction_complete": True
        }
        
    except Exception as e:
        # Clean up state on error
        try:
            await state_manager.delete_user_state(user_id, STATE_TYPE_LIST)
        except:
            pass
            
        return {
            "success": False,
            "error": str(e),
            "handler": "list_selection",
            "user_id": user_id,
            "state_cleaned": True
        }