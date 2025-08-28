"""
Echo Project Master Event Handler

Main event handler for the Echo Project demonstrating comprehensive Wappa functionality.
Uses layered processing pattern: State → Activation → Echo

Features:
- Comprehensive message echoing with metadata
- Interactive buttons and lists with state management
- CTA buttons and location requests
- Redis-based state management with TTL
- User profile caching
- Media echo using WhatsApp media IDs

Architecture:
- Inherits from WappaEventHandler
- Uses dependency injection for messenger and cache
- Implements layered processing pattern
- Delegates to specialized logic modules
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, Optional

from wappa import WappaEventHandler
from wappa.domain.interfaces.cache_interface import ICache
from wappa.webhooks import ErrorWebhook, IncomingMessageWebhook, StatusWebhook

from constants import (
    BUTTON_ACTIVATION_COMMAND, LIST_ACTIVATION_COMMAND, CTA_ACTIVATION_COMMAND, 
    LOCATION_ACTIVATION_COMMAND, STATE_TYPE_BUTTON, STATE_TYPE_LIST,
    FEATURES, WELCOME_MESSAGE, ERROR_MESSAGE_TEMPLATE, DEFAULT_RESPONSES
)
from state_manager import StateManager
from interactive_builder import InteractiveBuilder
from media_processor import MediaProcessor


class EchoProjectHandler(WappaEventHandler):
    """
    Comprehensive echo handler demonstrating all Wappa framework capabilities.
    
    Implements layered processing pattern from the original echo_test_event:
    1. Pre-processing: Dependency validation, logging
    2. State Layer: Check for active interactive states (buttons, lists)
    3. Activation Layer: Check for command activation
    4. Echo Layer: Default comprehensive message echoing  
    5. Post-processing: Cleanup, metrics, confirmation
    
    Dependencies injected per-request:
    - messenger: WhatsApp messaging interface
    - cache_factory: Redis cache factory for state and user data
    """

    def __init__(self):
        """Initialize handler with component managers."""
        super().__init__()
        
        # Component managers (will use injected dependencies)
        self.state_manager: Optional[StateManager] = None
        self.interactive_builder: Optional[InteractiveBuilder] = None 
        self.media_processor: Optional[MediaProcessor] = None
        
        # Cache instances (created per-request)
        self._state_cache: Optional[ICache] = None
        self._user_cache: Optional[ICache] = None
        
        # Request tracking
        self._request_count = 0
        
        self.logger.info("🚀 EchoProjectHandler initialized - components will be created per-request")

    async def process_message(self, webhook: IncomingMessageWebhook) -> None:
        """
        Process incoming messages with comprehensive echo functionality.
        
        Implements layered processing pattern:
        1. Setup - Validate dependencies and initialize components
        2. State Layer - Check for active interactive states
        3. Activation Layer - Check for command activation
        4. Echo Layer - Default comprehensive echo
        5. Cleanup - Post-processing and metrics
        """
        try:
            self._request_count += 1
            
            # Layer 1: Setup and Validation
            if not await self._setup_request_components(webhook):
                return
                
            user_id = webhook.user.user_id
            message_text = webhook.get_message_text()
            message_type = webhook.get_message_type_name()
            message_id = webhook.message.message_id
            
            self.logger.info(
                f"💬 Request #{self._request_count}: Processing {message_type} from {user_id}"
            )
            
            # Show dependency status for debugging
            self.logger.debug(f"📋 Request Dependencies: {self.get_dependency_status()}")
            
            # Layer 2: State Layer - Check for active interactive states
            state_result = await self._process_state_layer(webhook, user_id, message_text, message_type)
            if state_result:
                self.logger.info(f"✅ Message processed by state layer: {state_result.get('handler', 'unknown')}")
                return
                
            # Layer 3: Activation Layer - Check for command activation  
            activation_result = await self._process_activation_layer(webhook, user_id, message_text, message_type)
            if activation_result:
                self.logger.info(f"✅ Message processed by activation layer: {activation_result.get('command', 'unknown')}")
                return
                
            # Layer 4: Echo Layer - Default comprehensive echo
            echo_result = await self._process_echo_layer(webhook, user_id, message_text, message_type)
            if echo_result:
                self.logger.info(f"✅ Message processed by echo layer: {message_type}")
                return
                
            # Fallback - should not reach here
            self.logger.warning(f"⚠️ Message not processed by any layer: {message_type} from {user_id}")
            await self._send_error_response(user_id, "Message could not be processed", message_id)
            
        except Exception as e:
            self.logger.error(f"❌ Error processing message: {e}", exc_info=True)
            user_id = webhook.user.user_id if hasattr(webhook, 'user') else 'unknown'
            message_id = webhook.message.message_id if hasattr(webhook, 'message') else None
            await self._send_error_response(user_id, str(e), message_id)

    async def _setup_request_components(self, webhook: IncomingMessageWebhook) -> bool:
        """Setup components for this request with dependency injection."""
        try:
            # Validate core dependencies
            if not self.validate_dependencies():
                self.logger.error("❌ Core dependencies not injected")
                return False
                
            if not self.cache_factory:
                self.logger.error("❌ Cache factory not injected - state management unavailable")
                return False
                
            # Create cache instances for this request
            self._state_cache = self.cache_factory.create_state_cache()
            self._user_cache = self.cache_factory.create_user_cache()
            
            if not self._state_cache or not self._user_cache:
                self.logger.error("❌ Failed to create cache instances")
                return False
                
            # Initialize component managers with dependencies
            self.state_manager = StateManager(
                state_cache=self._state_cache,
                logger=self.logger
            )
            
            self.interactive_builder = InteractiveBuilder(
                messenger=self.messenger,
                logger=self.logger
            )
            
            self.media_processor = MediaProcessor(
                messenger=self.messenger,
                logger=self.logger
            )
            
            self.logger.debug("✅ Request components initialized successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Error setting up request components: {e}", exc_info=True)
            return False

    async def _process_state_layer(self, webhook: IncomingMessageWebhook, user_id: str, 
                                   message_text: str, message_type: str) -> Optional[Dict[str, Any]]:
        """
        Layer 2: Check for active interactive states (buttons, lists).
        
        Returns result dict if state was processed, None if no active state.
        """
        try:
            # Check for active button state
            button_state = await self.state_manager.get_user_state(user_id, STATE_TYPE_BUTTON)
            if button_state:
                self.logger.info(f"🔘 Active button state found for {user_id}")
                
                # Import and delegate to button selection logic
                from logic.button_selection import handle_button_selection
                result = await handle_button_selection(
                    webhook=webhook,
                    user_id=user_id,
                    message_text=message_text,
                    button_state=button_state,
                    messenger=self.messenger,
                    state_manager=self.state_manager,
                    interactive_builder=self.interactive_builder
                )
                
                return {"handler": "button_selection", "result": result}
                
            # Check for active list state
            list_state = await self.state_manager.get_user_state(user_id, STATE_TYPE_LIST)
            if list_state:
                self.logger.info(f"📋 Active list state found for {user_id}")
                
                # Import and delegate to list selection logic
                from logic.list_selection import handle_list_selection
                result = await handle_list_selection(
                    webhook=webhook,
                    user_id=user_id,
                    message_text=message_text,
                    list_state=list_state,
                    messenger=self.messenger,
                    state_manager=self.state_manager,
                    media_processor=self.media_processor
                )
                
                return {"handler": "list_selection", "result": result}
                
            # No active states found
            return None
            
        except Exception as e:
            self.logger.error(f"❌ Error in state layer processing: {e}", exc_info=True)
            return None

    async def _process_activation_layer(self, webhook: IncomingMessageWebhook, user_id: str,
                                        message_text: str, message_type: str) -> Optional[Dict[str, Any]]:
        """
        Layer 3: Check for command activation (/button, /list, /cta, /location).
        
        Returns result dict if command was processed, None if no command.
        """
        try:
            if not message_text:
                return None
                
            command = message_text.strip().lower()
            
            # Button activation
            if command == BUTTON_ACTIVATION_COMMAND:
                self.logger.info(f"🔘 Button activation command from {user_id}")
                
                from logic.button_activation import handle_button_activation
                result = await handle_button_activation(
                    webhook=webhook,
                    user_id=user_id,
                    messenger=self.messenger,
                    state_manager=self.state_manager,
                    interactive_builder=self.interactive_builder
                )
                
                return {"command": "button_activation", "result": result}
                
            # List activation
            elif command == LIST_ACTIVATION_COMMAND:
                self.logger.info(f"📋 List activation command from {user_id}")
                
                from logic.list_activation import handle_list_activation
                result = await handle_list_activation(
                    webhook=webhook,
                    user_id=user_id,
                    messenger=self.messenger,
                    state_manager=self.state_manager,
                    interactive_builder=self.interactive_builder
                )
                
                return {"command": "list_activation", "result": result}
                
            # CTA activation
            elif command == CTA_ACTIVATION_COMMAND:
                self.logger.info(f"🔗 CTA activation command from {user_id}")
                
                from logic.cta_activation import handle_cta_activation
                result = await handle_cta_activation(
                    webhook=webhook,
                    user_id=user_id,
                    messenger=self.messenger,
                    interactive_builder=self.interactive_builder
                )
                
                return {"command": "cta_activation", "result": result}
                
            # Location activation
            elif command == LOCATION_ACTIVATION_COMMAND:
                self.logger.info(f"📍 Location activation command from {user_id}")
                
                from logic.location_activation import handle_location_activation
                result = await handle_location_activation(
                    webhook=webhook,
                    user_id=user_id,
                    messenger=self.messenger
                )
                
                return {"command": "location_activation", "result": result}
                
            # No command found
            return None
            
        except Exception as e:
            self.logger.error(f"❌ Error in activation layer processing: {e}", exc_info=True)
            return None

    async def _process_echo_layer(self, webhook: IncomingMessageWebhook, user_id: str,
                                  message_text: str, message_type: str) -> Optional[Dict[str, Any]]:
        """
        Layer 4: Default comprehensive echo based on message type.
        
        Returns result dict if echo was processed.
        """
        try:
            self.logger.info(f"🔄 Processing comprehensive echo for {message_type}")
            
            # Delegate to appropriate message type handler
            if message_type.lower() == "text":
                from logic.text_echo import handle_text_echo
                result = await handle_text_echo(
                    webhook=webhook,
                    user_id=user_id,
                    message_text=message_text,
                    messenger=self.messenger,
                    user_cache=self._user_cache,
                    media_processor=self.media_processor
                )
                
            elif message_type.lower() == "image":
                from logic.image_echo import handle_image_echo
                result = await handle_image_echo(
                    webhook=webhook,
                    user_id=user_id,
                    messenger=self.messenger,
                    user_cache=self._user_cache,
                    media_processor=self.media_processor
                )
                
            elif message_type.lower() == "video":
                from logic.video_echo import handle_video_echo
                result = await handle_video_echo(
                    webhook=webhook,
                    user_id=user_id,
                    messenger=self.messenger,
                    user_cache=self._user_cache,
                    media_processor=self.media_processor
                )
                
            elif message_type.lower() == "audio":
                from logic.audio_echo import handle_audio_echo  
                result = await handle_audio_echo(
                    webhook=webhook,
                    user_id=user_id,
                    messenger=self.messenger,
                    user_cache=self._user_cache,
                    media_processor=self.media_processor
                )
                
            elif message_type.lower() == "document":
                from logic.document_echo import handle_document_echo
                result = await handle_document_echo(
                    webhook=webhook,
                    user_id=user_id,
                    messenger=self.messenger,
                    user_cache=self._user_cache,
                    media_processor=self.media_processor
                )
                
            elif message_type.lower() == "location":
                from logic.location_echo import handle_location_echo
                result = await handle_location_echo(
                    webhook=webhook,
                    user_id=user_id,
                    messenger=self.messenger,
                    user_cache=self._user_cache
                )
                
            elif message_type.lower() == "contacts":
                from logic.contact_echo import handle_contact_echo
                result = await handle_contact_echo(
                    webhook=webhook,
                    user_id=user_id,
                    messenger=self.messenger,
                    user_cache=self._user_cache
                )
                
            else:
                # Unsupported message type - use generic handler
                from logic.text_echo import handle_text_echo
                result = await handle_text_echo(
                    webhook=webhook,
                    user_id=user_id,
                    message_text=f"[{message_type.upper()} MESSAGE]",
                    messenger=self.messenger,
                    user_cache=self._user_cache,
                    media_processor=self.media_processor
                )
                
            return {"message_type": message_type, "result": result}
            
        except Exception as e:
            self.logger.error(f"❌ Error in echo layer processing: {e}", exc_info=True)
            return None

    async def _send_error_response(self, user_id: str, error_message: str, 
                                   reply_to_message_id: Optional[str] = None) -> None:
        """Send error response to user."""
        try:
            if not self.messenger:
                return
                
            error_text = ERROR_MESSAGE_TEMPLATE.format(error=error_message)
            
            result = await self.messenger.send_text(
                recipient=user_id,
                text=error_text,
                reply_to_message_id=reply_to_message_id
            )
            
            if result.success:
                self.logger.info(f"✅ Error response sent to {user_id}")
            else:
                self.logger.error(f"❌ Failed to send error response: {result.error}")
                
        except Exception as e:
            self.logger.error(f"❌ Error sending error response: {e}")

    async def process_status(self, webhook: StatusWebhook) -> None:
        """Custom status processing with comprehensive logging."""
        try:
            status_value = webhook.status.value
            recipient = webhook.recipient_id
            
            tenant_info = self.messenger.tenant_id if self.messenger else "unknown"
            
            self.logger.info(
                f"📊 Status update: {status_value.upper()} for {recipient} (tenant: {tenant_info})"
            )
            
            # Log additional status details if available
            if hasattr(webhook, 'timestamp'):
                self.logger.debug(f"📅 Status timestamp: {webhook.timestamp}")
                
        except Exception as e:
            self.logger.error(f"❌ Error processing status: {e}", exc_info=True)

    async def process_error(self, webhook: ErrorWebhook) -> None:
        """Custom error processing with comprehensive logging."""
        try:
            error_count = webhook.get_error_count()
            primary_error = webhook.get_primary_error()
            
            tenant_info = self.messenger.tenant_id if self.messenger else "unknown"
            
            self.logger.error(
                f"🚨 Platform error: {error_count} errors, "
                f"primary: {primary_error.error_code} - {primary_error.error_title} "
                f"(tenant: {tenant_info})"
            )
            
            # Log additional error details
            if hasattr(primary_error, 'error_data'):
                self.logger.debug(f"📄 Error details: {primary_error.error_data}")
                
        except Exception as e:
            self.logger.error(f"❌ Error processing error webhook: {e}", exc_info=True)