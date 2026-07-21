"""Strict WhatsApp Calling webhook schemas."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from wappa.webhooks.whatsapp.base_models import WhatsAppContact, WhatsAppMetadata


class CallSession(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    sdp_type: Literal["offer", "answer"]
    sdp: str


class WhatsAppCall(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str
    event: Literal["connect", "terminate"]
    timestamp: str
    direction: Literal["BUSINESS_INITIATED", "USER_INITIATED"]
    from_: str | None = Field(None, alias="from")
    from_user_id: str | None = None
    from_parent_user_id: str | None = None
    to: str | None = None
    to_user_id: str | None = None
    to_parent_user_id: str | None = None
    biz_opaque_callback_data: str | None = None
    session: CallSession | None = None
    status: str | None = None
    duration: int | None = None
    start_time: str | None = None
    end_time: str | None = None


class WhatsAppCallStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str
    type: Literal["call"]
    status: str
    timestamp: str
    recipient_id: str | None = None
    recipient_user_id: str | None = None
    recipient_parent_user_id: str | None = None
    biz_opaque_callback_data: str | None = None


class CallsWebhookValue(BaseModel):
    """Value object for Meta's `calls` webhook field."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    messaging_product: Literal["whatsapp"]
    metadata: WhatsAppMetadata
    contacts: list[WhatsAppContact] | None = None
    calls: list[WhatsAppCall] | None = None
    statuses: list[WhatsAppCallStatus] | None = None

    @model_validator(mode="after")
    def require_call_or_status(self) -> "CallsWebhookValue":
        if not self.calls and not self.statuses:
            raise ValueError("Calls webhook must include calls or statuses")
        return self
