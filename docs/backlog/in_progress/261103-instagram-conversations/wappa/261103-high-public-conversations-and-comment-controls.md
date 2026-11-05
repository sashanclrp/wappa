---
status: pending
urgency: high
owner: Instagram public-conversation adapters
depends_on: I01, I02 text and outcomes
---

# Public conversations and comment-control primitives

## Context

The [grilling session P1–P4/X2](../../../../sasha/grilling-sessions/261103-instagram-scope-and-extensions.md)
selected all accessible comment sources now, including Live. Wappa provides
moderation mechanisms; consumers own whether and when to use them. See the
[series plan](../plan.md) for scope and delivery gates.

## Scope

- Admit `comments`, `live_comments` and public `mentions` envelopes through
  the same authenticated Instagram callback and complete-batch routing.
- Typed comment source/placement/kind, qualified references, available parent,
  author and content/time allow consumer filtering without raw Meta parsing.
- `process_comment` for actual comments/replies; public mentions have explicit
  media/comment subjects and their own lane. DM story mentions stay messages.
- `reply_comment` on Messenger facade with a comment result.
- Instagram-only `PrivateReply(comment_ref)` on `send_text`, initially text only.
- Dedicated hide/unhide/delete comment and enable/disable comments-on-media
  operations in a focused capability, not required methods on every Messenger.

## Implementation notes and DDD

Processors translate; admission validates registered Inbox/account and scopes;
capabilities perform native I/O; Host policy filters/acts. Do not register new
Inboxes from comment authors or fabricate DM Users to make cache/context work.
Missing parent evidence is unknown, not proven top-level. Mentions of media do
not become fake comments. Keep author addressing distinct from native DM eligibility.

Treat visibility as explicit intent. A public reply returns Comment Reference;
a private reply returns private-message evidence; unsupported/expired/ineligible
destinations never switch visibility. Verify private-reply windows, limits,
follow-up DM conditions and Live restrictions from current provider evidence.

Validate qualified references and local knowable constraints before I/O, then
retain provider authorization/eligibility failures. Comment controls return
honest accepted/rejected/indeterminate outcomes; never retry a destructive or
uncertain mutation blindly. A successful control call does not prove a matching
webhook exists. Live bursts and owned-comment echo behavior need explicit tests.

Update glossary, webhook/messaging architecture, public contract, migration and
CHANGELOG when PrivateReply/public methods actually land. I08 teaches typed
filtering, not a hardcoded Wappa comment-policy gate.

## Out of scope

Consumer moderation policies/UI, arbitrary third-party media access, publishing,
reaction implementation and automatically treating every public author as DM-able.

## Open verification

Check supported placements and author/parent fields against sanitized real
Unified Login payloads, including ads where authorized. “All” does not override
provider access limits. Verify exact operation eligibility independently for Live.

## Exit criteria

- Regular/Live comments, replies, media/comment mentions and missing metadata
  dispatch honestly once; consumers can choose which source/types to ignore.
- Mixed messaging/public batches authenticate and admit fully before dispatch;
  unknown/inactive/mismatched accounts cannot partially schedule work.
- Live tests cover public reply, comment-triggered private reply then eligible
  DM follow-up, hide/unhide/delete and commenting enable/disable on controlled media.
- Include cross-Inbox/Platform PrivateReply rejection, permission/expiry errors,
  no fabricated User/comment/message IDs, burst behavior and own-action loops.
- Destructive live checks use disposable controlled comments/media and explicit
  test intent; no broad moderation of an account's real history.
