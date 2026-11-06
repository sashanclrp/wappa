---
status: implemented_pending_live_gate_c
urgency: high
owner: Symphonai Wappa adapter, conversation runtime and consumer integration
depends_on: gates A and B; I01 supported public contracts
last_reviewed: 2026-11-06
---

# Symphonai Instagram adoption and agent integration

## Code reality (2026-11-06)

Symphonai adoption code exists, including InboxCredentialAccess, targets and operator text. Its dependency is wappa==0.33.0 with a temporary editable local source. Gate C agent conversation, concurrent isolation, takeover and credential lifecycle acceptance has no recorded live result.

See the [series plan](../plan.md), [capability matrix](../references/capability-matrix.md) and [live evidence](../tests/live-test-plan.md). Historical test results do not replace the remaining live gates.

## Context

This cross-repository PRD executes gate C of the [series](../plan.md), grounded
in the [completed grilling session](../../../../sasha/grilling-sessions/261103-instagram-scope-and-extensions.md).
The session inspected Symphonai's working bearer-reuse pattern; do not implement
a second credential system. Follow that checkout's AGENTS, DDD, skill/template
and test-lane rules before changing it.

## Scope

- Migrate Symphonai's Directory Source and `runtime_inbox` adapter from explicit
  WhatsApp filtering/phone assumptions to qualified Platform identities and
  Wappa's supported credential-access capability.
- Adopt target/result/event contract changes across the actual host send paths,
  tools, Template adapters, delayed jobs, SSE and persistence as applicable.
- Connect a professional account through gate B, route incoming messages and
  selected public events to consumer-owned handlers, and demonstrate agent replies.
- Preserve consecutive-turn history/context, concurrent User/Inbox isolation and
  host-owned human takeover across immediate and delayed automation.
- Demonstrate a trusted backend extension obtaining current credentials from
  the same connection, reacting correctly to rotation/deactivation and handling
  a registered non-core field using a sanitized fixture if no live field is available.
- Update existing developer/consumer skills and scaffold templates affected by
  Instagram, `target=` and the revised extension seam; coordinate with I08.

## Implementation notes and DDD

Read Symphonai's TACS/consumer registry and canonical language before choosing
an active test consumer; the minimal lab and a deployed business application
are not interchangeable. Keep Wappa's Inbox/Platform vocabulary inside adapters
where Symphonai uses Owner/Channel business concepts. Persist canonical envelopes
and call Wappa's lifecycle after commit. Sharing an encryption key is not an
independent decryption contract.

Business policy belongs in existing Symphonai services/Score/StateHandler and
takeover seams. Wappa does not acquire a mandatory human queue model. Gate all
automated send paths, including jobs created before takeover; coordinate ownership
changes and sends, not just a flag read at intake. Agent tools receive capabilities,
not bearer tokens. Do not hold DB transactions across sends or AI calls.

Update Symphonai's DDD docs, public contract/templates, package boundaries and
skill source/mirror registrations in the same host change. Existing skills
`develop-wappa`, `symphonai-add-score`, `symphonai-add-state-handler` and
`develop-symphonai-package` remain the host-specific owners; I08 links by name
after confirming discovery instead of copying their business architecture.

## Out of scope

Implementing publishing/calendars/analytics, generic content management, replacing
the Score/StateHandler engine, or release/deploying a consumer without an explicit
request. The extension proof validates reuse, not an entire extra product.

## Open verification

Identify actual consumer and lockfile/build paths through Symphonai's registry.
Inspect existing takeover and context persistence before prescribing edits.
Record concrete compatibility gaps rather than treating Wappa unit tests as
proof of host adoption.

## Exit criteria

- A real agent conversation maintains context and returns through the correct
  Instagram Inbox; repeat with concurrent Users and multiple professional accounts.
- Human takeover pauses immediate/delayed automation; an authorized human can
  reply and explicitly resume according to host policy, with race tests.
- Credential reuse, replacement, deactivation and field-extension dispatch work
  without internal resolver imports in migrated callers or a second token store.
- Existing WhatsApp/Template flows and host security/ownership rules remain valid;
  host test/build lanes and consumer verification pass.
- Host docs/skills/templates describe actual APIs, and C live evidence is linked
  to this series without publishing secrets or claiming unsupported provider access.
