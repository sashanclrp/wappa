"""Normalized evidence for the Platform messages produced by one Wappa send."""

from typing import Any

from .part_content import PartContent
from .results import MessagePart, MessageResult, message_outcome


def message_part(
    role: str,
    text: str | None,
    result: MessageResult | None = None,
    *,
    content: PartContent | None = None,
) -> dict[str, Any]:
    part: dict[str, Any] = {
        "index": 0,
        "role": role,
        "text": text,
        "content": content.model_dump(mode="json", exclude_none=True)
        if content
        else None,
        "message_id": result.message_id if result else None,
        "outcome": message_outcome(result).value if result else "not_attempted",
    }
    if result and result.retry_after is not None:
        part["retry_after"] = result.retry_after
    if result and result.error_evidence:
        part["error_evidence"] = result.error_evidence.model_dump(mode="json")
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
    evidence = result.error_evidence
    if (
        evidence
        and not result.success
        and any(part["outcome"] == "accepted" for part in ordered)
    ):
        evidence = evidence.model_copy(update={"retry_safe": False})
    return result.model_copy(
        update={
            "error_evidence": evidence,
            "platform_response": response,
            "parts": tuple(MessagePart.model_validate(part) for part in ordered),
        }
    )
