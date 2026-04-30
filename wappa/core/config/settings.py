"""
Settings for the Wappa WhatsApp framework.

Simple, reliable environment variable configuration focused on core WhatsApp functionality.

Naming policy
─────────────
  Unprefixed platform contracts : PORT, DATABASE_URL, REDIS_URL
  Framework runtime             : SYSTEM_*
  Meta / WhatsApp transport     : META_*, WP_*
  AI vendor services            : OPENAI_*, ANTHROPIC_*
  Storage vendor services       : SUPABASE_*
  App-specific namespaces       : your own prefix (e.g. MIIA_*, BELLABELLA_*)

Legacy aliases are accepted for all renamed SYSTEM_* and META_* vars and emit a
DeprecationWarning once at startup so you know what to migrate.
"""

import os
import sys
import tomllib
import warnings
from pathlib import Path

from dotenv import load_dotenv

# Load .env file for local development - look in current working directory
load_dotenv(".env")


def _get_version_from_pyproject() -> str:
    """Read version from pyproject.toml file."""
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
                continue

    return "0.1.0"


def _is_cli_context() -> bool:
    """
    Detect if we're running in CLI context (help, init, examples) vs server context (dev, prod).

    Returns:
        True if running CLI commands that don't need WhatsApp credentials
    """
    if len(sys.argv) > 1:
        cli_only_commands = {"--help", "-h", "init", "examples"}

        for arg in sys.argv[1:]:
            if arg in cli_only_commands:
                return True

        if any("wappa" in arg for arg in sys.argv):
            server_commands = {"dev", "prod"}
            has_server_command = any(cmd in sys.argv for cmd in server_commands)
            if not has_server_command:
                return True

    return False


def _resolve_with_alias(canonical: str, legacy: str, default: str | None = None) -> str | None:
    """
    Resolve an env var by canonical name, falling back to a legacy name with a deprecation warning.

    Args:
        canonical: The preferred canonical env var name (e.g. SYSTEM_ENVIRONMENT).
        legacy:    The old env var name to accept as a fallback (e.g. ENVIRONMENT).
        default:   Value returned when neither is set.

    Returns:
        The resolved value, or *default* if neither var is present.
    """
    value = os.getenv(canonical)
    if value is not None:
        return value

    legacy_value = os.getenv(legacy)
    if legacy_value is not None:
        warnings.warn(
            f"[wappa] '{legacy}' is deprecated — rename it to '{canonical}' in your .env.",
            DeprecationWarning,
            stacklevel=3,
        )
        return legacy_value

    return default


class Settings:
    """Application settings with environment-based configuration."""

    def __init__(self):
        # ================================================================
        # Version & Framework Configuration
        # ================================================================
        self.version: str = _get_version_from_pyproject()

        # ================================================================
        # Platform Contracts (unprefixed — ecosystem standard)
        # ================================================================
        self.port: int = int(os.getenv("PORT", "8000"))

        # ================================================================
        # Framework / System Configuration  (SYSTEM_* canonical)
        # ================================================================
        self.environment: str = _resolve_with_alias("SYSTEM_ENVIRONMENT", "ENVIRONMENT", "DEV")
        self.log_level: str = _resolve_with_alias("SYSTEM_LOG_LEVEL", "LOG_LEVEL", "INFO")
        self.log_dir: str = _resolve_with_alias("SYSTEM_LOG_DIR", "LOG_DIR", "./logs")
        self.time_zone: str = _resolve_with_alias("SYSTEM_TIME_ZONE", "TIME_ZONE", "UTC")

        # ================================================================
        # Meta / WhatsApp Configuration  (META_* / WP_*)
        # ================================================================
        self.api_version: str = _resolve_with_alias("META_API_VERSION", "API_VERSION", "v25.0")

        # Internal — not exposed in .env.example; users rarely need to override this.
        self.base_url: str = _resolve_with_alias(
            "META_BASE_URL", "BASE_URL", "https://graph.facebook.com/"
        )

        # WhatsApp Business API credentials (Wappa-owned stable contract)
        self.wp_access_token: str | None = os.getenv("WP_ACCESS_TOKEN")
        self.wp_phone_id: str | None = os.getenv("WP_PHONE_ID")
        self.wp_bid: str | None = os.getenv("WP_BID")

        # Required for webhook verification and signature validation
        self.wp_webhook_verify_token: str | None = _resolve_with_alias(
            "WP_WEBHOOK_VERIFY_TOKEN", "WHATSAPP_WEBHOOK_VERIFY_TOKEN"
        )

        # ================================================================
        # AI & Tools Configuration (Optional)
        # ================================================================
        self.openai_api_key: str | None = os.getenv("OPENAI_API_KEY")

        # ================================================================
        # Persistence — Redis (Optional)
        # ================================================================
        self.redis_url: str | None = os.getenv("REDIS_URL")
        self.redis_max_connections: int = int(os.getenv("REDIS_MAX_CONNECTIONS", "64"))
        self.redis_connection_timeout: int = int(os.getenv("REDIS_CONNECTION_TIMEOUT", "30"))
        self.redis_health_check_interval: int = int(
            os.getenv("REDIS_HEALTH_CHECK_INTERVAL", "60")
        )

        # Apply validation (skip WhatsApp validation for CLI-only commands)
        self._validate_settings()

        if not _is_cli_context():
            self._validate_whatsapp_credentials()

    def _validate_settings(self):
        """Validate settings values."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR"]
        if self.log_level.upper() not in valid_levels:
            raise ValueError(f"SYSTEM_LOG_LEVEL must be one of {valid_levels}")
        self.log_level = self.log_level.upper()

        valid_environments = ["DEV", "PROD"]
        if self.environment.upper() not in valid_environments:
            self.environment = "DEV"
        self.environment = self.environment.upper()

    def _validate_whatsapp_credentials(self):
        """Validate required WhatsApp credentials."""
        if not self.wp_access_token:
            raise ValueError("WP_ACCESS_TOKEN is required")
        if not self.wp_phone_id:
            raise ValueError("WP_PHONE_ID is required")
        if not self.wp_bid:
            raise ValueError("WP_BID is required")
        if not self.wp_webhook_verify_token:
            raise ValueError("WP_WEBHOOK_VERIFY_TOKEN is required")

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
