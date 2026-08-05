---
name: explain-changes
description: Explain what a batch of code changes actually did, in before/now pairs a Product Manager can act on, then offer to drill into the mechanics of any bullet. Use this whenever a big feature, PRD implementation, migration, bug fix, or multi-file refactor has just landed and the user asks "what changed", "explain the changes", "walk me through it", "resume de los cambios", or is about to review, ship, or sign off on work they did not write themselves. Prefer this over an ad-hoc summary any time the answer would otherwise be a wall of file names or a diff dump.
---

# explain-changes

The person reading this is deciding whether to ship. They own the product, not the diff. They need to know what behaviour changed and what it costs them — not which files were touched.

So the unit of explanation is **the behaviour**, and the shape is always the same pair: what the system used to do, and what it does now. A file path with no behaviour attached tells them nothing. A behaviour with no before tells them nothing either — they cannot judge a fix without knowing the bug.

## When this fires

Use it after substantial work lands: a feature, a PRD implementation, a bug-fix batch, a migration, a refactor that crosses modules. Skip it for a one-line tweak — a sentence is a better answer there than a ceremony.

## Step 1 — Ground yourself in what actually changed

Never write the summary from memory of the conversation. Memory drifts, and a stale claim ("this is still open") in a shipping decision is worse than no summary. Read the real state first:

- `git diff` / `git diff --stat` against the base the work started from, or `git log` for the range.
- Open the files the diff touches when the diff alone does not tell you *why* the behaviour changed.
- Check the things that are easy to assume and easy to get wrong: did the migration actually get written, or only the fresh-DB DDL? Is the call site really wired, on both ends? Did the flag get read anywhere?

Every claim in the summary must be traceable to something you read in this session.

## Step 2 — Write the summary

Numbered list. Each entry is a short noun-phrase title, then exactly two lines:

```
N. <One phrase naming the behaviour that changed>
- Before: <what the system did, and why that was a problem>
- Now: <what it does instead>
```

What makes these land:

**Name the consequence, not the mechanism.** "Conversation close can no longer destroy data" beats "added a persistence_failed guard to close_conversation". The mechanism goes in the drill-down if they ask.

**Numbers earn trust.** If you know that 1,777 of 1,777 rows were mislabelled, or that 34% of a table was polluted, say it. A PM who sees a real count knows you looked. Never invent one — if you did not measure it, describe it qualitatively instead.

**Keep the causal chain intact in the Before.** "Notification dropped → never persisted → cache expired at 24h → message gone forever" tells the whole failure story in one line. That chain is what makes the fix feel necessary.

**Technical vocabulary is fine; unexplained vocabulary is not.** Say Redis, Postgres, webhook, enum, migration, cron — a product owner on a technical product knows these. But when a term is internal to the codebase (`_durable_conversation_messages()`, `MEDIA_MESSAGE_KINDS`, a lease column), attach a clause saying what it does. The test is whether someone who has never opened the file can follow the sentence.

**Say plainly when something is not what they asked for.** If a change they rejected is still in the tree, or a fix landed only halfway, that belongs in the bullet, in the same sentence, not softened.

Then close the summary with a section for what did **not** land:

```
---
Still open

- <thing>: <what state it is actually in, and what it means operationally>
```

This section is the reason the summary is trustworthy. Include anything half-done, anything that will break on deploy (a column with no migration, a flag with no default), and anything you specced but did not implement. If it is genuinely empty, say "Nothing open" rather than deleting the heading — the absence should be a stated fact, not a silence.

## Step 3 — Offer the drill-down

End with an explicit invitation, in plain terms:

> Want the mechanics on any of these? Tell me the numbers.

Then stop and wait. Do not pre-emptively explain all thirteen bullets — the whole point of the two-line format is that they choose where to spend attention.

## Step 4 — Answer the drill-downs

A mechanics answer is still short — a paragraph or two per item, not a code tour. Same before/now spine, one level deeper: the actual sequence of operations, in order.

```
#N — <title>, before → now

Before: <the old sequence of steps, in order, and the exact point where it broke>

Now: <the new sequence, and why the failure mode is now unreachable>
```

Ground it. Name the function and the file (`master_event.py:463`), quote the two or three lines that carry the change, state the order of operations when order is the point ("Redis first, DB second"). Precision here is what turns a summary into something they can reason about.

When they ask a question rather than requesting mechanics — "does this mean X?", "why did we add these columns?" — answer the question they asked, first word first. If they are right, say "yes, exactly that" and then confirm with specifics. If they are wrong, correct it plainly. If they have found a real problem, say so and say what you would do instead; a design objection from the person who owns the product usually beats an earlier recommendation of yours, and reversing yourself out loud costs nothing.

Two habits that matter more than they look:

- **Verify before answering.** If the question is about something you have not read this session, read it. Questions land precisely on the things you were least sure about.
- **Correct the record when the read was stale.** If a bullet said "still open" and it actually landed, say so in the drill-down and move on. One sentence, no post-mortem.

## Step 5 — Close the loop

After the drill-downs, ask once whether anything else about the changes is unclear. When they say no, the pass is complete — do not restate the summary or produce a recap document.

## Full example

**Summary bullets:**

```
1. Message durability
- Before: a message went to Redis and waited for a sync notification to flush it to Postgres. Notification dropped → never persisted → cache self-destructed at 24h → message gone forever.
- Now: every message is written to Postgres synchronously on arrival and on send. Note this is the change you rejected — it is still in the tree, unreverted.

2. Conversation close can no longer destroy data
- Before: close persisted messages, then wiped Redis. If persistence failed, it wiped anyway.
- Now: if persistence fails, close raises and aborts. The cache survives for the next attempt. This is the real root-cause fix, independent of #1.

3. Delivery status
- Before: every message was hardcoded `delivered` at insert and never updated — 1,777 of 1,777 over 14 days.
- Now: `failed` added to the enum; each message carries status + error code + reason; status only advances (sent → delivered → read, never backwards).

---
Still open

- Agent context unfiltered. The agent still reads failed sends as delivered history. Only the summarizer half landed.
```

**A drill-down answer:**

```
#2 — the close mechanism, before → now

Before: close_conversation ran persist → summarize (LLM) → write summary → flip the row to closed → delete every user-scoped Redis key. A failure in the persist step was caught and logged, and the Redis delete ran anyway. So a Postgres hiccup during close wiped the cache and the messages with it.

Now: the persist step sets a persistence_failed flag and the function raises twice — once before summarizing, once before closing:

    if persistence_failed:
        raise RuntimeError("refusing to close or delete cache after message persistence failure")

close_conversation also returns a bool from the UPDATE rowcount, and a false result raises too. Net: the Redis delete is unreachable unless every message is durably in Postgres. The cache survives, and the reconciliation sweep retries on a later tick.
```
