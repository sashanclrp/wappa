"""
Settings-based inbox credential store.

Default implementation backed by environment variables for single-inbox deployments.
"""

from wappa.core.config.settings import settings
from wappa.domain.interfaces.inbox_credential_store import (
    IInboxCredentialStore,
    InboxCredentials,
    InboxNotFoundError,
)


class SettingsInboxCredentialStore(IInboxCredentialStore):
    """
    Single-inbox credential store backed by environment variables.

    Validates that inbox_id matches the configured WP_PHONE_ID.
    For multi-inbox support, replace with a database-backed implementation.
    """

    async def get_credentials(self, inbox_id: str) -> InboxCredentials:
        if not await self.validate_inbox(inbox_id):
            raise InboxNotFoundError(inbox_id)

        access_token = settings.wp_access_token
        if access_token is None:
            raise InboxNotFoundError(inbox_id)

        return InboxCredentials(
            inbox_id=inbox_id,
            access_token=access_token,
            platform_account_id=settings.wp_bid or None,
        )

    async def validate_inbox(self, inbox_id: str) -> bool:
        try:
            return bool(settings.wp_access_token and settings.wp_phone_id == inbox_id)
        except Exception:
            return False

    async def invalidate_cache(self, inbox_id: str) -> None:
        return None
