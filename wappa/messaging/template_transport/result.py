"""Template transport result: normalized evidence of one provider call."""

from __future__ import annotations

from typing import TypedDict

from pydantic import BaseModel, ConfigDict, model_validator

from .values import (
    TemplateAddressKind,
    TemplateEndpoint,
    TemplateRoutingReason,
    TemplateTransportOutcome,
)


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
