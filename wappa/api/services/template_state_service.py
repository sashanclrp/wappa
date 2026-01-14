"""
Template state management service.

Handles creation and management of template-triggered user state.
Follows SRP: only responsible for template state operations.

When a template is sent with state_config, this service creates a cache entry
that can be retrieved when the user responds, enabling routing of responses
to specific handlers based on the original template context.
"""

from datetime import UTC, datetime
from typing import Any

from wappa.core.logging.logger import get_logger
from wappa.domain.interfaces.cache_factory import ICacheFactory
from wappa.messaging.whatsapp.models.template_models import TemplateStateConfig
from wappa.persistence.cache_factory import create_cache_factory


class TemplateStateService:
    """
    Service for managing template-triggered user state.

    Creates cache entries when templates with state_config are sent,
    enabling routing of subsequent user responses.

    Follows:
    - SRP: Only handles template state operations
    - DIP: Depends on ICacheFactory abstraction

    Example:
        When a template is sent with state_config:
        {
            "state_value": "reschedule_flow",
            "ttl_seconds": 3600,
            "initial_context": {"appointment_id": "apt-123"}
        }

        The service creates a state entry with key "template-reschedule_flow"
        that contains the template context and can be retrieved when the
        user responds.
    """

    STATE_KEY_PREFIX = "template-"

    def __init__(self, cache_factory: ICacheFactory):
        """
        Initialize with cache factory for state persistence.

        Args:
            cache_factory: Factory for creating cache instances with context
        """
        self.cache_factory = cache_factory
        self.logger = get_logger(__name__)

    def _make_state_key(self, state_value: str) -> str:
        """Create cache key from state value."""
        return f"{self.STATE_KEY_PREFIX}{state_value}"

    async def set_template_state(
        self,
        recipient: str,
        state_config: TemplateStateConfig,
        message_id: str | None,
        template_name: str,
    ) -> bool:
        """
        Create user cache state for template response routing.

        Creates a state entry keyed by "template-{state_value}" that includes
        the template context and any initial_context provided.

        Args:
            recipient: Phone number of the recipient
            state_config: State configuration from template request
            message_id: WhatsApp message ID from send response
            template_name: Name of the template sent

        Returns:
            True if state was created successfully, False otherwise
        """
        try:
            state_key = self._make_state_key(state_config.state_value)
            state_data = {
                "template_state": state_config.state_value,
                "template_name": template_name,
                "message_id": message_id,
                "recipient": recipient,
                "created_at": datetime.now(UTC).isoformat(),
                **(state_config.initial_context or {}),
            }

            # Create a new cache factory with the recipient as user_id
            # This ensures the state key includes the correct user_id
            cache_type = self.cache_factory.__class__.__name__.replace(
                "CacheFactory", ""
            ).lower()
            tenant_id = self.cache_factory.tenant_id

            recipient_cache_factory = create_cache_factory(cache_type)(
                tenant_id=tenant_id, user_id=recipient
            )

            state_cache = recipient_cache_factory.create_state_cache()
            success = await state_cache.upsert(
                handler_name=state_key,
                state_data=state_data,
                ttl=state_config.ttl_seconds,
            )

            if success:
                self.logger.info(
                    f"Template state created: {state_key} for {recipient}, "
                    f"TTL: {state_config.ttl_seconds}s"
                )
            else:
                self.logger.warning(f"Failed to create template state: {state_key}")

            return success

        except Exception as e:
            self.logger.error(f"Failed to set template state: {e}", exc_info=True)
            return False

    async def get_template_state(self, state_value: str) -> dict[str, Any] | None:
        """
        Retrieve template state by state_value.

        Args:
            state_value: The state identifier (without prefix)

        Returns:
            State data if found, None otherwise
        """
        try:
            state_cache = self.cache_factory.create_state_cache()
            return await state_cache.get(handler_name=self._make_state_key(state_value))
        except Exception as e:
            self.logger.error(f"Failed to get template state: {e}", exc_info=True)
            return None

    async def delete_template_state(self, state_value: str) -> bool:
        """
        Delete template state by state_value.

        Args:
            state_value: The state identifier (without prefix)

        Returns:
            True if deleted, False otherwise
        """
        try:
            state_key = self._make_state_key(state_value)
            state_cache = self.cache_factory.create_state_cache()
            deleted = await state_cache.delete(handler_name=state_key)

            if deleted > 0:
                self.logger.info(f"Template state deleted: {state_key}")
                return True
            return False
        except Exception as e:
            self.logger.error(f"Failed to delete template state: {e}", exc_info=True)
            return False

    async def template_state_exists(self, state_value: str) -> bool:
        """
        Check if template state exists.

        Args:
            state_value: The state identifier (without prefix)

        Returns:
            True if exists, False otherwise
        """
        try:
            state_cache = self.cache_factory.create_state_cache()
            return await state_cache.exists(
                handler_name=self._make_state_key(state_value)
            )
        except Exception as e:
            self.logger.error(
                f"Failed to check template state existence: {e}", exc_info=True
            )
            return False
