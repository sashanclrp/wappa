"""
Logic Module for Echo Project

Contains business logic functions for all message types and interactive features.
Each module handles a specific aspect of echo functionality with clean separation of concerns.

Modules:
- Message Type Handlers: text_echo, image_echo, video_echo, audio_echo, document_echo, location_echo, contact_echo
- Interactive Button Handlers: button_activation, button_selection, button_prompt
- Interactive List Handlers: list_activation, list_selection, list_prompt
- Other Interactive: cta_activation, location_activation
- Utilities: state_management, metadata_extraction, user_storage, message_confirmation

Architecture:
- Functional approach for business logic
- Clean separation of concerns
- Consistent interfaces across modules
- Comprehensive error handling
- Detailed logging and monitoring
"""

# Message type handlers
from .text_echo import handle_text_echo
from .audio_echo import handle_audio_echo
from .image_echo import handle_image_echo
from .video_echo import handle_video_echo
from .document_echo import handle_document_echo
from .location_echo import handle_location_echo
from .contact_echo import handle_contact_echo

# Interactive button handlers
from .button_activation import handle_button_activation
from .button_selection import handle_button_selection
from .button_prompt import handle_button_prompt

# Interactive list handlers
from .list_activation import handle_list_activation
from .list_selection import handle_list_selection
from .list_prompt import handle_list_prompt

# Other interactive handlers
from .cta_activation import handle_cta_activation
from .location_activation import handle_location_activation

# Utility handlers
from .state_management import handle_state_cleanup, handle_state_validation
from .metadata_extraction import extract_message_metadata, build_metadata_response
from .user_storage import store_user_data, get_user_data
from .message_confirmation import mark_as_read_with_typing

__all__ = [
    # Message type handlers
    "handle_text_echo",
    "handle_audio_echo", 
    "handle_image_echo",
    "handle_video_echo",
    "handle_document_echo",
    "handle_location_echo",
    "handle_contact_echo",
    
    # Interactive button handlers
    "handle_button_activation",
    "handle_button_selection", 
    "handle_button_prompt",
    
    # Interactive list handlers
    "handle_list_activation",
    "handle_list_selection",
    "handle_list_prompt",
    
    # Other interactive handlers
    "handle_cta_activation",
    "handle_location_activation",
    
    # Utility handlers
    "handle_state_cleanup",
    "handle_state_validation",
    "extract_message_metadata",
    "build_metadata_response", 
    "store_user_data",
    "get_user_data",
    "mark_as_read_with_typing"
]