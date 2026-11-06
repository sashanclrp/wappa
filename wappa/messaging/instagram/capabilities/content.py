"""Explicit Instagram post and comment reads.

Endpoints (Unified Login host ``graph.facebook.com``, v26.0):

- reads: ``GET /{media-id}``, ``GET /{comment-id}``,
  ``GET /{media-id}/comments`` (top-level, ≤ 50/page),
  ``GET /{comment-id}/replies``, and mentioned media/comment lookups through
  ``GET /{ig-user-id}?fields=mentioned_media.media_id(...)``.

Host policy decides whether to call any of this.
"""

from __future__ import annotations

from typing import Any

from wappa.domain.interfaces.conversation_capabilities import (
    CommentContent,
    ContentPage,
    IConversationContentReader,
    PostContent,
    ReadOutcome,
    ReadResult,
)
from wappa.domain.messaging_targets import CommentRef, PostRef

from ..client import InstagramClient
from ..errors import read_failure
from .content_parse import parse_comment, parse_page, parse_post

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


class InstagramContentReader(IConversationContentReader):
    def __init__(self, graph: InstagramClient) -> None:
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
            return read_failure(response)
        return ReadResult(
            outcome=ReadOutcome.FOUND, value=parse_post(post_ref, response.body)
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
            return read_failure(response)
        parsed = parse_comment(self._graph.inbox_ref, response.body)
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
            return read_failure(response)
        return ReadResult(
            outcome=ReadOutcome.FOUND,
            value=parse_page(self._graph.inbox_ref, response.body),
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
            return read_failure(response)
        body = response.body.get("mentioned_media")
        if not isinstance(body, dict):
            return ReadResult(
                outcome=ReadOutcome.NOT_FOUND, error="mentioned media not returned"
            )
        return ReadResult(outcome=ReadOutcome.FOUND, value=parse_post(post_ref, body))

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
            return read_failure(response)
        body = response.body.get("mentioned_comment")
        parsed = (
            parse_comment(self._graph.inbox_ref, body)
            if isinstance(body, dict)
            else None
        )
        if parsed is None:
            return ReadResult(
                outcome=ReadOutcome.NOT_FOUND, error="mentioned comment not returned"
            )
        return ReadResult(outcome=ReadOutcome.FOUND, value=parsed)
