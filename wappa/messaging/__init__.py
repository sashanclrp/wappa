"""
Wappa Messaging Components

Public outbound interfaces, middleware contracts, and Inbox-scoped capabilities.

WhatsApp clients, handlers, and Messenger construction are adapter internals.
Host Applications receive ``IMessenger`` from Wappa runtime contexts or resolve
the smaller Template capability through ``OutboundRuntime``.
"""

# Core Messaging Interface
# Messenger Pipeline (public contract for middleware authors)
from wappa.core.messaging.pipeline import (
    PRIORITY_CACHE,
    MessengerMiddleware,
    MessengerPipeline,
    SendInvocation,
    SendNext,
)
from wappa.domain.interfaces.messaging_interface import IMessenger

from .classification import (
    OutboundClassification,
    OutboundTransportFamily,
    OutboundTransportSubkind,
    UnsupportedOutboundPayloadError,
    classify_outbound_payload,
)
from .template_transport import (
    BsuidTemplateRecipient,
    InboxTemplateTransport,
    LocationTemplateTransportRequest,
    MediaTemplateTransportRequest,
    OutboundRuntime,
    PhoneNumberTemplateRecipient,
    TemplateAddressKind,
    TemplateAuthenticationMethod,
    TemplateCategory,
    TemplateEndpoint,
    TemplateMediaType,
    TemplateRoutingPolicy,
    TemplateRoutingReason,
    TemplateTransportLocationHeader,
    TemplateTransportMediaHeader,
    TemplateTransportOutcome,
    TemplateTransportParameter,
    TemplateTransportRequest,
    TemplateTransportResult,
    TemplateTransportRouting,
    TextTemplateTransportRequest,
)

__all__ = [
    # Core Interface
    "IMessenger",
    # Messenger Pipeline
    "MessengerMiddleware",
    "MessengerPipeline",
    "SendInvocation",
    "SendNext",
    "PRIORITY_CACHE",
    # Outbound payload classification (transport shape, not authority)
    "classify_outbound_payload",
    "OutboundClassification",
    "OutboundTransportFamily",
    "OutboundTransportSubkind",
    "UnsupportedOutboundPayloadError",
    # Inbox-scoped outbound Template transport
    "OutboundRuntime",
    "InboxTemplateTransport",
    "TemplateTransportRequest",
    "TemplateTransportParameter",
    "PhoneNumberTemplateRecipient",
    "BsuidTemplateRecipient",
    "TemplateAuthenticationMethod",
    "TemplateAddressKind",
    "TemplateCategory",
    "TemplateEndpoint",
    "TemplateMediaType",
    "TextTemplateTransportRequest",
    "MediaTemplateTransportRequest",
    "LocationTemplateTransportRequest",
    "TemplateTransportMediaHeader",
    "TemplateTransportLocationHeader",
    "TemplateTransportRouting",
    "TemplateRoutingPolicy",
    "TemplateRoutingReason",
    "TemplateTransportOutcome",
    "TemplateTransportResult",
]
