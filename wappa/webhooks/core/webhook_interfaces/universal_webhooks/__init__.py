"""
Universal Webhook Interface definitions for platform-agnostic webhook handling.

This package defines the universal webhook types that all messaging platforms
must transform their webhooks into, one module per type:

1. ``inbound`` - InboundMessageWebhook, all user-sent messages
2. ``call`` - CallWebhook, connect, terminate and status call events
3. ``status`` - StatusWebhook, message delivery status updates
4. ``error`` - ErrorWebhook, system, app and account-level errors
5. ``system`` - SystemWebhook and SystemEventType, Platform-level account,
   identity, group and sync events
6. ``custom`` - CustomWebhook, app-registered event payload envelope

``union`` holds UniversalWebhook, the union of every interface. Every Platform
(WhatsApp, Instagram, and later ones) adapts its webhooks to these interfaces.
"""

from wappa.webhooks.core.webhook_interfaces.universal_webhooks.call import CallWebhook
from wappa.webhooks.core.webhook_interfaces.universal_webhooks.custom import (
    CustomWebhook,
)
from wappa.webhooks.core.webhook_interfaces.universal_webhooks.error import ErrorWebhook
from wappa.webhooks.core.webhook_interfaces.universal_webhooks.inbound import (
    InboundMessageWebhook,
)
from wappa.webhooks.core.webhook_interfaces.universal_webhooks.status import (
    StatusWebhook,
)
from wappa.webhooks.core.webhook_interfaces.universal_webhooks.system import (
    SystemEventType,
    SystemWebhook,
)
from wappa.webhooks.core.webhook_interfaces.universal_webhooks.union import (
    UniversalWebhook,
)

__all__ = [
    "CallWebhook",
    "CustomWebhook",
    "ErrorWebhook",
    "InboundMessageWebhook",
    "StatusWebhook",
    "SystemEventType",
    "SystemWebhook",
    "UniversalWebhook",
]
