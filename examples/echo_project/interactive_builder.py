"""
Interactive Builder for Echo Project

Handles creation of interactive WhatsApp messages (buttons, lists, CTAs).
Provides clean interface for building complex interactive messages with proper formatting.

Features:
- Interactive button messages with reply buttons
- Interactive list messages with sections and rows
- Call-to-action (CTA) messages with URL buttons
- Proper message structure following WhatsApp requirements
- Error handling and validation
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from wappa.domain.interfaces.messaging_interface import IMessenger

from constants import (
    # Button constants
    BUTTON_ID_NICE, BUTTON_ID_YOURS, BUTTON_TITLE_NICE, BUTTON_TITLE_YOURS,
    BUTTON_MESSAGE_BODY, BUTTON_MESSAGE_HEADER, BUTTON_MESSAGE_FOOTER,
    
    # List constants
    LIST_ROW_IMAGE, LIST_ROW_VIDEO, LIST_ROW_AUDIO, LIST_ROW_DOCUMENT,
    LIST_TITLE_IMAGE, LIST_TITLE_VIDEO, LIST_TITLE_AUDIO, LIST_TITLE_DOCUMENT,
    LIST_DESC_IMAGE, LIST_DESC_VIDEO, LIST_DESC_AUDIO, LIST_DESC_DOCUMENT,
    LIST_MESSAGE_BODY, LIST_MESSAGE_HEADER, LIST_MESSAGE_FOOTER,
    LIST_BUTTON_TEXT, LIST_SECTION_TITLE,
    
    # CTA constants
    CTA_BUTTON_TEXT, CTA_BUTTON_URL, CTA_MESSAGE_BODY, 
    CTA_MESSAGE_HEADER, CTA_MESSAGE_FOOTER
)


class InteractiveBuilder:
    """
    Builds interactive WhatsApp messages using Wappa's messaging interface.
    
    Provides high-level methods for creating buttons, lists, and CTA messages
    with proper validation and error handling.
    """
    
    def __init__(self, messenger: IMessenger, logger):
        """
        Initialize InteractiveBuilder with messenger and logger.
        
        Args:
            messenger: Wappa messaging interface
            logger: Logger instance for debugging
        """
        self.messenger = messenger
        self.logger = logger
        
    async def send_button_message(self, user_id: str, reply_to_message_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Send interactive button message with two options.
        
        Creates a button message with "Nice Button" and "Button yours" options
        that will trigger different image responses when clicked.
        
        Args:
            user_id: Recipient user ID
            reply_to_message_id: Optional message ID to reply to
            
        Returns:
            Dictionary with send result and button context
        """
        try:
            self.logger.info(f"🔘 Building button message for {user_id}")
            
            # Build button list
            buttons = [
                {
                    "type": "reply",
                    "reply": {
                        "id": BUTTON_ID_NICE,
                        "title": BUTTON_TITLE_NICE
                    }
                },
                {
                    "type": "reply", 
                    "reply": {
                        "id": BUTTON_ID_YOURS,
                        "title": BUTTON_TITLE_YOURS
                    }
                }
            ]
            
            # Send interactive button message
            result = await self.messenger.send_button_message(
                recipient=user_id,
                buttons=buttons,
                body=BUTTON_MESSAGE_BODY,
                header=BUTTON_MESSAGE_HEADER,
                footer=BUTTON_MESSAGE_FOOTER,
                reply_to_message_id=reply_to_message_id
            )
            
            # Build context for state management
            button_context = {
                "message_type": "button",
                "buttons": {
                    BUTTON_ID_NICE: {
                        "title": BUTTON_TITLE_NICE,
                        "action": "send_nice_image"
                    },
                    BUTTON_ID_YOURS: {
                        "title": BUTTON_TITLE_YOURS,
                        "action": "send_yours_image"
                    }
                },
                "sent_at": result.message_id if result.success else None,
                "reply_to_message_id": reply_to_message_id
            }
            
            if result.success:
                self.logger.info(f"✅ Button message sent to {user_id}: {result.message_id}")
                return {
                    "success": True,
                    "message_id": result.message_id,
                    "button_context": button_context
                }
            else:
                self.logger.error(f"❌ Failed to send button message to {user_id}: {result.error}")
                return {
                    "success": False,
                    "error": result.error,
                    "button_context": button_context
                }
                
        except Exception as e:
            self.logger.error(f"❌ Error building button message for {user_id}: {e}")
            return {
                "success": False,
                "error": str(e)
            }
            
    async def send_list_message(self, user_id: str, reply_to_message_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Send interactive list message with media options.
        
        Creates a list message with image, video, audio, and document options
        that will trigger different media file responses when selected.
        
        Args:
            user_id: Recipient user ID
            reply_to_message_id: Optional message ID to reply to
            
        Returns:
            Dictionary with send result and list context
        """
        try:
            self.logger.info(f"📋 Building list message for {user_id}")
            
            # Build list rows
            rows = [
                {
                    "id": LIST_ROW_IMAGE,
                    "title": LIST_TITLE_IMAGE,
                    "description": LIST_DESC_IMAGE
                },
                {
                    "id": LIST_ROW_VIDEO,
                    "title": LIST_TITLE_VIDEO,
                    "description": LIST_DESC_VIDEO
                },
                {
                    "id": LIST_ROW_AUDIO,
                    "title": LIST_TITLE_AUDIO,
                    "description": LIST_DESC_AUDIO
                },
                {
                    "id": LIST_ROW_DOCUMENT,
                    "title": LIST_TITLE_DOCUMENT,
                    "description": LIST_DESC_DOCUMENT
                }
            ]
            
            # Build list sections
            sections = [
                {
                    "title": LIST_SECTION_TITLE,
                    "rows": rows
                }
            ]
            
            # Send interactive list message
            result = await self.messenger.send_list_message(
                recipient=user_id,
                sections=sections,
                body=LIST_MESSAGE_BODY,
                header=LIST_MESSAGE_HEADER,
                footer=LIST_MESSAGE_FOOTER,
                button_text=LIST_BUTTON_TEXT,
                reply_to_message_id=reply_to_message_id
            )
            
            # Build context for state management
            list_context = {
                "message_type": "list",
                "options": {
                    LIST_ROW_IMAGE: {
                        "title": LIST_TITLE_IMAGE,
                        "description": LIST_DESC_IMAGE,
                        "action": "send_sample_image"
                    },
                    LIST_ROW_VIDEO: {
                        "title": LIST_TITLE_VIDEO,
                        "description": LIST_DESC_VIDEO,
                        "action": "send_sample_video"
                    },
                    LIST_ROW_AUDIO: {
                        "title": LIST_TITLE_AUDIO,
                        "description": LIST_DESC_AUDIO,
                        "action": "send_sample_audio"
                    },
                    LIST_ROW_DOCUMENT: {
                        "title": LIST_TITLE_DOCUMENT,
                        "description": LIST_DESC_DOCUMENT,
                        "action": "send_sample_document"
                    }
                },
                "sent_at": result.message_id if result.success else None,
                "reply_to_message_id": reply_to_message_id
            }
            
            if result.success:
                self.logger.info(f"✅ List message sent to {user_id}: {result.message_id}")
                return {
                    "success": True,
                    "message_id": result.message_id,
                    "list_context": list_context
                }
            else:
                self.logger.error(f"❌ Failed to send list message to {user_id}: {result.error}")
                return {
                    "success": False,
                    "error": result.error,
                    "list_context": list_context
                }
                
        except Exception as e:
            self.logger.error(f"❌ Error building list message for {user_id}: {e}")
            return {
                "success": False,
                "error": str(e)
            }
            
    async def send_cta_message(self, user_id: str, reply_to_message_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Send call-to-action message with URL button.
        
        Creates a CTA message with a URL button that opens external link.
        This is stateless - no state management needed.
        
        Args:
            user_id: Recipient user ID
            reply_to_message_id: Optional message ID to reply to
            
        Returns:
            Dictionary with send result
        """
        try:
            self.logger.info(f"🔗 Building CTA message for {user_id}")
            
            # Build URL button
            buttons = [
                {
                    "type": "url",
                    "url": {
                        "url": CTA_BUTTON_URL,
                        "text": CTA_BUTTON_TEXT
                    }
                }
            ]
            
            # Send CTA button message
            result = await self.messenger.send_button_message(
                recipient=user_id,
                buttons=buttons,
                body=CTA_MESSAGE_BODY,
                header=CTA_MESSAGE_HEADER,
                footer=CTA_MESSAGE_FOOTER,
                reply_to_message_id=reply_to_message_id
            )
            
            if result.success:
                self.logger.info(f"✅ CTA message sent to {user_id}: {result.message_id}")
                return {
                    "success": True,
                    "message_id": result.message_id,
                    "button_url": CTA_BUTTON_URL
                }
            else:
                self.logger.error(f"❌ Failed to send CTA message to {user_id}: {result.error}")
                return {
                    "success": False,
                    "error": result.error
                }
                
        except Exception as e:
            self.logger.error(f"❌ Error building CTA message for {user_id}: {e}")
            return {
                "success": False,
                "error": str(e)
            }
            
    async def send_button_image_response(self, user_id: str, button_id: str, 
                                         reply_to_message_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Send image response based on button selection.
        
        Args:
            user_id: Recipient user ID
            button_id: Selected button ID (BUTTON_ID_NICE or BUTTON_ID_YOURS)
            reply_to_message_id: Optional message ID to reply to
            
        Returns:
            Dictionary with send result
        """
        try:
            # Determine image path and caption based on button selection
            if button_id == BUTTON_ID_NICE:
                from constants import IMAGE_PATH_NICE, CAPTION_NICE
                image_path = self._get_media_path(IMAGE_PATH_NICE)
                caption = CAPTION_NICE
                self.logger.info(f"📸 Sending 'Nice' image to {user_id}")
                
            elif button_id == BUTTON_ID_YOURS:
                from constants import IMAGE_PATH_YOURS, CAPTION_YOURS
                image_path = self._get_media_path(IMAGE_PATH_YOURS)
                caption = CAPTION_YOURS
                self.logger.info(f"📸 Sending 'Yours' image to {user_id}")
                
            else:
                self.logger.error(f"❌ Invalid button ID: {button_id}")
                return {
                    "success": False,
                    "error": f"Invalid button ID: {button_id}"
                }
                
            # Check if image file exists
            if not os.path.exists(image_path):
                self.logger.warning(f"⚠️ Image file not found: {image_path}")
                # Send text response instead
                result = await self.messenger.send_text(
                    recipient=user_id,
                    text=f"📸 {caption}\n\n(Image file not found: {os.path.basename(image_path)})",
                    reply_to_message_id=reply_to_message_id
                )
            else:
                # Send image with caption
                result = await self.messenger.send_image(
                    recipient=user_id,
                    image_path=image_path,
                    caption=caption,
                    reply_to_message_id=reply_to_message_id
                )
                
            if result.success:
                self.logger.info(f"✅ Button response sent to {user_id}: {result.message_id}")
                return {
                    "success": True,
                    "message_id": result.message_id,
                    "button_id": button_id,
                    "image_path": image_path,
                    "caption": caption
                }
            else:
                self.logger.error(f"❌ Failed to send button response to {user_id}: {result.error}")
                return {
                    "success": False,
                    "error": result.error,
                    "button_id": button_id
                }
                
        except Exception as e:
            self.logger.error(f"❌ Error sending button response for {user_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "button_id": button_id
            }
            
    def _get_media_path(self, relative_path: str) -> str:
        """
        Get absolute path for media file relative to echo_project directory.
        
        Args:
            relative_path: Relative path from constants (e.g., "media/image.png")
            
        Returns:
            Absolute path to media file
        """
        # Get echo_project directory (parent of this file)
        echo_project_dir = Path(__file__).parent
        
        # Join with relative path
        absolute_path = echo_project_dir / relative_path
        
        return str(absolute_path)
        
    def validate_interactive_message_support(self) -> Dict[str, bool]:
        """
        Validate that messenger supports interactive message types.
        
        Returns:
            Dictionary with support status for each message type
        """
        try:
            support = {
                "button_messages": hasattr(self.messenger, 'send_button_message'),
                "list_messages": hasattr(self.messenger, 'send_list_message'),
                "url_buttons": hasattr(self.messenger, 'send_button_message'),  # URL buttons use same method
                "reply_buttons": hasattr(self.messenger, 'send_button_message'),  # Reply buttons use same method
                "interactive_support": True
            }
            
            # Overall interactive support
            support["interactive_support"] = (
                support["button_messages"] and 
                support["list_messages"]
            )
            
            self.logger.debug(f"📋 Interactive message support: {support}")
            return support
            
        except Exception as e:
            self.logger.error(f"❌ Error validating interactive support: {e}")
            return {
                "error": str(e),
                "interactive_support": False
            }