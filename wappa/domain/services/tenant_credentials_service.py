"""
Tenant credentials service for managing tenant-specific WhatsApp credentials.

Currently uses settings for single tenant, but will be migrated to database
for multi-tenant support in the future.
"""

from wappa.core.config.settings import settings


class TenantCredentialsService:
    """Service to get tenant-specific WhatsApp credentials.

    Currently uses settings for single tenant, but will be migrated to database
    for multi-tenant support in the future.

    Note: In WhatsApp Business API, the phone_number_id IS the tenant identifier.
    """

    @staticmethod
    def get_whatsapp_access_token(phone_number_id: str) -> str:
        """Get WhatsApp access token for tenant.

        Args:
            phone_number_id: WhatsApp Business phone number ID (this IS the tenant_id)

        Returns:
            WhatsApp access token for this tenant

        Future: This will query the database using phone_number_id as the key:
        SELECT access_token FROM tenants WHERE phone_number_id = ?
        """
        # TODO: Replace with database query when migrating to multi-tenant
        # For now, use settings computed properties (DEV/PROD switching)
        return settings.wp_access_token

    @staticmethod
    def validate_tenant(phone_number_id: str) -> bool:
        """Validate that the tenant exists and is active.

        Args:
            phone_number_id: WhatsApp Business phone number ID

        Returns:
            True if tenant is valid and active, False otherwise

        Future: This will validate against the database
        """
        # TODO: Replace with database validation when migrating to multi-tenant
        # For now, check if we have valid credentials in settings
        try:
            token = settings.wp_access_token
            configured_phone_id = settings.wp_phone_id
            return bool(token and configured_phone_id == phone_number_id)
        except Exception:
            return False
