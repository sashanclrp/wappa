"""WhatsApp-only validators under ``/api/whatsapp/specialized``.

``POST /validate-contact`` and ``POST /validate-coordinates`` check a contact
card or a coordinate pair against WhatsApp's rules without calling Meta.
"""

import re

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, ValidationError

from wappa.core.logging.logger import get_logger
from wappa.domain.contacts import ContactCard
from wappa.messaging.whatsapp.models.specialized_models import (
    ContactValidationResult,
    LocationValidationResult,
)

logger = get_logger(__name__)

_EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

router = APIRouter(
    prefix="/specialized",
    tags=["WhatsApp - Validation"],
    responses={
        422: {"description": "Validation error"},
        500: {"description": "Internal server error"},
    },
)


class CoordinateValidationRequest(BaseModel):
    latitude: float = Field(..., description="Latitude to validate")
    longitude: float = Field(..., description="Longitude to validate")

    model_config = {"extra": "forbid"}


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
