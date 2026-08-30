"""Inbox identity, credential records, ports, services, and typed failures."""

from .credentials import (
    EncryptedSecretEnvelope,
    InboxCredentialRecord,
    InboxCredentialStatus,
    PlatformAccountActiveIndexRecord,
    PlatformAccountEmptyIndexRecord,
    PlatformAccountIndexRecord,
    WhatsAppActiveInboxCredentialRecord,
    WhatsAppInactiveInboxCredentialRecord,
    WhatsAppInboxCredentialRecord,
    dump_record_for_storage,
    parse_inbox_credential_record,
)
from .errors import (
    InboxConfigurationError,
    InboxCredentialIntegrityError,
    InboxDirectoryError,
    InboxDirectoryUnavailableError,
    InboxMembershipError,
    InboxMutationConflictError,
    InboxNotFoundError,
)
from .identity import (
    NAMESPACE_ENCODING_VERSION,
    QUALIFIED_NAMESPACE_SEPARATOR,
    InboxRef,
    PlatformAccountRef,
    validate_platform_native_id,
)
from .ports import (
    IInboxCredentialResolver,
    IInboxDirectorySource,
    ResolvedInboxCredentials,
)
from .routing import InboxRoutingMode
from .services import InboxCredentialService, InboxDirectory
from .settings_resolver import SettingsInboxCredentialResolver

__all__ = [
    "NAMESPACE_ENCODING_VERSION",
    "QUALIFIED_NAMESPACE_SEPARATOR",
    "EncryptedSecretEnvelope",
    "IInboxCredentialResolver",
    "IInboxDirectorySource",
    "InboxConfigurationError",
    "InboxCredentialIntegrityError",
    "InboxCredentialRecord",
    "InboxCredentialService",
    "InboxCredentialStatus",
    "InboxDirectory",
    "InboxDirectoryError",
    "InboxDirectoryUnavailableError",
    "InboxMembershipError",
    "InboxMutationConflictError",
    "InboxNotFoundError",
    "InboxRef",
    "InboxRoutingMode",
    "PlatformAccountActiveIndexRecord",
    "PlatformAccountEmptyIndexRecord",
    "PlatformAccountIndexRecord",
    "PlatformAccountRef",
    "ResolvedInboxCredentials",
    "SettingsInboxCredentialResolver",
    "WhatsAppActiveInboxCredentialRecord",
    "WhatsAppInactiveInboxCredentialRecord",
    "WhatsAppInboxCredentialRecord",
    "dump_record_for_storage",
    "parse_inbox_credential_record",
    "validate_platform_native_id",
]
