"""Instagram Comment Controls: public replies, hide, unhide, delete, enable or disable.

Endpoints (Unified Login host ``graph.facebook.com``, v26.0):

- hide/unhide: ``POST /{comment-id}?hide=true|false`` → ``{"success": true}``
- delete: ``DELETE /{comment-id}`` (media owner only; not on Live)
- commenting: ``POST /{media-id}?comment_enabled=true|false`` (not on Live)

Destructive mutations are never retried. A successful control does not prove a
matching webhook will arrive. Host policy decides whether to call any of this.
"""

from __future__ import annotations

from wappa.domain.interfaces.conversation_capabilities import ICommentControls
from wappa.domain.messaging_targets import CommentRef, PostRef
from wappa.domain.results import (
    CommentControlOperation,
    CommentResult,
    ControlResult,
    OperationOutcome,
)
from wappa.messaging.meta.graph import GraphResponse
from wappa.schemas.core.types import PlatformType

from ..client import InstagramClient

COMMENT_REPLY_MAX = 2200


class InstagramCommentControls(ICommentControls):
    def __init__(self, graph: InstagramClient) -> None:
        self._graph = graph

    async def reply_comment(self, comment_ref: CommentRef, text: str) -> CommentResult:
        """Public reply: ``POST /{comment-id}/replies`` ``{"message"}`` → ``{"id"}``."""
        comment_id = comment_ref.resolve(self._graph.inbox_ref)
        if not text.strip():
            raise ValueError("Instagram comment reply must not be empty")
        if len(text) > COMMENT_REPLY_MAX:
            raise ValueError(
                f"Instagram comment reply is {len(text)} characters; "
                f"limit is {COMMENT_REPLY_MAX}"
            )
        response = await self._graph.request(
            "POST",
            f"{comment_id}/replies",
            json={"message": text},
            operation="Instagram public comment reply",
        )
        reply_id = response.body.get("id") if response.ok else None
        outcome = response.outcome
        if outcome is OperationOutcome.ACCEPTED and not (
            isinstance(reply_id, str) and reply_id
        ):
            outcome = OperationOutcome.INDETERMINATE
        accepted = outcome is OperationOutcome.ACCEPTED
        return CommentResult(
            outcome=outcome,
            platform=PlatformType.INSTAGRAM,
            inbox_id=self._graph.account_id,
            comment_id=reply_id if accepted else None,
            parent_comment_id=comment_id,
            error=None
            if accepted
            else response.error or "Instagram comment reply outcome is unknown",
            error_code=None if accepted else response.error_code or "INDETERMINATE",
            retry_after=response.retry_after,
            platform_response=response.body or None,
        )

    def _result(
        self,
        operation: CommentControlOperation,
        resource_id: str,
        response: GraphResponse,
    ) -> ControlResult:
        outcome = response.outcome
        if (
            outcome is OperationOutcome.ACCEPTED
            and response.body.get("success") is not True
        ):
            outcome = OperationOutcome.INDETERMINATE
        return ControlResult(
            outcome=outcome,
            platform=PlatformType.INSTAGRAM,
            inbox_id=self._graph.account_id,
            operation=operation,
            resource_id=resource_id,
            error=response.error if outcome is not OperationOutcome.ACCEPTED else None,
            error_code=response.error_code
            if outcome is not OperationOutcome.ACCEPTED
            else None,
            retry_after=response.retry_after,
            platform_response=response.body or None,
        )

    async def _set_hidden(self, ref: CommentRef, hidden: bool) -> ControlResult:
        comment_id = ref.resolve(self._graph.inbox_ref)
        op = CommentControlOperation.HIDE if hidden else CommentControlOperation.UNHIDE
        response = await self._graph.request(
            "POST",
            comment_id,
            params={"hide": "true" if hidden else "false"},
            operation=f"Instagram {op.value} comment",
        )
        return self._result(op, comment_id, response)

    async def hide_comment(self, comment_ref: CommentRef) -> ControlResult:
        return await self._set_hidden(comment_ref, True)

    async def unhide_comment(self, comment_ref: CommentRef) -> ControlResult:
        return await self._set_hidden(comment_ref, False)

    async def delete_comment(self, comment_ref: CommentRef) -> ControlResult:
        comment_id = comment_ref.resolve(self._graph.inbox_ref)
        response = await self._graph.request(
            "DELETE", comment_id, operation="Instagram delete comment"
        )
        return self._result(CommentControlOperation.DELETE, comment_id, response)

    async def set_comments_enabled(
        self, post_ref: PostRef, enabled: bool
    ) -> ControlResult:
        media_id = post_ref.resolve(self._graph.inbox_ref)
        op = (
            CommentControlOperation.ENABLE_COMMENTS
            if enabled
            else CommentControlOperation.DISABLE_COMMENTS
        )
        response = await self._graph.request(
            "POST",
            media_id,
            params={"comment_enabled": "true" if enabled else "false"},
            operation=f"Instagram {op.value}",
        )
        return self._result(op, media_id, response)
