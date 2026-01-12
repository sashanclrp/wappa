"""
Extraction Utilities for DB + Redis Echo Example.

Pure utility functions for extracting data from webhooks:
- Media metadata extraction
- JSON content extraction for structured message types
- Contact data extraction
- Message kind determination

This module follows the Single Responsibility Principle -
it handles ONLY data extraction with no side effects.
"""

from __future__ import annotations

from wappa.webhooks import IncomingMessageWebhook


def extract_media_data(webhook: IncomingMessageWebhook) -> dict:
    """
    Extract media metadata from webhook for media messages.

    Args:
        webhook: Incoming message webhook

    Returns:
        Dictionary with media fields (mime, sha256, url, caption, etc.)
    """
    message = webhook.message
    media_data = {
        "media_mime": None,
        "media_sha256": None,
        "media_url": None,
        "media_caption": None,
        "media_description": None,
        "media_transcript": None,
    }

    # Check if this is a media message (has media_id property from BaseMediaMessage)
    if not hasattr(message, "media_id"):
        return media_data

    # Extract common media fields
    if hasattr(message, "media_type"):
        media_data["media_mime"] = str(message.media_type.value)
    if hasattr(message, "caption"):
        media_data["media_caption"] = message.caption

    # Extract SHA256 hash and URL based on message type
    message_type = webhook.get_message_type_name()

    if message_type == "image" and hasattr(message, "image"):
        if hasattr(message.image, "sha256"):
            media_data["media_sha256"] = message.image.sha256
        if hasattr(message.image, "url"):
            media_data["media_url"] = message.image.url

    elif message_type == "audio" and hasattr(message, "audio"):
        if hasattr(message.audio, "sha256"):
            media_data["media_sha256"] = message.audio.sha256
        if hasattr(message.audio, "url"):
            media_data["media_url"] = message.audio.url

    elif message_type == "video" and hasattr(message, "video"):
        if hasattr(message.video, "sha256"):
            media_data["media_sha256"] = message.video.sha256
        if hasattr(message.video, "url"):
            media_data["media_url"] = message.video.url

    elif message_type == "document" and hasattr(message, "document"):
        if hasattr(message.document, "sha256"):
            media_data["media_sha256"] = message.document.sha256
        if hasattr(message.document, "url"):
            media_data["media_url"] = message.document.url
        if hasattr(message.document, "filename"):
            media_data["media_description"] = message.document.filename

    # Fallback: If no URL was found, try get_download_info()
    if not media_data["media_url"] and hasattr(message, "get_download_info"):
        download_info = message.get_download_info()
        if "media_id" in download_info:
            media_data["media_url"] = f"whatsapp://media/{download_info['media_id']}"

    return media_data


def extract_json_content(webhook: IncomingMessageWebhook) -> dict | None:
    """
    Extract structured JSON content for special message types.

    Handles message types that have structured data beyond simple text/media:
    - Contact messages: Full contact data (name, phone, organization, etc.)
    - Location messages: Coordinates, location name, address, URL
    - Interactive messages: Button/list selection data
    - Reaction messages: Emoji and target message ID

    Args:
        webhook: Incoming message webhook

    Returns:
        Dictionary with structured data if applicable, None otherwise
    """
    message_type = webhook.get_message_type_name()
    message = webhook.message

    # Contact messages
    if message_type == "contact":
        return _extract_contact_json(message)

    # Location messages
    if message_type == "location":
        return _extract_location_json(message)

    # Interactive messages
    if message_type == "interactive":
        return _extract_interactive_json(webhook, message)

    # Reaction messages
    if message_type == "reaction":
        return _extract_reaction_json(message)

    # For other message types, no JSON content needed
    return None


def _extract_contact_json(message) -> dict:
    """Extract JSON content for contact messages."""
    json_content = {
        "message_type": "contact",
        "contact_name": None,
        "contact_phone": None,
        "contact_formatted_name": None,
        "contact_organization": None,
        "contacts": [],
    }

    if hasattr(message, "contact_name"):
        json_content["contact_name"] = message.contact_name
    if hasattr(message, "contact_phone"):
        json_content["contact_phone"] = message.contact_phone
    if hasattr(message, "formatted_name"):
        json_content["contact_formatted_name"] = message.formatted_name
    if hasattr(message, "organization"):
        json_content["contact_organization"] = message.organization
    if hasattr(message, "contact_data") and message.contact_data:
        json_content["contacts"] = message.contact_data

    return json_content


def _extract_location_json(message) -> dict:
    """Extract JSON content for location messages."""
    json_content = {
        "message_type": "location",
        "latitude": None,
        "longitude": None,
        "location_name": None,
        "location_address": None,
        "location_url": None,
    }

    if hasattr(message, "latitude"):
        json_content["latitude"] = message.latitude
    if hasattr(message, "longitude"):
        json_content["longitude"] = message.longitude
    if hasattr(message, "location_name"):
        json_content["location_name"] = message.location_name
    if hasattr(message, "address"):
        json_content["location_address"] = message.address
    if hasattr(message, "url"):
        json_content["location_url"] = message.url

    return json_content


def _extract_interactive_json(webhook: IncomingMessageWebhook, message) -> dict:
    """Extract JSON content for interactive messages."""
    json_content = {
        "message_type": "interactive",
        "interactive_type": None,
        "selected_id": None,
        "selected_title": None,
        "selected_description": None,
    }

    selected_value = webhook.get_interactive_selection()
    if selected_value:
        json_content["selected_id"] = selected_value

    if hasattr(message, "interactive_type"):
        json_content["interactive_type"] = message.interactive_type
    if hasattr(message, "title"):
        json_content["selected_title"] = message.title
    if hasattr(message, "description"):
        json_content["selected_description"] = message.description

    return json_content


def _extract_reaction_json(message) -> dict:
    """Extract JSON content for reaction messages."""
    json_content = {
        "message_type": "reaction",
        "emoji": None,
        "target_message_id": None,
    }

    if hasattr(message, "emoji"):
        json_content["emoji"] = message.emoji
    if hasattr(message, "message_id"):
        json_content["target_message_id"] = message.message_id

    return json_content


def extract_contact_data(webhook: IncomingMessageWebhook) -> dict:
    """
    Extract contact information from contact messages.

    Args:
        webhook: Incoming message webhook

    Returns:
        Dictionary with contact data (name, phone, etc.)
    """
    contact_data = {
        "name": None,
        "phone": None,
        "contacts": [],
    }

    message = webhook.message
    if not hasattr(message, "contact_name"):
        return contact_data

    # Get primary contact info
    if hasattr(message, "contact_name"):
        contact_data["name"] = message.contact_name
    if hasattr(message, "contact_phone"):
        contact_data["phone"] = message.contact_phone

    # Get full contact data if available
    if hasattr(message, "contact_data"):
        contact_data["contacts"] = message.contact_data

    return contact_data


def determine_message_kind(webhook: IncomingMessageWebhook) -> str:
    """
    Determine message kind from webhook.

    Args:
        webhook: Incoming message webhook

    Returns:
        Message type string
    """
    return webhook.get_message_type_name()


__all__ = [
    "determine_message_kind",
    "extract_contact_data",
    "extract_json_content",
    "extract_media_data",
]
