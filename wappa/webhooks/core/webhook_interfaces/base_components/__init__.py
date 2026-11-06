"""
Universal base components for platform-agnostic webhook interfaces.

These components provide the building blocks for all universal webhook types.
Every Platform adapter fills the fields it has evidence for; identity fields a
Platform does not supply (phone number, BSUID, username) stay ``None``.

``identity`` holds InboxBase and UserBase; ``context`` the business, forward,
entry-point and conversation contexts; ``errors`` ErrorDetailBase;
``system_event_detail`` SystemEventDetail and the group, contact-sync and
user-action details.
"""

from wappa.webhooks.core.webhook_interfaces.base_components.context import (
    BusinessContextBase,
    ConversationBase,
    EntryPointKind,
    EntryReferral,
    ForwardContextBase,
)
from wappa.webhooks.core.webhook_interfaces.base_components.errors import (
    ErrorDetailBase,
)
from wappa.webhooks.core.webhook_interfaces.base_components.identity import (
    InboxBase,
    UserBase,
)
from wappa.webhooks.core.webhook_interfaces.base_components.system_event_detail import (
    ContactSync,
    GroupParticipant,
    GroupUpdate,
    SystemEventDetail,
    UserAction,
)

__all__ = [
    "BusinessContextBase",
    "ContactSync",
    "ConversationBase",
    "EntryPointKind",
    "EntryReferral",
    "ErrorDetailBase",
    "ForwardContextBase",
    "GroupParticipant",
    "GroupUpdate",
    "InboxBase",
    "SystemEventDetail",
    "UserAction",
    "UserBase",
]
