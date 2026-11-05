"""Instagram Comment Controls and explicit post/comment reads.

Endpoints (Unified Login host ``graph.facebook.com``, v26.0):

- hide/unhide: ``POST /{comment-id}?hide=true|false`` → ``{"success": true}``
- delete: ``DELETE /{comment-id}`` (media owner only; not on Live)
- commenting: ``POST /{media-id}?comment_enabled=true|false`` (not on Live)
- reads: ``GET /{media-id}``, ``GET /{comment-id}``,
  ``GET /{media-id}/comments`` (top-level, ≤ 50/page),
  ``GET /{comment-id}/replies``, and mentioned media/comment lookups through
  ``GET /{ig-user-id}?fields=mentioned_media.media_id(...)``.

Destructive mutations are never retried. A successful control does not prove a
matching webhook will arrive. Host policy decides whether to call any of this.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from wappa.domain.inbox.identity import InboxRef
from wappa.domain.interfaces.conversation_capabilities import (
    CommentContent,
    ContentPage,
    ICommentControls,
    IConversationContentReader,
    PostChild,
    PostContent,
    ReadOutcome,
    ReadResult,
)
from wappa.domain.messaging_targets import CommentRef, PostRef
from wappa.domain.results import (
    CommentControlOperation,
    CommentResult,
    ControlResult,
    OperationOutcome,
)
from wappa.schemas.core.types import PlatformType

from .graph import GraphResponse, InstagramGraphClient

POST_FIELDS = (
    "id,caption,media_type,media_product_type,media_url,permalink,thumbnail_url,"
    "timestamp,username,comments_count,like_count,is_comment_enabled,"
    "children{id,media_type,media_url,thumbnail_url}"
)
COMMENT_FIELDS = (
    "id,text,timestamp,username,from{id,username},parent_id,hidden,like_count,media{id}"
)
MENTIONED_MEDIA_FIELDS = (
    "id,caption,media_type,media_url,permalink,timestamp,username,comments_count,"
    "like_count"
)
MAX_COMMENT_PAGE = 50


def _when(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("+0000", "+00:00"))
    except ValueError:
        return None


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _read_failure[T](response: GraphResponse) -> ReadResult[T]:
    code = response.native_code
    if response.outcome is OperationOutcome.INDETERMINATE:
        outcome = ReadOutcome.UNAVAILABLE
    elif response.error_code in ("100/33",) or response.status_code == 404:
        outcome = ReadOutcome.NOT_FOUND
    elif code in (10, 190, 200) or response.status_code in (401, 403):
        outcome = ReadOutcome.ACCESS_DENIED
    else:
        outcome = ReadOutcome.REJECTED
    return ReadResult(
        outcome=outcome, error=response.error, error_code=response.error_code
    )


def _post(ref: PostRef, body: dict[str, Any]) -> PostContent:
    children_raw = body.get("children")
    children: list[PostChild] = []
    if isinstance(children_raw, dict):
        for child in children_raw.get("data", []) or []:
            if isinstance(child, dict) and _str(child.get("id")):
                children.append(
                    PostChild(
                        media_id=child["id"],
                        media_type=_str(child.get("media_type")),
                        media_url=_str(child.get("media_url")),
                        thumbnail_url=_str(child.get("thumbnail_url")),
                        permalink=_str(child.get("permalink")),
                    )
                )
    enabled = body.get("is_comment_enabled")
    return PostContent(
        post_ref=ref,
        media_type=_str(body.get("media_type")),
        media_product_type=_str(body.get("media_product_type")),
        caption=_str(body.get("caption")),
        permalink=_str(body.get("permalink")),
        media_url=_str(body.get("media_url")),
        thumbnail_url=_str(body.get("thumbnail_url")),
        timestamp=_when(body.get("timestamp")),
        username=_str(body.get("username")),
        comments_count=_int(body.get("comments_count")),
        like_count=_int(body.get("like_count")),
        is_comment_enabled=enabled if isinstance(enabled, bool) else None,
        children=tuple(children),
        raw=body,
    )


def _comment(inbox_ref: InboxRef, body: dict[str, Any]) -> CommentContent | None:
    comment_id = _str(body.get("id"))
    if not comment_id:
        return None
    author = _dict(body.get("from"))
    media = _dict(body.get("media"))
    hidden = body.get("hidden")
    return CommentContent(
        comment_ref=CommentRef(inbox_ref=inbox_ref, comment_id=comment_id),
        text=_str(body.get("text")),
        timestamp=_when(body.get("timestamp")),
        author_id=_str(author.get("id")),
        author_username=_str(author.get("username")) or _str(body.get("username")),
        parent_comment_id=_str(body.get("parent_id")),
        media_id=_str(media.get("id")),
        hidden=hidden if isinstance(hidden, bool) else None,
        like_count=_int(body.get("like_count")),
        raw=body,
    )


def _page(inbox_ref: InboxRef, body: dict[str, Any]) -> ContentPage[CommentContent]:
    items = [
        parsed
        for raw in body.get("data", []) or []
        if isinstance(raw, dict) and (parsed := _comment(inbox_ref, raw)) is not None
    ]
    paging = _dict(body.get("paging"))
    cursors = _dict(paging.get("cursors"))
    after = _str(cursors.get("after")) if paging.get("next") else None
    return ContentPage[CommentContent](items=tuple(items), next_cursor=after)


COMMENT_REPLY_MAX = 2200


class InstagramCommentControls(ICommentControls):
    def __init__(self, graph: InstagramGraphClient) -> None:
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


class InstagramContentReader(IConversationContentReader):
    def __init__(self, graph: InstagramGraphClient) -> None:
        self._graph = graph

    async def get_post(self, post_ref: PostRef) -> ReadResult[PostContent]:
        media_id = post_ref.resolve(self._graph.inbox_ref)
        response = await self._graph.request(
            "GET",
            media_id,
            params={"fields": POST_FIELDS},
            operation="Instagram post read",
        )
        if not response.ok:
            return _read_failure(response)
        return ReadResult(
            outcome=ReadOutcome.FOUND, value=_post(post_ref, response.body)
        )

    async def get_comment(self, comment_ref: CommentRef) -> ReadResult[CommentContent]:
        comment_id = comment_ref.resolve(self._graph.inbox_ref)
        response = await self._graph.request(
            "GET",
            comment_id,
            params={"fields": COMMENT_FIELDS},
            operation="Instagram comment read",
        )
        if not response.ok:
            return _read_failure(response)
        parsed = _comment(self._graph.inbox_ref, response.body)
        if parsed is None:
            return ReadResult(
                outcome=ReadOutcome.UNAVAILABLE,
                error="provider response carried no comment ID",
                error_code="MALFORMED",
            )
        return ReadResult(outcome=ReadOutcome.FOUND, value=parsed)

    async def _list(
        self, path: str, *, after: str | None, limit: int, operation: str
    ) -> ReadResult[ContentPage[CommentContent]]:
        if not 1 <= limit <= MAX_COMMENT_PAGE:
            raise ValueError(f"limit must be between 1 and {MAX_COMMENT_PAGE}")
        params: dict[str, Any] = {"fields": COMMENT_FIELDS, "limit": limit}
        if after:
            params["after"] = after
        response = await self._graph.request(
            "GET", path, params=params, operation=operation
        )
        if not response.ok:
            return _read_failure(response)
        return ReadResult(
            outcome=ReadOutcome.FOUND, value=_page(self._graph.inbox_ref, response.body)
        )

    async def list_comments(
        self, post_ref: PostRef, *, after: str | None = None, limit: int = 25
    ) -> ReadResult[ContentPage[CommentContent]]:
        media_id = post_ref.resolve(self._graph.inbox_ref)
        return await self._list(
            f"{media_id}/comments",
            after=after,
            limit=limit,
            operation="Instagram comments read",
        )

    async def list_replies(
        self, comment_ref: CommentRef, *, after: str | None = None, limit: int = 25
    ) -> ReadResult[ContentPage[CommentContent]]:
        comment_id = comment_ref.resolve(self._graph.inbox_ref)
        return await self._list(
            f"{comment_id}/replies",
            after=after,
            limit=limit,
            operation="Instagram replies read",
        )

    async def get_mentioned_post(self, post_ref: PostRef) -> ReadResult[PostContent]:
        """Read media where the account was mentioned (often not owned)."""
        media_id = post_ref.resolve(self._graph.inbox_ref)
        response = await self._graph.request(
            "GET",
            self._graph.account_id,
            params={
                "fields": f"mentioned_media.media_id({media_id}){{{MENTIONED_MEDIA_FIELDS}}}"
            },
            operation="Instagram mentioned media read",
        )
        if not response.ok:
            return _read_failure(response)
        body = response.body.get("mentioned_media")
        if not isinstance(body, dict):
            return ReadResult(
                outcome=ReadOutcome.NOT_FOUND, error="mentioned media not returned"
            )
        return ReadResult(outcome=ReadOutcome.FOUND, value=_post(post_ref, body))

    async def get_mentioned_comment(
        self, comment_ref: CommentRef
    ) -> ReadResult[CommentContent]:
        """Read a comment (on another account's media) that mentions this one."""
        comment_id = comment_ref.resolve(self._graph.inbox_ref)
        response = await self._graph.request(
            "GET",
            self._graph.account_id,
            params={
                "fields": f"mentioned_comment.comment_id({comment_id})"
                "{id,text,timestamp,like_count,media{id}}"
            },
            operation="Instagram mentioned comment read",
        )
        if not response.ok:
            return _read_failure(response)
        body = response.body.get("mentioned_comment")
        parsed = (
            _comment(self._graph.inbox_ref, body) if isinstance(body, dict) else None
        )
        if parsed is None:
            return ReadResult(
                outcome=ReadOutcome.NOT_FOUND, error="mentioned comment not returned"
            )
        return ReadResult(outcome=ReadOutcome.FOUND, value=parsed)
