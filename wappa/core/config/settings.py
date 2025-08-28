"""
Settings for the Wappa WhatsApp framework.

Simple, reliable environment variable configuration focused on core WhatsApp functionality.
"""

import os
import tomllib
from pathlib import Path

from dotenv import load_dotenv

# Load .env file for local development - look in current working directory
load_dotenv(".env")


def _get_version_from_pyproject() -> str:
    """
    Read version from pyproject.toml file.

    Returns:
        Version string from pyproject.toml, or fallback version
    """
    # Look for pyproject.toml in the project root
    # Start from this file and go up to find the project root
    current_path = Path(__file__)
    for parent in [current_path.parent, *current_path.parents]:
        pyproject_path = parent / "pyproject.toml"
        if pyproject_path.exists():
            try:
                with open(pyproject_path, "rb") as f:
                    pyproject_data = tomllib.load(f)
                    version = pyproject_data.get("project", {}).get("version")
                    if version:
                        return version
            except (OSError, tomllib.TOMLDecodeError):
                # If we can't read the file, continue searching
                continue

    # Fallback version if pyproject.toml not found or doesn't contain version
    return "0.1.0"


class Settings:
    """Application settings with environment-based configuration."""

    def __init__(self):
        # ================================================================
        # Version & Framework Configuration
        # ================================================================
        self.version: str = _get_version_from_pyproject()

        # ================================================================
        # Environment & General Configuration
        # ================================================================
        self.port: int = int(os.getenv("PORT", "8000"))
        self.time_zone: str = os.getenv("TIME_ZONE", "UTC")
        self.log_level: str = os.getenv("LOG_LEVEL", "INFO")
        self.api_version: str = os.getenv("API_VERSION", "v21.0")
        self.base_url: str = os.getenv("BASE_URL", "https://graph.facebook.com/")

        # ================================================================
        # WhatsApp Configuration
        # ================================================================
        self.wp_access_token: str | None = os.getenv("WP_ACCESS_TOKEN")
        self.wp_phone_id: str | None = os.getenv("WP_PHONE_ID")
        self.wp_bid: str | None = os.getenv("WP_BID")

        # Common WhatsApp settings
        self.whatsapp_webhook_verify_token: str = os.getenv(
            "WHATSAPP_WEBHOOK_VERIFY_TOKEN", "demo_verify_token"
        )

        # ================================================================
        # AI & Tools Configuration (Optional)
        # ================================================================
        self.openai_api_key: str | None = os.getenv("OPENAI_API_KEY")

        # ================================================================
        # Redis Configuration (Optional)
        # ================================================================
        self.redis_url: str | None = os.getenv("REDIS_URL")

        # Redis connection settings (only used if Redis is enabled)
        self.redis_max_connections: int = int(os.getenv("REDIS_MAX_CONNECTIONS", "64"))
        self.redis_connection_timeout: int = int(
            os.getenv("REDIS_CONNECTION_TIMEOUT", "30")
        )
        self.redis_health_check_interval: int = int(
            os.getenv("REDIS_HEALTH_CHECK_INTERVAL", "60")
        )

        # ================================================================
        # Framework Configuration
        # ================================================================
        self.log_dir: str = os.getenv("LOG_DIR", "./logs")

        # Development/Production detection
        self.environment: str = os.getenv("ENVIRONMENT", "DEV")

        # Apply validation
        self._validate_settings()
        self._validate_whatsapp_credentials()

    def _validate_settings(self):
        """Validate settings values."""
        # Validate log level
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR"]
        if self.log_level.upper() not in valid_levels:
            raise ValueError(f"LOG_LEVEL must be one of {valid_levels}")
        self.log_level = self.log_level.upper()

        # Validate environment
        valid_environments = ["DEV", "PROD"]
        if self.environment.upper() not in valid_environments:
            self.environment = "DEV"  # Default fallback
        self.environment = self.environment.upper()

    def _validate_whatsapp_credentials(self):
        """Validate required WhatsApp credentials."""
        if not self.wp_access_token:
            raise ValueError("WP_ACCESS_TOKEN is required")
        if not self.wp_phone_id:
            raise ValueError("WP_PHONE_ID is required")
        if not self.wp_bid:
            raise ValueError("WP_BID is required")

    @property
    def owner_id(self) -> str:
        """
        Get owner ID (always the WhatsApp phone ID from configuration).

        USAGE PATTERN:
        - settings.owner_id: Use for URL generation, startup logging, and configuration display
        - get_current_tenant_context(): Use for ALL webhook processing and request-scoped operations

        This property represents the OWNER of the WhatsApp Business Account (configuration).
        For runtime business context, use tenant_id from webhook context instead.
        """
        if not self.wp_phone_id:
            raise ValueError("WP_PHONE_ID is required for owner_id")
        return self.wp_phone_id

    @property
    def has_redis(self) -> bool:
        """Check if Redis is configured."""
        return self.redis_url is not None

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.environment == "DEV"

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.environment == "PROD"


# Global settings instance
settings = Settings()
