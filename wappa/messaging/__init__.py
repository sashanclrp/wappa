"""
Wappa Messaging Components

Public outbound interfaces, middleware contracts, and Inbox-scoped capabilities.

WhatsApp clients, handlers, and Messenger construction are adapter internals.
Host Applications receive ``IMessenger`` (with ``media`` ready) and the
prebuilt Platform Messengers (``self.whatsapp``, ``self.instagram``) from Wappa
runtime contexts, or resolve the smaller Template capability through
``OutboundRuntime``. The capability interfaces below are exported for typing
and custom adapters; Hosts never look them up.
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
from wappa.domain.error_evidence import ErrorCategory, ErrorEvidence
from wappa.domain.interactive import (
    CardButton,
    CardMedia,
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
    DeleteResult,
    IMediaLibrary,
    MediaFamily,
    MediaInfo,
    UploadResult,
)
from wappa.domain.interfaces.messaging_interface import IMessenger
from wappa.domain.interfaces.template_messaging import ITemplateMessaging
from wappa.domain.interfaces.user_data_requests import IUserDataRequests
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
from wappa.domain.messenger_discovery import (
    MediaLimit,
    MessageLimits,
    MessengerDiscovery,
)
from wappa.domain.part_content import (
    PartButton,
    PartContent,
    PartElement,
    PartHeader,
    PartLocation,
    PartMedia,
    PartQuickReply,
    PartRow,
    PartSection,
    PartTemplate,
    PartTemplateComponent,
)
from wappa.domain.results import (
    AggregateOutcome,
    CommentControlOperation,
    CommentResult,
    ControlResult,
    MessagePart,
    MessageResult,
    OperationOutcome,
    aggregate_message_outcome,
    message_outcome,
)
from wappa.domain.user_identity import UserIdentity
from wappa.domain.user_profile import PlatformUserProfile

from .classification import (
    OutboundClassification,
    OutboundTransportFamily,
    OutboundTransportSubkind,
    UnsupportedOutboundPayloadError,
    classify_outbound_payload,
)
from .outbound_runtime import OutboundRuntime
from .template_transport import (
    BsuidTemplateRecipient,
    InboxTemplateTransport,
    LocationTemplateTransportRequest,
    MediaTemplateTransportRequest,
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
    # Interactive Messages (one shape on every Platform, ADR-0025)
    "ReplyButton",
    "UrlButton",
    "CardButton",
    "CardMedia",
    "InteractiveHeader",
    "MessageCard",
    "ListSection",
    "MediaRef",
    "ListRow",
    # Results
    "MessageResult",
    "MessagePart",
    "PartContent",
    "PartMedia",
    "PartButton",
    "PartQuickReply",
    "PartElement",
    "PartHeader",
    "PartSection",
    "PartRow",
    "PartLocation",
    "PartTemplate",
    "PartTemplateComponent",
    "AggregateOutcome",
    "aggregate_message_outcome",
    "UserIdentity",
    "MessengerDiscovery",
    "MediaLimit",
    "MessageLimits",
    "ErrorEvidence",
    "ErrorCategory",
    "CommentResult",
    "ControlResult",
    "CommentControlOperation",
    "OperationOutcome",
    "message_outcome",
    # User profile (IMessenger.resolve_platform_user_profile)
    "PlatformUserProfile",
    # Focused capability interfaces (prebuilt on messenger.media and the
    # Platform Messengers; capability(kind) is the internal seam)
    "ICommentControls",
    "IConversationContentReader",
    "ITemplateMessaging",
    "IUserDataRequests",
    "IConversationHistoryReader",
    "HistoryPage",
    "IMediaLibrary",
    "MediaFamily",
    "MediaInfo",
    "DeleteResult",
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
