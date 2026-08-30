"""Legacy single-Inbox credential resolver.

The only component allowed to consume the legacy ``WP_ACCESS_TOKEN`` /
``WP_PHONE_ID`` / ``WP_BID`` bundle is the assembly step that builds this
resolver. After construction nothing reads those variables again.
"""

from __future__ import annotations

from pydantic import SecretStr

from .errors import InboxNotFoundError
from .identity import InboxRef, PlatformAccountRef
from .ports import IInboxCredentialResolver, ResolvedInboxCredentials


class SettingsInboxCredentialResolver(IInboxCredentialResolver):
    """Resolve exactly one WhatsApp Inbox from process configuration."""

    def __init__(
        self,
        *,
        access_token: SecretStr,
        phone_number_id: str,
        business_account_id: str,
    ) -> None:
        if not access_token.get_secret_value():
            raise ValueError("access_token must not be empty")
        self._inbox_ref = InboxRef.whatsapp(phone_number_id)
        self._account_ref = PlatformAccountRef.whatsapp(business_account_id)
        self._credentials = ResolvedInboxCredentials(
            inbox_ref=self._inbox_ref,
            account_ref=self._account_ref,
            access_token=access_token,
            credential_version=1,
        )

    @property
    def inbox_ref(self) -> InboxRef:
        """The one Inbox this resolver knows; also the legacy HTTP default."""
        return self._inbox_ref

    @property
    def account_ref(self) -> PlatformAccountRef:
        return self._account_ref

    async def resolve_credentials(
        self, inbox_ref: InboxRef
    ) -> ResolvedInboxCredentials:
        if inbox_ref != self._inbox_ref:
            raise InboxNotFoundError(inbox_ref)
        return self._credentials

    async def list_inbox_refs_for_platform_account(
        self, account_ref: PlatformAccountRef
    ) -> tuple[InboxRef, ...]:
        if account_ref == self._account_ref:
            return (self._inbox_ref,)
        return ()


__all__ = ["SettingsInboxCredentialResolver"]
