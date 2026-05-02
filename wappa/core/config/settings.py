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
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(".env")

_RENAMED = {
    "ENVIRONMENT": "SYSTEM_ENVIRONMENT",
    "LOG_LEVEL": "SYSTEM_LOG_LEVEL",
    "LOG_DIR": "SYSTEM_LOG_DIR",
    "TIME_ZONE": "SYSTEM_TIME_ZONE",
    "API_VERSION": "META_API_VERSION",
    "BASE_URL": "META_BASE_URL",
    "WHATSAPP_WEBHOOK_VERIFY_TOKEN": "WP_WEBHOOK_VERIFY_TOKEN",
}


def _check_legacy_vars() -> None:
    found = [old for old in _RENAMED if os.getenv(old) is not None]
    if found:
        lines = "\n".join(f"  {old}  →  {_RENAMED[old]}" for old in found)
        raise EnvironmentError(
            f"\n\n[wappa] Outdated environment variables detected. "
            f"Rename them in your .env and redeploy:\n\n{lines}\n\n"
            f"See CHANGELOG v0.5.0 for the full migration guide."
        )


def _get_version_from_pyproject() -> str:
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
    if len(sys.argv) > 1:
        cli_only_commands = {"--help", "-h", "init", "examples"}
        for arg in sys.argv[1:]:
            if arg in cli_only_commands:
                return True
        if any("wappa" in arg for arg in sys.argv):
            server_commands = {"dev", "prod"}
            if not any(cmd in sys.argv for cmd in server_commands):
                return True
    return False


class Settings:
    """Application settings with environment-based configuration."""

    def __init__(self):
        _check_legacy_vars()

        # ── Version ──────────────────────────────────────────────
        self.version: str = _get_version_from_pyproject()

        # ── Platform contracts (unprefixed) ──────────────────────
        self.port: int = int(os.getenv("PORT", "8000"))

        # ── Framework (SYSTEM_*) ─────────────────────────────────
        self.environment: str = os.getenv("SYSTEM_ENVIRONMENT", "DEV")
        self.log_level: str = os.getenv("SYSTEM_LOG_LEVEL", "INFO")
        self.log_dir: str = os.getenv("SYSTEM_LOG_DIR", "./logs")
        self.time_zone: str = os.getenv("SYSTEM_TIME_ZONE", "UTC")

        # ── Meta / WhatsApp (META_* / WP_*) ─────────────────────
        self.api_version: str = os.getenv("META_API_VERSION", "v25.0")
        self.base_url: str = os.getenv("META_BASE_URL", "https://graph.facebook.com/")

        self.wp_access_token: str | None = os.getenv("WP_ACCESS_TOKEN")
        self.wp_phone_id: str | None = os.getenv("WP_PHONE_ID")
        self.wp_bid: str | None = os.getenv("WP_BID")
        self.wp_webhook_verify_token: str | None = os.getenv("WP_WEBHOOK_VERIFY_TOKEN")

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
        if not _is_cli_context():
            self._validate_whatsapp_credentials()

    def _validate_settings(self):
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR"]
        if self.log_level.upper() not in valid_levels:
            raise ValueError(f"SYSTEM_LOG_LEVEL must be one of {valid_levels}")
        self.log_level = self.log_level.upper()

        if self.environment.upper() not in ("DEV", "PROD"):
            self.environment = "DEV"
        self.environment = self.environment.upper()

    def _validate_whatsapp_credentials(self):
        missing = [
            name
            for name, val in [
                ("WP_ACCESS_TOKEN", self.wp_access_token),
                ("WP_PHONE_ID", self.wp_phone_id),
                ("WP_BID", self.wp_bid),
                ("WP_WEBHOOK_VERIFY_TOKEN", self.wp_webhook_verify_token),
            ]
            if not val
        ]
        if missing:
            raise EnvironmentError(
                f"[wappa] Missing required WhatsApp credentials: {', '.join(missing)}"
            )

    @property
    def owner_id(self) -> str:
        if not self.wp_phone_id:
            raise ValueError("WP_PHONE_ID is required for owner_id")
        return self.wp_phone_id

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
