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
    aistate_prefix: str = Field(default="aistate")
    pubsub_prefix: str = Field(default="notify")
    pk_marker: str = Field(default="pkid")

    # ---- pattern segments -------------------------------------------------
    @staticmethod
    def glob_escape(segment: str) -> str:
        """Escape a literal segment so Redis SCAN matches it character for character.

        SCAN takes a glob, so a value containing ``*``, ``?``, ``[``, ``]``, or
        ``\\`` changes what the pattern means. An `inbox_id` of ``a[1]`` would
        otherwise build a pattern matching ``a1`` and never its own keys —
        a delete that silently removes nothing.
        """
        escaped = segment.replace("\\", "\\\\")
        for char in "*?[]":
            escaped = escaped.replace(char, f"\\{char}")
        return escaped

    def _segment(self, value: str | None) -> str:
        """Render one pattern segment: ``None`` means "any", anything else is literal."""
        return "*" if value is None else self.glob_escape(value.replace(":", "_"))

    # ---- builders ---------------------------------------------------------
    def user(self, inbox: str, user_id: str) -> str:
        return f"{inbox}:{self.user_prefix}:{user_id}"

    def handler(self, inbox: str, name: str, user_id: str) -> str:
        return f"{inbox}:{self.handler_prefix}:{name}:{user_id}"

    def table(self, inbox: str, table: str, pkid: str) -> str:
        safe_tbl = table.replace(":", "_")
        safe_pk = pkid.replace(":", "_")
        return f"{inbox}:{self.table_prefix}:{safe_tbl}:{self.pk_marker}:{safe_pk}"

    def trigger(self, inbox: str, action: str, ident: str) -> str:
        """
        Build trigger key for expiry actions.

        Pattern: {inbox}:EXPTRIGGER:{safe_action}:{safe_identifier}

        Args:
            inbox: Inbox identifier
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
        return f"{inbox}:{self.trigger_prefix}:{safe_action}:{safe_ident}"

    def aistate(self, inbox: str, agent_name: str, user_id: str) -> str:
        """
        Build AI state key for agent state management.

        Pattern: {inbox}:aistate:{agent_name}:{user_id}

        Args:
            inbox: Inbox identifier
            agent_name: AI agent name (e.g., "summarizer", "analyzer")
            user_id: User identifier

        Returns:
            Formatted AI state key

        Example:
            >>> keys.aistate("wappa", "summarizer", "user123")
            "wappa:aistate:summarizer:user123"

        Note:
            Colons in agent_name are replaced with underscores for safety.
        """
        safe_agent = agent_name.replace(":", "_")
        return f"{inbox}:{self.aistate_prefix}:{safe_agent}:{user_id}"

    # ---- SCAN patterns ----------------------------------------------------
    # Every enumeration (delete-by-pattern, find-by-field, list-*) builds its
    # glob here rather than with an f-string, so no caller can forget to escape
    # a literal segment. Pass ``None`` for the dimension you want to range over.

    def user_pattern(self, inbox: str, user_id: str | None = None) -> str:
        return f"{self._segment(inbox)}:{self.user_prefix}:{self._segment(user_id)}"

    def handler_pattern(
        self,
        inbox: str,
        name: str | None = None,
        user_id: str | None = None,
        *,
        name_prefix: str | None = None,
    ) -> str:
        """Pattern over handler states. ``name_prefix`` matches names starting with it."""
        if name_prefix is not None:
            handler = f"{self.glob_escape(name_prefix)}*"
        else:
            handler = self._segment(name)
        return (
            f"{self._segment(inbox)}:{self.handler_prefix}:{handler}"
            f":{self._segment(user_id)}"
        )

    def table_pattern(
        self, inbox: str, table: str | None = None, pkid: str | None = None
    ) -> str:
        return (
            f"{self._segment(inbox)}:{self.table_prefix}:{self._segment(table)}"
            f":{self.pk_marker}:{self._segment(pkid)}"
        )

    def trigger_pattern(
        self, inbox: str, action: str | None = None, ident: str | None = None
    ) -> str:
        return (
            f"{self._segment(inbox)}:{self.trigger_prefix}:{self._segment(action)}"
            f":{self._segment(ident)}"
        )

    def aistate_pattern(
        self,
        inbox: str,
        agent_name: str | None = None,
        user_id: str | None = None,
        *,
        name_prefix: str | None = None,
    ) -> str:
        """Pattern over AI agent states. ``name_prefix`` matches names starting with it."""
        if name_prefix is not None:
            agent = f"{self.glob_escape(name_prefix)}*"
        else:
            agent = self._segment(agent_name)
        return (
            f"{self._segment(inbox)}:{self.aistate_prefix}:{agent}"
            f":{self._segment(user_id)}"
        )

    def channel(self, inbox: str, user_id: str, event_type: str) -> str:
        """
        Build PubSub channel name for real-time notifications.

        Pattern: wappa:notify:{inbox}:{user_id}:{event_type}

        Args:
            inbox: Inbox identifier
            user_id: User/phone identifier
            event_type: Event type (incoming_message, outgoing_message, status_change)

        Returns:
            Formatted channel name

        Example:
            >>> keys.channel("mimeia", "5511999887766", "status_change")
            "wappa:notify:mimeia:5511999887766:status_change"

        Note:
            Colons in user_id/event_type are replaced with underscores for safety.
        """
        safe_user = user_id.replace(":", "_")
        safe_event = event_type.replace(":", "_").lower()
        return f"wappa:{self.pubsub_prefix}:{inbox}:{safe_user}:{safe_event}"

    def channel_pattern(
        self, inbox: str, user_id: str = "*", event_type: str = "*"
    ) -> str:
        """
        Build PubSub channel pattern for PSUBSCRIBE.

        Supports wildcard (*) for flexible subscription patterns.

        Args:
            inbox: Inbox identifier (required)
            user_id: User/phone identifier (default "*" for all users)
            event_type: Event type (default "*" for all events)

        Returns:
            Channel pattern string

        Example:
            >>> keys.channel_pattern("mimeia")  # All events for inbox
            "wappa:notify:mimeia:*:*"

            >>> keys.channel_pattern("mimeia", "5511999887766")  # All events for user
            "wappa:notify:mimeia:5511999887766:*"

            >>> keys.channel_pattern("mimeia", event_type="status_change")
            "wappa:notify:mimeia:*:status_change"
        """
        safe_user = "*" if user_id == "*" else self._segment(user_id)
        safe_event = "*" if event_type == "*" else self._segment(event_type.lower())
        return (
            f"wappa:{self.pubsub_prefix}:{self._segment(inbox)}"
            f":{safe_user}:{safe_event}"
        )

    # ---- parsers ----------------------------------------------------------
    def parse_trigger(self, key: str) -> tuple[str, str, str] | None:
        """
        Parse trigger key back to components.

        Args:
            key: Redis key like "wappa:EXPTRIGGER:payment_reminder:TXN_12345"

        Returns:
            (inbox, action, identifier) or None if not a trigger key

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

            inbox, _, action, identifier = parts
            return inbox, action, identifier
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
