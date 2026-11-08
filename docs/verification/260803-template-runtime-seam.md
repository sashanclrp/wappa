# Template runtime verification

Verified 2026-08-03: the Inbox-scoped Template transport implementation, ownership audit and offline checks below. No controlled Meta sends were available during this pass; provider certification was not established. The delivered contract snapshot is historical; current request/result rules belong to the [public contract](../public-contract.md#inbox-scoped-template-transport).

## Contract delivered

- `OutboundRuntime` resolves an Inbox-scoped `InboxTemplateTransport` without exposing credentials, HTTP clients, Messenger construction, handlers, or pipeline composition.
- The public request is a strict discriminated union for text, media-header, and location-header Templates. It accepts exactly one typed phone-number or BSUID Delivery Address and rejects Host Application fields.
- Marketing uses `/marketing_messages` by category default. Utility and authentication use `/messages`. The only marketing fallback is the named `cloud_messages_fallback` policy selected before I/O; there is no automatic cross-endpoint retry.
- Authentication Templates require a named method and reject regular and parent BSUID addresses.
- Results distinguish `accepted`, `rejected`, `transport_unavailable`, and `indeterminate`. `accepted` is invalid without a platform Message ID.
- The optional standalone Template HTTP adapter delegates to the same public capability and is absent unless explicitly enabled.

## Clean-break and ownership audit

The implementation removes the obsolete raw state/client aliases and duplicate surfaces encountered in this work:

- removed the shadow `wappa/sse.py` module; `wappa/sse/` is the sole SSE public package;
- removed status aliases and obsolete logger/session accessors;
- removed raw `app.state.http_session` and `app.state.media_download_client` access; `SessionLifecycle` is the sole client owner;
- removed unmanaged media-download client creation;
- removed optional event-dispatch request behavior and obsolete Template HTTP request models;
- removed the ignored user parameter from user-scoped state deletion;
- removed media payload creation from `MessageFactory`; `MediaFactory` is its single owner;
- removed the unused `I*Repository` contract family; `ICacheFactory` and the five type-specific `I*Cache` interfaces are the only persistence contracts;
- removed the compatibility-only Template status endpoint and response model;
- removed the unused `MessengerPlatform` enum and stale example aliases;
- renamed the ambiguous Template `override` switch to `routing_policy`.

Repository searches find no executable compatibility/deprecation/shim markers or references to the removed raw client aliases. Remaining mentions in ADRs, historical implementation records, and architecture notes describe an explicit clean-break rule or record already removed code.

## Automated evidence

| Gate | Result |
|---|---|
| `uv run ruff check .` | Pass |
| `uv run ruff format --check .` | Pass |
| `uv run pytest -q` | 402 passed |
| `uv run mypy wappa` | Pass; 332 source files, 0 errors |
| `vulture wappa --min-confidence 80` | Pass; no findings |
| `jscpd` at 20 lines / 120 tokens, excluding exports and generated examples | 35 structural clones; 3.59% duplicated lines |

The clone review removed the actionable competing media factory and unused repository contract hierarchy. Remaining clone groups are independent backend implementations, explicit WhatsApp payload schema shapes, one Universal Model shape, and one documentation example. They do not implement competing behavior or a second Template transport seam; merging them would couple independent adapters or weaken explicit platform validation. The generated CLI examples were excluded from clone metrics, but they are included in Ruff, strict mypy, and import/test verification.

## Provider evidence limit

No live credentials or Meta calls were available during this implementation pass. Certification required controlled non-bulk sends through `/messages` and `/marketing_messages` on an eligible account, with sanitized request/result identity and correlated statuses. Later Messenger-capability sends on both routes are recorded on 2026-11-05 in the [conversations ledger](261103-instagram-conversations-live-tests.md); they do not independently certify this Template Transport seam.
