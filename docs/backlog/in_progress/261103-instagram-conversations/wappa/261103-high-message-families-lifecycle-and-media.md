---
status: implemented_pending_live_gates
urgency: high
owner: Instagram messaging, processors and media adapters
depends_on: I01
last_reviewed: 2026-11-06
---

# Message families, lifecycle and media

## Code reality (2026-11-06)

November 5 live evidence covers DM media sends, uploaded images, inbound image/audio/video bytes, read/typing, reactions and edits. Story/share/referral/deletion variants, selected failures and concurrent User/Inbox isolation still need recorded acceptance.

See the [series plan](../plan.md), [capability matrix](../references/capability-matrix.md) and [live evidence](../tests/live-test-plan.md). Historical test results do not replace the remaining live gates.

## Context

The [series](../plan.md) implements the
[grilled scope](../../../../sasha/grilling-sessions/261103-instagram-scope-and-extensions.md).
Plain text, seen and outbound echoes work; media and content changes are not
certified by that hello exchange. Images are the next message implementation slice.

## Scope

- Implement incoming text, images, audio, video, supported files, shared posts,
  story replies/mentions and selected supported attachment variants honestly.
- Implement outgoing text, image/audio/video/supported files using DirectMessage,
  with individual native source/size/MIME/caption/reply constraints.
- Normalize seen, echoes, referrals, edits and deletions into their distinct
  lanes. Keep text unchanged; echoes never retrigger ordinary message handling.
- Provide safe media metadata/download/stream/bytes primitives needed by
  consumer AI processing; I05 adds post/comment lookup on top of them.
- Implement seen/typing controls with native targeting and explicit outcomes.

## Implementation notes

Maintain a checked-in capability matrix with one row per inbound variant and
outbound operation, target/options, native endpoint/field, current permission,
limits, source date, fixture and offline/live evidence. Do not mark an outbound
type supported merely because its inbound counterpart parses. Validate limits
from current primary sources; use sanitized real fixtures when possible.

Media may provide only a URL/reference. Separate provider-authenticated lookup
from third-party downloads; never forward a bearer across arbitrary hosts or
redirects. Bound redirects/timeouts/size and validate actual content where
appropriate; expose unavailable/expired/deleted resources rather than fabricate
bytes. No hidden network reads in a Processor. Let consumers supply media to AI.

Edits go to `process_message_update` with original message reference and available
replacement/revision; deletions retain a tombstone without invented text. Read
evidence remains `process_status`. Preserve one automation trigger for one native
event and typed unknown-content outcomes. No automatic retry for indeterminate sends.

Update messaging/webhook/persistence docs only where responsibilities change,
public capability/target/result docs, generated examples and the test record.
The universal models must not gain fake WA phone evidence for Instagram.

## Out of scope

Reactions, cross-app handover, conversation history sync, transcription/AI,
publishing, business fallback or converting unsupported content silently.

## Open verification

The selected `message_edit` appears in dashboard/examples but was absent from
the Unified Login permission-field table inspected in research. Verify actual
subscription/delivery; record the outcome and leave its gate open if unavailable.
Confirm file types, owned/shared-media access and reply semantics per setup.

## Exit criteria

- Each selected family has a valid/invalid boundary test, sanitized translation
  fixture, mocked native send/download test and controlled live evidence.
- Include source timeout, expired URL, unavailable bytes, MIME/size failure,
  credential isolation, wrong Inbox, unsupported options and uncertain send.
- Edit/deletion/referral/seen/echo events dispatch with correct meaning once.
- Concurrent Users and multiple Inboxes cannot cross targets or scoped state;
  repeat the earlier sequential check without overstating what it proves.
- Matrix, examples, supported_operations and docs agree with implemented support;
  all existing WhatsApp contract tests pass.
