"""
Settings for the Wappa WhatsApp framework.

Naming policy
─────────────
  Unprefixed platform contracts : PORT, DATABASE_URL, REDIS_URL
  Framework runtime             : SYSTEM_*
  Meta / WhatsApp transport     : META_*, WP_*
  AI vendor services            : OPENAI_*, ANTHROPIC_*
  Storage vendor services       : SUPABASE_*
  App-specific namespaces       : your own prefix (e.g. MIIA_*, BELLABELLA_*)
"""

import os
import sys
import tomllib
from importlib import metadata
from pathlib import Path
from typing import cast

from dotenv import load_dotenv

load_dotenv(".env")


def _get_version_from_pyproject() -> str:
    """Resolve the package version.

    A source checkout reads ``pyproject.toml``; an installed distribution has
    no ``pyproject.toml`` on the import path, so the packaging metadata is the
    authority there. ``0.1.0`` is only the last-resort fallback.
    """
    current_path = Path(__file__)
    for parent in [current_path.parent, *current_path.parents]:
        pyproject_path = parent / "pyproject.toml"
        if pyproject_path.exists():
            try:
                with open(pyproject_path, "rb") as f:
                    pyproject_data = tomllib.load(f)
                    if pyproject_data.get("project", {}).get("name") == "wappa":
                        version = pyproject_data["project"].get("version")
                        if version:
                            return cast(str, version)
            except (OSError, tomllib.TOMLDecodeError):
                continue
    try:
        return metadata.version("wappa")
    except metadata.PackageNotFoundError:
        return "0.1.0"


def _is_cli_context() -> bool:
    """Return whether settings are loading for a non-server CLI command."""
    if len(sys.argv) <= 1:
        return False
    cli_only_commands = {"--help", "-h", "init", "examples"}
    if any(argument in cli_only_commands for argument in sys.argv[1:]):
        return True
    if any("wappa" in argument for argument in sys.argv):
        return not any(command in sys.argv for command in {"dev", "prod"})
    return False


class Settings:
    """Application settings with environment-based configuration."""

    def __init__(self) -> None:
        # ── Version ──────────────────────────────────────────────
        self.version: str = _get_version_from_pyproject()

        # ── Platform contracts (unprefixed) ──────────────────────
        self.port: int = int(os.getenv("PORT", "8000"))

        # ── Framework (SYSTEM_*) ─────────────────────────────────
        self.environment: str = os.getenv("SYSTEM_ENVIRONMENT", "DEV")
        self.log_level: str = os.getenv("SYSTEM_LOG_LEVEL", "INFO")
        self.log_dir: str = os.getenv("SYSTEM_LOG_DIR", "./logs")
        self.time_zone: str = os.getenv("SYSTEM_TIME_ZONE", "UTC")
        _rich_raw = os.getenv("SYSTEM_LOGS_RICH_FORMAT", "").strip().upper()
        self.logs_rich_format: bool | None = (
            True if _rich_raw == "TRUE" else False if _rich_raw == "FALSE" else None
        )

        # ── Meta / WhatsApp (META_* / WP_*) ─────────────────────
        self.api_version: str = os.getenv("META_API_VERSION", "v26.0")
        self.base_url: str = os.getenv("META_BASE_URL", "https://graph.facebook.com/")

        # Meta Application Configuration (one Meta App per Wappa application).
        self.meta_app_secret: str | None = os.getenv("META_APP_SECRET")
        self.wp_webhook_verify_token: str | None = os.getenv("WP_WEBHOOK_VERIFY_TOKEN")

        # Legacy single-Inbox bundle. Only the legacy settings adapter built by
        # ``wappa.core.factory.inbox_assembly`` may consume these three values.
        self.wp_access_token: str | None = os.getenv("WP_ACCESS_TOKEN")
        self.wp_phone_id: str | None = os.getenv("WP_PHONE_ID")
        self.wp_bid: str | None = os.getenv("WP_BID")

        # Inbox Routing Mode and explicit-mode credential encryption.
        self.inbox_routing_mode: str | None = os.getenv("SYSTEM_INBOX_ROUTING_MODE")
        self.system_token_enc_key: str | None = os.getenv("SYSTEM_TOKEN_ENC_KEY")
        self.system_token_enc_previous_keys: str | None = os.getenv(
            "SYSTEM_TOKEN_ENC_PREVIOUS_KEYS"
        )

        # ── AI (OPENAI_*) ────────────────────────────────────────
        self.openai_api_key: str | None = os.getenv("OPENAI_API_KEY")

        # ── Persistence (REDIS_*) ────────────────────────────────
        self.redis_url: str | None = os.getenv("REDIS_URL")
        self.redis_max_connections: int = int(os.getenv("REDIS_MAX_CONNECTIONS", "64"))
        self.redis_connection_timeout: int = int(
            os.getenv("REDIS_CONNECTION_TIMEOUT", "30")
        )
        self.redis_health_check_interval: int = int(
            os.getenv("REDIS_HEALTH_CHECK_INTERVAL", "60")
        )

        self._validate_settings()

    def _validate_settings(self) -> None:
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR"]
        if self.log_level.upper() not in valid_levels:
            raise ValueError(f"SYSTEM_LOG_LEVEL must be one of {valid_levels}")
        self.log_level = self.log_level.upper()

        if self.environment.upper() not in ("DEV", "PROD"):
            self.environment = "DEV"
        self.environment = self.environment.upper()

    @property
    def has_redis(self) -> bool:
        return self.redis_url is not None

    @property
    def is_development(self) -> bool:
        return self.environment == "DEV"

    @property
    def is_production(self) -> bool:
        return self.environment == "PROD"


settings = Settings()
