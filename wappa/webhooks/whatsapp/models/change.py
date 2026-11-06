"""One webhook change: the ``field`` and its routed ``value``."""

from __future__ import annotations

from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    model_validator,
)

from wappa.webhooks.whatsapp.fields import (
    ACCOUNT_EVENT_FIELDS,
    BUILTIN_WEBHOOK_FIELDS,
    BUSINESS_USERNAME_EVENT_FIELDS,
)
from wappa.webhooks.whatsapp.models.calls import CallsWebhookValue
from wappa.webhooks.whatsapp.models.coexistence import (
    CoexistenceWebhookValue,
    HistoryWebhookValue,
    SmbAppStateSyncWebhookValue,
    SmbMessageEchoesWebhookValue,
)
from wappa.webhooks.whatsapp.models.values import (
    AccountWebhookValue,
    BusinessUsernameWebhookValue,
    CustomWebhookValue,
    WebhookValue,
)


class WebhookChange(BaseModel):
    """
    Change object describing what changed in the webhook.

    WhatsApp Business webhooks use different field values. Wappa handles its
    native message, identity, group, Calling, account, and Coexistence fields
    with typed value models.

    Any other field value (e.g. ``message_template_status_update``) is only
    accepted when the app has registered a typed handler for it via
    ``WappaBuilder.register_webhook_field`` (the registry is propagated into
    Pydantic's validation context). Unknown, unregistered fields still raise
    a validation error.
    """

    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)

    field: str = Field(..., description="Webhook field type")
    value: (
        WebhookValue
        | AccountWebhookValue
        | BusinessUsernameWebhookValue
        | CallsWebhookValue
        | CoexistenceWebhookValue
        | CustomWebhookValue
    ) = Field(..., description="The webhook payload data")

    @model_validator(mode="before")
    @classmethod
    def _route_field(cls, data: Any, info: ValidationInfo) -> Any:
        """Gate ``field`` against built-ins + registry, route ``value`` accordingly.

        Built-in fields pre-validate with the strict ``WebhookValue`` model so
        malformed payloads surface as clear field errors rather than falling
        through to the permissive ``CustomWebhookValue`` path.
        Registered custom fields use the permissive path; unregistered fields raise.
        """
        if not isinstance(data, dict):
            return data

        field = data.get("field")
        raw_value = data.get("value")

        # Account-level coexistence events are built-in but their value is a
        # flat WABA-scoped object (waba_id/reason/phone_number_id/timestamp),
        # not the phone-scoped WebhookValue shape — validate against the strict
        # AccountWebhookValue model so malformed payloads surface as clear
        # field errors, same as any other built-in field.
        if field in ACCOUNT_EVENT_FIELDS:
            if isinstance(raw_value, dict):
                return {**data, "value": AccountWebhookValue.model_validate(raw_value)}
            return data

        if field in BUSINESS_USERNAME_EVENT_FIELDS:
            if isinstance(raw_value, dict):
                return {
                    **data,
                    "value": BusinessUsernameWebhookValue.model_validate(raw_value),
                }
            return data

        if field == "calls":
            if isinstance(raw_value, dict):
                return {**data, "value": CallsWebhookValue.model_validate(raw_value)}
            return data

        coexistence_models: dict[str, type[BaseModel]] = {
            "history": HistoryWebhookValue,
            "smb_message_echoes": SmbMessageEchoesWebhookValue,
            "smb_app_state_sync": SmbAppStateSyncWebhookValue,
        }
        coexistence_model = coexistence_models.get(str(field))
        if coexistence_model is not None:
            if isinstance(raw_value, dict):
                return {**data, "value": coexistence_model.model_validate(raw_value)}
            return data

        if field in BUILTIN_WEBHOOK_FIELDS:
            if isinstance(raw_value, dict):
                return {**data, "value": WebhookValue.model_validate(raw_value)}
            return data

        # A field Wappa does not model and no app parser covers is kept as an
        # untyped value: the processor delivers it as UNSUPPORTED_EVENT and
        # logs schema drift instead of rejecting the callback (ADR-0023).
        if isinstance(raw_value, dict):
            return {**data, "value": CustomWebhookValue.model_validate(raw_value)}
        return data
