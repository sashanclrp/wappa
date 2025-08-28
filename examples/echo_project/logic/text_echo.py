"""
Text Echo Logic

Handles text message echoing with comprehensive metadata extraction,
user storage, and message confirmation features.
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, Optional

from wappa.domain.interfaces.messaging_interface import IMessenger
from wappa.domain.interfaces.cache_interface import ICache

from ..constants import (
    ECHO_PROCESSING_DELAY_SECONDS, METADATA_EXTRACTION_ENABLED,
    USER_STORAGE_ENABLED, MESSAGE_CONFIRMATION_ENABLED, USER_DATA_TTL_SECONDS
)


async def handle_text_echo(webhook, user_id: str, message_text: str, 
                           messenger: IMessenger, user_cache: ICache, 
                           media_processor=None) -> Dict[str, Any]:
    """
    Handle comprehensive text message echo.
    
    Implements the complete workflow:
    1. Extract metadata from text message
    2. Store/update user data with 24hr TTL
    3. Mark message as read with typing indicator
    4. Send metadata-rich response
    5. Send text echo after delay
    
    Args:
        webhook: IncomingMessageWebhook
        user_id: User identifier
        message_text: Text content of message
        messenger: Messaging interface
        user_cache: Redis user cache
        media_processor: Optional media processor (not used for text)
        
    Returns:
        Dictionary with comprehensive results
    """
    try:
        message_id = webhook.message.message_id
        
        # Step 1: Extract metadata
        metadata = {}
        if METADATA_EXTRACTION_ENABLED:
            from .metadata_extraction import extract_message_metadata
            metadata = await extract_message_metadata(webhook, "text")
            
        # Step 2: Store/update user data
        user_storage_result = {}
        if USER_STORAGE_ENABLED and user_cache:
            from .user_storage import store_user_data
            user_storage_result = await store_user_data(
                webhook=webhook,
                user_id=user_id,
                user_cache=user_cache,
                metadata=metadata,
                ttl_seconds=USER_DATA_TTL_SECONDS
            )
            
        # Step 3: Message confirmation
        confirmation_result = {}
        if MESSAGE_CONFIRMATION_ENABLED and messenger:
            from .message_confirmation import mark_as_read_with_typing
            confirmation_result = await mark_as_read_with_typing(
                messenger=messenger,
                message_id=message_id,
                typing=True
            )
            
        # Step 4: Send metadata response
        metadata_result = None
        if METADATA_EXTRACTION_ENABLED and messenger and metadata:
            from .metadata_extraction import build_metadata_response
            metadata_response = await build_metadata_response("text", metadata, message_text)
            
            metadata_result = await messenger.send_text(
                recipient=user_id,
                text=metadata_response,
                reply_to_message_id=message_id
            )
            
        # Step 5: Wait processing delay
        await asyncio.sleep(ECHO_PROCESSING_DELAY_SECONDS)
        
        # Step 6: Send text echo
        echo_text = f"🔄 ECHO: {message_text}"
        echo_result = await messenger.send_text(
            recipient=user_id,
            text=echo_text,
            reply_to_message_id=message_id
        )
        
        # Compile results
        return {
            "success": True,
            "message_type": "text",
            "user_id": user_id,
            "original_text": message_text,
            "echo_text": echo_text,
            "processing_steps": {
                "metadata_extraction": bool(metadata),
                "user_storage": user_storage_result.get("success", False),
                "message_confirmation": confirmation_result.get("success", False),
                "metadata_response": metadata_result.success if metadata_result else False,
                "text_echo": echo_result.success if echo_result else False
            },
            "results": {
                "metadata": metadata,
                "user_storage": user_storage_result,
                "message_confirmation": confirmation_result,
                "metadata_response": {
                    "success": metadata_result.success if metadata_result else False,
                    "message_id": metadata_result.message_id if metadata_result and metadata_result.success else None
                },
                "text_echo": {
                    "success": echo_result.success if echo_result else False,
                    "message_id": echo_result.message_id if echo_result and echo_result.success else None,
                    "error": echo_result.error if echo_result and not echo_result.success else None
                }
            },
            "processing_time_seconds": ECHO_PROCESSING_DELAY_SECONDS,
            "processed_at": datetime.utcnow().isoformat() + 'Z'
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message_type": "text",
            "user_id": user_id,
            "processed_at": datetime.utcnow().isoformat() + 'Z'
        }