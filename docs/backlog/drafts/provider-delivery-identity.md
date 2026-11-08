---
status: draft
last_reviewed: 2026-11-06
---

# Provider delivery identity and idempotency

## Code reality (2026-11-06)

This is webhook redelivery identity and deduplication, not InboxRef, IGSID, Delivery Address resolution or echo filtering. The Instagram series explicitly leaves business idempotency with the Host, and its text-test record says echo suppression is not duplicate-callback idempotency. Neither active series absorbs the ADR, provider-evidence and replay/fan-out requirements below.

Evidence: the Instagram [text-test record](../../verification/261103-instagram-simple-text-test.md) distinguishes echo suppression from duplicate-callback idempotency; the [scope](../../platforms/instagram-scope.md) leaves durable business idempotency with the consumer.

## Problem

Wappa delivery is at least once. Provider retries, payload batch splitting, and
Platform Account fan-out can invoke a Host handler more than once for one
provider fact. Wappa intentionally does not currently manufacture a delivery
fingerprint: a payload hash can collapse separate legitimate events and batch
positions change when a provider repackages a callback.

## Proposed outcome

Define a provider-aware delivery identity contract only when a concrete
Platform adapter supplies stable provider evidence. The contract must state
which event kinds are idempotent, the lifetime and storage authority of a
deduplication record, and how fan-out preserves one provider fact without
collapsing distinct events.

## Constraints

- A Host remains responsible for business side-effect idempotency until this
  contract exists.
- No generic payload hash or URL-derived identifier is acceptable.
- The design must preserve payload-routed multi-Inbox delivery and qualified
  `InboxRef` scope.

## Exit criteria

1. An ADR records the provider evidence and collision semantics.
2. One adapter implements the contract with replay and fan-out tests.
3. Public documentation clearly distinguishes delivery identity from business
   idempotency.
