"""
Message processing utility functions following Single Responsibility Principle.

This module provides message-related helper functions used across
different score modules for consistent message handling.
"""

from datetime import datetime

from wappa.webhooks import IncomingMessageWebhook


def extract_user_data(webhook: IncomingMessageWebhook) -> dict[str, str]:
    """
    Extract user data from webhook in a standardized format.

    Args:
        webhook: Incoming message webhook

    Returns:
        Dictionary with standardized user data
    """
    return {
        "user_id": webhook.user.user_id,
        "user_name": webhook.user.profile_name or "Unknown User",
        "tenant_id": webhook.tenant.get_tenant_key(),
        "message_id": webhook.message.message_id,
    }


def sanitize_message_text(text: str, max_length: int = 500) -> str:
    """
    Sanitize message text for safe storage and processing.

    Args:
        text: Raw message text
        max_length: Maximum allowed length

    Returns:
        Sanitized message text
    """
    if not text:
        return ""

    # Convert to string and strip whitespace
    sanitized = str(text).strip()

    # Truncate if too long
    if len(sanitized) > max_length:
        sanitized = sanitized[: max_length - 3] + "..."

    # Replace problematic characters
    sanitized = sanitized.replace("\x00", "").replace("\r\n", "\n")

    return sanitized


def format_timestamp(dt: datetime, format_type: str = "display") -> str:
    """
    Format timestamps consistently across the application.

    Args:
        dt: Datetime to format
        format_type: Format type ('display', 'compact', 'iso')

    Returns:
        Formatted timestamp string
    """
    if format_type == "display":
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    elif format_type == "compact":
        return dt.strftime("%m/%d %H:%M")
    elif format_type == "iso":
        return dt.isoformat()
    else:
        raise ValueError(f"Unknown format_type: {format_type}")


def extract_command_from_message(text: str) -> tuple[str | None, str]:
    """
    Extract command and remaining text from message.

    Args:
        text: Message text

    Returns:
        Tuple of (command, remaining_text)
        Command is None if no command found

    Examples:
        >>> extract_command_from_message("/WAPPA hello")
        ("/WAPPA", "hello")
        >>> extract_command_from_message("regular message")
        (None, "regular message")
    """
    if not text:
        return None, ""

    text = text.strip()

    # Check if it starts with a command
    if text.startswith("/"):
        parts = text.split(" ", 1)
        command = parts[0].upper()
        remaining = parts[1] if len(parts) > 1 else ""
        return command, remaining

    return None, text


def is_special_command(text: str) -> bool:
    """
    Check if message text contains a special command.

    Args:
        text: Message text to check

    Returns:
        True if text contains a recognized command
    """
    command, _ = extract_command_from_message(text)

    if not command:
        return False

    # List of recognized commands
    special_commands = ["/WAPPA", "/EXIT", "/HISTORY", "/HELP", "/STATUS"]

    return command in special_commands


def get_message_type_display_name(message_type: str) -> str:
    """
    Get human-readable display name for message types.

    Args:
        message_type: Technical message type

    Returns:
        Human-readable display name
    """
    type_mapping = {
        "text": "Text",
        "image": "Image",
        "audio": "Audio",
        "video": "Video",
        "document": "Document",
        "location": "Location",
        "contacts": "Contact",
        "interactive": "Interactive",
        "button": "Button Response",
        "list": "List Response",
        "sticker": "Sticker",
    }

    return type_mapping.get(message_type.lower(), message_type.title())


def create_user_greeting(user_name: str | None, message_count: int) -> str:
    """
    Create personalized user greeting message.

    Args:
        user_name: User's display name (can be None)
        message_count: Number of messages from user

    Returns:
        Personalized greeting text
    """
    name = user_name or "there"

    if message_count == 1:
        return f"👋 Hello {name}! Welcome to the Redis Cache Demo!"
    elif message_count < 5:
        return f"👋 Hello {name}! Nice to see you again!"
    else:
        return f"👋 Hello {name}! You're becoming a regular here! ({message_count} messages)"


def format_message_history_display(
    messages, total_count: int, display_count: int = 20
) -> str:
    """
    Format message history for display to user.

    Args:
        messages: List of MessageHistory objects
        total_count: Total number of messages in history
        display_count: Number of messages being displayed

    Returns:
        Formatted history text
    """
    if not messages:
        return "📚 Your message history is empty. Start chatting to build your history!"

    history_text = f"📚 Your Message History ({total_count} total messages):\n\n"

    for i, msg_history in enumerate(messages, 1):
        timestamp_str = format_timestamp(msg_history.timestamp, "compact")
        msg_type = (
            f"[{get_message_type_display_name(msg_history.message_type)}]"
            if msg_history.message_type != "text"
            else ""
        )

        # Truncate long messages for display
        display_message = sanitize_message_text(msg_history.message, 50)

        history_text += f"{i:2d}. {timestamp_str} {msg_type} {display_message}\n"

    if total_count > display_count:
        history_text += f"\n... showing last {display_count} of {total_count} messages"

    return history_text


def create_cache_info_message(user_profile, cache_stats) -> str:
    """
    Create informational message about cache status.

    Args:
        user_profile: User profile data
        cache_stats: Cache statistics data

    Returns:
        Formatted cache information message
    """
    info_lines = [
        "👤 Your Profile:",
        f"• Messages sent: {user_profile.message_count}",
        f"• First seen: {format_timestamp(user_profile.first_seen, 'compact')}",
        f"• Last seen: {format_timestamp(user_profile.last_seen, 'compact')}",
        "",
        "🎯 Special Commands:",
        "• Send '/WAPPA' to enter special state",
        "• Send '/EXIT' to leave special state",
        "• Send '/HISTORY' to see your message history",
        "",
        "📊 Cache Statistics:",
        f"• Total operations: {cache_stats.total_operations}",
        f"• User cache hit rate: {cache_stats.get_user_hit_rate():.1%}",
        f"• Active states: {cache_stats.state_cache_active}",
        "",
        "💾 This demo showcases Redis caching:",
        "• User data cached in user_cache",
        "• Message history stored in table_cache per user",
        "• Commands tracked in state_cache",
    ]

    return "\n".join(info_lines)
