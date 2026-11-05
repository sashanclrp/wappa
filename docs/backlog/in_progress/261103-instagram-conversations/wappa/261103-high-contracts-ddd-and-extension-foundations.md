---
status: partial_baseline_remaining_pending
urgency: high
owner: Wappa domain, inbound runtime and public contract
decided_by: docs/sasha/grilling-sessions/261103-instagram-scope-and-extensions.md
---

# Contracts, DDD and extension foundations

## Context

Read the [series plan](../plan.md),
[completed grilling decisions](../../../../sasha/grilling-sessions/261103-instagram-scope-and-extensions.md)
and [detailed scope](../references/scope.md).
The current text adapter, DirectMessage and encrypted records exist. New event
lanes, PrivateReply, neutral results, supported credential access and Instagram
extension registration do not. Existing Symphonai bearer reuse is real but
depends on an internal resolver; formalize it rather than recreating it.

## Scope

- Define Inbox-qualified Comment/Post References and strict immutable
  Instagram-only PrivateReply targets. Preserve actual native identity and
  absent evidence; validate bound Inbox again at execution.
- Introduce typed message-update, interaction, comment and mention models,
  handler hooks and event-union/dispatch integration. Keep new message,
  delivery status, content change and system meanings distinct.
- Model comment dimensions independently: source, available placement/type,
  kind, parent evidence, author and text/time. Media-only mentions have no
  fabricated Comment or required DM User.
- Move shared results/evidence to neutral ownership and distinguish message,
  comment and control outcomes. Preserve existing WhatsApp imports only if
  deliberately retained/documented as stable exports, not accidental dependency.
- Provide a small public runtime capability for trusted adapters to resolve
  current active credentials/version using InboxRef. Keep internal directory
  methods private and source adaptation unchanged. Host authorization comes first.
- Add Platform-qualified Instagram field registration through exact-body
  authentication and whole-batch admission, reusing proven WA registry behavior
  where it fits. Extension parsers/handlers own extra domain schemas.

## Implementation notes and DDD improvements

Use domain/interface contracts with injected runtime/adapter implementations.
Assembly resolves current credentials and lifecycle; routes only adapt HTTP.
No `auto` authority, env fallback, raw bearer endpoint or Host-written directory
rows. Returned secrets stay in trusted backend adapter execution, never AI
arguments/browser/logs; rotation/deactivation affects subsequent resolution,
not calls already holding credentials.

Use optional non-abstract handler defaults for newly introduced lanes so existing
handlers need not fake behavior. The dispatcher has an exhaustive typed route;
capability discovery reflects implemented operations and accepted targets.
New hooks follow the existing Template Method logging/context discipline.
Public sends must honor advertised support or reject explicitly, never no-op.

Registration rejects built-in/conflicting field ownership, uses pure bounded
parsers, defines unknown-field outcomes and fails admission before any scheduling
when an admitted batch cannot be constructed. Extension events retain native
field/Platform/Inbox evidence without becoming generic untrusted broadcasts or
External Webhook Source events. Reuse one Instagram callback and explicit scope.

Update root/local glossary/architecture, context map, public imports and contract,
ADR-0015 implementation status and migration docs in the same changes. Audit
SSE, pipeline, background/expiry factories, generated examples and REST adapters
for target/result/event assumptions. A comment ID is never a DM message ID.

## Out of scope

Publishing/analytics implementations, Host moderation policy, general credential
export services, business identity mapping and extra public messaging Platforms.
No family-interface proliferation without concrete ownership pressure.

## Open verification

Finalize public capability/type names before consumer migration. Choose explicit
resource/result discriminators and extension failure mapping from real payloads.
Audit absent-User dispatch and cleanup without weakening existing message rules.
These are implementation decisions within settled scope, not missing product input.

## Exit criteria

- Wrong-Platform/Inbox targets and malformed models fail before I/O. Public
  resource kinds and absent author/parent evidence remain honest.
- Every hook dispatches once with correct context; new edits cannot become new
  messages or statuses. Existing handlers/WhatsApp tests continue to work.
- Credential capability tests prove active/current version, rotation,
  deactivation, integrity failure and unavailability without secret exposure.
- Signed mixed built-in/extension batches route correctly; invalid signatures
  perform zero parsing/resolution; admission failure schedules zero items.
- Supported imports, handler defaults, error semantics and consumer migration
  are documented; no host import of the internal resolver is newly prescribed.
- DDD graph and neutral result ownership match the actual implementation.
