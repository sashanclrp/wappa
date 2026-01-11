import asyncio
import logging
from collections.abc import Awaitable, Callable

from pydantic import BaseModel, Field

from ...persistence.redis.redis_handler.utils.key_factory import KeyFactory

logger = logging.getLogger(__name__)

# Type alias for async handler functions
AsyncHandler = Callable[[str, str], Awaitable[None]]


class ExpirationHandlerRegistry(BaseModel):
    """
    Central registry for expiry action handlers.

    Provides decorator for registering async handlers and
    lookup mechanism for dispatching expired triggers.

    Example:
        from wappa import expiry_registry

        @expiry_registry.on_expire_action("payment_reminder")
        async def handle_payment_reminder(identifier: str, full_key: str):
            print(f"Payment reminder for {identifier}")
    """

    keys: KeyFactory = Field(default_factory=KeyFactory)
    handlers: dict[str, AsyncHandler] = Field(default_factory=dict)

    class Config:
        arbitrary_types_allowed = True

    def on_expire_action(
        self, action_name: str
    ) -> Callable[[AsyncHandler], AsyncHandler]:
        """
        Decorator to register expiry action handler.

        Args:
            action_name: Action identifier (e.g., "payment_reminder")

        Returns:
            Decorator function

        Example:
            @expiry_registry.on_expire_action("payment_reminder")
            async def handle_payment(identifier: str, full_key: str):
                # identifier: "TXN_123"
                # full_key: "wappa:EXPTRIGGER:payment_reminder:TXN_123"
                print(f"Processing payment for {identifier}")

        Handler Signature:
            async def handler(identifier: str, full_key: str) -> None:
                identifier: Unique ID extracted from key
                full_key: Complete Redis key that expired
        """
        # Build registry key (prefix for matching)
        full_prefix = f"{self.keys.trigger_prefix}:{action_name}:"
        # Example: "EXPTRIGGER:payment_reminder:"

        def decorator(fn: AsyncHandler) -> AsyncHandler:
            # Validate handler is async
            if not asyncio.iscoroutinefunction(fn):
                raise TypeError(
                    f"Handler for action '{action_name}' must be async. "
                    f"Use: async def {fn.__name__}(...)"
                )

            # Register handler
            self.handlers[full_prefix] = fn

            logger.info("Registered expiry action: %s → %s", action_name, fn.__name__)

            return fn

        return decorator

    def resolve(self, expired_key: str) -> tuple[AsyncHandler, str] | None:
        """
        Resolve handler for expired key.

        Args:
            expired_key: Full Redis key that expired
                        (e.g., "wappa:EXPTRIGGER:payment_reminder:TXN_123")

        Returns:
            (handler_function, identifier) or None if no handler registered

        Example:
            handler, identifier = registry.resolve(expired_key)
            if handler:
                await handler(identifier, expired_key)
        """
        # Find longest matching prefix (most specific match)
        matched_prefix = self._best_match(expired_key)

        if not matched_prefix:
            return None

        # Extract identifier by removing prefix
        # expired_key: "wappa:EXPTRIGGER:payment_reminder:TXN_123"
        # matched_prefix: "EXPTRIGGER:payment_reminder:"
        # Result: "TXN_123"

        # Find where the prefix occurs in the key
        prefix_index = expired_key.find(matched_prefix)
        if prefix_index == -1:
            return None

        # Extract everything after the prefix
        after_prefix = expired_key[prefix_index + len(matched_prefix) :]
        identifier = after_prefix

        handler = self.handlers[matched_prefix]
        return handler, identifier

    def _best_match(self, key: str) -> str | None:
        """
        Find longest matching prefix in handlers dict.

        Enables hierarchical matching:
        - "EXPTRIGGER:payment_reminder:urgent:" (most specific)
        - "EXPTRIGGER:payment_reminder:" (less specific)
        - "EXPTRIGGER:" (catch-all, not recommended)
        """
        matches = [prefix for prefix in self.handlers if prefix in key]
        return max(matches, key=len) if matches else None

    def list_actions(self) -> list[str]:
        """List all registered action names"""
        actions = []
        for prefix in self.handlers:
            # Extract action from prefix: "EXPTRIGGER:action:" → "action"
            parts = prefix.split(":")
            if len(parts) >= 2 and parts[0] == self.keys.trigger_prefix:
                actions.append(parts[1])
        return sorted(actions)

    def get_handler_info(self) -> dict[str, str]:
        """Get debugging info about registered handlers"""
        return {
            action: handler.__name__
            for action, handler in zip(
                self.list_actions(), self.handlers.values(), strict=False
            )
        }


# Global singleton instance (like wpDemoHotels pattern)
expiry_registry = ExpirationHandlerRegistry()
