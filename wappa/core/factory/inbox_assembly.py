"""Inbox Routing Mode assembly.

This is the only place that reads the legacy ``WP_ACCESS_TOKEN`` /
``WP_PHONE_ID`` / ``WP_BID`` bundle or the explicit-mode encryption keys.
After assembly every runtime component consumes the resulting
``InboxRuntimeConfiguration`` and never touches those variables again.

Legacy and explicit mode never fall back to one another.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from pydantic import SecretStr

from wappa.core.security.credential_codec import (
    CredentialCodec,
    CredentialCodecConfigurationError,
)
from wappa.domain.inbox.errors import InboxConfigurationError
from wappa.domain.inbox.identity import InboxRef
from wappa.domain.inbox.ports import IInboxCredentialResolver, IInboxDirectorySource
from wappa.domain.inbox.routing import InboxRoutingMode
from wappa.domain.inbox.services import InboxCredentialService, InboxDirectory
from wappa.domain.inbox.settings_resolver import SettingsInboxCredentialResolver
from wappa.persistence.inbox_directory import InboxDirectoryTable
from wappa.persistence.scope import create_system_table_cache

if TYPE_CHECKING:
    from wappa.core.config.settings import Settings

LEGACY_INBOX_VARIABLES: Final[tuple[str, ...]] = (
    "WP_ACCESS_TOKEN",
    "WP_PHONE_ID",
    "WP_BID",
)
ENCRYPTION_KEY_VARIABLE: Final[str] = "SYSTEM_TOKEN_ENC_KEY"
ROUTING_MODE_VARIABLE: Final[str] = "SYSTEM_INBOX_ROUTING_MODE"


@dataclass(frozen=True)
class InboxRuntimeConfiguration:
    """The selected credential authority and everything derived from it."""

    mode: InboxRoutingMode
    credential_resolver: IInboxCredentialResolver
    directory: InboxDirectory | None = None
    credential_service: InboxCredentialService | None = None
    default_inbox_ref: InboxRef | None = None

    def health_status(self) -> dict[str, Any]:
        """Mode and readiness facts. Never tokens, envelopes, or keys."""
        return {
            "inbox_routing_mode": self.mode.value,
            "inbox_directory_configured": self.directory is not None,
            "legacy_default_inbox_configured": self.default_inbox_ref is not None,
            "legacy_default_inbox_id": (
                self.default_inbox_ref.inbox_id if self.default_inbox_ref else None
            ),
        }


def resolve_routing_mode(
    explicit: InboxRoutingMode | str | None, settings: Settings
) -> InboxRoutingMode:
    """Builder argument first, then the environment, then ``legacy``."""
    raw: InboxRoutingMode | str | None = explicit
    if raw is None:
        raw = (settings.inbox_routing_mode or "").strip() or None
    if raw is None:
        return InboxRoutingMode.LEGACY
    try:
        return InboxRoutingMode(str(raw).lower())
    except ValueError as exc:
        raise InboxConfigurationError(
            f"[wappa] Unknown Inbox Routing Mode {raw!r}. Use "
            f"{InboxRoutingMode.LEGACY.value!r} or {InboxRoutingMode.EXPLICIT.value!r}."
        ) from exc


def assemble_inbox_runtime(
    *,
    mode: InboxRoutingMode,
    source: IInboxDirectorySource | None,
    settings: Settings,
    cache_type: str,
) -> InboxRuntimeConfiguration:
    """Validate the mode's contract and build its credential authority."""
    present = {
        "WP_ACCESS_TOKEN": bool((settings.wp_access_token or "").strip()),
        "WP_PHONE_ID": bool((settings.wp_phone_id or "").strip()),
        "WP_BID": bool((settings.wp_bid or "").strip()),
    }

    if mode is InboxRoutingMode.LEGACY:
        if source is not None:
            raise InboxConfigurationError(
                "[wappa] Legacy Inbox routing rejects an IInboxDirectorySource. "
                "Select InboxRoutingMode.EXPLICIT to use the Inbox Directory, or "
                "remove the source to stay on the single settings-backed Inbox."
            )
        missing = [name for name, ok in present.items() if not ok]
        if missing:
            raise InboxConfigurationError(
                "[wappa] Legacy Inbox routing requires the complete bundle "
                f"{', '.join(LEGACY_INBOX_VARIABLES)}. Missing: {', '.join(missing)}. "
                "Explicit multi-Inbox routing needs InboxRoutingMode.EXPLICIT, an "
                f"IInboxDirectorySource, and {ENCRYPTION_KEY_VARIABLE}."
            )
        assert settings.wp_access_token and settings.wp_phone_id and settings.wp_bid
        try:
            resolver = SettingsInboxCredentialResolver(
                access_token=SecretStr(settings.wp_access_token.strip()),
                phone_number_id=settings.wp_phone_id.strip(),
                business_account_id=settings.wp_bid.strip(),
            )
        except ValueError as exc:
            raise InboxConfigurationError(
                f"[wappa] Legacy Inbox settings are invalid: {exc}"
            ) from exc
        return InboxRuntimeConfiguration(
            mode=mode,
            credential_resolver=resolver,
            default_inbox_ref=resolver.inbox_ref,
        )

    # Explicit mode.
    if source is None:
        raise InboxConfigurationError(
            "[wappa] Explicit Inbox routing requires an IInboxDirectorySource. "
            "Register one with Wappa(inbox_directory_source=...) or "
            "WappaBuilder.with_inbox_directory_source(...)."
        )
    if not isinstance(source, IInboxDirectorySource):
        raise InboxConfigurationError(
            "[wappa] The Inbox Directory source must implement "
            "IInboxDirectorySource: get_inbox(inbox_ref) and "
            "list_inboxes_for_platform_account(account_ref)."
        )
    configured = [name for name, ok in present.items() if ok]
    if configured:
        raise InboxConfigurationError(
            "[wappa] Explicit Inbox routing rejects the legacy Inbox variables "
            f"{', '.join(configured)}. Remove them from the process environment; "
            "every Inbox credential comes from the Inbox Directory source."
        )
    try:
        codec = CredentialCodec.from_environment(
            settings.system_token_enc_key, settings.system_token_enc_previous_keys
        )
    except CredentialCodecConfigurationError as exc:
        raise InboxConfigurationError(f"[wappa] {exc}") from exc

    directory = InboxDirectory(
        source=source,
        table=InboxDirectoryTable(create_system_table_cache(cache_type)),
        codec=codec,
    )
    return InboxRuntimeConfiguration(
        mode=mode,
        credential_resolver=directory,
        directory=directory,
        credential_service=InboxCredentialService(codec),
    )


__all__ = [
    "ENCRYPTION_KEY_VARIABLE",
    "LEGACY_INBOX_VARIABLES",
    "ROUTING_MODE_VARIABLE",
    "InboxRuntimeConfiguration",
    "assemble_inbox_runtime",
    "resolve_routing_mode",
]
