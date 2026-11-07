"""
Identity resolver interface for mapping transport identifiers to canonical user ids.

The transport identifier delivered by a webhook (e.g. a WhatsApp ``wa_id``
phone number) is not always the identity host applications want to key their
caches, expiry triggers, or domain state by. Multi-channel apps typically
maintain a canonical platform user id (BSUID, account id, household id, …)
that survives across channels.

``IIdentityResolver`` is the single seam where Wappa asks the host: "given
this transport recipient in this Inbox, what id should I scope state under?".
The default
``PassthroughIdentityResolver`` returns the recipient unchanged, preserving
today's behavior. Host applications register their own resolver via
``WappaBuilder.with_identity_resolver`` (or ``Wappa.set_identity_resolver``)
to inject canonical-id lookups without modifying framework code.
"""

from abc import ABC, abstractmethod

from wappa.domain.inbox.identity import InboxRef


class IIdentityResolver(ABC):
    """
    Resolve a transport recipient identifier to a canonical user id.

    Implementations MUST be safe to call concurrently and SHOULD be cheap
    (sub-millisecond) on the hot path; if the lookup is expensive, cache
    inside the implementation.
    """

    @abstractmethod
    async def resolve(self, recipient: str, *, inbox_ref: InboxRef) -> str:
        """
        Map ``recipient`` to the canonical user id used for cache scoping.

        Args:
            recipient: Native delivery identifier from the API request or
                scheduled task. It can be numeric on any Platform, so its
                shape is no evidence of the Platform.
            inbox_ref: Qualified Inbox in which Wappa will address the
                recipient. It is runtime scope, not authority and not a cache
                namespace; two Platforms can share a raw ``inbox_id``.

        Returns:
            The canonical user id to use as ``user_id`` when scoping caches,
            expiry triggers, and other per-user state. Returning ``recipient``
            unchanged is valid and is the default behavior.
        """


class PassthroughIdentityResolver(IIdentityResolver):
    """Default resolver: returns the recipient unchanged."""

    async def resolve(self, recipient: str, *, inbox_ref: InboxRef) -> str:
        return recipient
