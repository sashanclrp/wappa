"""Inbox-scoped outbound Template transport.

This package is the public boundary between a Host Application and Wappa's
provider-facing Template delivery machinery.  It deliberately exposes request
and result values, while keeping credentials, sessions, clients, handlers, and
Messenger Pipeline composition inside Wappa.
"""

from __future__ import annotations

from .dispatch import (
    _request_digest,  # noqa: F401 - imported by tests
    _send_request,  # noqa: F401 - imported by tests
    resolve_template_route,
)
from .requests import (
    LocationTemplateTransportRequest,
    MediaTemplateTransportRequest,
    TemplateTransportLocationHeader,
    TemplateTransportMediaHeader,
    TemplateTransportParameter,
    TemplateTransportRequest,
    TemplateTransportRouting,
    TextTemplateTransportRequest,
)
from .result import TemplateTransportResult
from .transport import InboxTemplateTransport
from .values import (
    BsuidTemplateRecipient,
    PhoneNumberTemplateRecipient,
    TemplateAddressKind,
    TemplateAuthenticationMethod,
    TemplateCategory,
    TemplateEndpoint,
    TemplateMediaType,
    TemplateRoutingPolicy,
    TemplateRoutingReason,
    TemplateTransportOutcome,
    TemplateTransportRecipient,
)

__all__ = [
    "BsuidTemplateRecipient",
    "InboxTemplateTransport",
    "LocationTemplateTransportRequest",
    "MediaTemplateTransportRequest",
    "PhoneNumberTemplateRecipient",
    "TemplateAddressKind",
    "TemplateAuthenticationMethod",
    "TemplateCategory",
    "TemplateEndpoint",
    "TemplateMediaType",
    "TemplateRoutingPolicy",
    "TemplateRoutingReason",
    "TemplateTransportLocationHeader",
    "TemplateTransportMediaHeader",
    "TemplateTransportOutcome",
    "TemplateTransportParameter",
    "TemplateTransportRecipient",
    "TemplateTransportRequest",
    "TemplateTransportResult",
    "TemplateTransportRouting",
    "TextTemplateTransportRequest",
    "resolve_template_route",
]
