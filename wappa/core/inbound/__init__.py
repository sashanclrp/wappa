"""Inbound Runtime boundary for accepted platform webhooks."""

from .meta_callback_auth import SIGNATURE_HEADER, MetaCallbackAuthenticator
from .platform_webhooks import (
    PayloadRoutingError,
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
from .webhook_routing import (
    PlatformAccountNotRegisteredError,
    route_whatsapp_payload,
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
    "route_whatsapp_payload",
)
