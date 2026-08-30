"""Meta Application Configuration.

One Wappa application binds to exactly one Meta App: its App Secret for POST
callback authentication, the shared verify token for the GET challenge, and
the Graph API version and base URL. It may serve many WABAs and Inboxes under
that App, and it never selects among several App Secrets.

Exactly one configuration source may be active: an explicit
``MetaApplicationConfig`` supplied at construction, or Wappa's environment
adapter. Configuring both is a startup error; there is no precedence rule.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, SecretStr, field_validator

from wappa.domain.inbox.errors import InboxConfigurationError

if TYPE_CHECKING:
    from .settings import Settings

_VERSION_PATTERN = re.compile(r"^v\d+\.\d+$")

META_APP_SECRET_VARIABLE = "META_APP_SECRET"
VERIFY_TOKEN_VARIABLE = "WP_WEBHOOK_VERIFY_TOKEN"


class MetaApplicationConfig(BaseModel):
    """Immutable application-wide Meta trust and Graph API configuration."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    app_secret: SecretStr
    whatsapp_webhook_verify_token: SecretStr
    graph_api_version: str = "v26.0"
    graph_base_url: AnyHttpUrl = AnyHttpUrl("https://graph.facebook.com/")

    @field_validator("app_secret", "whatsapp_webhook_verify_token")
    @classmethod
    def _non_blank_secret(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("secret must not be blank")
        return value

    @field_validator("graph_api_version")
    @classmethod
    def _version_shape(cls, value: str) -> str:
        if not _VERSION_PATTERN.fullmatch(value):
            raise ValueError("graph_api_version must look like 'v26.0'")
        return value

    def health_status(self) -> dict[str, Any]:
        """Readiness facts only; never secret values."""
        return {
            "app_secret_configured": True,
            "verify_token_configured": True,
            "graph_api_version": self.graph_api_version,
            "graph_base_url": str(self.graph_base_url),
        }


def resolve_meta_application_config(
    explicit: MetaApplicationConfig | None,
    settings: Settings,
    *,
    callback_mounted: bool,
) -> MetaApplicationConfig | None:
    """Select the one Meta Application Configuration source.

    Returns ``None`` only for an outbound-only application that mounts no
    WhatsApp callback and configured nothing.
    """
    env_secret = (settings.meta_app_secret or "").strip()
    env_verify = (settings.wp_webhook_verify_token or "").strip()

    if explicit is not None and (env_secret or env_verify):
        configured = [
            name
            for name, value in (
                (META_APP_SECRET_VARIABLE, env_secret),
                (VERIFY_TOKEN_VARIABLE, env_verify),
            )
            if value
        ]
        raise InboxConfigurationError(
            "[wappa] An explicit MetaApplicationConfig and the environment "
            f"variables {', '.join(configured)} are both configured. Wappa accepts "
            "exactly one Meta Application Configuration source; remove one."
        )
    if explicit is not None:
        return explicit

    if env_secret or env_verify:
        if not (env_secret and env_verify):
            if not callback_mounted:
                # Outbound-only application: the callback secrets are unused.
                return None
            missing = (
                META_APP_SECRET_VARIABLE if not env_secret else VERIFY_TOKEN_VARIABLE
            )
            raise InboxConfigurationError(
                f"[wappa] {missing} is required alongside "
                f"{VERIFY_TOKEN_VARIABLE if missing == META_APP_SECRET_VARIABLE else META_APP_SECRET_VARIABLE}. "
                "The Meta App Secret authenticates POST callbacks and the verify "
                "token answers the GET challenge; both belong to one Meta App."
            )
        return MetaApplicationConfig(
            app_secret=SecretStr(env_secret),
            whatsapp_webhook_verify_token=SecretStr(env_verify),
            graph_api_version=settings.api_version,
            graph_base_url=AnyHttpUrl(settings.base_url),
        )

    if callback_mounted:
        raise InboxConfigurationError(
            "[wappa] Mounting the WhatsApp callback requires "
            f"{META_APP_SECRET_VARIABLE} and {VERIFY_TOKEN_VARIABLE} in every "
            "environment, or an explicit MetaApplicationConfig. There is no "
            "development bypass for Meta POST authentication."
        )
    return None


__all__ = [
    "META_APP_SECRET_VARIABLE",
    "VERIFY_TOKEN_VARIABLE",
    "MetaApplicationConfig",
    "resolve_meta_application_config",
]
