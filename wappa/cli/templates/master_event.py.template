from wappa import WappaEventHandler
from wappa.webhooks import IncomingMessageWebhook

class MasterEventHandler(WappaEventHandler):
    
    async def process_message(self, webhook: IncomingMessageWebhook):
        await self.messenger.mark_as_read(webhook.message.message_id, webhook.user.user_id)
        await self.messenger.send_text("Wappa App ready", webhook.user.user_id)