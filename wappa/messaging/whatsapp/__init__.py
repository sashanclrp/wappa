"""WhatsApp Cloud API adapter.

``WhatsAppMessenger`` is the Host-facing WhatsApp Platform Messenger
(``self.whatsapp`` on the handler); everything else in this package is adapter
internals.
"""

from .platform_messenger import WhatsAppMessenger

__all__ = ["WhatsAppMessenger"]
