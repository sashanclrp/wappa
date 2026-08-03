# Wappa Template Runtime Seam — Verification Record

**Date:** 2026-08-03
**Scope:** Wappa workstream of the Wappa–Symphonai Template runtime seam PRD
**Engineering status:** Complete
**Provider release certification:** Pending controlled Meta sends

## Contract delivered

- `OutboundRuntime` resolves an Inbox-scoped `InboxTemplateTransport` without
  exposing credentials, HTTP clients, Messenger construction, handlers, or
  pipeline composition.
- The public request is a strict discriminated union for text, media-header,
  and location-header Templates. It accepts exactly one typed phone-number or
  BSUID Delivery Address and rejects Host Application fields.
- Marketing uses `/marketing_messages` by category default. Utility and
  authentication use `/messages`. The only marketing fallback is the named
  `cloud_messages_fallback` policy selected before I/O; there is no automatic
  cross-endpoint retry.
- Authentication Templates require a named method and reject regular and
  parent BSUID addresses.
- Results distinguish `accepted`, `rejected`, `transport_unavailable`, and
  `indeterminate`. `accepted` is invalid without a platform Message ID.
- The optional standalone Template HTTP adapter delegates to the same public
  capability and is absent unless explicitly enabled.

## Clean-break and ownership audit

The implementation removes the obsolete raw state/client aliases and duplicate
surfaces encountered in this work:

- removed the shadow `wappa/sse.py` module; `wappa/sse/` is the sole SSE public
  package;
- removed status aliases and obsolete logger/session accessors;
- removed raw `app.state.http_session` and `app.state.media_download_client`
  access; `SessionLifecycle` is the sole client owner;
- removed unmanaged media-download client creation;
- removed optional event-dispatch request behavior and obsolete Template HTTP
  request models;
- removed the ignored user parameter from user-scoped state deletion;
- removed media payload creation from `MessageFactory`; `MediaFactory` is its
  single owner;
- renamed the ambiguous Template `override` switch to `routing_policy`.

Repository searches find no executable compatibility/deprecation/shim markers
or references to the removed raw client aliases. Remaining mentions in ADRs,
historical implementation records, and architecture notes describe an explicit
clean-break rule or record already removed code.

## Automated evidence

| Gate | Result |
|---|---|
| `uv run ruff check .` | Pass |
| `uv run ruff format --check .` | Pass |
| `uv run pytest -q` | 402 passed |
| Strict mypy on the new transport, lifecycle, expiry composition, and Template route adapter | Pass; 4 source files |
| `vulture` at 80% confidence | No actionable finding after excluding abstract/protocol signatures and the type-check-only `CronConfig` import |
| `jscpd` at 20 lines / 120 tokens, excluding exports and generated examples | 36 structural clones; 3.56% duplicated lines |

The clone review removed the actionable duplicate media factory. Remaining
clone groups are backend-specific persistence adapter implementations, repeated
provider webhook schema shapes, one universal-model shape, and one documentation
example. They are separate contract representations, not parallel Template
transport implementations. Sharing those shapes would couple independent
adapters or weaken explicit provider validation; they are therefore not treated
as a Wappa Template seam or behavior duplication.

The repository-wide `uv run mypy wappa` baseline is not green: it reports 793
errors across 142 files. The new and materially changed seam files pass strict
mypy, but this record does not misrepresent the unrelated repository-wide type
backlog as resolved.

## Provider certification still required

The PRD's Meta API compliance gate remains blocking for release certification.
Before publishing the Wappa release, run one controlled non-bulk send through
`/messages` and one through `/marketing_messages` on an eligible account, then
record the sanitized endpoint, request shape, platform Message ID, returned
identity evidence, and correlated status webhook. No live credentials or
provider calls were available during this implementation pass.
