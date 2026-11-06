"""
Wappa Expiry Example - Main Application Entry Point

Demonstrates Redis expiry triggers on the scheduled lane:
- Messages accumulate in UserCache during conversation
- 15-second inactivity timer resets on each message
- After 15s of silence, the expired key reaches process_scheduled_event, which
  echoes all messages back with timestamps
- Clean up happens in that same hook
"""

from wappa import InboxRef, SchedulingPlugin, Wappa

from .master_event import USER_INACTIVITY, MasterEventHandler


async def expiry_subject(
    *, inbox_ref: InboxRef, action: str, identifier: str
) -> str | None:
    """Tell Wappa which expired actions are keyed by a User.

    Only the Host knows: an identifier could equally be a message ID. Returning
    None dispatches Inbox-only work with no User and no User cache.
    """
    return identifier if action == USER_INACTIVITY else None


# Create Wappa application with Redis cache
app = Wappa(cache="redis")

# Listen for expired triggers and route them to process_scheduled_event
app.add_plugin(SchedulingPlugin(redis_expiry=True, expiry_subjects=expiry_subject))

# Set event handler
app.set_event_handler(MasterEventHandler())
