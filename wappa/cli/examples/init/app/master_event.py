from wappa import WappaEventHandler
from wappa.webhooks import InboundMessageWebhook


class MasterEventHandler(WappaEventHandler):
    async def process_message(self, webhook: InboundMessageWebhook):
        await self.messenger.mark_as_read(webhook.message.message_id)
        await self.messenger.send_text("Welcome to Wappa", webhook.user.user_id)
