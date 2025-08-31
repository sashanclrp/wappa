"""
Interactive state models for the Wappa Full Example application.

Contains models for managing button and list interactive states with TTL.
"""

from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class StateType(str, Enum):
    """Types of interactive states."""

    BUTTON = "button"
    LIST = "list"
    CTA = "cta"
    LOCATION = "location"
    CUSTOM = "custom"


class StateStatus(str, Enum):
    """Status of interactive states."""

    ACTIVE = "active"
    EXPIRED = "expired"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class InteractiveState(BaseModel):
    """Base model for interactive session states (buttons/lists)."""

    # State identification
    state_id: str = Field(
        default_factory=lambda: f"state_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
    )
    user_id: str
    state_type: StateType

    # State timing
    created_at: datetime = Field(default_factory=datetime.now)
    expires_at: datetime
    last_activity: datetime = Field(default_factory=datetime.now)

    # State data
    context: dict[str, Any] = Field(default_factory=dict)
    original_message_id: str | None = None
    interactive_message_id: str | None = None

    # State management
    status: StateStatus = StateStatus.ACTIVE
    attempts: int = 0
    max_attempts: int = 5

    # Metadata
    creation_metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("user_id", mode="before")
    @classmethod
    def validate_user_id(cls, v):
        """Convert user ID to string if it's an integer."""
        return str(v) if v is not None else v

    @classmethod
    def create_with_ttl(
        cls, user_id: str, state_type: StateType, ttl_seconds: int = 600, **kwargs
    ) -> "InteractiveState":
        """Create a new interactive state with TTL."""
        expires_at = datetime.now() + timedelta(seconds=ttl_seconds)
        return cls(
            user_id=user_id, state_type=state_type, expires_at=expires_at, **kwargs
        )

    def is_expired(self) -> bool:
        """Check if the state has expired."""
        return datetime.now() > self.expires_at or self.status == StateStatus.EXPIRED

    def is_active(self) -> bool:
        """Check if the state is currently active."""
        return not self.is_expired() and self.status == StateStatus.ACTIVE

    def time_remaining_seconds(self) -> int:
        """Get remaining time in seconds."""
        if self.is_expired():
            return 0
        remaining = self.expires_at - datetime.now()
        return max(0, int(remaining.total_seconds()))

    def time_remaining_minutes(self) -> int:
        """Get remaining time in minutes."""
        return max(0, self.time_remaining_seconds() // 60)

    def increment_attempts(self) -> None:
        """Increment the attempts counter."""
        self.attempts += 1
        self.last_activity = datetime.now()

        if self.attempts >= self.max_attempts:
            self.status = StateStatus.CANCELLED

    def mark_completed(self) -> None:
        """Mark the state as completed."""
        self.status = StateStatus.COMPLETED
        self.last_activity = datetime.now()

    def mark_expired(self) -> None:
        """Mark the state as expired."""
        self.status = StateStatus.EXPIRED
        self.last_activity = datetime.now()

    def mark_cancelled(self) -> None:
        """Mark the state as cancelled."""
        self.status = StateStatus.CANCELLED
        self.last_activity = datetime.now()

    def update_context(self, key: str, value: Any) -> None:
        """Update a context value."""
        self.context[key] = value
        self.last_activity = datetime.now()

    def get_context_value(self, key: str, default: Any = None) -> Any:
        """Get a context value."""
        return self.context.get(key, default)

    def extend_ttl(self, additional_seconds: int) -> None:
        """Extend the TTL of this state."""
        if self.is_active():
            self.expires_at = self.expires_at + timedelta(seconds=additional_seconds)
            self.last_activity = datetime.now()

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of this state."""
        return {
            "state_id": self.state_id,
            "user_id": self.user_id,
            "state_type": self.state_type.value,
            "status": self.status.value,
            "is_active": self.is_active(),
            "time_remaining_seconds": self.time_remaining_seconds(),
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "context": self.context,
        }


class ButtonState(InteractiveState):
    """State model specifically for button interactions."""

    state_type: StateType = StateType.BUTTON

    # Button-specific data
    button_options: list[dict[str, str]] = Field(default_factory=list)
    selected_button_id: str | None = None
    button_message_text: str | None = None

    @classmethod
    def create_button_state(
        cls,
        user_id: str,
        buttons: list[dict[str, str]],
        message_text: str,
        ttl_seconds: int = 600,
        original_message_id: str = None,
    ) -> "ButtonState":
        """Create a new button state."""
        return cls.create_with_ttl(
            user_id=user_id,
            state_type=StateType.BUTTON,
            ttl_seconds=ttl_seconds,
            button_options=buttons,
            button_message_text=message_text,
            original_message_id=original_message_id,
            context={
                "button_count": len(buttons),
                "message_text": message_text,
                "expected_selections": [btn.get("id", "") for btn in buttons],
            },
        )

    def is_valid_selection(self, button_id: str) -> bool:
        """Check if the button selection is valid."""
        valid_ids = [btn.get("id", "") for btn in self.button_options]
        return button_id in valid_ids

    def handle_selection(self, button_id: str) -> bool:
        """Handle button selection."""
        if self.is_valid_selection(button_id) and self.is_active():
            self.selected_button_id = button_id
            self.mark_completed()
            self.update_context("selected_button_id", button_id)
            self.update_context("selected_at", datetime.now().isoformat())
            return True
        return False

    def get_selected_button(self) -> dict[str, str] | None:
        """Get the selected button information."""
        if not self.selected_button_id:
            return None

        for button in self.button_options:
            if button.get("id") == self.selected_button_id:
                return button
        return None


class ListState(InteractiveState):
    """State model specifically for list interactions."""

    state_type: StateType = StateType.LIST

    # List-specific data
    list_sections: list[dict[str, Any]] = Field(default_factory=list)
    selected_item_id: str | None = None
    list_button_text: str = "Choose an option"
    list_message_text: str | None = None

    @classmethod
    def create_list_state(
        cls,
        user_id: str,
        sections: list[dict[str, Any]],
        message_text: str,
        button_text: str = "Choose an option",
        ttl_seconds: int = 600,
        original_message_id: str = None,
    ) -> "ListState":
        """Create a new list state."""
        # Extract all possible item IDs for validation
        valid_ids = []
        for section in sections:
            rows = section.get("rows", [])
            for row in rows:
                if "id" in row:
                    valid_ids.append(row["id"])

        return cls.create_with_ttl(
            user_id=user_id,
            state_type=StateType.LIST,
            ttl_seconds=ttl_seconds,
            list_sections=sections,
            list_message_text=message_text,
            list_button_text=button_text,
            original_message_id=original_message_id,
            context={
                "sections_count": len(sections),
                "total_items": len(valid_ids),
                "message_text": message_text,
                "button_text": button_text,
                "expected_selections": valid_ids,
            },
        )

    def is_valid_selection(self, item_id: str) -> bool:
        """Check if the list item selection is valid."""
        valid_ids = self.get_context_value("expected_selections", [])
        return item_id in valid_ids

    def handle_selection(self, item_id: str) -> bool:
        """Handle list item selection."""
        if self.is_valid_selection(item_id) and self.is_active():
            self.selected_item_id = item_id
            self.mark_completed()
            self.update_context("selected_item_id", item_id)
            self.update_context("selected_at", datetime.now().isoformat())
            return True
        return False

    def get_selected_item(self) -> dict[str, Any] | None:
        """Get the selected list item information."""
        if not self.selected_item_id:
            return None

        for section in self.list_sections:
            rows = section.get("rows", [])
            for row in rows:
                if row.get("id") == self.selected_item_id:
                    return row
        return None


class CommandState(InteractiveState):
    """State model for command-based interactions."""

    state_type: StateType = StateType.CUSTOM

    # Command-specific data
    command_name: str
    expected_responses: list[str] = Field(default_factory=list)
    current_step: int = 0
    total_steps: int = 1

    @classmethod
    def create_command_state(
        cls,
        user_id: str,
        command_name: str,
        expected_responses: list[str] = None,
        ttl_seconds: int = 600,
        total_steps: int = 1,
        original_message_id: str = None,
    ) -> "CommandState":
        """Create a new command state."""
        return cls.create_with_ttl(
            user_id=user_id,
            state_type=StateType.CUSTOM,
            ttl_seconds=ttl_seconds,
            command_name=command_name,
            expected_responses=expected_responses or [],
            total_steps=total_steps,
            original_message_id=original_message_id,
            context={
                "command_name": command_name,
                "expected_responses": expected_responses or [],
                "total_steps": total_steps,
                "current_step": 0,
            },
        )

    def advance_step(self) -> bool:
        """Advance to the next step."""
        if self.current_step < self.total_steps - 1:
            self.current_step += 1
            self.update_context("current_step", self.current_step)
            return True
        else:
            self.mark_completed()
            return False

    def is_final_step(self) -> bool:
        """Check if this is the final step."""
        return self.current_step >= self.total_steps - 1

    def get_progress_percentage(self) -> float:
        """Get the progress percentage."""
        if self.total_steps <= 1:
            return 100.0 if self.status == StateStatus.COMPLETED else 0.0
        return (self.current_step / self.total_steps) * 100.0


class StateManager(BaseModel):
    """Manager for handling multiple interactive states."""

    active_states: dict[str, InteractiveState] = Field(default_factory=dict)
    completed_states: dict[str, InteractiveState] = Field(default_factory=dict)

    def add_state(self, state: InteractiveState) -> None:
        """Add a new state to the manager."""
        state_key = f"{state.user_id}_{state.state_type.value}"

        # Remove any existing state of the same type for this user
        if state_key in self.active_states:
            old_state = self.active_states[state_key]
            old_state.mark_cancelled()
            self.completed_states[f"{state_key}_{old_state.state_id}"] = old_state

        self.active_states[state_key] = state

    def get_user_state(
        self, user_id: str, state_type: StateType
    ) -> InteractiveState | None:
        """Get the active state for a user and state type."""
        state_key = f"{user_id}_{state_type.value}"
        state = self.active_states.get(state_key)

        if state and state.is_expired():
            state.mark_expired()
            self.completed_states[f"{state_key}_{state.state_id}"] = state
            del self.active_states[state_key]
            return None

        return state if state and state.is_active() else None

    def remove_state(
        self, user_id: str, state_type: StateType
    ) -> InteractiveState | None:
        """Remove a state from active states."""
        state_key = f"{user_id}_{state_type.value}"
        state = self.active_states.pop(state_key, None)

        if state:
            self.completed_states[f"{state_key}_{state.state_id}"] = state

        return state

    def cleanup_expired_states(self) -> int:
        """Clean up expired states and return count of cleaned states."""
        expired_count = 0
        expired_keys = []

        for state_key, state in self.active_states.items():
            if state.is_expired():
                state.mark_expired()
                self.completed_states[f"{state_key}_{state.state_id}"] = state
                expired_keys.append(state_key)
                expired_count += 1

        for key in expired_keys:
            del self.active_states[key]

        return expired_count

    def get_user_states(self, user_id: str) -> list[InteractiveState]:
        """Get all active states for a user."""
        user_states = []
        for state in self.active_states.values():
            if state.user_id == user_id and state.is_active():
                user_states.append(state)
        return user_states

    def get_statistics(self) -> dict[str, Any]:
        """Get manager statistics."""
        active_count = len(self.active_states)
        completed_count = len(self.completed_states)

        # Count by state type
        type_counts = {}
        for state in self.active_states.values():
            state_type = state.state_type.value
            type_counts[state_type] = type_counts.get(state_type, 0) + 1

        return {
            "active_states": active_count,
            "completed_states": completed_count,
            "total_states": active_count + completed_count,
            "state_type_distribution": type_counts,
            "cleanup_needed": sum(
                1 for state in self.active_states.values() if state.is_expired()
            ),
        }
