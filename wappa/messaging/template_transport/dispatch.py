"""Template transport dispatch: routing, provider send, digest and result mapping."""

from __future__ import annotations

import hashlib
import json
from time import monotonic
from typing import TYPE_CHECKING

from wappa.domain.inbox.identity import InboxRef
from wappa.domain.interfaces.template_messaging import ITemplateMessaging
from wappa.domain.messaging_targets import DeliveryAddresses, DirectMessage
from wappa.domain.results import MessageResult

from .requests import (
    MediaTemplateTransportRequest,
    TemplateTransportRequest,
    TextTemplateTransportRequest,
)
from .result import TemplateTransportResult, _TemplateResultCommon
from .values import (
    TemplateAddressKind,
    TemplateCategory,
    TemplateEndpoint,
    TemplateRoutingPolicy,
    TemplateRoutingReason,
    TemplateTransportOutcome,
)

if TYPE_CHECKING:
    from wappa.domain.interfaces.messaging_interface import IMessenger


async def _send_request(
    messenger: IMessenger,
    request: TemplateTransportRequest,
) -> MessageResult:
    templates = messenger.require_capability(ITemplateMessaging)
    body_parameters = [
        parameter.model_dump(exclude_none=True) for parameter in request.body_parameters
    ] or None
    if isinstance(request, TextTemplateTransportRequest):
        return await templates.send_text_template(
            template_name=request.template_name,
            target=DirectMessage(
                inbox_ref=InboxRef(
                    platform=messenger.platform, inbox_id=messenger.inbox_id
                ),
                addresses=DeliveryAddresses.of(request.recipient.value),
            ),
            body_parameters=body_parameters,
            language_code=request.language_code,
            template_type=request.category.value,
            routing_policy=request.routing.policy.value,
            authentication_method=(
                request.authentication_method.value
                if request.authentication_method is not None
                else None
            ),
            authentication_button_index=request.authentication_button_index,
        )
    if isinstance(request, MediaTemplateTransportRequest):
        media_header = request.media_header
        return await templates.send_media_template(
            template_name=request.template_name,
            target=DirectMessage(
                inbox_ref=InboxRef(
                    platform=messenger.platform, inbox_id=messenger.inbox_id
                ),
                addresses=DeliveryAddresses.of(request.recipient.value),
            ),
            media_type=media_header.media_type.value,
            media_id=media_header.media_id,
            media_url=media_header.media_url,
            body_parameters=body_parameters,
            language_code=request.language_code,
            template_type=request.category.value,
            routing_policy=request.routing.policy.value,
        )
    location_header = request.location_header
    return await templates.send_location_template(
        template_name=request.template_name,
        target=DirectMessage(
            inbox_ref=InboxRef(
                platform=messenger.platform, inbox_id=messenger.inbox_id
            ),
            addresses=DeliveryAddresses.of(request.recipient.value),
        ),
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
        if code == "INDETERMINATE"
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
