---
status: implemented_pending_live_gates
urgency: high
owner: Wappa interaction transport and consumer example
depends_on: I01, relevant I02 message families
last_reviewed: 2026-11-06
---

# Interactions and a host-owned Conversational Flow

## Code reality (2026-11-06)

Form happy path, Other branch, invalid-email validation, buttons, quick replies, cards and carousel taps have live evidence. Resume/cancel and repeated/stale action scenarios need complete evidence; concurrent Users and the same User across Inboxes remain open.

See the [series plan](../plan.md), [capability matrix](../references/capability-matrix.md) and [live evidence](../tests/live-test-plan.md). Historical test results do not replace the remaining live gates.

## Context

Follow the [series](../plan.md) and
[grilling decisions W2/S1](../../../../sasha/grilling-sessions/261103-instagram-scope-and-extensions.md).
Developers need portable interaction evidence, not WhatsApp Template terminology
or a Platform-specific payload parser in every consumer Score.

## Scope

- Quick Replies, Button Messages (including supported URL actions), Message
  Cards and Message Carousels through the Messenger facade with DirectMessage.
- Normalize quick-reply messages with structured selection; standalone postbacks
  use the dedicated interaction lane. Preserve action identity/source evidence.
- Build an application/example intake that collects validated answers, branches,
  resumes, cancels and completes using Inbox/User-bound state.
- Show dependency-injected application Scores/handlers; in Symphonai use its
  existing Score/StateHandler seams rather than a Wappa-owned workflow engine.

## Implementation notes and DDD

Use Interactive Message, Quick Reply, Button Message, Message Card, Message
Carousel, Postback and Conversational Flow. Keep Meta wire “template” strings
inside adapters; WhatsApp Template remains the approved WA feature. A CLI
Application Scaffold is neither. Do not promise native Instagram forms equivalent
to WhatsApp Flows; use conversation steps unless an explicit separate form is chosen.

Define reusable selection values and operation constraints; inject transport,
state and application policy. Source IDs may be absent; repeated/stale actions
must have deliberate consumer handling. Do not require a comment/mention to
pretend it belongs to a DM flow. I08 owns teaching material for these seams.

Demonstrate Redis state plus a memory-backed local path where applicable.
Use Wappa scope constructors, never hand-built keys; no general persistence of
business records in workflow state. The consumer decides TTL, completion side
effects and conflict policy. Validate concurrent turns against real cache behavior.

## Out of scope

Business form engine, generic Score registry in Wappa, native Instagram forms,
WhatsApp-only lists/Templates masquerading as IG features, human assignment UI.

## Open verification

Confirm supported button/action counts, payload limits and card semantics from
current Meta docs. Select exact operation names consistent with I01 capabilities.

## Exit criteria

- Each interactive form sends correctly and round-trips its action evidence.
- Quick replies do not dispatch twice as message plus standalone interaction.
- Example proves validation, branching, resume/cancel, stale/repeated actions,
  concurrent Users and the same native User/address under distinct Inboxes.
- Unsupported content/target/action combinations reject explicitly before I/O
  when knowable; WA behavior is retained.
- Example, DDD/docs and I08 skill inputs teach application-owned flows with DI.
