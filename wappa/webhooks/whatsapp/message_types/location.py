"""
WhatsApp location message schema.

This module contains Pydantic models for processing WhatsApp location messages,
including coordinates, addresses, and location metadata sent via Click-to-WhatsApp ads.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from wappa.webhooks.core.base_message import BaseLocationMessage, BaseMessageContext
from wappa.webhooks.core.types import (
    ConversationType,
    MessageType,
    PlatformType,
    UniversalMessageData,
)
from wappa.webhooks.whatsapp.base_models import AdReferral, MessageContext


class LocationContent(BaseModel):
    """Location message content."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    address: str | None = Field(
        None, description="Human-readable address of the location"
    )
    latitude: float = Field(..., description="Latitude coordinate of the location")
    longitude: float = Field(..., description="Longitude coordinate of the location")
    name: str | None = Field(None, description="Name or title of the location")
    url: str | None = Field(
        None, description="URL with more information about the location"
    )

    @field_validator("latitude")
    @classmethod
    def validate_latitude(cls, v: float) -> float:
        """Validate latitude is within valid range."""
        if not -90.0 <= v <= 90.0:
            raise ValueError("Latitude must be between -90.0 and 90.0")
        return v

    @field_validator("longitude")
    @classmethod
    def validate_longitude(cls, v: float) -> float:
        """Validate longitude is within valid range."""
        if not -180.0 <= v <= 180.0:
            raise ValueError("Longitude must be between -180.0 and 180.0")
        return v

    @field_validator("address")
    @classmethod
    def validate_address(cls, v: str | None) -> str | None:
        """Validate address if present."""
        if v is not None:
            v = v.strip()
            if not v:
                return None
            if len(v) > 1000:  # Reasonable address length limit
                raise ValueError("Address cannot exceed 1000 characters")
        return v

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str | None) -> str | None:
        """Validate location name if present."""
        if v is not None:
            v = v.strip()
            if not v:
                return None
            if len(v) > 256:  # Reasonable name length limit
                raise ValueError("Location name cannot exceed 256 characters")
        return v

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str | None) -> str | None:
        """Validate location URL if present."""
        if v is not None:
            v = v.strip()
            if not v:
                return None
            if not (v.startswith("http://") or v.startswith("https://")):
                raise ValueError("Location URL must start with http:// or https://")
        return v


class WhatsAppLocationMessage(BaseLocationMessage):
    """
    WhatsApp location message model.

    Supports various location message scenarios:
    - Current location sharing
    - Business location sharing
    - Custom location with name and address
    - Click-to-WhatsApp ad location messages
    """

    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, validate_assignment=True
    )

    # Standard message fields (BSUID support v24.0+)
    from_: str = Field(
        default="",
        alias="from",
        description="WhatsApp user phone number (may be empty for username-only users)",
    )
    from_bsuid: str | None = Field(
        None,
        alias="from_user_id",
        description="Business Scoped User ID (BSUID) - stable identifier from webhook",
    )
    id: str = Field(..., description="Unique WhatsApp message ID")
    timestamp_str: str = Field(
        ..., alias="timestamp", description="Unix timestamp when the message was sent"
    )
    type: Literal["location"] = Field(
        ..., description="Message type, always 'location' for location messages"
    )

    # Location content
    location: LocationContent = Field(
        ..., description="Location coordinates and metadata"
    )

    # Optional context fields
    context: MessageContext | None = Field(
        None,
        description="Context for forwards (locations don't support replies typically)",
    )
    referral: AdReferral | None = Field(
        None, description="Click-to-WhatsApp ad referral information"
    )

    @property
    def sender_id(self) -> str:
        """Get the recommended sender identifier (BSUID if available, else phone)."""
        if self.from_bsuid and self.from_bsuid.strip():
            return self.from_bsuid.strip()
        return self.from_

    @property
    def has_bsuid(self) -> bool:
        """Check if this message has a BSUID set."""
        return bool(self.from_bsuid and self.from_bsuid.strip())

    @field_validator("id")
    @classmethod
    def validate_message_id(cls, v: str) -> str:
        """Validate WhatsApp message ID format."""
        if not v or len(v) < 10:
            raise ValueError("WhatsApp message ID must be at least 10 characters")
        # WhatsApp message IDs typically start with 'wamid.'
        if not v.startswith("wamid."):
            raise ValueError("WhatsApp message ID should start with 'wamid.'")
        return v

    @field_validator("timestamp_str")
    @classmethod
    def validate_timestamp(cls, v: str) -> str:
        """Validate Unix timestamp format."""
        if not v.isdigit():
            raise ValueError("Timestamp must be numeric")
        # Validate reasonable timestamp range (after 2020, before 2100)
        timestamp_int = int(v)
        if timestamp_int < 1577836800 or timestamp_int > 4102444800:
            raise ValueError("Timestamp must be a valid Unix timestamp")
        return v

    @property
    def has_name(self) -> bool:
        """Check if this location has a name."""
        return self.location.name is not None and len(self.location.name.strip()) > 0

    @property
    def has_address(self) -> bool:
        """Check if this location has an address."""
        return (
            self.location.address is not None and len(self.location.address.strip()) > 0
        )

    @property
    def has_url(self) -> bool:
        """Check if this location has a URL."""
        return self.location.url is not None and len(self.location.url.strip()) > 0

    @property
    def is_ad_message(self) -> bool:
        """Check if this location message came from a Click-to-WhatsApp ad."""
        return self.referral is not None

    @property
    def sender_phone(self) -> str:
        """Get the sender's phone number (clean accessor)."""
        return self.from_

    @property
    def coordinates(self) -> tuple[float, float]:
        """Get the location coordinates as (latitude, longitude)."""
        return (self.location.latitude, self.location.longitude)

    @property
    def latitude(self) -> float:
        """Get the latitude coordinate."""
        return self.location.latitude

    @property
    def longitude(self) -> float:
        """Get the longitude coordinate."""
        return self.location.longitude

    @property
    def address(self) -> str | None:
        """Get the location address."""
        return self.location.address

    @property
    def name(self) -> str | None:
        """Get the location name."""
        return self.location.name

    @property
    def url(self) -> str | None:
        """Get the location URL."""
        return self.location.url

    @property
    def unix_timestamp(self) -> int:
        """Get the timestamp as an integer."""
        return self.timestamp

    def get_google_maps_url(self) -> str:
        """
        Generate a Google Maps URL for this location.

        Returns:
            Google Maps URL with the coordinates.
        """
        return f"https://www.google.com/maps?q={self.latitude},{self.longitude}"

    def get_distance_from(self, other_lat: float, other_lon: float) -> float:
        """
        Calculate distance from this location to another point using Haversine formula.

        Args:
            other_lat: Latitude of the other point
            other_lon: Longitude of the other point

        Returns:
            Distance in kilometers
        """
        import math

        # Convert latitude and longitude from degrees to radians
        lat1, lon1, lat2, lon2 = map(
            math.radians, [self.latitude, self.longitude, other_lat, other_lon]
        )

        # Haversine formula
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        )
        c = 2 * math.asin(math.sqrt(a))

        # Radius of earth in kilometers
        r = 6371

        return c * r

    def get_ad_context(self) -> tuple[str | None, str | None]:
        """
        Get ad context information for Click-to-WhatsApp location messages.

        Returns:
            Tuple of (ad_id, ad_click_id) if this came from an ad,
            (None, None) otherwise.
        """
        if self.is_ad_message and self.referral:
            return (self.referral.source_id, self.referral.ctwa_clid)
        return (None, None)

    def to_summary_dict(self) -> dict[str, str | bool | int | float]:
        """
        Create a summary dictionary for logging and analysis.

        Returns:
            Dictionary with key message information for structured logging.
        """
        return {
            "message_id": self.id,
            "sender": self.sender_phone,
            "timestamp": self.unix_timestamp,
            "type": self.type,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "has_name": self.has_name,
            "has_address": self.has_address,
            "has_url": self.has_url,
            "location_name": self.name,
            "google_maps_url": self.get_google_maps_url(),
            "is_ad_message": self.is_ad_message,
        }

    # Implement abstract methods from BaseMessage

    @property
    def platform(self) -> PlatformType:
        return PlatformType.WHATSAPP

    @property
    def message_type(self) -> MessageType:
        return MessageType.LOCATION

    @property
    def message_id(self) -> str:
        return self.id

    @property
    def timestamp(self) -> int:
        return int(self.timestamp_str)

    @property
    def conversation_id(self) -> str:
        return self.from_

    @property
    def conversation_type(self) -> ConversationType:
        return ConversationType.PRIVATE

    def has_context(self) -> bool:
        return self.context is not None

    def get_context(self) -> BaseMessageContext | None:
        from .text import WhatsAppMessageContext

        return WhatsAppMessageContext(self.context) if self.context else None

    def to_universal_dict(self) -> UniversalMessageData:
        return {
            "platform": self.platform.value,
            "message_type": self.message_type.value,
            "message_id": self.message_id,
            "sender_id": self.sender_id,
            "conversation_id": self.conversation_id,
            "conversation_type": self.conversation_type.value,
            "timestamp": self.timestamp,
            "processed_at": self.processed_at.isoformat(),
            "has_context": self.has_context(),
            "latitude": self.latitude,
            "longitude": self.longitude,
            "location_name": self.name,
            "location_address": self.address,
            "location_url": self.url,
            "whatsapp_data": {
                "whatsapp_id": self.id,
                "from": self.from_,
                "timestamp_str": self.timestamp_str,
                "type": self.type,
                "location_content": self.location.model_dump(),
                "context": self.context.model_dump() if self.context else None,
                "referral": self.referral.model_dump() if self.referral else None,
            },
        }

    def get_platform_data(self) -> dict[str, Any]:
        return {
            "whatsapp_message_id": self.id,
            "from_phone": self.from_,
            "timestamp_str": self.timestamp_str,
            "message_type": self.type,
            "location_content": self.location.model_dump(),
            "context": self.context.model_dump() if self.context else None,
            "referral": self.referral.model_dump() if self.referral else None,
            "location_summary": {
                "coordinates": f"{self.latitude}, {self.longitude}",
                "google_maps_url": self.get_google_maps_url(),
                "has_name": self.has_name,
                "has_address": self.has_address,
            },
        }

    # Abstract methods already implemented above

    @property
    def location_name(self) -> str | None:
        """Get the location name if available."""
        return self.location.name

    @classmethod
    def from_platform_data(
        cls, data: dict[str, Any], **kwargs
    ) -> "WhatsAppLocationMessage":
        return cls.model_validate(data)
