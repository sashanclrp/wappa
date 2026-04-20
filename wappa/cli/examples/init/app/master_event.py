from wappa import WappaEventHandler
from wappa.webhooks import IncomingMessageWebhook


class MasterEventHandler(WappaEventHandler):
    async def process_message(self, webhook: IncomingMessageWebhook):
        # Prefer the WhatsApp numeric WA ID for outbound replies until BSUID
        # sending is enabled for the account. `user.user_id` resolves to BSUID.
        wa_id = webhook.whatsapp.wa_id if webhook.whatsapp else None
        recipient = wa_id or webhook.user.phone_number or webhook.user.user_id

        await self.messenger.mark_as_read(webhook.message.message_id)
        await self.messenger.send_text("Welcome to Wappa", recipient)
