"""
WhatsApp Specialized Messaging API Routes.

Provides REST API endpoints for specialized WhatsApp messaging operations:
- Contact card sharing with comprehensive contact information
- Location sharing with coordinates, names, and addresses
- Location request messages with interactive prompts

Follows SOLID principles with proper error handling and Pydantic v2 validation.
Based on WhatsApp Cloud API 2025 specifications for specialized messaging.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, ValidationError

from wappa.api.dependencies.event_dependencies import get_api_event_dispatcher
from wappa.api.dependencies.whatsapp_dependencies import get_whatsapp_messenger
from wappa.api.utils import dispatch_message_event, map_whatsapp_api_error_to_status
from wappa.core.events.api_event_dispatcher import APIEventDispatcher
from wappa.core.logging.logger import get_logger
from wappa.domain.interfaces.messaging_interface import IMessenger
from wappa.messaging.whatsapp.models.basic_models import MessageResult
from wappa.messaging.whatsapp.models.specialized_models import (
    ContactCard,
    ContactValidationResult,
    LocationValidationResult,
)

logger = get_logger(__name__)


def _raise_for_whatsapp_error(result, operation_name: str) -> None:
    """Raise HTTPException based on WhatsApp API error message patterns.

    Centralizes the repeated error mapping logic for specialized routes.

    Args:
        result: Messaging operation result
        operation_name: Human-readable operation name for error messages

    Raises:
        HTTPException: With appropriate status code based on error pattern
    """
    if result.success:
        return

    error_str = str(result.error or "")
    status_code = map_whatsapp_api_error_to_status(error_str)
    raise HTTPException(
        status_code=status_code, detail=f"{operation_name}: {result.error}"
    )


router = APIRouter(
    prefix="/specialized",
    tags=["whatsapp - Specialized"],
    responses={
        400: {"description": "Invalid request parameters"},
        401: {"description": "Authentication failed"},
        422: {"description": "Validation error"},
        500: {"description": "Internal server error"},
    },
)


# Request Models
class ContactRequest(BaseModel):
    """Request model for sending contact card messages."""

    recipient: str = Field(..., description="Recipient phone number")
    contact: ContactCard = Field(..., description="Contact information to share")
    reply_to_message_id: str | None = Field(
        None, description="Optional message ID to reply to"
    )

    model_config = {"extra": "forbid"}


class LocationRequest(BaseModel):
    """Request model for sending location messages."""

    recipient: str = Field(..., description="Recipient phone number")
    latitude: float = Field(
        ..., ge=-90, le=90, description="Location latitude in decimal degrees"
    )
    longitude: float = Field(
        ..., ge=-180, le=180, description="Location longitude in decimal degrees"
    )
    name: str | None = Field(
        None, max_length=1024, description="Optional location name"
    )
    address: str | None = Field(
        None, max_length=1024, description="Optional street address"
    )
    reply_to_message_id: str | None = Field(
        None, description="Optional message ID to reply to"
    )

    model_config = {"extra": "forbid"}


class LocationRequestRequest(BaseModel):
    """Request model for sending location request messages."""

    recipient: str = Field(..., description="Recipient phone number")
    body: str = Field(
        ..., min_length=1, max_length=1024, description="Request message text"
    )
    reply_to_message_id: str | None = Field(
        None, description="Optional message ID to reply to"
    )

    model_config = {"extra": "forbid"}


class CoordinateValidationRequest(BaseModel):
    """Request model for coordinate validation."""

    latitude: float = Field(..., description="Latitude to validate")
    longitude: float = Field(..., description="Longitude to validate")

    model_config = {"extra": "forbid"}


# API Endpoints


@router.post("/send-contact", response_model=MessageResult)
@dispatch_message_event("contact")
async def send_contact_card(
    request: ContactRequest,
    messenger: IMessenger = Depends(get_whatsapp_messenger),
    api_dispatcher: APIEventDispatcher | None = Depends(get_api_event_dispatcher),
) -> MessageResult:
    """
    Send contact card message using WhatsApp API.

    Shares contact information including name, phone numbers, emails, and addresses.
    Contact cards are automatically added to the recipient's address book.

    Args:
        request: Contact card request with recipient and contact information
        messenger: Injected WhatsApp messenger implementation
        api_dispatcher: API event dispatcher for tracking (injected)

    Returns:
        MessageResult with operation status and metadata

    Raises:
        HTTPException: For validation errors, authentication failures, or API errors
    """
    try:
        logger.info(f"Sending contact card to {request.recipient}")

        result = await messenger.send_contact(
            contact=request.contact.model_dump(),
            recipient=request.recipient,
            reply_to_message_id=request.reply_to_message_id,
        )

        _raise_for_whatsapp_error(result, "Failed to send contact card")

        logger.info(
            f"Contact card sent successfully to {request.recipient}, message_id: {result.message_id}"
        )
        return result

    except ValidationError as e:
        logger.error(f"Contact validation error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Contact validation failed: {str(e)}",
        ) from e
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error sending contact card: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}",
        ) from e


@router.post("/send-location", response_model=MessageResult)
@dispatch_message_event("location")
async def send_location_message(
    request: LocationRequest,
    messenger: IMessenger = Depends(get_whatsapp_messenger),
    api_dispatcher: APIEventDispatcher | None = Depends(get_api_event_dispatcher),
) -> MessageResult:
    """
    Send location message using WhatsApp API.

    Shares geographic coordinates with optional location name and address.
    Recipients see a map preview with the shared location.

    Args:
        request: Location request with coordinates and optional details
        messenger: Injected WhatsApp messenger implementation
        api_dispatcher: API event dispatcher for tracking (injected)

    Returns:
        MessageResult with operation status and metadata

    Raises:
        HTTPException: For validation errors, authentication failures, or API errors
    """
    try:
        logger.info(
            f"Sending location to {request.recipient}: ({request.latitude}, {request.longitude})"
        )

        result = await messenger.send_location(
            latitude=request.latitude,
            longitude=request.longitude,
            recipient=request.recipient,
            name=request.name,
            address=request.address,
            reply_to_message_id=request.reply_to_message_id,
        )

        _raise_for_whatsapp_error(result, "Failed to send location")

        logger.info(
            f"Location sent successfully to {request.recipient}, message_id: {result.message_id}"
        )
        return result

    except ValidationError as e:
        logger.error(f"Location validation error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Location validation failed: {str(e)}",
        ) from e
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error sending location: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}",
        ) from e


@router.post("/send-location-request", response_model=MessageResult)
@dispatch_message_event("location_request")
async def send_location_request_message(
    request: LocationRequestRequest,
    messenger: IMessenger = Depends(get_whatsapp_messenger),
    api_dispatcher: APIEventDispatcher | None = Depends(get_api_event_dispatcher),
) -> MessageResult:
    """
    Send location request message using WhatsApp API.

    Sends an interactive message that prompts the recipient to share their location.
    Recipients see a "Send Location" button that allows easy location sharing.

    Args:
        request: Location request with message text
        messenger: Injected WhatsApp messenger implementation
        api_dispatcher: API event dispatcher for tracking (injected)

    Returns:
        MessageResult with operation status and metadata

    Raises:
        HTTPException: For validation errors, authentication failures, or API errors
    """
    try:
        logger.info(f"Sending location request to {request.recipient}")

        result = await messenger.send_location_request(
            body=request.body,
            recipient=request.recipient,
            reply_to_message_id=request.reply_to_message_id,
        )

        _raise_for_whatsapp_error(result, "Failed to send location request")

        logger.info(
            f"Location request sent successfully to {request.recipient}, message_id: {result.message_id}"
        )
        return result

    except ValidationError as e:
        logger.error(f"Location request validation error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Location request validation failed: {str(e)}",
        ) from e
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error sending location request: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}",
        ) from e


@router.post("/validate-contact", response_model=ContactValidationResult)
async def validate_contact_data(contact: ContactCard) -> ContactValidationResult:
    """
    Validate contact card data without sending a message.

    Provides validation utilities for contact information to ensure compatibility
    with WhatsApp Business API requirements before sending.

    Args:
        contact: Contact card data to validate

    Returns:
        ContactValidationResult with validation status and details

    Raises:
        HTTPException: For validation errors or processing failures
    """
    try:
        logger.info("Validating contact card data")

        # Pydantic v2 validation happens automatically on model instantiation
        # Additional business logic validation can be added here

        validation_issues = []

        # Validate phone numbers format (basic validation)
        for phone in contact.phones:
            if not phone.phone.startswith("+"):
                validation_issues.append(
                    f"Phone number should start with country code: {phone.phone}"
                )

        # Validate email format if provided
        if contact.emails:
            import re

            email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
            for email in contact.emails:
                if not re.match(email_pattern, email.email):
                    validation_issues.append(f"Invalid email format: {email.email}")

        is_valid = len(validation_issues) == 0

        result = ContactValidationResult(
            is_valid=is_valid,
            validation_errors=validation_issues if validation_issues else None,
            contact_summary=f"{contact.name.formatted_name} with {len(contact.phones)} phone(s)",
        )

        logger.info(
            f"Contact validation completed: {'valid' if is_valid else 'invalid'}"
        )
        return result

    except ValidationError as e:
        logger.error(f"Contact validation error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Contact validation failed: {str(e)}",
        ) from e
    except Exception as e:
        logger.error(f"Unexpected error validating contact: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}",
        ) from e


@router.post("/validate-coordinates", response_model=LocationValidationResult)
async def validate_coordinates(
    request: CoordinateValidationRequest,
) -> LocationValidationResult:
    """
    Validate geographic coordinates without sending a message.

    Provides validation utilities for latitude and longitude coordinates to ensure
    they fall within valid ranges for location sharing.

    Args:
        request: Coordinates to validate

    Returns:
        LocationValidationResult with validation status and details

    Raises:
        HTTPException: For validation errors or processing failures
    """
    try:
        logger.info(
            f"Validating coordinates: ({request.latitude}, {request.longitude})"
        )

        validation_issues = []

        # Validate latitude range
        if not (-90 <= request.latitude <= 90):
            validation_issues.append(
                f"Latitude must be between -90 and 90 degrees: {request.latitude}"
            )

        # Validate longitude range
        if not (-180 <= request.longitude <= 180):
            validation_issues.append(
                f"Longitude must be between -180 and 180 degrees: {request.longitude}"
            )

        # Check for null island (0,0) which might be unintentional
        if request.latitude == 0 and request.longitude == 0:
            validation_issues.append(
                "Coordinates (0,0) point to Null Island - verify if intentional"
            )

        is_valid = len(validation_issues) == 0

        # Determine location region for additional context
        region = "Unknown"
        if -90 <= request.latitude <= 90 and -180 <= request.longitude <= 180:
            if request.latitude >= 0:
                region = "Northern Hemisphere"
            else:
                region = "Southern Hemisphere"

        result = LocationValidationResult(
            is_valid=is_valid,
            validation_errors=validation_issues if validation_issues else None,
            coordinates_summary=f"({request.latitude}, {request.longitude}) - {region}",
        )

        logger.info(
            f"Coordinate validation completed: {'valid' if is_valid else 'invalid'}"
        )
        return result

    except ValidationError as e:
        logger.error(f"Coordinate validation error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Coordinate validation failed: {str(e)}",
        ) from e
    except Exception as e:
        logger.error(f"Unexpected error validating coordinates: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}",
        ) from e
