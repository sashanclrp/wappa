from __future__ import annotations

import json
import logging
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger("RedisSerde")


def _convert_bools_to_redis(obj: Any) -> Any:
    """Recursively convert boolean values to Redis-optimized "1"/"0" strings"""
    if isinstance(obj, bool):
        return "1" if obj else "0"
    elif isinstance(obj, dict):
        return {k: _convert_bools_to_redis(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_convert_bools_to_redis(item) for item in obj]
    else:
        return obj


def _convert_redis_to_bools(obj: Any) -> Any:
    """Recursively convert Redis "1"/"0" strings back to boolean values"""
    if obj == "1":
        return True
    elif obj == "0":
        return False
    elif isinstance(obj, dict):
        return {k: _convert_redis_to_bools(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_convert_redis_to_bools(item) for item in obj]
    else:
        return obj


def _datetime_handler(obj: Any) -> str:
    """Handle datetime objects during JSON serialization"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def _convert_iso_strings_to_datetime(obj: Any) -> Any:
    """Recursively convert ISO datetime strings back to datetime objects"""
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


def dumps(obj: Any) -> str:
    """Serialize Python object to Redis-compatible string"""
    if obj is None:
        return "null"
    if isinstance(obj, bool):
        return str(int(obj))
    if isinstance(obj, int | float):
        return str(obj)
    if isinstance(obj, str):
        return obj
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, Enum):
        return str(obj.value)
    if isinstance(obj, BaseModel):
        # Convert to dict first, then convert bools to "1"/"0", then to JSON
        model_dict = obj.model_dump()
        redis_dict = _convert_bools_to_redis(model_dict)
        return json.dumps(redis_dict, ensure_ascii=False, default=_datetime_handler)
    try:
        return json.dumps(obj, ensure_ascii=False, default=_datetime_handler)
    except TypeError as e:
        logger.warning(
            f"Could not JSON serialize value of type {type(obj)}. Falling back to str(). Error: {e}. Value: {obj!r}"
        )
        return str(obj)


def loads(raw: str | None, model: type[BaseModel] | None = None) -> Any:
    """Deserialize Redis string back to Python object"""
    if raw in (None, "null"):
        return None
    if raw == "1":
        return True
    if raw == "0":
        return False
    try:
        data = json.loads(raw)
        if model is not None:
            # Convert Redis "1"/"0" back to bools and handle datetime strings
            bool_converted_data = _convert_redis_to_bools(data)
            datetime_converted_data = _convert_iso_strings_to_datetime(
                bool_converted_data
            )
            return model.model_validate(datetime_converted_data)
        return data
    except (json.JSONDecodeError, TypeError):
        return raw


def dumps_hash(data: dict[str, Any] | BaseModel) -> dict[str, str]:
    """Serialize dictionary or BaseModel values for Redis hash storage"""
    if isinstance(data, BaseModel):
        # Convert BaseModel to dict first
        data = data.model_dump()
    return {field: dumps(value) for field, value in data.items()}


def loads_hash(
    raw_data: dict[str, str] | None, models: type[BaseModel] | None = None
) -> dict[str, Any] | BaseModel:
    """
    Deserialize Redis hash back to Python dictionary or BaseModel

    Args:
        raw_data: Raw string data from Redis hash
        models: Optional BaseModel class for full object reconstruction
                e.g., User (will automatically handle nested UserContact, UserLocation)
    """
    if not raw_data:
        return {}

    # Deserialize all fields normally (no model-specific deserialization)
    data = {field: loads(value_str) for field, value_str in raw_data.items()}

    if models:
        # Let Pydantic handle nested model reconstruction with preprocessing
        # The model_validate will automatically call @model_validator(mode="before") methods
        return models.model_validate(data)
    else:
        return data
