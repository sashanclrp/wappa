"""WhatsApp native payloads → neutral per-part structured evidence."""

from typing import Any, cast

from wappa.domain.part_content import (
    PartButton,
    PartContent,
    PartElement,
    PartHeader,
    PartLocation,
    PartMedia,
    PartSection,
    PartTemplate,
)


def _media(kind: str, value: dict[str, Any]) -> PartMedia:
    return PartMedia(
        type=kind,
        id=value.get("id"),
        url=value.get("link"),
        filename=value.get("filename"),
        voice=value.get("voice"),
    )


def _header(value: dict[str, Any] | None) -> PartHeader | None:
    if value is None:
        return None
    if value["type"] == "text":
        return PartHeader(text=value["text"])
    return PartHeader(media=_media(value["type"], value[value["type"]]))


def _buttons(action: dict[str, Any]) -> tuple[PartButton, ...]:
    if action.get("name") == "cta_url":
        value = action["parameters"]
        return (PartButton(type="url", title=value["display_text"], url=value["url"]),)
    return tuple(
        PartButton(type="reply", **button.get("reply", button.get("quick_reply", {})))
        for button in action.get("buttons", ())
    )


def message_content(payload: dict[str, Any]) -> PartContent | None:
    kind = payload["type"]
    if kind == "text":
        return None
    if kind in {"image", "audio", "video", "document", "sticker"}:
        return PartContent(media=_media(kind, payload[kind]))
    if kind == "contacts":
        return PartContent(contacts=tuple(payload[kind]))
    if kind == "location":
        return PartContent(location=PartLocation.model_validate(payload[kind]))
    if kind == "template":
        value = payload[kind]
        return PartContent(
            template=PartTemplate(
                name=value["name"],
                language=value["language"]["code"],
                components=tuple(value.get("components", ())),
            )
        )
    value = payload["interactive"]
    action = value["action"]
    fields: dict[str, Any] = {
        "header": _header(value.get("header")),
        "footer": value.get("footer", {}).get("text"),
    }
    if value["type"] == "carousel":
        fields["elements"] = tuple(
            PartElement(
                title=card["body"]["text"],
                media=cast(PartHeader, _header(card["header"])).media,
                buttons=_buttons(card["action"]),
            )
            for card in action["cards"]
        )
    elif value["type"] == "list":
        fields.update(
            button_text=action["button"],
            sections=tuple(
                PartSection.model_validate(section) for section in action["sections"]
            ),
        )
    elif value["type"] in {"location_request_message", "request_contact_info"}:
        fields["request"] = (
            "contact" if value["type"] == "request_contact_info" else "location"
        )
    else:
        fields["buttons"] = _buttons(action)
    return PartContent(**fields)
