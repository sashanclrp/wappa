"""Inbox-scoped outbound Template transport.

This module is the public boundary between a Host Application and Wappa's
provider-facing Template delivery machinery.  It deliberately exposes request
and result values, while keeping credentials, sessions, clients, handlers, and
Messenger Pipeline composition inside Wappa.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from enum import StrEnum
from time import monotonic
from typing import TYPE_CHECKING, Annotated, Literal, TypedDict, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from wappa.core.messaging.pipeline import MessengerPipeline, MiddlewareEntry
from wappa.domain.interfaces.inbox_credential_store import IInboxCredentialStore
from wappa.domain.interfaces.session_provider import (
    HTTPSessionClosedError,
    RuntimeDrainingError,
)
from wappa.messaging.whatsapp.models.basic_models import MessageResult
from wappa.schemas.core.recipient import RecipientKind, resolve_recipient
from wappa.schemas.core.types import PlatformType

if TYPE_CHECKING:
    import httpx
    from fastapi import FastAPI

    from wappa.domain.factories import MessengerFactory
    from wappa.domain.interfaces.messaging_interface import IMessenger


class TemplateTransportOutcome(StrEnum):
    """What Wappa can prove about one provider call."""

    ACCEPTED = "accepted"
    REJECTED = "rejected"
    TRANSPORT_UNAVAILABLE = "transport_unavailable"
    INDETERMINATE = "indeterminate"


class TemplateAddressKind(StrEnum):
    """Supported provider-facing Template destination kinds."""

    PHONE_NUMBER = "phone_number"
    BSUID = "bsuid"


class TemplateCategory(StrEnum):
    """Template category used by the platform for endpoint selection."""

    MARKETING = "marketing"
    UTILITY = "utility"
    AUTHENTICATION = "authentication"


class TemplateMediaType(StrEnum):
    """Supported media-header kinds."""

    IMAGE = "image"
    VIDEO = "video"
    DOCUMENT = "document"


class TemplateAuthenticationMethod(StrEnum):
    """Authentication button method represented by the Template."""

    ONE_TAP = "one_tap"
    ZERO_TAP = "zero_tap"
    COPY_CODE = "copy_code"


class TemplateRoutingPolicy(StrEnum):
    """Explicit endpoint policy for a Template call."""

    CATEGORY_DEFAULT = "category_default"
    CLOUD_MESSAGES_FALLBACK = "cloud_messages_fallback"


class TemplateEndpoint(StrEnum):
    MESSAGES = "messages"
    MARKETING_MESSAGES = "marketing_messages"


class TemplateRoutingReason(StrEnum):
    CATEGORY_DEFAULT = "category_default"
    EXPLICIT_MARKETING_FALLBACK = "explicit_marketing_fallback"


class PhoneNumberTemplateRecipient(BaseModel):
    """A normalized phone number sent through Meta's ``to`` field."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["phone_number"] = "phone_number"
    value: str

    @field_validator("value")
    @classmethod
    def normalize_phone_number(cls, value: str) -> str:
        recipient = resolve_recipient(value)
        if recipient.kind is not RecipientKind.PHONE_NUMBER:
            raise ValueError("A phone_number recipient must contain a phone number")
        return recipient.transport_value


class BsuidTemplateRecipient(BaseModel):
    """A normalized regular or parent BSUID sent through Meta's ``recipient`` field."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["bsuid"] = "bsuid"
    value: str

    @field_validator("value")
    @classmethod
    def normalize_bsuid(cls, value: str) -> str:
        recipient = resolve_recipient(value)
        if recipient.kind is not RecipientKind.BSUID:
            raise ValueError("A bsuid recipient must contain a regular or parent BSUID")
        return recipient.transport_value


TemplateTransportRecipient = Annotated[
    PhoneNumberTemplateRecipient | BsuidTemplateRecipient,
    Field(discriminator="kind"),
]


class TemplateTransportParameter(BaseModel):
    """One named or positional text substitution value."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["text"] = "text"
    text: str = Field(min_length=1, max_length=1024)
    parameter_name: str | None = Field(
        default=None,
        max_length=128,
        pattern=r"^[a-zA-Z][a-zA-Z0-9_]*$",
    )


class TemplateTransportMediaHeader(BaseModel):
    """Provider-facing media header selection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    media_type: TemplateMediaType
    media_id: str | None = Field(default=None, min_length=1)
    media_url: str | None = Field(default=None, pattern=r"^https?://")

    @model_validator(mode="after")
    def validate_source(self) -> TemplateTransportMediaHeader:
        if bool(self.media_id) == bool(self.media_url):
            raise ValueError("Exactly one of media_id or media_url is required")
        return self


class TemplateTransportLocationHeader(BaseModel):
    """Provider-facing location header values."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    latitude: str
    longitude: str
    name: str = Field(min_length=1, max_length=100)
    address: str = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def validate_coordinates(self) -> TemplateTransportLocationHeader:
        try:
            latitude = float(self.latitude)
            longitude = float(self.longitude)
        except ValueError as exc:
            raise ValueError("Latitude and longitude must be valid numbers") from exc
        if not -90 <= latitude <= 90:
            raise ValueError("Latitude must be between -90 and 90 degrees")
        if not -180 <= longitude <= 180:
            raise ValueError("Longitude must be between -180 and 180 degrees")
        return self


class TemplateTransportRouting(BaseModel):
    """Provider endpoint routing options."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    policy: TemplateRoutingPolicy = TemplateRoutingPolicy.CATEGORY_DEFAULT


class _TemplateTransportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    recipient: TemplateTransportRecipient
    template_name: str = Field(min_length=1, max_length=512)
    category: TemplateCategory
    authentication_method: TemplateAuthenticationMethod | None = None
    language_code: str = Field(default="es", min_length=2, max_length=32)
    body_parameters: tuple[TemplateTransportParameter, ...] = Field(
        default=(), max_length=10
    )
    routing: TemplateTransportRouting = Field(default_factory=TemplateTransportRouting)

    @model_validator(mode="after")
    def validate_policy(self) -> _TemplateTransportRequest:
        if (
            self.category != TemplateCategory.MARKETING
            and self.routing.policy is not TemplateRoutingPolicy.CATEGORY_DEFAULT
        ):
            raise ValueError(
                "cloud_messages_fallback is only valid for marketing Templates"
            )
        if self.category is TemplateCategory.AUTHENTICATION:
            if self.authentication_method is None:
                raise ValueError(
                    "authentication_method is required for authentication Templates"
                )
            if isinstance(self.recipient, BsuidTemplateRecipient):
                raise ValueError(
                    "Authentication Templates cannot use a BSUID recipient"
                )
        elif self.authentication_method is not None:
            raise ValueError(
                "authentication_method is only valid for authentication Templates"
            )
        return self


class TextTemplateTransportRequest(_TemplateTransportRequest):
    kind: Literal["text"] = "text"


class MediaTemplateTransportRequest(_TemplateTransportRequest):
    kind: Literal["media"] = "media"
    media_header: TemplateTransportMediaHeader


class LocationTemplateTransportRequest(_TemplateTransportRequest):
    kind: Literal["location"] = "location"
    location_header: TemplateTransportLocationHeader


TemplateTransportRequest = Annotated[
    TextTemplateTransportRequest
    | MediaTemplateTransportRequest
    | LocationTemplateTransportRequest,
    Field(discriminator="kind"),
]


class TemplateTransportResult(BaseModel):
    """Normalized evidence returned by Wappa after a Template transport call."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    outcome: TemplateTransportOutcome
    inbox_id: str
    requested_address_kind: TemplateAddressKind
    requested_address: str
    platform_message_id: str | None = None
    resolved_recipient_id: str | None = None
    returned_phone_number: str | None = None
    returned_bsuid: str | None = None
    returned_parent_bsuid: str | None = None
    returned_username: str | None = None
    selected_endpoint: TemplateEndpoint
    routing_reason: TemplateRoutingReason
    error_code: str | None = None
    error_message: str | None = None
    request_digest: str
    platform_latency_ms: int

    @model_validator(mode="after")
    def validate_acceptance_evidence(self) -> TemplateTransportResult:
        if (
            self.outcome is TemplateTransportOutcome.ACCEPTED
            and self.platform_message_id is None
        ):
            raise ValueError(
                "An accepted Template result requires a platform Message ID"
            )
        return self

    @property
    def accepted(self) -> bool:
        """Whether provider acceptance and Message identity are both proven."""
        return self.outcome is TemplateTransportOutcome.ACCEPTED


class _TemplateResultCommon(TypedDict):
    inbox_id: str
    requested_address_kind: TemplateAddressKind
    requested_address: str
    resolved_recipient_id: str | None
    returned_phone_number: str | None
    returned_bsuid: str | None
    returned_parent_bsuid: str | None
    returned_username: str | None
    selected_endpoint: TemplateEndpoint
    routing_reason: TemplateRoutingReason
    request_digest: str
    platform_latency_ms: int


class InboxTemplateTransport:
    """Template transport capability bound to one Inbox."""

    def __init__(self, *, runtime: OutboundRuntime, inbox_id: str) -> None:
        if not inbox_id:
            raise ValueError("inbox_id is required")
        self._runtime = runtime
        self.inbox_id = inbox_id

    async def send(self, request: TemplateTransportRequest) -> TemplateTransportResult:
        digest = _request_digest(request)
        started = monotonic()
        endpoint, routing_reason = resolve_template_route(
            request.category, request.routing.policy
        )

        def failure(
            outcome: TemplateTransportOutcome, code: str, message: str
        ) -> TemplateTransportResult:
            return _failure_result(
                outcome=outcome,
                inbox_id=self.inbox_id,
                digest=digest,
                started=started,
                request=request,
                endpoint=endpoint,
                routing_reason=routing_reason,
                code=code,
                message=message,
            )

        try:
            messenger = await self._runtime._messenger(self.inbox_id)
        except (RuntimeDrainingError, HTTPSessionClosedError):
            return failure(
                TemplateTransportOutcome.TRANSPORT_UNAVAILABLE,
                "runtime_unavailable",
                "The outbound runtime is not accepting new transport calls.",
            )
        except Exception:
            return failure(
                TemplateTransportOutcome.TRANSPORT_UNAVAILABLE,
                "transport_unavailable",
                "The Inbox transport could not be prepared.",
            )

        try:
            result = await _send_request(messenger, request)
        except (RuntimeDrainingError, HTTPSessionClosedError):
            return failure(
                TemplateTransportOutcome.TRANSPORT_UNAVAILABLE,
                "runtime_unavailable",
                "The outbound runtime is not accepting new transport calls.",
            )
        except ValueError:
            return failure(
                TemplateTransportOutcome.REJECTED,
                "invalid_template_request",
                "The Template request is invalid for this platform.",
            )
        except Exception:
            return failure(
                TemplateTransportOutcome.INDETERMINATE,
                "platform_outcome_indeterminate",
                "The platform outcome could not be determined.",
            )
        return _normalize_result(
            result,
            inbox_id=self.inbox_id,
            digest=digest,
            started=started,
            request=request,
            endpoint=endpoint,
            routing_reason=routing_reason,
        )


class OutboundRuntime:
    """Build Inbox-scoped outbound capabilities from Wappa-owned resources."""

    def __init__(
        self,
        *,
        session_provider: Callable[[], httpx.AsyncClient],
        media_download_client_provider: Callable[[], httpx.AsyncClient],
        credential_store: IInboxCredentialStore,
        messenger_middleware: Sequence[MiddlewareEntry] = (),
    ) -> None:
        # Local import prevents the public ``wappa.messaging`` package from
        # cycling while MessengerFactory imports its WhatsApp adapter modules.
        from wappa.domain.factories import MessengerFactory

        self._messenger_factory: MessengerFactory = MessengerFactory(
            session_provider=session_provider,
            credential_store=credential_store,
            media_download_client_provider=media_download_client_provider,
        )
        self._messenger_middleware = tuple(messenger_middleware)

    @classmethod
    def from_app(cls, app: FastAPI) -> OutboundRuntime:
        """Resolve Wappa's active resources from a configured FastAPI app."""
        existing = getattr(app.state, "outbound_runtime", None)
        if isinstance(existing, cls):
            return existing

        lifecycle = getattr(app.state, "session_lifecycle", None)
        if lifecycle is None:
            raise RuntimeError(
                "SessionLifecycle is not available; Wappa startup is incomplete"
            )
        credential_store = getattr(app.state, "inbox_credential_store", None)
        if credential_store is None:
            raise RuntimeError("IInboxCredentialStore is not configured")

        runtime = cls(
            session_provider=lifecycle.get_session,
            credential_store=cast(IInboxCredentialStore, credential_store),
            messenger_middleware=getattr(app.state, "messenger_middleware", ()),
            media_download_client_provider=lifecycle.get_media_download_client,
        )
        app.state.outbound_runtime = runtime
        return runtime

    def templates(self, inbox_id: str) -> InboxTemplateTransport:
        """Return a Template transport capability scoped to ``inbox_id``."""
        return InboxTemplateTransport(runtime=self, inbox_id=inbox_id)

    async def _messenger(self, inbox_id: str) -> IMessenger:
        raw = await self._messenger_factory.create_messenger(
            platform=PlatformType.WHATSAPP,
            inbox_id=inbox_id,
        )
        return MessengerPipeline(raw=raw, middleware=self._messenger_middleware)


async def _send_request(
    messenger: IMessenger,
    request: TemplateTransportRequest,
) -> MessageResult:
    body_parameters = [
        parameter.model_dump(exclude_none=True) for parameter in request.body_parameters
    ] or None
    if isinstance(request, TextTemplateTransportRequest):
        return await messenger.send_text_template(
            template_name=request.template_name,
            recipient=request.recipient.value,
            body_parameters=body_parameters,
            language_code=request.language_code,
            template_type=request.category.value,
            routing_policy=request.routing.policy.value,
        )
    if isinstance(request, MediaTemplateTransportRequest):
        media_header = request.media_header
        return await messenger.send_media_template(
            template_name=request.template_name,
            recipient=request.recipient.value,
            media_type=media_header.media_type.value,
            media_id=media_header.media_id,
            media_url=media_header.media_url,
            body_parameters=body_parameters,
            language_code=request.language_code,
            template_type=request.category.value,
            routing_policy=request.routing.policy.value,
        )
    location_header = request.location_header
    return await messenger.send_location_template(
        template_name=request.template_name,
        recipient=request.recipient.value,
        latitude=location_header.latitude,
        longitude=location_header.longitude,
        name=location_header.name,
        address=location_header.address,
        body_parameters=body_parameters,
        language_code=request.language_code,
        template_type=request.category.value,
        routing_policy=request.routing.policy.value,
    )


def resolve_template_route(
    category: TemplateCategory,
    policy: TemplateRoutingPolicy,
) -> tuple[TemplateEndpoint, TemplateRoutingReason]:
    """Resolve the one endpoint selected before provider I/O."""
    if category is TemplateCategory.MARKETING:
        if policy is TemplateRoutingPolicy.CLOUD_MESSAGES_FALLBACK:
            return (
                TemplateEndpoint.MESSAGES,
                TemplateRoutingReason.EXPLICIT_MARKETING_FALLBACK,
            )
        return (
            TemplateEndpoint.MARKETING_MESSAGES,
            TemplateRoutingReason.CATEGORY_DEFAULT,
        )
    if policy is not TemplateRoutingPolicy.CATEGORY_DEFAULT:
        raise ValueError("Only marketing Templates support a routing fallback")
    return TemplateEndpoint.MESSAGES, TemplateRoutingReason.CATEGORY_DEFAULT


def _request_digest(request: TemplateTransportRequest) -> str:
    canonical = json.dumps(
        request.model_dump(mode="json", exclude_none=True),
        sort_keys=True,
        separators=(",", ":"),
    )
    return "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()


def _normalize_result(
    result: MessageResult,
    *,
    inbox_id: str,
    digest: str,
    started: float,
    request: TemplateTransportRequest,
    endpoint: TemplateEndpoint,
    routing_reason: TemplateRoutingReason,
) -> TemplateTransportResult:
    latency = round((monotonic() - started) * 1000)
    common: _TemplateResultCommon = {
        "inbox_id": inbox_id,
        "requested_address_kind": TemplateAddressKind(request.recipient.kind),
        "requested_address": request.recipient.value,
        "resolved_recipient_id": result.recipient,
        "returned_phone_number": result.recipient_phone,
        "returned_bsuid": result.recipient_bsuid,
        "returned_parent_bsuid": result.recipient_parent_bsuid,
        "returned_username": result.recipient_username,
        "selected_endpoint": endpoint,
        "routing_reason": routing_reason,
        "request_digest": digest,
        "platform_latency_ms": latency,
    }

    if result.success and result.message_id:
        return TemplateTransportResult(
            outcome=TemplateTransportOutcome.ACCEPTED,
            platform_message_id=result.message_id,
            **common,
        )
    if result.success:
        return TemplateTransportResult(
            outcome=TemplateTransportOutcome.INDETERMINATE,
            error_code="accepted_without_platform_message_id",
            error_message=(
                "The platform reported success without a platform Message ID."
            ),
            **common,
        )

    code = _safe_error_code(result.error_code)
    outcome = (
        TemplateTransportOutcome.TRANSPORT_UNAVAILABLE
        if code in {"runtime_unavailable", "transport_unavailable"}
        else TemplateTransportOutcome.INDETERMINATE
        if code == "platform_outcome_indeterminate"
        else TemplateTransportOutcome.REJECTED
    )
    message = {
        TemplateTransportOutcome.TRANSPORT_UNAVAILABLE: (
            "The Inbox transport is unavailable."
        ),
        TemplateTransportOutcome.INDETERMINATE: (
            "The platform outcome could not be determined."
        ),
        TemplateTransportOutcome.REJECTED: "The platform rejected the Template send.",
    }[outcome]
    return TemplateTransportResult(
        outcome=outcome,
        error_code=code,
        error_message=message,
        **common,
    )


def _safe_error_code(value: str | None) -> str:
    if value and value.replace("_", "").replace("-", "").isalnum():
        return value[:128]
    return "platform_rejected"


def _failure_result(
    *,
    outcome: TemplateTransportOutcome,
    inbox_id: str,
    digest: str,
    started: float,
    code: str,
    message: str,
    request: TemplateTransportRequest,
    endpoint: TemplateEndpoint,
    routing_reason: TemplateRoutingReason,
) -> TemplateTransportResult:
    return TemplateTransportResult(
        outcome=outcome,
        inbox_id=inbox_id,
        requested_address_kind=TemplateAddressKind(request.recipient.kind),
        requested_address=request.recipient.value,
        selected_endpoint=endpoint,
        routing_reason=routing_reason,
        error_code=code,
        error_message=message,
        request_digest=digest,
        platform_latency_ms=round((monotonic() - started) * 1000),
    )
