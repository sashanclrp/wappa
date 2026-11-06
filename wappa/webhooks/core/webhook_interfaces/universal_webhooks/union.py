"""The union of every universal webhook interface."""

from __future__ import annotations

from wappa.webhooks.core.webhook_interfaces.conversation_webhooks import (
    HistorySyncWebhook,
    InboxConnectionWebhook,
    IncomingCommentWebhook,
    MentionWebhook,
    MessageUpdateWebhook,
    OutboundEchoWebhook,
)
from wappa.webhooks.core.webhook_interfaces.universal_webhooks.call import CallWebhook
from wappa.webhooks.core.webhook_interfaces.universal_webhooks.custom import (
    CustomWebhook,
)
from wappa.webhooks.core.webhook_interfaces.universal_webhooks.error import ErrorWebhook
from wappa.webhooks.core.webhook_interfaces.universal_webhooks.inbound import (
    InboundMessageWebhook,
)
from wappa.webhooks.core.webhook_interfaces.universal_webhooks.status import (
    StatusWebhook,
)
from wappa.webhooks.core.webhook_interfaces.universal_webhooks.system import (
    SystemWebhook,
)

# Type union for all universal webhook interfaces
UniversalWebhook = (
    InboundMessageWebhook
    | CallWebhook
    | StatusWebhook
    | ErrorWebhook
    | SystemWebhook
    | CustomWebhook
    | MessageUpdateWebhook
    | IncomingCommentWebhook
    | MentionWebhook
    | OutboundEchoWebhook
    | HistorySyncWebhook
    | InboxConnectionWebhook
)
