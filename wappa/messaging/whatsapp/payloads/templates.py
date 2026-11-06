"""Cloud API payloads for Template messages (text, media, location, Authentication).

Pure builders (no I/O). Template routing (which endpoint a category takes)
and the sends live in ``messenger/templates.py``.
"""

from __future__ import annotations

from typing import Any

from wappa.messaging.template_transport import TemplateAuthenticationMethod
from wappa.messaging.template_transport.values import TemplateMediaType
from wappa.messaging.whatsapp.models.template_models import (
    TemplateParameter,
    TemplateParameterType,
    WhatsAppTemplateType,
)
from wappa.schemas.core.recipient import apply_recipient_to_payload


def build_text_parameter(param: TemplateParameter) -> dict[str, Any]:
    param_dict: dict[str, Any] = {"type": "text", "text": param.text}
    if param.parameter_name:
        param_dict["parameter_name"] = param.parameter_name
    return param_dict


def build_body_component(
    body_parameters: list[TemplateParameter] | None,
) -> dict[str, Any] | None:
    if not body_parameters:
        return None
    api_parameters = [
        build_text_parameter(param)
        for param in body_parameters
        if param.type == TemplateParameterType.TEXT
    ]
    return {"type": "body", "parameters": api_parameters}


def resolve_authentication_code(body_parameters: list[TemplateParameter] | None) -> str:
    """Return the single OTP code an Authentication Template body carries.

    Meta's authentication body is the fixed preset ``{{1}} is your
    verification code``, so exactly one positional text parameter is
    legal. Failing here costs one local raise instead of a provider
    round trip that returns a parameter-count error.
    """
    parameters = [
        parameter
        for parameter in (body_parameters or [])
        if parameter.type == TemplateParameterType.TEXT
    ]
    if len(parameters) != 1:
        raise ValueError(
            "An authentication Template requires exactly one body text "
            f"parameter carrying the code, got {len(parameters)}"
        )
    code = parameters[0].text
    if not code:
        raise ValueError("The authentication Template code cannot be empty")
    if parameters[0].parameter_name:
        raise ValueError(
            "Authentication Templates use the positional {{1}} code "
            "placeholder and cannot bind a named parameter"
        )
    return code


def build_authentication_button_component(
    code: str, button_index: int
) -> dict[str, Any]:
    """Build the OTP button component Meta requires beside the body.

    The button's URL ends in ``...&code=otp{{1}}``, so its single
    parameter is a real placeholder. Meta rejects the whole send when it
    is missing. ``index`` is serialised as a string because that is the
    type Meta's Cloud API reference declares for it.
    """
    return {
        "type": "button",
        "sub_type": "url",
        "index": str(button_index),
        "parameters": [{"type": "text", "text": code}],
    }


def build_authentication_components(
    body_parameters: list[TemplateParameter] | None,
    authentication_method: str,
    button_index: int,
) -> list[dict[str, Any]]:
    """Build ``[body, button]`` for one Authentication Template send.

    Both components carry the same code, filled once here rather than by
    two callers agreeing: the body is what the person reads, the button
    is what "Copy code" writes to their clipboard.
    """
    # Raises on an unknown method rather than silently degrading to a
    # body-only payload Meta would reject anyway.
    TemplateAuthenticationMethod(authentication_method)
    code = resolve_authentication_code(body_parameters)
    body_component = build_body_component(body_parameters)
    if body_component is None:  # pragma: no cover - guarded above
        raise ValueError("An authentication Template requires a body parameter")
    return [
        body_component,
        build_authentication_button_component(code, button_index),
    ]


def build_template_payload(
    recipient: str,
    template_data: dict[str, Any],
    *,
    include_recipient_type: bool = True,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "messaging_product": "whatsapp",
        "type": "template",
        "template": template_data,
    }
    if include_recipient_type:
        payload["recipient_type"] = "individual"
    apply_recipient_to_payload(payload, recipient)
    return payload


def build_components_with_header(
    header_component: dict[str, Any],
    body_parameters: list[TemplateParameter] | None,
) -> list[dict[str, Any]]:
    components: list[dict[str, Any]] = [header_component]
    if body_component := build_body_component(body_parameters):
        components.append(body_component)
    return components


def build_template_data(
    template_name: str,
    language_code: str,
    components: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "name": template_name,
        "language": {"code": language_code},
    }
    if components:
        data["components"] = components
    return data


def resolve_text_components(
    body_parameters: list[TemplateParameter] | None,
    *,
    template_type: WhatsAppTemplateType,
    authentication_method: str | None,
    authentication_button_index: int,
) -> list[dict[str, Any]] | None:
    """Decide the components one text Template send puts on the wire."""
    is_authentication = template_type is WhatsAppTemplateType.AUTHENTICATION
    if authentication_method is not None and not is_authentication:
        raise ValueError(
            "authentication_method is only valid for authentication Templates"
        )
    if is_authentication:
        if authentication_method is None:
            raise ValueError(
                "authentication_method is required for authentication Templates"
            )
        return build_authentication_components(
            body_parameters,
            authentication_method,
            authentication_button_index,
        )
    body_component = build_body_component(body_parameters)
    return [body_component] if body_component else None


def media_header_component(
    media_type: TemplateMediaType,
    media_id: str | None,
    media_url: str | None,
) -> dict[str, Any]:
    if bool(media_id) == bool(media_url):
        raise ValueError("Either media_id or media_url must be provided, but not both")

    media_source = {"id": media_id} if media_id else {"link": media_url}
    return {
        "type": "header",
        "parameters": [{"type": media_type.value, media_type.value: media_source}],
    }


def location_header_component(
    latitude: str, longitude: str, name: str, address: str
) -> dict[str, Any]:
    try:
        lat = float(latitude)
        lon = float(longitude)
    except ValueError as e:
        raise ValueError("Latitude and longitude must be valid numbers") from e
    if not -90 <= lat <= 90:
        raise ValueError("Latitude must be between -90 and 90 degrees")
    if not -180 <= lon <= 180:
        raise ValueError("Longitude must be between -180 and 180 degrees")

    return {
        "type": "header",
        "parameters": [
            {
                "type": "location",
                "location": {
                    "latitude": latitude,
                    "longitude": longitude,
                    "name": name,
                    "address": address,
                },
            }
        ],
    }
