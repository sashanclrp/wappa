"""Every v0.27 supported public import resolves (PRD 5)."""

from __future__ import annotations

import importlib

import pytest

PUBLIC_IMPORTS: dict[str, tuple[str, ...]] = {
    "wappa": (
        "Wappa",
        "WappaBuilder",
        "WappaEventHandler",
        "InboxRoutingMode",
        "MetaApplicationConfig",
        "IInboxDirectorySource",
    ),
    "wappa.domain.inbox": (
        "InboxRef",
        "PlatformAccountRef",
        "InboxRoutingMode",
        "IInboxDirectorySource",
        "InboxCredentialService",
        "InboxDirectory",
        "EncryptedSecretEnvelope",
        "InboxCredentialRecord",
        "InboxCredentialStatus",
        "WhatsAppActiveInboxCredentialRecord",
        "WhatsAppInactiveInboxCredentialRecord",
        "PlatformAccountActiveIndexRecord",
        "PlatformAccountEmptyIndexRecord",
        "InboxDirectoryError",
        "InboxConfigurationError",
        "InboxNotFoundError",
        "InboxMembershipError",
        "InboxDirectoryUnavailableError",
        "InboxCredentialIntegrityError",
        "InboxMutationConflictError",
        "parse_inbox_credential_record",
        "dump_record_for_storage",
    ),
    "wappa.core.config.meta_application": ("MetaApplicationConfig",),
    "wappa.core.security": (
        "CredentialCodec",
        "CredentialCodecConfigurationError",
        "SecretBinding",
    ),
    "wappa.persistence": (
        "SYSTEM_SCOPE",
        "create_system_table_cache",
        "TypedTableCache",
        "VersionedTableCache",
        "ITableCache",
    ),
    "wappa.persistence.inbox_directory": ("InboxDirectoryTable",),
    "wappa.api.dependencies": (
        "INBOX_ID_HEADER",
        "InboxExecutionContext",
        "get_inbox_execution_context",
    ),
    "wappa.core.inbound": (
        "SIGNATURE_HEADER",
        "MetaCallbackAuthenticator",
        "route_whatsapp_payload",
        "RoutedWebhookDelivery",
    ),
    "wappa.messaging": ("OutboundRuntime", "InboxTemplateTransport"),
}


@pytest.mark.parametrize(
    ("module", "names"), PUBLIC_IMPORTS.items(), ids=list(PUBLIC_IMPORTS)
)
def test_supported_public_imports_resolve(module: str, names: tuple[str, ...]) -> None:
    loaded = importlib.import_module(module)
    for name in names:
        assert getattr(loaded, name, None) is not None, f"{module}.{name}"


@pytest.mark.parametrize(
    "removed",
    [
        "wappa.domain.interfaces.inbox_credential_store",
        "wappa.domain.services.inbox_credentials_service",
        "wappa.domain.services.database_inbox_credential_store",
    ],
)
def test_replaced_credential_store_modules_are_gone(removed: str) -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(removed)


def test_wappa_top_level_no_longer_exposes_a_host_credential_store() -> None:
    import wappa
    from wappa.domain import interfaces

    assert not hasattr(interfaces, "IInboxCredentialStore")
    assert not hasattr(wappa, "IInboxCredentialStore")
