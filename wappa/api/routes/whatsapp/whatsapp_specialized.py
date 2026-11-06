import re

from fastapi import Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, ValidationError

from wappa.api.dependencies.event_dependencies import get_api_event_dispatcher
from wappa.api.dependencies.inbox_context import get_inbox_messenger
from wappa.api.routes.whatsapp.route_families import RouteFamily
from wappa.api.utils import direct_target, dispatch_message_event, map_send_errors
from wappa.core.events.api_event_dispatcher import APIEventDispatcher
from wappa.core.logging.logger import get_logger
from wappa.domain.contacts import ContactCard
from wappa.domain.interfaces.messaging_interface import IMessenger
from wappa.domain.results import MessageResult
from wappa.messaging.whatsapp.models.specialized_models import (
    ContactMessage,
    ContactValidationResult,
    LocationMessage,
    LocationRequestMessage,
    LocationValidationResult,
)

logger = get_logger(__name__)

_EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


# Contact/location sends are omissible outbound mutations; the validation
# endpoints touch no platform and stay mounted.
_family = RouteFamily(
    prefix="/specialized",
    tags=["WhatsApp - Specialized"],
    responses={
        400: {"description": "Invalid request parameters"},
        401: {"description": "Authentication failed"},
        422: {"description": "Validation error"},
        500: {"description": "Internal server error"},
    },
)
send_router = _family.router()
router = _family.router()


# Request Models
#
# Each extends the canonical outbound schema rather than restating its fields:
# the HTTP boundary only adds `extra="forbid"` and, for location, wider
# free-text limits. Sharing the schema is also what lets the outbound
# classifier name these sends without this module telling it anything.
class ContactRequest(ContactMessage):
    model_config = {"extra": "forbid"}


class LocationRequest(LocationMessage):
    name: str | None = Field(
        None, max_length=1024, description="Optional location name"
    )
    address: str | None = Field(
        None, max_length=1024, description="Optional street address"
    )

    model_config = {"extra": "forbid"}


class LocationRequestRequest(LocationRequestMessage):
    model_config = {"extra": "forbid"}


class CoordinateValidationRequest(BaseModel):
    latitude: float = Field(..., description="Latitude to validate")
    longitude: float = Field(..., description="Longitude to validate")

    model_config = {"extra": "forbid"}


# API Endpoints


@send_router.post("/send-contact", response_model=MessageResult)
@map_send_errors("send contact card")
@dispatch_message_event()
async def send_contact_card(
    request: ContactRequest,
    fastapi_request: Request,
    messenger: IMessenger = Depends(get_inbox_messenger),
    api_dispatcher: APIEventDispatcher | None = Depends(get_api_event_dispatcher),
) -> MessageResult:
    return await messenger.send_contact(
        contacts=request.contacts,
        target=direct_target(messenger, request),
        reply_to_message_id=request.reply_to_message_id,
    )


@send_router.post("/send-location", response_model=MessageResult)
@map_send_errors("send location")
@dispatch_message_event()
async def send_location_message(
    request: LocationRequest,
    fastapi_request: Request,
    messenger: IMessenger = Depends(get_inbox_messenger),
    api_dispatcher: APIEventDispatcher | None = Depends(get_api_event_dispatcher),
) -> MessageResult:
    return await messenger.send_location(
        latitude=request.latitude,
        longitude=request.longitude,
        target=direct_target(messenger, request),
        name=request.name,
        address=request.address,
        reply_to_message_id=request.reply_to_message_id,
    )


@send_router.post("/send-location-request", response_model=MessageResult)
@map_send_errors("send location request")
@dispatch_message_event()
async def send_location_request_message(
    request: LocationRequestRequest,
    fastapi_request: Request,
    messenger: IMessenger = Depends(get_inbox_messenger),
    api_dispatcher: APIEventDispatcher | None = Depends(get_api_event_dispatcher),
) -> MessageResult:
    return await messenger.send_location_request(
        body=request.body,
        target=direct_target(messenger, request),
        reply_to_message_id=request.reply_to_message_id,
    )


@router.post("/validate-contact", response_model=ContactValidationResult)
async def validate_contact_data(contact: ContactCard) -> ContactValidationResult:
    try:
        logger.info("Validating contact card data")

        validation_issues: list[str] = []

        for phone in contact.phones or []:
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
            valid=is_valid,
            errors=validation_issues or None,
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
            detail=f"Unexpected {type(e).__name__} in specialized message handler: {e}",
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
            valid=is_valid,
            latitude=request.latitude,
            longitude=request.longitude,
            errors=validation_issues or None,
            address_suggestions=[region],
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
            detail=f"Unexpected {type(e).__name__} in specialized message handler: {e}",
        ) from e
