"""Shared contact and location send routes under ``/api/{platform}/specialized``.

- ``POST /send-contact``: one or more contact cards
- ``POST /send-location``: a location pin
- ``POST /send-location-request``: ask the User to share a location
- ``POST /send-contact-request``: ask the User to share a phone number

The two requests gate on the Inbox's ``IUserDataRequests`` capability
(WhatsApp today); another Platform answers 501.
"""

from fastapi import Depends, Request
from pydantic import Field

from wappa.api.dependencies.event_dependencies import get_api_event_dispatcher
from wappa.api.dependencies.inbox_context import (
    get_inbox_messenger,
    requires_capability,
)
from wappa.api.routes.families import RouteFamily
from wappa.api.utils import direct_target, dispatch_message_event, map_send_errors
from wappa.core.events.api_event_dispatcher import APIEventDispatcher
from wappa.domain.interfaces.messaging_interface import IMessenger
from wappa.domain.interfaces.user_data_requests import IUserDataRequests
from wappa.domain.results import MessageResult
from wappa.schemas.requests.specialized_models import (
    ContactMessage,
    ContactRequestMessage,
    LocationMessage,
    LocationRequestMessage,
)

_family = RouteFamily(
    prefix="/specialized",
    tags=["Specialized"],
    responses={
        400: {"description": "Invalid request parameters"},
        401: {"description": "Authentication failed"},
        422: {"description": "Validation error"},
        500: {"description": "Internal server error"},
    },
)
send_router = _family.router()


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


class ContactRequestRequest(ContactRequestMessage):
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
    requests: IUserDataRequests = Depends(requires_capability(IUserDataRequests)),
    api_dispatcher: APIEventDispatcher | None = Depends(get_api_event_dispatcher),
) -> MessageResult:
    return await requests.send_location_request(
        body=request.body,
        target=direct_target(messenger, request),
        reply_to_message_id=request.reply_to_message_id,
    )


@send_router.post("/send-contact-request", response_model=MessageResult)
@map_send_errors("send contact request")
@dispatch_message_event()
async def send_contact_request_message(
    request: ContactRequestRequest,
    fastapi_request: Request,
    messenger: IMessenger = Depends(get_inbox_messenger),
    requests: IUserDataRequests = Depends(requires_capability(IUserDataRequests)),
    api_dispatcher: APIEventDispatcher | None = Depends(get_api_event_dispatcher),
) -> MessageResult:
    return await requests.send_contact_request(
        body=request.body,
        target=direct_target(messenger, request),
        reply_to_message_id=request.reply_to_message_id,
    )
