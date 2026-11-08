"""Normalized evidence for the Platform messages produced by one Wappa send."""

from typing import Any

from .results import MessageResult, message_outcome


def message_part(
    role: str, text: str | None, result: MessageResult | None = None
) -> dict[str, Any]:
    part: dict[str, Any] = {
        "index": 0,
        "role": role,
        "text": text,
        "message_id": result.message_id if result else None,
        "outcome": message_outcome(result).value if result else "not_attempted",
    }
    if result and result.error_code:
        part["error_code"] = result.error_code
    return part


def with_message_parts(
    result: MessageResult, parts: list[dict[str, Any]]
) -> MessageResult:
    response = dict(result.platform_response or {})
    ordered = [dict(part, index=index) for index, part in enumerate(parts)]
    message_ids = [
        part["message_id"]
        for part in ordered
        if part["outcome"] == "accepted" and part["message_id"]
    ]
    response["wappa_parts"] = {
        "message_ids": message_ids,
        "delivered": len(message_ids),
        "parts": ordered,
    }
    return result.model_copy(update={"platform_response": response})
