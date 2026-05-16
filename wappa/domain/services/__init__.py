"""
Domain services.

Contains business logic that doesn't belong to a specific entity.
"""

from .inbox_credentials_service import SettingsInboxCredentialStore

__all__ = [
    "SettingsInboxCredentialStore",
]
