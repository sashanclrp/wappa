"""
State Commands Score - Single Responsibility: /WAPPA and /EXIT command processing.

This module handles all state-related commands including:
- /WAPPA command activation and state management
- /EXIT command deactivation and cleanup
- WAPPA state message processing
"""

from wappa.webhooks import IncomingMessageWebhook

from ..models.json_demo_models import StateHandler
from ..utils.cache_utils import get_cache_ttl
from ..utils.message_utils import extract_command_from_message, extract_user_data
from .constants import WAPPA_HANDLER
from .score_base import ScoreBase


class StateCommandsScore(ScoreBase):
    """
    Handles state-related command processing.

    Follows Single Responsibility Principle by focusing only
    on state management and command processing.
    """

    async def can_handle(self, webhook: IncomingMessageWebhook) -> bool:
        """
        This score handles /WAPPA, /EXIT commands and messages in WAPPA state.

        Args:
            webhook: Incoming message webhook

        Returns:
            True if this is a state command or user is in WAPPA state
        """
        message_text = webhook.get_message_text()
        if not message_text:
            return False

        # Check for state commands
        command, _ = extract_command_from_message(message_text.strip())
        if command in ["/WAPPA", "/EXIT"]:
            return True

        # Check if user is in WAPPA state (need to handle regular messages in state)
        # User identity is already bound in cache_factory
        try:
            # IStateCache.get() takes (handler_name, models=...)
            state = await self.state_cache.get(WAPPA_HANDLER, models=StateHandler)
            return state is not None and state.is_wappa
        except Exception:
            return False

    async def process(self, webhook: IncomingMessageWebhook) -> bool:
        """
        Process state commands and WAPPA state messages.

        Args:
            webhook: Incoming message webhook

        Returns:
            True if processing was successful
        """
        if not await self.validate_dependencies():
            return False

        try:
            message_text = webhook.get_message_text()
            if not message_text:
                return False

            command, remaining_text = extract_command_from_message(message_text.strip())
            user_data = extract_user_data(webhook)
            user_id = user_data["user_id"]

            if command == "/WAPPA":
                await self._handle_wappa_activation(webhook, user_id)
            elif command == "/EXIT":
                await self._handle_wappa_exit(webhook, user_id)
            else:
                # Handle regular message in WAPPA state
                await self._handle_wappa_state_message(webhook, user_id, message_text)

            self._record_processing(success=True)
            return True

        except Exception as e:
            await self._handle_error(e, "state_command_processing")
            return False

    async def _handle_wappa_activation(
        self, webhook: IncomingMessageWebhook, user_id: str
    ) -> None:
        """
        Handle /WAPPA command activation.

        Args:
            webhook: Incoming message webhook
            user_id: User's phone number ID
        """
        try:
            # Create and save WAPPA state
            state = StateHandler()
            state.activate_wappa()

            # Store state with TTL using IStateCache interface
            # IStateCache.upsert() takes (handler_name, data, ttl=...)
            ttl = get_cache_ttl("state")
            await self.state_cache.upsert(WAPPA_HANDLER, state.model_dump(), ttl=ttl)

            # Mark message as read with typing indicator first
            await self.messenger.mark_as_read(
                message_id=webhook.message.message_id, typing=True
            )

            # Send activation message
            activation_message = (
                "🎉 You are in wappa state, to exit wappa state write /EXIT\n\n"
                "✨ While in WAPPA state:\n"
                "• I'll respond with 'Hola Wapp@ ;)' to all your messages\n"
                "• Your state is cached in JSON files\n"
                "• Write /EXIT to leave WAPPA state"
            )

            result = await self.messenger.send_text(
                recipient=user_id,
                text=activation_message,
                reply_to_message_id=webhook.message.message_id,
            )

            if result.success:
                self.logger.info(f"✅ WAPPA state activated for {user_id}")
            else:
                self.logger.error(
                    f"❌ Failed to send WAPPA activation message: {result.error}"
                )

        except Exception as e:
            self.logger.error(f"Error in WAPPA activation: {e}")
            raise

    async def _handle_wappa_exit(
        self, webhook: IncomingMessageWebhook, user_id: str
    ) -> None:
        """
        Handle /EXIT command deactivation.

        Args:
            webhook: Incoming message webhook
            user_id: User's phone number ID
        """
        try:
            # Check if user has WAPPA state using IStateCache interface
            state = await self.state_cache.get(WAPPA_HANDLER, models=StateHandler)

            if state and state.is_wappa:
                # Calculate session stats
                duration = state.get_state_duration() or 0
                command_count = state.command_count

                # Deactivate and delete state using IStateCache interface
                await self.state_cache.delete(WAPPA_HANDLER)

                # Mark message as read with typing indicator first
                await self.messenger.mark_as_read(
                    message_id=webhook.message.message_id, typing=True
                )

                # Send exit message
                exit_message = (
                    "👋 You are no longer in wappa state!\n\n"
                    f"📊 Session Summary:\n"
                    f"• Duration: {duration} seconds\n"
                    f"• Commands processed: {command_count}\n"
                    f"• State cleared from JSON cache"
                )

                result = await self.messenger.send_text(
                    recipient=user_id,
                    text=exit_message,
                    reply_to_message_id=webhook.message.message_id,
                )

                if result.success:
                    self.logger.info(
                        f"✅ WAPPA state deactivated for {user_id} (duration: {duration}s)"
                    )
                else:
                    self.logger.error(
                        f"❌ Failed to send WAPPA exit message: {result.error}"
                    )
            else:
                # No active state found
                await self.messenger.send_text(
                    recipient=user_id,
                    text="❓ You are not currently in WAPPA state. Send /WAPPA to activate it.",
                    reply_to_message_id=webhook.message.message_id,
                )

        except Exception as e:
            self.logger.error(f"Error in WAPPA exit: {e}")
            raise

    async def _handle_wappa_state_message(
        self, webhook: IncomingMessageWebhook, user_id: str, message_text: str
    ) -> None:
        """
        Handle regular messages when user is in WAPPA state.

        Args:
            webhook: Incoming message webhook
            user_id: User's phone number ID
            message_text: Message content
        """
        try:
            # Get state using IStateCache interface
            state = await self.state_cache.get(WAPPA_HANDLER, models=StateHandler)

            if state and state.is_wappa:
                # Update state with command processing
                state.process_command(message_text)

                # Save updated state using IStateCache interface
                ttl = get_cache_ttl("state")
                await self.state_cache.upsert(
                    WAPPA_HANDLER, state.model_dump(), ttl=ttl
                )

                # Mark message as read with typing indicator first
                await self.messenger.mark_as_read(
                    message_id=webhook.message.message_id, typing=True
                )

                # Send WAPPA response
                result = await self.messenger.send_text(
                    recipient=user_id,
                    text="Hola Wapp@ ;)",
                    reply_to_message_id=webhook.message.message_id,
                )

                if result.success:
                    self.logger.info(
                        f"✅ WAPPA response sent to {user_id} (command #{state.command_count})"
                    )
                else:
                    self.logger.error(
                        f"❌ Failed to send WAPPA response: {result.error}"
                    )

        except Exception as e:
            self.logger.error(f"Error handling WAPPA state message: {e}")
            raise

    async def is_user_in_wappa_state(self) -> bool:
        """
        Check if user is currently in WAPPA state (for other score modules).

        User identity is bound in cache_factory, so no explicit user_id needed.

        Returns:
            True if user is in WAPPA state
        """
        try:
            state = await self.state_cache.get(WAPPA_HANDLER, models=StateHandler)
            return state is not None and state.is_wappa
        except Exception as e:
            self.logger.error(f"Error checking WAPPA state: {e}")
            return False
