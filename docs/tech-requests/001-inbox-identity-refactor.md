# Tech Request: Write Per-Context Documentation for Wappa

**Priority:** High — must land before or in parallel with the inbox_id rename  
**Effort:** 1 session (documentation only, no code changes)  
**Scope:** Write `CONTEXT.md` and `ARCHITECTURE.md` for each bounded context listed in `CONTEXT-MAP.md`

## Why This Matters

We're about to execute a full rename refactor (`tenant_id` → `inbox_id`) across Wappa. The root documentation foundation is already in place:

- `CONTEXT-MAP.md` — maps all bounded contexts and their relationships
- `CONTEXT.md` — shared kernel glossary with canonical terms
- `ARCHITECTURE.md` — root message flow, design patterns, layer dependencies
- `docs/adr/0001-inbox-id-runtime-scope.md` — the decision record

What's missing: each bounded context needs its own `CONTEXT.md` (local glossary) and `ARCHITECTURE.md` (internal structure, responsibilities, interfaces). These docs serve as the reference for agents and developers working inside each context — both during the rename and for all future work.

## What To Write

For each context listed in `CONTEXT-MAP.md`, create two files:

| Context | Files to create |
|---------|----------------|
| Webhooks | `wappa/webhooks/CONTEXT.md`, `wappa/webhooks/ARCHITECTURE.md` |
| Messaging | `wappa/messaging/CONTEXT.md`, `wappa/messaging/ARCHITECTURE.md` |
| Persistence | `wappa/persistence/CONTEXT.md`, `wappa/persistence/ARCHITECTURE.md` |
| SSE / PubSub | `wappa/core/sse/CONTEXT.md`, `wappa/core/sse/ARCHITECTURE.md` |
| Expiry | `wappa/core/expiry/CONTEXT.md`, `wappa/core/expiry/ARCHITECTURE.md` |
| Plugins | `wappa/core/plugins/CONTEXT.md`, `wappa/core/plugins/ARCHITECTURE.md` |
| CLI | `wappa/cli/CONTEXT.md`, `wappa/cli/ARCHITECTURE.md` |

## How Each File Should Be Written

### CONTEXT.md (per-context glossary)

- Only terms specific to that context. Don't repeat the shared kernel — reference it.
- Format: term table like the root `CONTEXT.md`.
- Must use the **new canonical language** (`inbox_id`, `platform`, `InboxBase`, etc.) even though the code still says `tenant_id`. The docs describe the target state.
- Keep it a glossary. No implementation details, no architecture, no plans.

### ARCHITECTURE.md (per-context internals)

- What this context owns (responsibilities)
- What it does NOT own (explicit boundaries)
- Internal module structure and how pieces relate
- Key interfaces/classes and their roles
- Design patterns used within this context
- How data flows through this context
- Extension points (if any)
- Reference the code as it exists today, but use the canonical terms from `CONTEXT.md`

## Rules

1. **Read the code** in each context before writing. Describe what actually exists, not what might exist.
2. **Use canonical Inbox language** from root `CONTEXT.md` even when the code still says `tenant`. The rename is coming; docs should already reflect the target.
3. **Do NOT modify any code.** This is a documentation-only task.
4. **Do NOT create ADRs** unless you discover a decision that is hard to reverse, surprising without context, and the result of a real trade-off. Most contexts won't need one.
5. **Keep docs concise.** A 40-line ARCHITECTURE.md that captures the real structure beats a 200-line one padded with obvious statements.
6. **Cross-reference** the root `CONTEXT-MAP.md` and root `ARCHITECTURE.md` where relevant. Don't duplicate their content.

## Why Now

The inbox_id rename is starting in parallel. Having per-context docs means:
- The rename agent can validate its changes against documented responsibilities
- Future sessions working in any context have immediate orientation
- We catch any misunderstandings about context boundaries before code changes lock them in

## Acceptance Criteria

- All 14 files listed above exist
- Each `CONTEXT.md` is a glossary only, uses Inbox language, no implementation details
- Each `ARCHITECTURE.md` describes actual code structure, responsibilities, boundaries, and patterns
- No code was modified
- Root `CONTEXT-MAP.md` links remain valid (paths match created files)
