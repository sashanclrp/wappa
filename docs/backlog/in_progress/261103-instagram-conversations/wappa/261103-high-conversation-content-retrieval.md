---
status: pending
urgency: high
owner: Instagram content adapters
depends_on: I01, I02 media primitives, I04 qualified public references
---

# Explicit conversation-content retrieval

## Context

[R1 in the grilling session](../../../../sasha/grilling-sessions/261103-instagram-scope-and-extensions.md)
requires content and supported media bytes for consumer AI processing. A Post
Reference identifies media; it does not prove caption, image or complete metadata
was sent in a webhook. This is the final A capability slice in the [series](../plan.md).

## Scope

- Focused separately callable read capability for accessible post/media metadata,
  caption, permalink, native type, child media and available content references.
- Fetch an individual accessible comment, relevant comments/replies and child
  resources with explicit pagination rather than automatic full-account scans.
- Reuse I02's media lookup/download/stream/bytes path for sources exposed by the
  provider. Return honest unavailable/expired/private/deleted outcomes.
- Provide a consumer example that explicitly enriches a conversation then
  hands available bytes/text to a host-injected AI dependency or test double.

## Implementation notes and DDD

Keep a small public content capability hiding native endpoint/response errors,
credential/lifecycle details and pagination. It is not a pass-through route,
generic Graph proxy, content calendar or full media library service.
Use Inbox-qualified references consistently, keep processors pure, and expose
missing fields as absent. Verify fields/authorization per login setup and
resource type before making them required in public models.

Decouple metadata from bytes: a carousel can have several children, a shared
post may have only a URL, and ownership/access affect fetchability. Do not send
provider auth to arbitrary third-party hosts. A failed lookup must not prevent
the consumer from handling the original event; it receives an explicit outcome.
The consumer chooses timing, caching/business snapshots, AI and fallback policy.

## Out of scope

Conversation history sync, content publishing/scheduling, insights/attribution,
automatic enrichment in intake, general account-media crawling and AI models.

## Open verification

Verify exact available fields, pagination and URL refresh paths. Do not promise
downloadable bytes for every media reference or inaccessible third-party post.

## Exit criteria

- Controlled post, comment, carousel children and replies are fetched through
  the bound Inbox, and examples consume supported bytes without secret leakage.
- Tests cover pagination, absent fields, deletion/access denial, expired media,
  source constraints and cross-Inbox use.
- Processor tests prove zero content network I/O; reader failures do not invent
  metadata or corrupt the original normalized event.
- DDD/content responsibility, imports, errors and examples match I01/I02 seams.
