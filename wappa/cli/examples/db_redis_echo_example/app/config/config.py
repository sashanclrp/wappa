"""
Configuration settings for DB + Redis Echo Example.

Extends Wappa's base Settings class to add database-specific configuration.
"""

import os

from wappa.core.config.settings import Settings


class DBRedisSettings(Settings):
    """Extended settings with database configuration."""

    def __init__(self):
        # Initialize base Wappa settings
        super().__init__()

        # ================================================================
        # Database Configuration (PostgreSQL)
        # ================================================================
        self.database_url: str | None = os.getenv("DATABASE_URL")

        # Validate database configuration for server operations
        from wappa.core.config.settings import _is_cli_context

        if not _is_cli_context():
            self._validate_database_configuration()

    def _validate_database_configuration(self):
        """Validate database configuration for server operations."""
        if not self.database_url:
            raise ValueError(
                "DATABASE_URL is required. "
                "Set it in your .env file: DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/db"
            )

        # Basic URL format validation
        if not self.database_url.startswith("postgresql"):
            raise ValueError(
                "DATABASE_URL must be a PostgreSQL URL starting with 'postgresql://' or 'postgresql+asyncpg://'"
            )

    @property
    def has_database(self) -> bool:
        """Check if database is configured."""
        return self.database_url is not None


# Global settings instance with database configuration
settings_with_db = DBRedisSettings()
