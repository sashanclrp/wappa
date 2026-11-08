"""Instagram wire messages → neutral per-part structured evidence."""

from typing import Any

from wappa.domain.part_content import (
    PartButton,
    PartContent,
    PartElement,
    PartMedia,
    PartQuickReply,
)


def _button(value: dict[str, Any]) -> PartButton:
    return PartButton(
        type="reply" if value["type"] == "postback" else "url",
        title=value.get("title"),
        id=value.get("payload"),
        url=value.get("url"),
    )


def message_content(message: dict[str, Any]) -> PartContent | None:
    if "quick_replies" in message:
        return PartContent(
            quick_replies=tuple(
                PartQuickReply(
                    type=reply["content_type"],
                    title=reply.get("title"),
                    id=reply.get("payload"),
                    image_url=reply.get("image_url"),
                )
                for reply in message["quick_replies"]
            )
        )
    attachment = message.get("attachment")
    if attachment is None:
        return None
    if "payload" not in attachment:
        return None  # prerequisite upload failed; no media reference was sent
    payload = attachment["payload"]
    if payload.get("template_type") == "button":
        return PartContent(
            buttons=tuple(_button(button) for button in payload["buttons"])
        )
    if payload.get("template_type") == "generic":
        return PartContent(
            elements=tuple(
                PartElement(
                    title=element["title"],
                    subtitle=element.get("subtitle"),
                    media=PartMedia(type="image", url=element["image_url"])
                    if element.get("image_url")
                    else None,
                    buttons=tuple(
                        _button(button) for button in element.get("buttons", ())
                    ),
                    default_action=_button(element["default_action"])
                    if element.get("default_action")
                    else None,
                )
                for element in payload["elements"]
            )
        )
    return PartContent(
        media=PartMedia(
            type="document" if attachment["type"] == "file" else attachment["type"],
            id=payload.get("attachment_id"),
            url=payload.get("url"),
            reusable=payload.get("is_reusable"),
        )
    )
