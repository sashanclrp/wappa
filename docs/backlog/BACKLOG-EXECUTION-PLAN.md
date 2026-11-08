# Backlog execution plan

Reviewed 2026-11-08 against the current code, recorded live evidence and the user's scope decisions. This file lists every active top-level backlog item. Individual PRDs own requirements and exit criteria; [README.md](./README.md) defines completion and consolidation rules.

## In progress

1. [261103-instagram-conversations/](./in_progress/261103-instagram-conversations/plan.md): runtime and skills implemented; substantial November 5 live conversation/media/interaction/public-read evidence. Gate A remains partial. Core Gate B passed, with Creator/access/revocation limitations recorded. Symphonai adoption code exists; live Gate C and final documentation/distribution verification remain. User decision 2026-11-06: Wappa Scheduling delivery and a separate Symphonai adoption PRD are prerequisites for Gate C; this Wappa initiative does not edit Symphonai. See the [live evidence](./in_progress/261103-instagram-conversations/tests/live-test-plan.md).

2. [261105-mid-inbox-connector-contract.md](./in_progress/261105-mid-inbox-connector-contract.md): shared connectors implemented and hardened. Core Instagram Gate B passed. Open Wappa work is the Creator account check, WhatsApp Embedded Signup acceptance, and deferred credential-step/new-number registration support when those paths are built. Host migration belongs in the Host backlog.

3. [261106-architecture-hardening/](./in_progress/261106-architecture-hardening/plan.md): H-01–H-25 and H-28–H-31 implemented; H-27 proposal rename complete. H-26 User profile reading, H-32 final docs/ADR reconciliation, H-33 third-Platform/two-Platform proof and final verification remain. The plan contains per-item status; historical audits are not fresh implementation instructions.

## Pending

None.

## Drafts

Each retained draft contains scope that has not been fully absorbed by an active PRD. Partial overlaps are called out inside the files.

- [261105-low-conversation-entry-points-capability.md](./drafts/261105-low-conversation-entry-points-capability.md): Platform starters, persistent menu/commands and welcome configuration. No equivalent implementation found in Wappa or Symphonai; Agency conversation starters are a different concern.
- [261105-low-profile-reader-capability.md](./drafts/261105-low-profile-reader-capability.md): IInboxProfileReader for the connected Inbox's business profile. H-27 renames the proposal only; H-26 is a separate User-profile capability. Symphonai's stored setup metadata is not this reader.
- [261105-mid-commerce-capability.md](./drafts/261105-mid-commerce-capability.md): shared product/catalog sending, inbound order contract and live acceptance; unimplemented.
- [261105-mid-whatsapp-calling-prd.md](./drafts/261105-mid-whatsapp-calling-prd.md): call controls/settings and live call acceptance; inbound CallWebhook already exists.
- [261105-mid-whatsapp-flows-prd.md](./drafts/261105-mid-whatsapp-flows-prd.md): outbound Flow capability, pipeline integration and live acceptance; phase-2 crypto/management scope still needs a decision. H-25 already implements typed inbound nfm_reply and must not be rebuilt.
- [261106-low-whatsapp-first-remaining-gaps.md](./drafts/261106-low-whatsapp-first-remaining-gaps.md): retained at the user's request. Outbound reactions are deprioritized; remaining interactive types, address-message scope and result/Template details stay open.

- [provider-delivery-identity.md](./drafts/provider-delivery-identity.md): provider-event redelivery identity and replay/fan-out semantics. Separate from Instagram Inbox/User/address identity and echo filtering; not absorbed by either active series.

## Scope decisions (2026-11-06)

- Scheduled-task dispatch is a prerequisite for Gate C, with actual Symphonai adoption in a separate Host PRD. The final clarified scope is shared Wappa context/handler dispatch, existing Redis TTL integration and external scheduler callback mechanisms. The proposed durable scheduler, native recovery/leases/history, backend parity, admin routes and declaration registry were rejected. Keep Redis TTL behavior and Host scheduler ownership. The approved responsibility split shipped in 0.34.0. Version 0.34.2 defers scheduled Messenger credentials until first use; Symphonai adoption and live Gate C remain Host-owned.

- Deleted the completed v0.27 series at the user's request after confirmation of the published-package gate. Git history retains the series and release reports.
- Deleted the Template management draft from Wappa. Symphonai owns catalog create/delete and lifecycle extension handling in `backend/symphonai/services/wappa/template_catalog/application.py` and `backend/symphonai/engine/system/meta_template_status_webhook.py`. Full generic update coverage was not asserted; further catalog product scope remains Host-owned.
- Deleted the standalone outbound reaction draft because the user deprioritized it. Existing inbound reaction support remains implemented.
- Deleted the empty ideas file.
- Keep a draft only for remaining independent scope. If an active PRD absorbs its whole scope and gates, update references and delete the duplicate draft.
