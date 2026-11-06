"""Instagram built-in webhook fields; Host extensions may not register these names."""

from __future__ import annotations

INSTAGRAM_MESSAGING_KEYS: frozenset[str] = frozenset(
    {"message", "read", "postback", "referral", "reaction", "message_edit"}
)
INSTAGRAM_CHANGE_FIELDS: frozenset[str] = frozenset(
    {"comments", "live_comments", "mentions"}
)
INSTAGRAM_BUILTIN_FIELDS: frozenset[str] = frozenset(
    {
        "messages",
        "messaging_seen",
        "messaging_postbacks",
        "messaging_referral",
        "message_edit",
        "message_reactions",
        "message_echoes",
        "messaging_optins",
        "messaging_handover",
        "standby",
    }
    | INSTAGRAM_CHANGE_FIELDS
)
"""Reserved Instagram field names (handled, excluded or core subscriptions)."""
