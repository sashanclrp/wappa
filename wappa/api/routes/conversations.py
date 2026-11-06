"""Conversation routes that exist where the Inbox's Platform provides them.

Mounted under ``/api/{platform}`` with every other messaging route (ADR-0024).
Each route asks the selected Inbox's Messenger for a capability and answers
501 when the Platform has none, so nothing here branches on Platform name:

- ``ICommentControls``: reply to, hide, unhide or delete a public comment;
  turn comments on or off for a post (today: Instagram).
- ``IConversationContentReader``: read a post, a comment, a post's comments
  and a comment's replies (today: Instagram).
- ``IConversationHistoryReader``: read past messages with one User
  (today: Instagram).
- Private reply: a DM answering a comment, the shared ``send_text`` with a
  ``PrivateReply`` target (501 where the Platform has no comments).

Capability groups (ADR-0024): comment mutations are their own group
(``comment_controls``), the private reply belongs to outbound transport, and
reads are always mounted.
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from wappa.api.dependencies.inbox_context import (
    InboxExecutionContext,
    get_inbox_execution_context,
    get_inbox_messenger,
    requires_capability,
)
from wappa.api.routes.families import RouteFamily
from wappa.api.utils import map_send_errors, raise_if_rate_limited
from wappa.domain.interfaces.conversation_capabilities import (
    ICommentControls,
    IConversationContentReader,
    ReadOutcome,
    ReadResult,
)
from wappa.domain.interfaces.history_reader import IConversationHistoryReader
from wappa.domain.interfaces.messaging_interface import IMessenger
from wappa.domain.messaging_targets import (
    CommentRef,
    PostRef,
    PrivateReply,
)
from wappa.domain.results import CommentResult, ControlResult, MessageResult

_READ_STATUS = {
    ReadOutcome.NOT_FOUND: 404,
    ReadOutcome.ACCESS_DENIED: 403,
    ReadOutcome.REJECTED: 400,
    ReadOutcome.UNAVAILABLE: 503,
}
_RESPONSES: dict[int | str, dict[str, Any]] = {
    501: {"description": "The Inbox's Platform does not provide this capability"},
}

_comments = RouteFamily(
    prefix="",
    tags=["Comments & posts (ICommentControls / IConversationContentReader)"],
    responses=_RESPONSES,
)
comment_controls_router = _comments.router()  # mutations on public comments
conversation_reads_router = _comments.router()  # reads, always mounted
private_reply_router = RouteFamily(
    prefix="/messages", tags=["Messages"], responses=_RESPONSES
).router()


class CommentReplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(..., min_length=1, description="Public reply text")


class CommentsEnabledRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = Field(..., description="False turns comments off for the post")


class PrivateReplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    comment_id: str = Field(..., min_length=1, description="Comment to answer")
    text: str = Field(..., min_length=1, description="Private (DM) reply text")


def _comment(context: InboxExecutionContext, comment_id: str) -> CommentRef:
    return CommentRef(inbox_ref=context.inbox_ref, comment_id=comment_id)


def _post(context: InboxExecutionContext, media_id: str) -> PostRef:
    return PostRef(inbox_ref=context.inbox_ref, media_id=media_id)


def _control(result: ControlResult | CommentResult) -> Any:
    if not result.success:
        raise_if_rate_limited(result.retry_after, result.error)
        raise HTTPException(
            status_code=400, detail=result.error or "The Platform rejected it"
        )
    return result


def _read(result: ReadResult[Any]) -> Any:
    if result.outcome is ReadOutcome.FOUND:
        return result.value
    raise_if_rate_limited(result.retry_after, result.error)
    raise HTTPException(
        status_code=_READ_STATUS.get(result.outcome, 502),
        detail=result.error or result.outcome.value,
    )


# ── comment controls (mutations) ─────────────────────────────────────────


@comment_controls_router.post(
    "/comments/{comment_id}/reply", response_model=CommentResult
)
async def reply_comment(
    comment_id: str,
    body: CommentReplyRequest,
    context: InboxExecutionContext = Depends(get_inbox_execution_context),
    controls: ICommentControls = Depends(requires_capability(ICommentControls)),
) -> Any:
    """Public reply under a comment."""
    try:
        return _control(
            await controls.reply_comment(_comment(context, comment_id), body.text)
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@comment_controls_router.post(
    "/comments/{comment_id}/hide", response_model=ControlResult
)
async def hide_comment(
    comment_id: str,
    context: InboxExecutionContext = Depends(get_inbox_execution_context),
    controls: ICommentControls = Depends(requires_capability(ICommentControls)),
) -> Any:
    return _control(await controls.hide_comment(_comment(context, comment_id)))


@comment_controls_router.post(
    "/comments/{comment_id}/unhide", response_model=ControlResult
)
async def unhide_comment(
    comment_id: str,
    context: InboxExecutionContext = Depends(get_inbox_execution_context),
    controls: ICommentControls = Depends(requires_capability(ICommentControls)),
) -> Any:
    return _control(await controls.unhide_comment(_comment(context, comment_id)))


@comment_controls_router.delete("/comments/{comment_id}", response_model=ControlResult)
async def delete_comment(
    comment_id: str,
    context: InboxExecutionContext = Depends(get_inbox_execution_context),
    controls: ICommentControls = Depends(requires_capability(ICommentControls)),
) -> Any:
    return _control(await controls.delete_comment(_comment(context, comment_id)))


@comment_controls_router.post(
    "/posts/{media_id}/comments-enabled", response_model=ControlResult
)
async def set_comments_enabled(
    media_id: str,
    body: CommentsEnabledRequest,
    context: InboxExecutionContext = Depends(get_inbox_execution_context),
    controls: ICommentControls = Depends(requires_capability(ICommentControls)),
) -> Any:
    return _control(
        await controls.set_comments_enabled(_post(context, media_id), body.enabled)
    )


# ── reads ────────────────────────────────────────────────────────────────


@conversation_reads_router.get("/posts/{media_id}")
async def get_post(
    media_id: str,
    context: InboxExecutionContext = Depends(get_inbox_execution_context),
    reader: IConversationContentReader = Depends(
        requires_capability(IConversationContentReader)
    ),
) -> Any:
    return _read(await reader.get_post(_post(context, media_id)))


@conversation_reads_router.get("/posts/{media_id}/comments")
async def list_comments(
    media_id: str,
    after: str | None = Query(None, description="Cursor from next_cursor"),
    limit: int = Query(25, ge=1, le=100),
    context: InboxExecutionContext = Depends(get_inbox_execution_context),
    reader: IConversationContentReader = Depends(
        requires_capability(IConversationContentReader)
    ),
) -> Any:
    return _read(
        await reader.list_comments(_post(context, media_id), after=after, limit=limit)
    )


@conversation_reads_router.get("/comments/{comment_id}")
async def get_comment(
    comment_id: str,
    context: InboxExecutionContext = Depends(get_inbox_execution_context),
    reader: IConversationContentReader = Depends(
        requires_capability(IConversationContentReader)
    ),
) -> Any:
    return _read(await reader.get_comment(_comment(context, comment_id)))


@conversation_reads_router.get("/comments/{comment_id}/replies")
async def list_replies(
    comment_id: str,
    after: str | None = Query(None, description="Cursor from next_cursor"),
    limit: int = Query(25, ge=1, le=100),
    context: InboxExecutionContext = Depends(get_inbox_execution_context),
    reader: IConversationContentReader = Depends(
        requires_capability(IConversationContentReader)
    ),
) -> Any:
    return _read(
        await reader.list_replies(
            _comment(context, comment_id), after=after, limit=limit
        )
    )


@conversation_reads_router.get("/conversations/{user_id}/messages")
async def read_history(
    user_id: str,
    after: str | None = Query(None, description="Cursor from next_cursor"),
    limit: int = Query(20, ge=1, le=100),
    reader: IConversationHistoryReader = Depends(
        requires_capability(IConversationHistoryReader)
    ),
) -> Any:
    """Past messages with one User (newest first, as the Platform pages)."""
    return _read(await reader.read_history(user_id, limit=limit, after=after))


# ── private reply (outbound transport) ───────────────────────────────────


@private_reply_router.post("/send-private-reply", response_model=MessageResult)
@map_send_errors("send private reply")
async def send_private_reply(
    body: PrivateReplyRequest,
    request: Request,
    context: InboxExecutionContext = Depends(get_inbox_execution_context),
    messenger: IMessenger = Depends(get_inbox_messenger),
) -> MessageResult:
    """DM the author of a comment (``send_text`` with a ``PrivateReply``).

    Meta allows one private reply per comment inside its window; the User
    must answer before a normal DM follows.
    """
    return await messenger.send_text(
        body.text,
        PrivateReply(comment_ref=_comment(context, body.comment_id)),
    )


__all__ = [
    "comment_controls_router",
    "conversation_reads_router",
    "private_reply_router",
]
