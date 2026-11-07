"""Built-in WhatsApp webhook fields: the field sets the adapter handles natively."""

from __future__ import annotations

ACCOUNT_EVENT_FIELDS: frozenset[str] = frozenset(
    {"account_offboarded", "account_reconnected"}
)
# The only fields routed to a known inactive Inbox (ADR-0032): a Host cannot
# restore an offboarded account if the event announcing its return is refused.
INACTIVE_INBOX_FIELDS: frozenset[str] = frozenset({"account_reconnected"})
BUSINESS_USERNAME_EVENT_FIELDS: frozenset[str] = frozenset(
    {"business_username_updates"}
)
COEXISTENCE_EVENT_FIELDS: frozenset[str] = frozenset(
    {"history", "smb_message_echoes", "smb_app_state_sync"}
)
"""Account-level Coexistence fields whose ``value`` is a flat WABA-scoped object.

Their value shape (``waba_id``/``reason``/``phone_number_id``/``timestamp``) differs
from the phone-scoped :class:`WebhookValue` used by all other built-in fields.
"""

BUILTIN_WEBHOOK_FIELDS: frozenset[str] = (
    frozenset(
        {
            "messages",
            "user_preferences",
            "user_id_update",
            "group_participants_update",
            "calls",
        }
    )
    | ACCOUNT_EVENT_FIELDS
    | BUSINESS_USERNAME_EVENT_FIELDS
    | COEXISTENCE_EVENT_FIELDS
)
"""WhatsApp field values handled natively — reserved from Host registration."""

# Pre-computed union used by ``is_system_event`` to identify fields that are
# system events by their field name alone (as opposed to system messages that
# surface via field="messages" with type="system").
_DIRECT_SYSTEM_EVENT_FIELDS: frozenset[str] = (
    frozenset({"user_preferences", "user_id_update", "group_participants_update"})
    | ACCOUNT_EVENT_FIELDS
    | BUSINESS_USERNAME_EVENT_FIELDS
    | COEXISTENCE_EVENT_FIELDS
)
