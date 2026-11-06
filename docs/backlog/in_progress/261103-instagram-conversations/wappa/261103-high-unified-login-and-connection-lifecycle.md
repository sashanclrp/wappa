---
status: implemented_core_gate_b_passed_remaining_access_checks
urgency: high
owner: Wappa connection primitives and controlled consumer backend
depends_on: I01; complete live acceptance after gate A
last_reviewed: 2026-11-06
---

# Unified Login and connection lifecycle

## Code reality (2026-11-06)

Core Gate B passed on November 5: connection, real DM routing, replay rejection, cancellation and reconnect. Permission deselection and per-user deauthorize are not applicable to this Unified Login grant. Creator B-08 is unrun; independent-customer access and real credential revocation remain separate limitations. The unsupported Instagram deauthorize route was removed in 6cc8cf1.

See the [series plan](../plan.md), [capability matrix](../references/capability-matrix.md) and [live evidence](../tests/live-test-plan.md). Historical test results do not replace the remaining live gates.

## Context

The [grilling session C1–C3](../../../../sasha/grilling-sessions/261103-instagram-scope-and-extensions.md)
settled Wappa as reusable package infrastructure for a Host backend. Current
dashboard-generated credentials prove controlled testing, not self-service
onboarding. See the [series](../plan.md) and the actual
[Meta setup walkthrough](../references/setup.md).

## Scope

- Reusable Unified Login initiation/completion primitives, code exchange,
  authorized professional-account discovery and granted-scope validation.
- Register/persist/refresh canonical encrypted Inbox records through the
  existing authority; subscribe the account to selected core/extension fields.
- Required conversation readiness and optional extension readiness are distinct;
  missing publishing/analytics scopes do not disable authorized messaging.
- Cancellation, denial/missing scopes, partial failure, retry/reconnect,
  permission removal, token replacement, account revocation and deactivation.
- Consumer-backed login UI/redirect routes and backend orchestration to test the
  package end to end. No manual customer account-ID/token copying at this gate.

## Implementation notes and ownership

Wappa owns provider protocol/translation, account/scope/subscription operations,
credentials and errors. The Host owns authenticated operator/connection intent,
durable transactions, Owner/Channel mapping, web routes/UI and readiness state.
Dependency-injected primitives must be usable by Symphonai without adopting the
controlled example's persistence schema or UI. No new credential authority.

Bind callback completion to original authenticated intent and selected assets;
validate state/redirects and prevent one-use code/handoff replay. Multiple
concurrent account connections cannot attach to the wrong Host business.
Commit Host storage before directory refresh; directory presence alone does not
prove subscription/bootstrap success. Compensate/retry partial setup explicitly,
without creating a second token store or automatically reconnecting a revoked Inbox.

Use the chosen Unified Login token type/host and current application API version,
not token-prefix guessing or Instagram Login fallback. Discovery must return
authorized Instagram account IDs, not mistake the system user's `/me` ID for an
Inbox. Request optional extension permissions deliberately and verify actual
grants/assets; same Meta app/use case does not prove one grant covers all work.

Update connection architecture, public imports/config/error semantics and the
setup guide's separate app setup/GET/subscription/OAuth paths. I08 turns observed
steps into a version-checked reference. Actual app review/independent-customer
access requirements are gates, not local implementation workarounds.

## Out of scope

Publishing/analytics operations, hosting a business-specific account model in
Wappa, cross-app identity linking and Meta dashboard automation requiring an
invented permission to change production configuration.

## Open verification

Verify Business/Creator prerequisites, review/access requirements for the intended
audience, bootstrap needs, optional-scope changes and revocation signals against
the selected API. Never assert a never-scheduled-expiry token cannot be revoked.

## Exit criteria

- Real authorized Business/Creator paths connect and receive/respond using the
  selected capabilities without per-customer token/ID copying; any provider
  account restrictions are explicit and verified.
- Invalid/replayed state/code, cross-account intent, cancellation, partial
  consent, subscription failure and reconnect have deterministic tested outcomes.
- Rotation/revocation reaches subsequent Messenger and extension resolution;
  stale snapshots are not used as a permanent credential cache.
- Encrypted persistence and after-commit refresh demonstrated in the consumer;
  no secrets in browser artifacts, logs or setup/test records.
- Gate B runs after A and reports real access/review limitations honestly;
  app-role-only testing is insufficient for an independent-customer audience.
