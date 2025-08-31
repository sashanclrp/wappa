"""
Pydantic models for Redis cache demonstration.

These models demonstrate how to structure data for different cache types
in the Wappa Redis caching system.
"""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class MessageHistory(BaseModel):
    """
    Individual message entry for message history storage.

    Stores a single message with its timestamp.
    """

    message: str = Field(
        ..., description="The message content or type description", max_length=500
    )

    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="When the message was sent"
    )

    message_type: str = Field(
        default="text",
        description="Type of message (text, image, audio, etc.)",
        max_length=20,
    )


class User(BaseModel):
    """
    User profile model for user_cache demonstration.

    Stores user information extracted from WhatsApp webhook data.
    """

    phone_number: str = Field(
        ...,
        description="User's phone number (WhatsApp ID)",
        min_length=10,
        max_length=20,
    )

    user_name: str | None = Field(
        None, description="User's display name from WhatsApp profile", max_length=100
    )

    first_seen: datetime = Field(
        default_factory=datetime.utcnow, description="When the user was first seen"
    )

    last_seen: datetime = Field(
        default_factory=datetime.utcnow, description="When the user was last seen"
    )

    message_count: int = Field(
        default=0, description="Total number of messages received from this user", ge=0
    )

    is_active: bool = Field(
        default=True, description="Whether the user is currently active"
    )

    @field_validator("phone_number", mode="before")
    @classmethod
    def validate_phone_number(cls, v) -> str:
        """Convert phone number to string if it's an integer."""
        if isinstance(v, int):
            return str(v)
        return v

    def increment_message_count(self) -> None:
        """Increment the message count and update last_seen timestamp."""
        self.message_count += 1
        self.last_seen = datetime.utcnow()


class MessageLog(BaseModel):
    """
    Message log model for table_cache demonstration.

    Stores message history for a user with waid as primary key.
    Contains a list of all messages sent by the user.
    """

    user_id: str = Field(
        ...,
        description="User's phone number/ID (primary key)",
        min_length=10,
        max_length=20,
    )

    text_message: list[MessageHistory] = Field(
        default_factory=list, description="List of all messages sent by this user"
    )

    tenant_id: str | None = Field(
        None,
        description="Tenant/business ID that received the messages",
        max_length=100,
    )

    def get_log_key(self) -> str:
        """Generate the primary key for this user's message log."""
        return f"msg_history:{self.user_id}"

    def add_message(self, message: str, message_type: str = "text") -> None:
        """Add a new message to the user's history."""
        new_message = MessageHistory(
            message=message, message_type=message_type, timestamp=datetime.utcnow()
        )
        self.text_message.append(new_message)

    def get_recent_messages(self, count: int = 10) -> list[MessageHistory]:
        """Get the most recent messages from the user's history."""
        return self.text_message[-count:] if self.text_message else []

    @field_validator("user_id", "tenant_id", mode="before")
    @classmethod
    def validate_string_ids(cls, v) -> str:
        """Convert ID fields to string if they're integers."""
        if isinstance(v, int):
            return str(v)
        return v

    def get_message_count(self) -> int:
        """Get the total number of messages in the history."""
        return len(self.text_message)


class StateHandler(BaseModel):
    """
    State handler model for state_cache demonstration.

    Manages user state for the /WAPPA command flow.
    """

    is_wappa: bool = Field(
        default=False, description="Whether the user is in 'WAPPA' state"
    )

    activated_at: datetime | None = Field(
        None, description="When the WAPPA state was activated"
    )

    command_count: int = Field(
        default=0, description="Number of commands processed while in WAPPA state", ge=0
    )

    last_command: str | None = Field(
        None, description="Last command processed in WAPPA state", max_length=100
    )

    def activate_wappa(self) -> None:
        """Activate WAPPA state."""
        self.is_wappa = True
        self.activated_at = datetime.utcnow()
        self.command_count = 0
        self.last_command = "/WAPPA"

    def deactivate_wappa(self) -> None:
        """Deactivate WAPPA state."""
        self.is_wappa = False
        self.last_command = "/EXIT"

    def process_command(self, command: str) -> None:
        """Process a command while in WAPPA state."""
        self.command_count += 1
        self.last_command = command

    def get_state_duration(self) -> int | None:
        """Get how long the WAPPA state has been active in seconds."""
        if not self.is_wappa or not self.activated_at:
            return None
        return int((datetime.utcnow() - self.activated_at).total_seconds())


class CacheStats(BaseModel):
    """
    Cache statistics model for monitoring cache usage.

    Used to track cache performance and usage statistics.
    """

    # Cache performance metrics
    user_cache_hits: int = Field(default=0, ge=0)
    user_cache_misses: int = Field(default=0, ge=0)
    table_cache_entries: int = Field(default=0, ge=0)
    state_cache_active: int = Field(default=0, ge=0)

    # Operation tracking
    total_operations: int = Field(default=0, ge=0)
    errors: int = Field(default=0, ge=0)

    # System information
    cache_type: str = Field(default="Unknown")
    connection_status: str = Field(default="Unknown")
    is_healthy: bool = Field(default=True)

    # Timing
    last_updated: datetime = Field(default_factory=datetime.utcnow)

    def record_user_hit(self) -> None:
        """Record a user cache hit."""
        self.user_cache_hits += 1
        self.total_operations += 1
        self.last_updated = datetime.utcnow()

    def record_user_miss(self) -> None:
        """Record a user cache miss."""
        self.user_cache_misses += 1
        self.total_operations += 1
        self.last_updated = datetime.utcnow()

    def record_table_entry(self) -> None:
        """Record a new table cache entry."""
        self.table_cache_entries += 1
        self.total_operations += 1
        self.last_updated = datetime.utcnow()

    def record_state_activation(self) -> None:
        """Record a state cache activation."""
        self.state_cache_active += 1
        self.total_operations += 1
        self.last_updated = datetime.utcnow()

    def record_state_deactivation(self) -> None:
        """Record a state cache deactivation."""
        if self.state_cache_active > 0:
            self.state_cache_active -= 1
        self.total_operations += 1
        self.last_updated = datetime.utcnow()

    def record_error(self) -> None:
        """Record an error."""
        self.errors += 1
        self.total_operations += 1
        self.last_updated = datetime.utcnow()

    def get_user_hit_rate(self) -> float:
        """Calculate user cache hit rate."""
        total_user_ops = self.user_cache_hits + self.user_cache_misses
        if total_user_ops == 0:
            return 0.0
        return round(self.user_cache_hits / total_user_ops, 3)

    def get_error_rate(self) -> float:
        """Calculate overall error rate."""
        if self.total_operations == 0:
            return 0.0
        return round(self.errors / self.total_operations, 3)
