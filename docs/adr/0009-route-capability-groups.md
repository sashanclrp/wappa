# ADR-0009: Route Capability Groups — "Mutation" Is More Than "Send"

**Status:** Accepted  
**Date:** 2026-08-05  
**Extends:** ADR-0007

## Context

ADR-0007 split Wappa's WhatsApp HTTP surface in two: routes that **send** a
message, and everything else. `include_outbound_transport_api=False` let an
embedding Host Application drop the first group while keeping media upload,
downloads, lookups, limits, validation, and Template info.

That split was drawn along the wrong line. Auditing what an unauthenticated
caller could still reach with sends ejected turned up three routes that mutate:

| Route | Effect |
|---|---|
| `DELETE /api/whatsapp/media/{media_id}` | Destroys a media asset on the platform |
| `POST /api/whatsapp/state-handlers/set` | Overwrites the cached conversational state of **any** recipient named in the body |
| `DELETE /api/whatsapp/state-handlers/delete/{recipient}/{handler_value}` | Deletes the cached state of **any** recipient in the path |

The state-handler pair is the more serious of the two. It takes the target
recipient as an untrusted input, so an unauthenticated caller could enumerate
users and wipe or forge their conversation routing — a bigger hole than the
media delete that prompted the audit.

The v0.26.0 grouping made this invisible: all three sat in the "service" half
because they were not sends, and "service" had come to mean "not a send" rather
than "safe to expose".

## Decision

Group routes by **what an unauthenticated caller could do with them**, not by
whether they send a message. Five capability groups, each independently
mountable:

| Capability | Routes | Standalone | Embedded |
|---|---|---|---|
| `outbound_transport` | 10 ordinary sends | on | **off** |
| *(interactive sends travel with it)* | 5 interactive sends | on | **off** |
| `template_transport` | 3 Template sends | off | off |
| `media_management` | `DELETE /media/{id}` | on | **off** |
| `media_upload` | `POST /media/upload` | on | **on** |
| `state_handler_api` | 3 `/state-handlers/*` | on | **off** |
| *(everything else)* | reads, lookups, validation | on | on |

Two named profiles, `standalone` and `embedded`, set these together, because a
host getting one of five booleans wrong is a security bug rather than a
preference. Any capability named explicitly overrides the profile.

**Ejecting sends implies the embedded profile.** When no profile is named,
`include_outbound_transport=False` resolves the remaining unset capabilities to
their embedded values. A host that adopted the v0.26.0 spelling gets the
corrected surface without changing a line — the fix should not require noticing
that it exists.

**Media upload stays mounted under `embedded`.** It is the one capability that
reaches the platform and is still on, because an embedding host needs Wappa's
upload path and the agreed capability matrix requires it. It is a create, not a
destroy, and `include_media_upload=False` closes it for hosts that front
uploads themselves.

`/state-handlers/get` is grouped with the writes rather than the reads. It
exposes an arbitrary recipient's state, so a host ejecting the writes almost
never wants the read left open, and splitting the group would invite exactly
that mistake.

## Consequences

- An embedding host reaches zero unauthenticated routes that send, delete, or
  rewrite state — `POST /media/upload` aside, which is one explicit flag away.
- The route table, not the constructor flags, is what the tests assert. The
  central invariant is expressed directly:
  `EVERY_MUTATION & mounted == MEDIA_UPLOAD_ROUTES`.
- Standalone behaviour is unchanged. The profile resolves to the same surface a
  standalone app has always had, asserted by comparing the explicit
  `standalone` profile against the default.
- Capability groups are now the unit of change. A new destructive route must
  pick a group at its decorator, in the module that owns it, and a route added
  to the wrong group shows up in review as a router name that does not match
  what the route does.
- Five booleans is more surface than ADR-0007's one. The profiles keep the
  common cases to a single argument; the booleans exist for hosts whose split
  does not match either profile.
