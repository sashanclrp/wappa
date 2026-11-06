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
from wappa.domain.contacts import (
    ContactAddress,
    ContactCard,
    ContactEmail,
    ContactName,
    ContactOrganization,
    ContactPhone,
    ContactUrl,
)
from wappa.domain.interactive import (
    CardButton,
    InteractiveHeader,
    ListRow,
    ListSection,
    MediaRef,
    MessageCard,
    ReplyButton,
    UrlButton,
)
from wappa.domain.interfaces.conversation_capabilities import (
    CommentContent,
    ContentPage,
    ICommentControls,
    IConversationContentReader,
    MediaBytes,
    PostChild,
    PostContent,
    ReadOutcome,
    ReadResult,
)
from wappa.domain.interfaces.history_reader import (
    HistoryPage,
    IConversationHistoryReader,
)
from wappa.domain.interfaces.media_library import (
    IMediaLibrary,
    MediaFamily,
    UploadResult,
)
from wappa.domain.interfaces.messaging_interface import IMessenger
from wappa.domain.interfaces.template_messaging import ITemplateMessaging
from wappa.domain.messaging_targets import (
    CommentRef,
    DeliveryAddresses,
    DirectMessage,
    MessageTarget,
    PostRef,
    PrivateReply,
    TargetInboxMismatchError,
    UnsupportedOperationError,
)
from wappa.domain.results import (
    CommentControlOperation,
    CommentResult,
    ControlResult,
    MessageResult,
    OperationOutcome,
    message_outcome,
)

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
    "ContactAddress",
    "ContactCard",
    "ContactEmail",
    "ContactName",
    "ContactOrganization",
    "ContactPhone",
    "ContactUrl",
    "DeliveryAddresses",
    # Core Interface
    "IMessenger",
    "DirectMessage",
    "PrivateReply",
    "MessageTarget",
    "CommentRef",
    "PostRef",
    "TargetInboxMismatchError",
    "UnsupportedOperationError",
    # Interactive Messages (one shape on every Platform, ADR-0016)
    "ReplyButton",
    "UrlButton",
    "CardButton",
    "InteractiveHeader",
    "MessageCard",
    "ListSection",
    "MediaRef",
    "ListRow",
    # Results
    "MessageResult",
    "CommentResult",
    "ControlResult",
    "CommentControlOperation",
    "OperationOutcome",
    "message_outcome",
    # Optional focused capabilities (IMessenger.capability(kind))
    "ICommentControls",
    "IConversationContentReader",
    "ITemplateMessaging",
    "IConversationHistoryReader",
    "HistoryPage",
    "IMediaLibrary",
    "MediaFamily",
    "UploadResult",
    "PostContent",
    "PostChild",
    "CommentContent",
    "ContentPage",
    "MediaBytes",
    "ReadOutcome",
    "ReadResult",
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
