import re

from fastapi import APIRouter, Depends, HTTPException, Request, status
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
from wappa.schemas.core.recipient import RecipientRequest

logger = get_logger(__name__)

_EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


def _raise_for_whatsapp_error(result, operation_name: str) -> None:
    if result.success:
        return

    error_str = str(result.error or "")
    status_code = map_whatsapp_api_error_to_status(error_str)
    raise HTTPException(
        status_code=status_code, detail=f"{operation_name}: {result.error}"
    )


router = APIRouter(
    prefix="/specialized",
    tags=["WhatsApp - Specialized"],
    responses={
        400: {"description": "Invalid request parameters"},
        401: {"description": "Authentication failed"},
        422: {"description": "Validation error"},
        500: {"description": "Internal server error"},
    },
)


# Request Models
class ContactRequest(RecipientRequest):
    contact: ContactCard = Field(..., description="Contact information to share")
    reply_to_message_id: str | None = Field(
        None, description="Optional message ID to reply to"
    )

    model_config = {"extra": "forbid"}


class LocationRequest(RecipientRequest):
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


class LocationRequestRequest(RecipientRequest):
    body: str = Field(
        ..., min_length=1, max_length=1024, description="Request message text"
    )
    reply_to_message_id: str | None = Field(
        None, description="Optional message ID to reply to"
    )

    model_config = {"extra": "forbid"}


class CoordinateValidationRequest(BaseModel):
    latitude: float = Field(..., description="Latitude to validate")
    longitude: float = Field(..., description="Longitude to validate")

    model_config = {"extra": "forbid"}


# API Endpoints


@router.post("/send-contact", response_model=MessageResult)
@dispatch_message_event("contact", platform="whatsapp")
async def send_contact_card(
    request: ContactRequest,
    fastapi_request: Request,
    messenger: IMessenger = Depends(get_whatsapp_messenger),
    api_dispatcher: APIEventDispatcher | None = Depends(get_api_event_dispatcher),
) -> MessageResult:
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
@dispatch_message_event("location", platform="whatsapp")
async def send_location_message(
    request: LocationRequest,
    fastapi_request: Request,
    messenger: IMessenger = Depends(get_whatsapp_messenger),
    api_dispatcher: APIEventDispatcher | None = Depends(get_api_event_dispatcher),
) -> MessageResult:
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
@dispatch_message_event("location_request", platform="whatsapp")
async def send_location_request_message(
    request: LocationRequestRequest,
    fastapi_request: Request,
    messenger: IMessenger = Depends(get_whatsapp_messenger),
    api_dispatcher: APIEventDispatcher | None = Depends(get_api_event_dispatcher),
) -> MessageResult:
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
    try:
        logger.info("Validating contact card data")

        validation_issues: list[str] = []

        for phone in contact.phones:
            if not phone.phone.startswith("+"):
                validation_issues.append(
                    f"Phone number should start with country code: {phone.phone}"
                )

        if contact.emails:
            for email in contact.emails:
                if not _EMAIL_PATTERN.match(email.email):
                    validation_issues.append(f"Invalid email format: {email.email}")

        is_valid = not validation_issues

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
    try:
        logger.info(
            f"Validating coordinates: ({request.latitude}, {request.longitude})"
        )

        validation_issues: list[str] = []

        if not (-90 <= request.latitude <= 90):
            validation_issues.append(
                f"Latitude must be between -90 and 90 degrees: {request.latitude}"
            )

        if not (-180 <= request.longitude <= 180):
            validation_issues.append(
                f"Longitude must be between -180 and 180 degrees: {request.longitude}"
            )

        if request.latitude == 0 and request.longitude == 0:
            validation_issues.append(
                "Coordinates (0,0) point to Null Island - verify if intentional"
            )

        is_valid = not validation_issues

        region = "Unknown"
        if -90 <= request.latitude <= 90 and -180 <= request.longitude <= 180:
            region = (
                "Northern Hemisphere"
                if request.latitude >= 0
                else "Southern Hemisphere"
            )

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
