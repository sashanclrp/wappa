"""
User tracking models for the Wappa Full Example application.

Contains models for user profiles, message history, and interaction statistics.
"""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class UserProfile(BaseModel):
    """User profile model for tracking user information and statistics."""

    # Basic user information
    phone_number: str
    user_name: str | None = None
    profile_name: str | None = None

    # Timestamps
    first_seen: datetime = Field(default_factory=datetime.now)
    last_seen: datetime = Field(default_factory=datetime.now)
    last_message_timestamp: datetime | None = None

    # Statistics
    total_messages: int = 0
    message_count: int = 0  # Alias for compatibility
    text_messages: int = 0
    media_messages: int = 0
    interactive_messages: int = 0
    location_messages: int = 0
    contact_messages: int = 0

    # Interaction history
    total_interactions: int = 0
    button_clicks: int = 0
    list_selections: int = 0

    # Special command usage
    commands_used: dict[str, int] = Field(default_factory=dict)

    # User preferences
    preferred_language: str = "en"
    timezone: str | None = None

    # Flags
    is_first_time_user: bool = True
    has_received_welcome: bool = False

    @field_validator("phone_number", mode="before")
    @classmethod
    def validate_phone_number(cls, v):
        """Convert phone number to string if it's an integer."""
        return str(v) if v is not None else v

    def increment_message_count(self, message_type: str = "text") -> None:
        """Increment the message count and update statistics."""
        self.total_messages += 1
        self.message_count += 1  # For compatibility
        self.last_seen = datetime.now()
        self.last_message_timestamp = datetime.now()
        self.is_first_time_user = False

        # Update message type counters
        if message_type in ["text"]:
            self.text_messages += 1
        elif message_type in [
            "image",
            "video",
            "audio",
            "voice",
            "document",
            "sticker",
        ]:
            self.media_messages += 1
        elif message_type in ["interactive"]:
            self.interactive_messages += 1
        elif message_type in ["location"]:
            self.location_messages += 1
        elif message_type in ["contact", "contacts"]:
            self.contact_messages += 1

    def increment_interactions(self, interaction_type: str = "general") -> None:
        """Increment total interactions and specific interaction counters."""
        self.total_interactions += 1
        self.last_seen = datetime.now()

        if interaction_type == "button":
            self.button_clicks += 1
        elif interaction_type == "list":
            self.list_selections += 1

    def increment_command_usage(self, command: str) -> None:
        """Increment usage counter for a specific command."""
        if command not in self.commands_used:
            self.commands_used[command] = 0
        self.commands_used[command] += 1
        self.last_seen = datetime.now()

    def update_profile_info(
        self, user_name: str | None = None, profile_name: str | None = None
    ) -> None:
        """Update user profile information if new data is available."""
        if user_name and user_name != self.user_name:
            self.user_name = user_name

        if profile_name and profile_name != self.profile_name:
            self.profile_name = profile_name

        self.last_seen = datetime.now()

    def mark_welcome_sent(self) -> None:
        """Mark that the welcome message has been sent to this user."""
        self.has_received_welcome = True
        self.is_first_time_user = False
        self.last_seen = datetime.now()

    def get_display_name(self) -> str:
        """Get the best available display name for this user."""
        if self.user_name:
            return self.user_name
        elif self.profile_name:
            return self.profile_name
        else:
            return self.phone_number

    def get_activity_summary(self) -> dict[str, any]:
        """Get a summary of user activity."""
        return {
            "user_id": self.phone_number,
            "display_name": self.get_display_name(),
            "total_messages": self.total_messages,
            "message_types": {
                "text": self.text_messages,
                "media": self.media_messages,
                "interactive": self.interactive_messages,
                "location": self.location_messages,
                "contact": self.contact_messages,
            },
            "interactions": {
                "total": self.total_interactions,
                "buttons": self.button_clicks,
                "lists": self.list_selections,
            },
            "commands_used": self.commands_used,
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "is_active_user": self.total_messages >= 5,
            "is_new_user": self.is_first_time_user or self.total_messages <= 3,
        }


class UserSession(BaseModel):
    """User session model for tracking current conversation context."""

    user_id: str
    session_id: str = Field(
        default_factory=lambda: f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )

    # Session timestamps
    session_start: datetime = Field(default_factory=datetime.now)
    last_activity: datetime = Field(default_factory=datetime.now)

    # Session statistics
    messages_in_session: int = 0
    commands_in_session: list[str] = Field(default_factory=list)
    interactions_in_session: int = 0

    # Current context
    last_message_type: str | None = None
    last_command_used: str | None = None
    current_state: str | None = None  # For tracking active interactive states

    # Session metadata
    user_agent: str | None = None
    platform_version: str | None = None

    def update_activity(
        self, message_type: str = None, command: str = None, interaction: bool = False
    ) -> None:
        """Update session activity."""
        self.last_activity = datetime.now()
        self.messages_in_session += 1

        if message_type:
            self.last_message_type = message_type

        if command:
            self.last_command_used = command
            self.commands_in_session.append(command)

        if interaction:
            self.interactions_in_session += 1

    def set_current_state(self, state: str = None) -> None:
        """Set the current interactive state."""
        self.current_state = state
        self.last_activity = datetime.now()

    def is_session_active(self, timeout_minutes: int = 30) -> bool:
        """Check if the session is still active based on last activity."""
        time_diff = datetime.now() - self.last_activity
        return time_diff.total_seconds() < (timeout_minutes * 60)

    def get_session_duration_seconds(self) -> int:
        """Get the current session duration in seconds."""
        return int((self.last_activity - self.session_start).total_seconds())

    def get_session_summary(self) -> dict[str, any]:
        """Get a summary of the current session."""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "duration_seconds": self.get_session_duration_seconds(),
            "messages_count": self.messages_in_session,
            "interactions_count": self.interactions_in_session,
            "commands_used": list(set(self.commands_in_session)),  # Unique commands
            "last_message_type": self.last_message_type,
            "last_command": self.last_command_used,
            "current_state": self.current_state,
            "is_active": self.is_session_active(),
            "session_start": self.session_start.isoformat(),
            "last_activity": self.last_activity.isoformat(),
        }


class UserStatistics(BaseModel):
    """Aggregate statistics for all users."""

    total_users: int = 0
    active_users_today: int = 0
    active_users_week: int = 0
    new_users_today: int = 0

    total_messages: int = 0
    messages_today: int = 0

    # Message type distribution
    message_type_stats: dict[str, int] = Field(default_factory=dict)

    # Command usage statistics
    command_usage_stats: dict[str, int] = Field(default_factory=dict)

    # Interactive feature usage
    button_usage: int = 0
    list_usage: int = 0

    # Timestamps
    last_updated: datetime = Field(default_factory=datetime.now)

    def update_stats(self, user_profile: UserProfile) -> None:
        """Update statistics with data from a user profile."""
        self.total_users += 1 if user_profile.is_first_time_user else 0
        self.total_messages += user_profile.total_messages

        # Update message type stats
        for msg_type, count in {
            "text": user_profile.text_messages,
            "media": user_profile.media_messages,
            "interactive": user_profile.interactive_messages,
            "location": user_profile.location_messages,
            "contact": user_profile.contact_messages,
        }.items():
            if msg_type not in self.message_type_stats:
                self.message_type_stats[msg_type] = 0
            self.message_type_stats[msg_type] += count

        # Update command usage stats
        for command, count in user_profile.commands_used.items():
            if command not in self.command_usage_stats:
                self.command_usage_stats[command] = 0
            self.command_usage_stats[command] += count

        # Update interaction stats
        self.button_usage += user_profile.button_clicks
        self.list_usage += user_profile.list_selections

        self.last_updated = datetime.now()

    def get_summary(self) -> dict[str, any]:
        """Get a comprehensive statistics summary."""
        return {
            "overview": {
                "total_users": self.total_users,
                "active_users_today": self.active_users_today,
                "new_users_today": self.new_users_today,
                "total_messages": self.total_messages,
                "messages_today": self.messages_today,
            },
            "message_distribution": self.message_type_stats,
            "popular_commands": dict(
                sorted(
                    self.command_usage_stats.items(), key=lambda x: x[1], reverse=True
                )
            ),
            "interactive_usage": {
                "button_clicks": self.button_usage,
                "list_selections": self.list_usage,
                "total_interactions": self.button_usage + self.list_usage,
            },
            "last_updated": self.last_updated.isoformat(),
        }
