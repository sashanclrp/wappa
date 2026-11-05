from wappa import WappaEventHandler
from wappa.domain.inbox import InboxRef
from wappa.messaging import DeliveryAddresses, DirectMessage
from wappa.webhooks import InboundMessageWebhook


class MasterEventHandler(WappaEventHandler):
    async def process_message(self, webhook: InboundMessageWebhook) -> None:
        assert self.messenger is not None
        await self.messenger.mark_as_read(webhook.message.message_id)
        await self.messenger.send_text(
            "Welcome to Wappa",
            DirectMessage(
                inbox_ref=InboxRef(
                    platform=self.messenger.platform, inbox_id=self.messenger.inbox_id
                ),
                addresses=DeliveryAddresses.of(webhook.user.user_id),
            ),
        )
