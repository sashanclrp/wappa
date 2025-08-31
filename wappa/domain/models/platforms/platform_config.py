"""
Platform configuration models for messenger platforms.

Defines configuration structure for messenger platforms similar to
payment provider configuration but adapted for messaging platforms.
"""

from typing import Any

from pydantic import BaseModel, Field


class PlatformCapabilities(BaseModel):
    """Platform-specific capabilities and limits."""

    max_text_length: int = Field(
        default=4096, description="Maximum text message length"
    )
    max_media_size: int = Field(
        default=16 * 1024 * 1024, description="Maximum media file size in bytes"
    )
    supports_threads: bool = Field(
        default=False, description="Whether platform supports message threads"
    )
    supports_reactions: bool = Field(
        default=True, description="Whether platform supports message reactions"
    )
    supports_editing: bool = Field(
        default=False, description="Whether platform supports message editing"
    )
    supported_message_types: list[str] = Field(
        default_factory=list, description="Supported message types"
    )
    supported_interactive_types: list[str] = Field(
        default_factory=list, description="Supported interactive message types"
    )


class PlatformCredentials(BaseModel):
    """Platform-specific credentials and API keys."""

    access_token: str | None = Field(default=None, description="Platform access token")
    app_id: str | None = Field(default=None, description="Application ID")
    app_secret: str | None = Field(default=None, description="Application secret")
    phone_id: str | None = Field(default=None, description="Phone number ID (WhatsApp)")
    business_id: str | None = Field(default=None, description="Business account ID")
    webhook_verify_token: str | None = Field(
        default=None, description="Webhook verification token"
    )

    def is_configured(self) -> bool:
        """Check if minimum required credentials are present."""
        # For WhatsApp, we need access_token and phone_id
        return bool(self.access_token and self.phone_id)


class PlatformLimits(BaseModel):
    """Platform-specific rate limits and constraints."""

    max_requests_per_minute: int = Field(
        default=1000, description="Maximum API requests per minute"
    )
    max_recipients_per_message: int = Field(
        default=1, description="Maximum recipients per message"
    )
    max_buttons_per_message: int = Field(
        default=3, description="Maximum buttons per interactive message"
    )
    max_list_sections: int = Field(
        default=10, description="Maximum sections in list messages"
    )
    max_list_rows_per_section: int = Field(
        default=10, description="Maximum rows per list section"
    )


class PlatformConfig(BaseModel):
    """Complete platform configuration."""

    platform_name: str = Field(description="Internal platform name (lowercase)")
    display_name: str = Field(description="Human-readable platform name")
    is_enabled: bool = Field(default=True, description="Whether platform is enabled")
    is_test_mode: bool = Field(
        default=False, description="Whether platform is in test mode"
    )

    credentials: PlatformCredentials = Field(description="Platform credentials")
    capabilities: PlatformCapabilities = Field(description="Platform capabilities")
    limits: PlatformLimits = Field(description="Platform limits")

    webhook_events: list[str] = Field(
        default_factory=list, description="Supported webhook events"
    )
    webhook_url_template: str = Field(description="Webhook URL template")

    platform_settings: dict[str, Any] = Field(
        default_factory=dict, description="Platform-specific settings"
    )

    def is_configured(self) -> bool:
        """Check if platform is properly configured."""
        return self.credentials.is_configured()
