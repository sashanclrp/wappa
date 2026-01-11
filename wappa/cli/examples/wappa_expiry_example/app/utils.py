"""
Utility functions specific to wappa_expiry_example.

These are example-specific helpers with opinionated formatting
and business logic for the 15-second inactivity echo demo.

These functions were intentionally moved out of the framework core
because they contain hardcoded messages and formatting specific to
this example's 15-second inactivity pattern.
"""

from datetime import datetime


def format_inactivity_message_history(messages: list[dict], message_count: int) -> str:
    """
    Format message history for the 15-second inactivity echo feature.

    THIS IS EXAMPLE-SPECIFIC. Contains hardcoded messages:
    - "You were inactive for 15 seconds"
    - "Session Complete!"
    - "Send another message to start a new session"

    This function is specific to the wappa_expiry_example's
    15-second inactivity pattern and would need modification
    for different use cases.

    Args:
        messages: List of message dictionaries with 'timestamp', 'text', and 'type' keys
        message_count: Total number of messages

    Returns:
        Formatted message history string with timestamps and metadata

    Example:
        messages = [
            {"timestamp": "2024-01-01T10:30:45", "text": "Hello", "type": "text"},
            {"timestamp": "2024-01-01T10:30:47", "text": "How are you?", "type": "text"},
        ]
        formatted = format_inactivity_message_history(messages, len(messages))
        # Returns formatted history with timestamps and 15-second inactivity messaging
    """
    plural_suffix = "s" if message_count != 1 else ""

    # Build header
    lines = [
        f"*Message History* ({message_count} message{plural_suffix})",
        "",
        "_You were inactive for 15 seconds. Here's what you sent:_",
        "",
    ]

    # Format each message with timestamp
    for idx, msg in enumerate(messages, 1):
        timestamp_str = msg.get("timestamp", "")
        message_text = msg.get("text", "[No content]")

        # Parse timestamp for display
        time_display = parse_timestamp_display(timestamp_str)

        # Format message line
        lines.append(f"`{idx}.` *[{time_display}]* {message_text}")

    # Add footer
    lines.extend(
        [
            "",
            "*Session Complete!*",
            f"Total: {message_count} message{plural_suffix}",
            "Timer: 15 seconds",
            "",
            "_Send another message to start a new session!_",
        ]
    )

    return "\n".join(lines)


def parse_timestamp_display(timestamp_str: str) -> str:
    """
    Parse ISO timestamp string to HH:MM:SS display format.

    Args:
        timestamp_str: ISO format timestamp string

    Returns:
        Formatted time display (HH:MM:SS) or "??:??:??" if parsing fails

    Example:
        >>> parse_timestamp_display("2024-01-01T10:30:45")
        "10:30:45"
        >>> parse_timestamp_display("")
        "??:??:??"
    """
    if not timestamp_str:
        return "??:??:??"

    try:
        timestamp = datetime.fromisoformat(timestamp_str)
        return timestamp.strftime("%H:%M:%S")
    except (ValueError, TypeError):
        return "??:??:??"
