---
version: 1.0.0
last_reviewed: 2026-08-30
status: done
author: sasha
urgency: high
owner: Wappa API and application builder
blocked_by: encrypted Inbox Directory
decided_by: docs/grill-me-sessions/260829_wappa-v0.27.0-multi-inbox-hardening.md
---

# Inbox-scoped HTTP execution and routing modes

## Context

Webhook intake derives Inbox identity from authenticated Platform input. Wappa's
own HTTP operations have no Meta callback payload, so an authorized caller must
select the Inbox with `X-Wappa-Inbox-ID`.

The first implementation slice added that header through global middleware and
applied it broadly to `/api/whatsapp/*`. This overreaches. Static limits and
local validators do not need directory access, while media lookup, Template
information, state operations, and Inbox-specific health do.

The candidate also retains `auto` routing and warning-based precedence. The
settled design has only `legacy` and `explicit` authority modes.

## Code reality

Already present:

- Header format checks, existence checks, and per-request context reset.
- Explicit mode can boot without `WP_PHONE_ID` and `WP_BID`.
- A settings store can provide one default Inbox.
- Outbound runtime and Messenger factories accept an explicit Inbox.
- Credential invalidation clears two outbound cache layers.

Must change:

- Replace Host-defined credential-store validation with Wappa's directory.
- Resolve one `InboxExecutionContext`; avoid repeated lookup in middleware and
  client factories.
- Move the Inbox requirement from path-prefix middleware to capability routers
  or route dependencies.
- Remove `auto` and reject mixed configuration.
- Derive Template WABA from the canonical Inbox record.
- Remove demonstration send endpoints from production routes.

## Scope

- Define and build one validated `InboxExecutionContext` per Inbox-dependent
  HTTP request.
- Classify every WhatsApp HTTP operation as Inbox-dependent or local-only.
- Apply the header only where the operation needs Inbox capabilities.
- Keep Host authentication and authorization separate from scope selection.
- Define exact legacy and explicit startup contracts.
- Use the same runtime construction after either mode supplies a canonical
  record.
- Update health data and migration errors to name the active mode.

## Out of scope

- Defining Host permissions, roles, or Owner authorization.
- Adding Owner to Wappa's request context.
- Accepting a caller-supplied WABA alongside the Inbox header.
- Keeping `auto` as a third compatibility mode.
- Reworking programmatic outbound entry points beyond making them use the same
  internal resolver and typed errors.

## Inbox Execution Context

The HTTP boundary resolves:

```python
class InboxExecutionContext:
    inbox_ref: InboxRef
    # Internal capabilities required by the route family.
```

It may contain a client, Messenger, media service, Template transport, Cache
Factory, or other internal capability. It must not expose decrypted access
tokens to route functions or callers.

Resolution order for an Inbox-dependent WhatsApp route:

1. Host authentication and authorization run according to the mounted Wappa
   authentication configuration.
2. Read `X-Wappa-Inbox-ID`.
3. Combine it with the route's known Platform, WhatsApp.
4. In legacy mode only, use the settings-backed default if the header is absent.
5. Resolve and validate the active record through the Inbox Directory.
6. Build the required capabilities once.
7. Pass the context through FastAPI dependencies to the route.

The header selects runtime scope and proves only that Wappa knows an active
Inbox. It grants no permission. Public docs must state this beside every header
example.

Internal non-HTTP entry points validate their `InboxRef` at their own boundary.
They do not trust an ambient ContextVar.

## Route capability matrix

| Operation family | Inbox required | Reason |
| --- | ---: | --- |
| Send text | yes | Selects Meta sender, token, and event scope |
| Mark read or typing | yes | Calls Meta for the selected phone number |
| Send image, video, audio, document, or sticker | yes | Selects sender, token, media handling, and event scope |
| Send buttons, list, or CTA | yes | Selects sender, token, and event scope |
| Send contact, location, or location request | yes | Selects sender, token, and event scope |
| Send text-header, media-header, or location-header Template | yes | Selects credentials and Template transport |
| Upload, inspect, download, or delete media | yes | Metadata resolution uses the selected token; upload/delete mutate Meta assets |
| Get Template by ID/name, list Templates, or get namespace | yes | Uses the selected token and record WABA |
| Inbox-specific WhatsApp health | yes | Constructs Inbox-specific Meta capabilities |
| State Handler set, get, or delete | yes | Reads or mutates Inbox and User state |
| Validate contact or coordinates locally | no | Pure local validation |
| Return text, media, interactive, or Template limits | no | Static/local values |
| Root health, docs, or OpenAPI | no | Application-level or documentation response |

Local-only routes ignore a supplied Inbox header. They do not validate it, bind
it, or read the directory. An unknown header cannot make a local validation
route fail.

Media download remains Inbox-dependent even if the final temporary URL does not
need authentication. Wappa first resolves the media object through Meta with the
selected Inbox token.

Template information routes accept no independent WABA argument. They load
`platform_account_id` from the selected canonical Inbox record. This prevents a
caller from selecting Inbox A and WABA B.

Remove `/send-complex-buttons` and `/send-menu-list` from production routing.
Keep the demonstration code in examples.

## Routing modes

```python
class InboxRoutingMode(StrEnum):
    LEGACY = "legacy"
    EXPLICIT = "explicit"
```

Omitting the setting defaults to legacy for existing single-Inbox users. There
is no `auto` member.

### Legacy mode

Legacy mode requires the complete bundle:

```text
WP_ACCESS_TOKEN
WP_PHONE_ID
WP_BID
```

The settings adapter creates the same canonical encrypted-capability input used
by the runtime. It is the only component allowed to read these variables.

`WP_PHONE_ID` supplies the one WhatsApp Inbox and default HTTP selection.
`WP_BID` supplies its Platform Account. `WP_ACCESS_TOKEN` supplies the bearer
credential used by the WhatsApp adapter. After construction, middleware,
Messenger, cache, events, webhook routing, and health code do not read those
variables directly.

A header may repeat the configured `WP_PHONE_ID`. A different header resolves
to no active legacy record and returns 404. With no header, Wappa uses the one
legacy default.

Legacy mode rejects `IInboxDirectorySource`. A partial environment bundle fails
startup.

### Explicit mode

Explicit mode requires:

```text
IInboxDirectorySource
SYSTEM_TOKEN_ENC_KEY
```

It rejects any of `WP_ACCESS_TOKEN`, `WP_PHONE_ID`, or `WP_BID`. It has no
default Inbox, so every Inbox-dependent HTTP operation requires the header.

Supplying a source without selecting explicit mode fails startup with a direct
configuration message. No warning or precedence rule chooses the credential
authority.

The Meta callback variables are separate from these Inbox routing modes.
`META_APP_SECRET` and `WP_WEBHOOK_VERIFY_TOKEN` may be required in either mode
when the WhatsApp callback is mounted.

## Health and diagnostics

Application health reports:

- selected Inbox Routing Mode;
- whether the Inbox Directory is configured and reachable;
- whether a legacy default Inbox exists, without revealing its token;
- Meta callback configuration readiness when the callback is mounted; and
- safe directory dependency failures.

Do not return tokens, encrypted envelopes, App Secrets, encryption keys, full
records, or raw exception strings.

Local root health must not fail solely because an Inbox header is absent.
Inbox-specific WhatsApp health resolves a context and follows the route matrix.

## Failure behavior

| Condition | Status |
| --- | ---: |
| Inbox-dependent route has no header and no legacy default | 400 |
| Header format is invalid | 400 |
| Healthy directory confirms unknown or inactive Inbox | 404 |
| Directory, source, cache, or decrypt operation unavailable | 503 |
| Local-only route receives any Inbox header | normal local response |

Format validation runs before directory lookup. Host authorization failures use
the Host/Auth plugin's status and do not become directory errors.

## Implementation notes

- Attach dependencies to capability routers or route groups. Do not grow a
  path allowlist in global middleware.
- Build one context per request and reuse it. `get_whatsapp_client`, media
  handlers, Template dependencies, and state services must not each resolve the
  same record.
- ContextVars may support logging, but they are not the source of truth passed
  into factories.
- Bind and reset any ambient Inbox context with a token in `finally`.
- Keep the route's Platform fixed as WhatsApp for v0.27. The header does not
  need a Platform field because the route already supplies it.
- Programmatic Messenger, Template, expiry, cron, and external-event paths use
  `InboxRef` directly and construct their own validated context.

## Verification

For every route family, test header present, absent, malformed, unknown,
inactive, directory unavailable, and valid legacy default where applicable.

Tests must also prove:

- Host authorization runs before Inbox resolution where the route requires it.
- A valid Inbox header alone grants no permission.
- Each Inbox-dependent request calls the directory once.
- Media download uses the selected Inbox for metadata lookup.
- Template information derives WABA only from the record.
- Local limits and validators ignore malformed and unknown headers without a
  directory call.
- Root health, docs, and OpenAPI need no Inbox.
- No Inbox context leaks between sequential requests on one worker.
- Legacy mode accepts only a complete bundle and has one default.
- Explicit mode rejects every legacy Inbox environment variable.
- Source-without-explicit and source-plus-legacy configurations fail startup.
- Health reports the selected mode and redacts all secrets.
- Removed demonstration routes return 404 while their examples remain usable.

## Documentation obligations

- Add Inbox Execution Context and Inbox Routing Mode to the DDD glossary.
- Document the route matrix and header semantics in the public contract.
- Update OpenAPI descriptions so the header does not read like authorization.
- Update `.env.example`, CLI templates, README, and migration notes for the two
  modes and their mutually exclusive settings.
- Remove `auto`, custom credential store examples, global path-prefix rules,
  caller-supplied WABA, and production example sends from docs.

## Open questions

None. The route matrix, header meaning, one-context rule, and routing-mode
configuration are settled.

## Exit criteria

- Every Inbox-dependent route resolves one qualified Inbox Execution Context.
- Local-only routes never depend on Inbox Directory health.
- The complete WhatsApp operation matrix has tests and public documentation.
- Template and media services resolve the correct Inbox and Platform Account.
- Only `legacy` and `explicit` modes exist.
- Mixed or incomplete credential configuration fails startup.
- No component beyond the legacy settings adapter reads `WP_PHONE_ID`,
  `WP_BID`, or `WP_ACCESS_TOKEN`.
- Header selection and Host authorization remain separate concerns.
- All route, mode, health, and redaction tests pass.
