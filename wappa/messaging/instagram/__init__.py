"""Instagram Unified Login messaging adapter.

``InstagramMessenger`` is the Host-facing Instagram Platform Messenger
(``self.instagram`` on the handler); everything else in this package is
adapter internals.
"""

from .platform_messenger import InstagramMessenger

__all__ = ["InstagramMessenger"]
