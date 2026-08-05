# ADR-0008: Redis Hash Boolean Encoding Is `"1"` / `"0"`

**Status:** Accepted  
**Date:** 2026-08-05

## Context

Wappa stores cache rows as Redis hashes. Hash fields are strings, so `serde.py`
decides how each Python value is spelled on the wire. A top-level boolean is
stored as `"1"` or `"0"`, and `loads()` maps those two strings back to `True`
and `False`.

This has been the format since the cache layer existed, and Host Applications
depend on it directly. They read and write these fields outside Wappa — from
`redis-cli`, from analytics jobs, from services that are not Python — so the
spelling is not an internal detail Wappa can change on their behalf. Rows also
outlive a deploy: changing the format makes every in-flight row read back
differently until its TTL expires.

The format has a known cost. `"1"` is also how an integer `1` is spelled, so an
**untyped** read cannot tell them apart:

| Written | Stored | Untyped read |
|---|---|---|
| `True` | `"1"` | `True` |
| `1` | `"1"` | `True` ← not an int |
| `"1"` | `"1"` | `True` ← not a string |

A JSON-native spelling (`true` / `false`) would remove the ambiguity, since
`1` and `true` are then distinct. That alternative was implemented and reverted
during the 0.26 hardening pass, which is the reason this ADR exists: the
ambiguity is visible in the code and reads like a bug, so without a written
decision it will keep getting "fixed".

## Decision

**The `"1"` / `"0"` boolean spelling stays.** It is part of Wappa's observable
storage contract, not an implementation detail.

Scope of the rule:

- A **top-level hash field** holding a boolean is `"1"` / `"0"`.
- A boolean **nested inside** a JSON value (a dict, a list, a nested model)
  keeps JSON spelling — `{"on": false}`. The two spellings coexist in one row;
  the field boundary is where it switches.
- `loads()` maps exactly the strings `"1"` and `"0"` back to booleans.

The ambiguity is accepted, with one mitigation and one prohibition:

- **Mitigation — read through a Pydantic model.** `TypedTableCache[T]` and the
  `models=` parameter settle what `"1"` meant: an `int` field returns `1`, a
  `bool` field returns `True`. Typed reads are the supported path; untyped dict
  reads are best-effort.
- **Prohibition — never store `"1"` or `"0"` as a string value.** It is written
  as `"1"`, read back as `True`, and then rejected by a `str` field. This case
  is unrecoverable at any layer. Store a real bool, a real int, or a value with
  a distinguishing prefix.

Any future change to this format is a breaking change requiring a major-version
note, a migration story for live rows, and a superseding ADR.

## Consequences

- Downstream apps reading Wappa's Redis hashes keep working across upgrades.
- `row_conditions.condition_token` inherits the spelling, so a `replace_if`
  condition on `True` also matches a stored `1` (and vice versa). Condition on a
  status string or an integer revision rather than a bare boolean when the
  distinction matters.
- `tests/test_redis_value_encoding.py` pins the format, the nested-JSON
  boundary, the accepted ambiguity, and the `str` prohibition. Those tests are
  guardrails, not descriptions: a failure there means someone changed the
  contract, and this ADR is the thing to read before deciding that is intended.
- The memory and JSON backends store native Python values and never had this
  ambiguity. Backends therefore differ in what an *untyped* read returns for a
  `1`. Typed reads agree across all three, which is what the cache contract
  guarantees.
