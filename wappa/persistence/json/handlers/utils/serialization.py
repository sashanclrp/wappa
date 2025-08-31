"""
JSON serialization utilities with BaseModel support.

Provides JSON-based serialization compatible with Redis patterns
while optimizing for file storage.
"""

import json
import logging
from datetime import datetime
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger("JSONSerde")


def _datetime_handler(obj: Any) -> str:
    """Handle datetime objects during JSON serialization."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def _convert_iso_strings_to_datetime(obj: Any) -> Any:
    """Recursively convert ISO datetime strings back to datetime objects."""
    if isinstance(obj, str):
        # Try to parse as ISO datetime
        try:
            # Check if it looks like an ISO datetime (basic heuristic)
            if "T" in obj and len(obj) >= 19:  # YYYY-MM-DDTHH:MM:SS minimum
                return datetime.fromisoformat(obj.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            pass
        return obj
    elif isinstance(obj, dict):
        return {k: _convert_iso_strings_to_datetime(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_convert_iso_strings_to_datetime(item) for item in obj]
    else:
        return obj


def serialize_for_json(obj: Any) -> Any:
    """Serialize Python object for JSON storage."""
    if obj is None:
        return None
    if isinstance(obj, BaseModel):
        return obj.model_dump()
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: serialize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [serialize_for_json(item) for item in obj]
    return obj


def deserialize_from_json(data: Any, model: type[BaseModel] | None = None) -> Any:
    """Deserialize data from JSON storage."""
    if data is None:
        return None

    # Convert datetime strings back to datetime objects
    data = _convert_iso_strings_to_datetime(data)

    if model is not None:
        return model.model_validate(data)

    return data


def create_cache_file_data(
    data: dict[str, Any], ttl: int | None = None
) -> dict[str, Any]:
    """Create JSON cache file structure with metadata."""
    now = datetime.now()
    expires_at = None
    if ttl:
        expires_at = datetime.fromtimestamp(now.timestamp() + ttl)

    return {
        "_metadata": {
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat() if expires_at else None,
            "version": "1.0",
        },
        "data": serialize_for_json(data),
    }


def extract_cache_file_data(file_data: dict[str, Any]) -> dict[str, Any] | None:
    """Extract data from JSON cache file, checking expiration."""
    if not isinstance(file_data, dict):
        return None

    metadata = file_data.get("_metadata", {})
    expires_at_str = metadata.get("expires_at")

    # Check expiration
    if expires_at_str:
        try:
            expires_at = datetime.fromisoformat(expires_at_str)
            if datetime.now() > expires_at:
                return None  # Expired
        except ValueError:
            logger.warning(f"Invalid expires_at format: {expires_at_str}")

    return file_data.get("data", {})


def to_json_string(data: Any) -> str:
    """Convert data to JSON string."""
    return json.dumps(data, ensure_ascii=False, indent=2, default=_datetime_handler)


def from_json_string(json_str: str) -> Any:
    """Convert JSON string to data."""
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON: {e}")
        raise
