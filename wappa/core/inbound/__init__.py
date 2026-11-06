"""Inbound Runtime boundary for accepted platform webhooks.

Each Platform's payload routing lives with its adapter:
``wappa.webhooks.whatsapp.routing.route_whatsapp_payload`` and
``wappa.webhooks.instagram.routing.route_instagram_payload``.
"""

from .meta_callback_auth import SIGNATURE_HEADER, MetaCallbackAuthenticator
from .platform_webhooks import (
    PayloadRoutingError,
    PlatformAccountNotRegisteredError,
    PlatformWebhooks,
    RoutedWebhookDelivery,
)
from .runtime import (
    DispatchContext,
    DispatchContextError,
    InboundRuntime,
    InboundRuntimeDependencies,
    InboundRuntimeError,
    PayloadInboxMismatchError,
    ProcessorFailureError,
    UnsupportedPlatformError,
)

__all__ = (
    "SIGNATURE_HEADER",
    "DispatchContext",
    "DispatchContextError",
    "InboundRuntime",
    "InboundRuntimeDependencies",
    "InboundRuntimeError",
    "MetaCallbackAuthenticator",
    "PayloadInboxMismatchError",
    "PayloadRoutingError",
    "PlatformAccountNotRegisteredError",
    "PlatformWebhooks",
    "ProcessorFailureError",
    "RoutedWebhookDelivery",
    "UnsupportedPlatformError",
)
