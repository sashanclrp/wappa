"""
Custom validators for WhatsApp webhook schemas.

This module contains reusable validation functions and error handling
utilities for WhatsApp Business Platform data validation.
"""

import re
from typing import Any

from pydantic import ValidationError


class WhatsAppValidationError(Exception):
    """Custom exception for WhatsApp-specific validation errors."""

    def __init__(self, message: str, field: str | None = None, value: Any = None):
        self.message = message
        self.field = field
        self.value = value
        super().__init__(message)


class WhatsAppValidators:
    """Collection of validation utilities for WhatsApp data."""

    # WhatsApp phone number regex (international format)
    PHONE_REGEX = re.compile(r"^\+?[1-9]\d{1,14}$")

    # WhatsApp message ID regex
    MESSAGE_ID_REGEX = re.compile(r"^wamid\.[A-Za-z0-9+/=_-]+$")

    # Business account ID regex (numeric)
    BUSINESS_ID_REGEX = re.compile(r"^\d{10,}$")

    # SHA256 hash regex
    SHA256_REGEX = re.compile(r"^[a-fA-F0-9]{64}$")

    @classmethod
    def validate_phone_number(cls, phone: str, field_name: str = "phone") -> str:
        """
        Validate WhatsApp phone number format.

        Args:
            phone: Phone number to validate
            field_name: Field name for error messages

        Returns:
            Cleaned phone number

        Raises:
            WhatsAppValidationError: If phone number is invalid
        """
        if not phone:
            raise WhatsAppValidationError(
                f"{field_name} cannot be empty", field_name, phone
            )

        # Remove common formatting
        cleaned = (
            phone.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
        )

        # Check minimum length
        if len(cleaned) < 8:
            raise WhatsAppValidationError(
                f"{field_name} must be at least 8 characters", field_name, phone
            )

        # Check maximum length (international format allows up to 15 digits)
        if len(cleaned.replace("+", "")) > 15:
            raise WhatsAppValidationError(
                f"{field_name} cannot exceed 15 digits", field_name, phone
            )

        # Basic format validation - should be mostly numeric
        if not cls.PHONE_REGEX.match(cleaned):
            raise WhatsAppValidationError(
                f"{field_name} must be in valid international format", field_name, phone
            )

        return cleaned

    @classmethod
    def validate_message_id(
        cls, message_id: str, field_name: str = "message_id"
    ) -> str:
        """
        Validate WhatsApp message ID format.

        Args:
            message_id: Message ID to validate
            field_name: Field name for error messages

        Returns:
            Validated message ID

        Raises:
            WhatsAppValidationError: If message ID is invalid
        """
        if not message_id:
            raise WhatsAppValidationError(
                f"{field_name} cannot be empty", field_name, message_id
            )

        if len(message_id) < 10:
            raise WhatsAppValidationError(
                f"{field_name} must be at least 10 characters", field_name, message_id
            )

        if not message_id.startswith("wamid."):
            raise WhatsAppValidationError(
                f"{field_name} must start with 'wamid.'", field_name, message_id
            )

        if not cls.MESSAGE_ID_REGEX.match(message_id):
            raise WhatsAppValidationError(
                f"{field_name} contains invalid characters", field_name, message_id
            )

        return message_id

    @classmethod
    def validate_business_account_id(
        cls, business_id: str, field_name: str = "business_id"
    ) -> str:
        """
        Validate WhatsApp Business Account ID format.

        Args:
            business_id: Business account ID to validate
            field_name: Field name for error messages

        Returns:
            Validated business account ID

        Raises:
            WhatsAppValidationError: If business ID is invalid
        """
        if not business_id:
            raise WhatsAppValidationError(
                f"{field_name} cannot be empty", field_name, business_id
            )

        if not business_id.isdigit():
            raise WhatsAppValidationError(
                f"{field_name} must be numeric", field_name, business_id
            )

        if len(business_id) < 10:
            raise WhatsAppValidationError(
                f"{field_name} must be at least 10 digits", field_name, business_id
            )

        return business_id

    @classmethod
    def validate_timestamp(cls, timestamp: str, field_name: str = "timestamp") -> str:
        """
        Validate Unix timestamp format.

        Args:
            timestamp: Timestamp to validate
            field_name: Field name for error messages

        Returns:
            Validated timestamp

        Raises:
            WhatsAppValidationError: If timestamp is invalid
        """
        if not timestamp:
            raise WhatsAppValidationError(
                f"{field_name} cannot be empty", field_name, timestamp
            )

        if not timestamp.isdigit():
            raise WhatsAppValidationError(
                f"{field_name} must be numeric", field_name, timestamp
            )

        # Check reasonable timestamp range (after 2020, before 2100)
        timestamp_int = int(timestamp)
        if timestamp_int < 1577836800:  # 2020-01-01
            raise WhatsAppValidationError(
                f"{field_name} is too old (must be after 2020)", field_name, timestamp
            )

        if timestamp_int > 4102444800:  # 2100-01-01
            raise WhatsAppValidationError(
                f"{field_name} is too far in the future (must be before 2100)",
                field_name,
                timestamp,
            )

        return timestamp

    @classmethod
    def validate_sha256_hash(cls, hash_value: str, field_name: str = "hash") -> str:
        """
        Validate SHA256 hash format.

        Args:
            hash_value: Hash to validate
            field_name: Field name for error messages

        Returns:
            Validated hash (lowercase)

        Raises:
            WhatsAppValidationError: If hash is invalid
        """
        if not hash_value:
            raise WhatsAppValidationError(
                f"{field_name} cannot be empty", field_name, hash_value
            )

        if len(hash_value) != 64:
            raise WhatsAppValidationError(
                f"{field_name} must be exactly 64 characters", field_name, hash_value
            )

        if not cls.SHA256_REGEX.match(hash_value):
            raise WhatsAppValidationError(
                f"{field_name} must contain only hexadecimal characters",
                field_name,
                hash_value,
            )

        return hash_value.lower()

    @classmethod
    def validate_mime_type(
        cls, mime_type: str, allowed_types: list[str], field_name: str = "mime_type"
    ) -> str:
        """
        Validate MIME type against allowed types.

        Args:
            mime_type: MIME type to validate
            allowed_types: List of allowed MIME types
            field_name: Field name for error messages

        Returns:
            Validated MIME type (lowercase)

        Raises:
            WhatsAppValidationError: If MIME type is invalid
        """
        if not mime_type:
            raise WhatsAppValidationError(
                f"{field_name} cannot be empty", field_name, mime_type
            )

        mime_lower = mime_type.lower().strip()
        if mime_lower not in [t.lower() for t in allowed_types]:
            raise WhatsAppValidationError(
                f"{field_name} must be one of {allowed_types}, got: {mime_type}",
                field_name,
                mime_type,
            )

        return mime_lower

    @classmethod
    def validate_text_length(
        cls,
        text: str,
        max_length: int,
        field_name: str = "text",
        allow_empty: bool = False,
    ) -> str:
        """
        Validate text length constraints.

        Args:
            text: Text to validate
            max_length: Maximum allowed length
            field_name: Field name for error messages
            allow_empty: Whether empty text is allowed

        Returns:
            Stripped text

        Raises:
            WhatsAppValidationError: If text length is invalid
        """
        if text is None:
            if allow_empty:
                return ""
            raise WhatsAppValidationError(
                f"{field_name} cannot be None", field_name, text
            )

        stripped = text.strip()

        if not stripped and not allow_empty:
            raise WhatsAppValidationError(
                f"{field_name} cannot be empty", field_name, text
            )

        if len(stripped) > max_length:
            raise WhatsAppValidationError(
                f"{field_name} cannot exceed {max_length} characters (got {len(stripped)})",
                field_name,
                text,
            )

        return stripped

    @classmethod
    def validate_url(
        cls, url: str, field_name: str = "url", allow_none: bool = False
    ) -> str | None:
        """
        Validate URL format.

        Args:
            url: URL to validate
            field_name: Field name for error messages
            allow_none: Whether None values are allowed

        Returns:
            Validated URL or None

        Raises:
            WhatsAppValidationError: If URL is invalid
        """
        if url is None:
            if allow_none:
                return None
            raise WhatsAppValidationError(
                f"{field_name} cannot be None", field_name, url
            )

        if not url.strip():
            if allow_none:
                return None
            raise WhatsAppValidationError(
                f"{field_name} cannot be empty", field_name, url
            )

        url = url.strip()
        if not (url.startswith("http://") or url.startswith("https://")):
            raise WhatsAppValidationError(
                f"{field_name} must start with http:// or https://", field_name, url
            )

        # Basic URL validation - check for obvious issues
        if " " in url:
            raise WhatsAppValidationError(
                f"{field_name} cannot contain spaces", field_name, url
            )

        return url


class WhatsAppErrorHandler:
    """Utility class for handling WhatsApp validation and processing errors."""

    @staticmethod
    def format_validation_error(error: ValidationError) -> dict[str, Any]:
        """
        Format Pydantic ValidationError for API responses.

        Args:
            error: Pydantic ValidationError

        Returns:
            Formatted error dictionary
        """
        errors = []
        for err in error.errors():
            errors.append(
                {
                    "field": ".".join(str(loc) for loc in err["loc"]),
                    "message": err["msg"],
                    "type": err["type"],
                    "input": err.get("input", None),
                }
            )

        return {
            "error": "validation_failed",
            "message": "WhatsApp webhook validation failed",
            "details": errors,
            "error_count": len(errors),
        }

    @staticmethod
    def format_whatsapp_error(error: WhatsAppValidationError) -> dict[str, Any]:
        """
        Format WhatsAppValidationError for API responses.

        Args:
            error: WhatsAppValidationError

        Returns:
            Formatted error dictionary
        """
        return {
            "error": "whatsapp_validation_failed",
            "message": error.message,
            "field": error.field,
            "value": error.value,
        }

    @staticmethod
    def is_recoverable_error(error: Exception) -> bool:
        """
        Determine if an error is recoverable and the request should be retried.

        Args:
            error: Exception to check

        Returns:
            True if error is recoverable, False otherwise
        """
        # Validation errors are not recoverable
        if isinstance(error, ValidationError | WhatsAppValidationError):
            return False

        # Network/timeout errors might be recoverable
        if isinstance(error, ConnectionError | TimeoutError):
            return True

        # Generic exceptions might be recoverable
        return True

    @staticmethod
    def get_error_priority(error: Exception) -> str:
        """
        Get the priority level for an error for logging and alerting.

        Args:
            error: Exception to evaluate

        Returns:
            Priority level: 'low', 'medium', 'high', 'critical'
        """
        if isinstance(error, ValidationError):
            # Validation errors are medium priority - indicate data issues
            return "medium"

        if isinstance(error, WhatsAppValidationError):
            # WhatsApp-specific validation errors are medium priority
            return "medium"

        if isinstance(error, ConnectionError | TimeoutError):
            # Network issues are high priority - service availability
            return "high"

        # Unknown errors are critical priority
        return "critical"
