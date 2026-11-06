"""Dependency checks of ``WappaEventHandler``."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ._state import _HandlerState

if TYPE_CHECKING:
    pass


class _Diagnostics(_HandlerState):
    """Dependency checks of ``WappaEventHandler``."""

    def validate_dependencies(self) -> bool:
        """
        Validate that required context and dependencies have been properly injected.

        Returns:
            True if all required context and dependencies are available, False otherwise
        """
        # Validate context (required for proper multi-inbox operation)
        if self.inbox_id is None or self.user_id is None:
            self.logger.error(
                f"Request context not set - inbox_id={self.inbox_id}, user_id={self.user_id}. "
                "Ensure with_context() was called before processing."
            )
            return False

        if self.messenger is None:
            self.logger.error(
                "Messenger dependency not injected - cannot send messages (check WebhookController)"
            )
            return False

        # Cache factory is optional for now (placeholder)
        if self.cache_factory is None:
            self.logger.debug(
                "Cache factory not injected - using placeholder (expected)"
            )
        else:
            self.logger.debug(
                f"Cache factory injected: {type(self.cache_factory).__name__}"
            )

        # Database is optional - only available if PostgresDatabasePlugin is registered
        if self.db is None:
            self.logger.debug(
                "Database not injected - PostgresDatabasePlugin may not be registered"
            )
        else:
            self.logger.debug("Database session factory injected")

        self.logger.debug(
            f"Per-request context validation passed - "
            f"inbox: {self.inbox_id}, user: {self.user_id}, "
            f"messenger: {self.messenger.__class__.__name__} "
            f"(platform: {self.messenger.platform.value})"
        )
        return True
