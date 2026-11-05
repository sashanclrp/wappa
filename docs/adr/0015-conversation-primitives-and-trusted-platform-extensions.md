# Conversation primitives and trusted Platform extensions

Status note (2026-11-05): [ADR-0016](0016-one-messenger-method-per-action.md) supersedes the Instagram-specific send and sender-action methods and the separate interaction lane introduced here; shared actions use one Messenger method per action and `reply_comment` moved to `ICommentControls`.

Accepted scope decision, 2026-11-03. Implementation status (unreleased working
tree): the capabilities below are implemented — `InboxCredentialAccess` is the
supported trusted-adapter seam, `ICommentControls`/`IConversationContentReader`
are reached through `IMessenger.capability()`, and Instagram extension fields
register with `platform=PlatformType.INSTAGRAM`. Live certification is tracked
per capability in the series capability matrix. See the [Instagram PRD](../backlog/in_progress/261103-instagram-conversations/references/scope.md)
and [completed grilling session](../sasha/grilling-sessions/261103-instagram-scope-and-extensions.md).

Wappa owns Platform conversation mechanisms, including comment intake, replies,
private replies, content/media reads and comment-control API primitives. Hosts
own decisions about responses, moderation, AI, human takeover and durable
conversation history. Publishing, calendars and content/account analytics are
Host or extension domains. Excluding moderation policy does not exclude the
underlying hide/delete/enable-comment operations from Wappa's adapter scope.

Formalize the existing Symphonai pattern with a narrow supported credential
access capability for trusted backend adapters. Wappa retains encryption,
current-credential resolution and invalidation; extensions own extra provider
operations and client lifecycle. This deliberately allows a resolved bearer to
cross into a trusted adapter, replacing the intended absolute prohibition on
credentials leaving Wappa once that seam is implemented. It does not make the
internal directory/resolver a Host-owned or broadly supported API. The
alternative of forcing all extra provider calls through a Wappa-owned client
would expand Wappa's responsibility and displace working consumer adapters.

Additional Instagram fields enter the same authenticated callback through an
explicit registration seam; extension parsers and handlers own their domain
schemas. This avoids copying analytics/publishing models into conversation
contracts while retaining one signature/admission boundary. Pure processors,
qualified references, explicit capabilities and separate host policy remain
invariants. These seams and their migration guide landed together.
