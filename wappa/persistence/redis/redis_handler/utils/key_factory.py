from __future__ import annotations

import logging

from pydantic import BaseModel, Field

logger = logging.getLogger("RedisKeyFactory")


class KeyFactory(BaseModel):
    """Pure stateless helpers for Wappa cache key generation."""

    user_prefix: str = Field(default="user")
    handler_prefix: str = Field(default="state")
    table_prefix: str = Field(default="df")
    trigger_prefix: str = Field(default="EXPTRIGGER")
    pk_marker: str = Field(default="pkid")

    # ---- builders ---------------------------------------------------------
    def user(self, tenant: str, user_id: str) -> str:
        return f"{tenant}:{self.user_prefix}:{user_id}"

    def handler(self, tenant: str, name: str, user_id: str) -> str:
        return f"{tenant}:{self.handler_prefix}:{name}:{user_id}"

    def table(self, tenant: str, table: str, pkid: str) -> str:
        safe_tbl = table.replace(":", "_")
        safe_pk = pkid.replace(":", "_")
        return f"{tenant}:{self.table_prefix}:{safe_tbl}:{self.pk_marker}:{safe_pk}"

    def trigger(self, tenant: str, action: str, ident: str) -> str:
        """
        Build trigger key for expiry actions.

        Pattern: {tenant}:EXPTRIGGER:{safe_action}:{safe_identifier}

        Args:
            tenant: Tenant identifier
            action: Action name (e.g., "payment_reminder")
            ident: Unique identifier (e.g., "TXN_12345")

        Returns:
            Formatted trigger key

        Example:
            >>> keys.trigger("wappa", "payment_reminder", "TXN_12345")
            "wappa:EXPTRIGGER:payment_reminder:TXN_12345"

        Note:
            Colons in action/identifier are replaced with underscores for safety.
        """
        safe_action = action.replace(":", "_")
        safe_ident = ident.replace(":", "_")
        return f"{tenant}:{self.trigger_prefix}:{safe_action}:{safe_ident}"

    # ---- parsers ----------------------------------------------------------
    def parse_trigger(self, key: str) -> tuple[str, str, str] | None:
        """
        Parse trigger key back to components.

        Args:
            key: Redis key like "wappa:EXPTRIGGER:payment_reminder:TXN_12345"

        Returns:
            (tenant, action, identifier) or None if not a trigger key

        Example:
            >>> keys.parse_trigger("wappa:EXPTRIGGER:payment_reminder:TXN_12345")
            ("wappa", "payment_reminder", "TXN_12345")

            >>> keys.parse_trigger("wappa:user:123")
            None
        """
        if f":{self.trigger_prefix}:" not in key:
            return None

        try:
            parts = key.split(":", 3)  # Max 4 parts
            if len(parts) != 4 or parts[1] != self.trigger_prefix:
                return None

            tenant, _, action, identifier = parts
            return tenant, action, identifier
        except (ValueError, IndexError):
            return None

    def is_trigger_key(self, key: str) -> bool:
        """
        Check if key is a trigger key.

        Args:
            key: Redis key to check

        Returns:
            True if key is a trigger key, False otherwise

        Example:
            >>> keys.is_trigger_key("wappa:EXPTRIGGER:payment_reminder:TXN_123")
            True

            >>> keys.is_trigger_key("wappa:user:123")
            False
        """
        return self.parse_trigger(key) is not None


# Default instance for global use
default_key_factory = KeyFactory()
