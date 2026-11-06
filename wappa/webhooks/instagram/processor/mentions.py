"""Instagram ``mentions`` changes → ``MentionWebhook``."""

from __future__ import annotations

from typing import Any

from wappa.domain.inbox.identity import InboxRef
from wappa.domain.messaging_targets import CommentRef, PostRef
from wappa.webhooks.core.schema_drift import report_schema_drift
from wappa.webhooks.core.webhook_interfaces.conversation_webhooks import (
    MentionSubject,
    MentionWebhook,
)
from wappa.webhooks.core.webhook_interfaces.universal_webhooks import UniversalWebhook
from wappa.webhooks.instagram.models import InstagramChange, InstagramMentionValue

from ._base import InstagramProcessorBase


class MentionsLaneMixin(InstagramProcessorBase):
    """Translate a mention change."""

    def _mention(
        self, change: InstagramChange, ref: InboxRef, meta: dict[str, Any]
    ) -> UniversalWebhook:
        mention = InstagramMentionValue.model_validate(change.value)
        report_schema_drift(mention, platform="instagram", logger=self.logger)
        return MentionWebhook(
            **meta,
            webhook_id=f"mention:{mention.media_id}:{mention.comment_id or '-'}",
            subject=MentionSubject.COMMENT
            if mention.comment_id
            else MentionSubject.MEDIA,
            post_ref=PostRef(inbox_ref=ref, media_id=mention.media_id),
            comment_ref=CommentRef(inbox_ref=ref, comment_id=mention.comment_id)
            if mention.comment_id
            else None,
        )
