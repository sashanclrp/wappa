"""Inbound Runtime boundary for accepted platform webhooks."""

from .meta_callback_auth import SIGNATURE_HEADER, MetaCallbackAuthenticator
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
    PayloadRoutingError,
    PlatformAccountNotRegisteredError,
    RoutedWebhookDelivery,
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
    "ProcessorFailureError",
    "RoutedWebhookDelivery",
    "UnsupportedPlatformError",
    "route_whatsapp_payload",
)
