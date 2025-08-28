"""
Message Confirmation Logic

Handles read receipts and typing indicators for message confirmation.
"""

import asyncio
from typing import Any, Dict, Optional

from wappa.domain.interfaces.messaging_interface import IMessenger

from ..constants import TYPING_INDICATOR_ENABLED, READ_RECEIPT_ENABLED


async def mark_as_read_with_typing(messenger: IMessenger, message_id: str,
                                   typing: bool = True, typing_duration: float = 2.0) -> Dict[str, Any]:
    """
    Mark message as read and optionally show typing indicator.
    
    Args:
        messenger: Messaging interface
        message_id: Message ID to mark as read
        typing: Whether to show typing indicator
        typing_duration: How long to show typing (seconds)
        
    Returns:
        Dictionary with confirmation result
    """
    try:
        results = {
            "message_id": message_id,
            "read_receipt": {"attempted": False, "success": False},
            "typing_indicator": {"attempted": False, "success": False}
        }
        
        # Mark as read if enabled
        if READ_RECEIPT_ENABLED:
            try:
                results["read_receipt"]["attempted"] = True
                
                # Use mark_as_read method if available
                if hasattr(messenger, 'mark_as_read'):
                    read_result = await messenger.mark_as_read(
                        message_id=message_id,
                        typing=typing and TYPING_INDICATOR_ENABLED
                    )
                    
                    if hasattr(read_result, 'success'):
                        results["read_receipt"]["success"] = read_result.success
                        if not read_result.success:
                            results["read_receipt"]["error"] = getattr(read_result, 'error', 'Unknown error')
                    else:
                        # Assume success if no explicit result object
                        results["read_receipt"]["success"] = True
                        
                else:
                    results["read_receipt"]["error"] = "mark_as_read method not available"
                    
            except Exception as e:
                results["read_receipt"]["error"] = str(e)
                
        # Show typing indicator if enabled and requested
        if typing and TYPING_INDICATOR_ENABLED:
            try:
                results["typing_indicator"]["attempted"] = True
                
                # If mark_as_read handles typing, we're done
                if results["read_receipt"]["success"] and hasattr(messenger, 'mark_as_read'):
                    results["typing_indicator"]["success"] = True
                    results["typing_indicator"]["method"] = "combined_with_read_receipt"
                    
                # Otherwise try separate typing method
                elif hasattr(messenger, 'send_typing_indicator'):
                    typing_result = await messenger.send_typing_indicator(typing_duration)
                    
                    if hasattr(typing_result, 'success'):
                        results["typing_indicator"]["success"] = typing_result.success
                        if not typing_result.success:
                            results["typing_indicator"]["error"] = getattr(typing_result, 'error', 'Unknown error')
                    else:
                        results["typing_indicator"]["success"] = True
                        
                    results["typing_indicator"]["method"] = "separate_typing_call"
                    
                # Fallback: just wait to simulate typing
                else:
                    await asyncio.sleep(typing_duration)
                    results["typing_indicator"]["success"] = True
                    results["typing_indicator"]["method"] = "simulated_delay"
                    
            except Exception as e:
                results["typing_indicator"]["error"] = str(e)
                
        # Overall success
        read_success = results["read_receipt"]["success"] if results["read_receipt"]["attempted"] else True
        typing_success = results["typing_indicator"]["success"] if results["typing_indicator"]["attempted"] else True
        
        results["success"] = read_success and typing_success
        results["attempted_operations"] = []
        
        if results["read_receipt"]["attempted"]:
            results["attempted_operations"].append("read_receipt")
        if results["typing_indicator"]["attempted"]:
            results["attempted_operations"].append("typing_indicator")
            
        return results
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message_id": message_id,
            "attempted_operations": []
        }