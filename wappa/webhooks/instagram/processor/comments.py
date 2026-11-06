"""Instagram ``comments`` and ``live_comments`` changes → ``IncomingCommentWebhook``."""

from __future__ import annotations

from typing import Any

from wappa.domain.inbox.identity import InboxRef
from wappa.domain.messaging_targets import CommentRef, PostRef
from wappa.webhooks.core.schema_drift import report_schema_drift
from wappa.webhooks.core.webhook_interfaces.conversation_webhooks import (
    CommentAuthor,
    CommentSource,
    IncomingCommentWebhook,
)
from wappa.webhooks.core.webhook_interfaces.universal_webhooks import UniversalWebhook
from wappa.webhooks.instagram.models import InstagramChange, InstagramCommentValue

from ._base import InstagramProcessorBase


class CommentsLaneMixin(InstagramProcessorBase):
    """Translate a comment change."""

    def _comment(
        self, change: InstagramChange, ref: InboxRef, meta: dict[str, Any]
    ) -> UniversalWebhook:
        value = InstagramCommentValue.model_validate(change.value)
        report_schema_drift(value, platform="instagram", logger=self.logger)
        comment_id = value.native_comment_id
        author = value.from_
        media = value.media
        return IncomingCommentWebhook(
            **meta,
            webhook_id=f"{change.field}:{comment_id}",
            comment_ref=CommentRef(inbox_ref=ref, comment_id=comment_id),
            post_ref=PostRef(inbox_ref=ref, media_id=media.id)
            if media and media.id
            else None,
            source=CommentSource(change.field),
            media_product_type=media.media_product_type if media else None,
            parent_comment_ref=CommentRef(inbox_ref=ref, comment_id=value.parent_id)
            if value.parent_id
            else None,
            author=CommentAuthor(
                author_id=author.id,
                username=author.username,
                self_scoped_id=author.self_ig_scoped_id,
            )
            if author
            else None,
            text=value.text,
            ad_id=media.ad_id if media else None,
            ad_title=media.ad_title if media else None,
        )
