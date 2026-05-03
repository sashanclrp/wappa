---
name: bump-version
description: Run the end-of-session release workflow for the Wappa library — bump the version, refresh CHANGELOG.md, rebuild the wheel, and create a tagged commit. Use this skill whenever the user says "bump version", "/bump-version", "release", "cut a release", "tag a new version", or asks to ship/publish the next version of wappa. Optionally runs the code-simplifier subagent first to clean up recently changed code before the release.
---

# bump-version

Release workflow for the Wappa library. The user runs this at the end of a working session when they're ready to ship the changes that just landed on `main`.

## Argument parsing

The user invokes this skill three ways:

| Invocation | Behavior |
|---|---|
| `/bump-version run code-simplifier` | Run code-simplifier first, then proceed with the release |
| `/bump-version don't run code-simplifier` (or `skip code-simplifier`) | Skip simplifier, go straight to release |
| `/bump-version` (no qualifier) | **Ask** the user whether to run code-simplifier before continuing |

Don't assume. If the user's invocation doesn't explicitly include "run code-simplifier" or "don't / skip / no code-simplifier", stop and ask once: *"Run code-simplifier first, or skip it?"* — then proceed based on the answer.

## Workflow

Execute the steps in this order. Each step depends on the previous one — don't parallelize.

### Step 0 — (optional) code-simplifier pass

Only if the user opted in. Spawn the `code-simplifier` subagent on the Sonnet 4.6 model with this brief:

> Review the code changed in this session (git diff against the last release tag, or against `HEAD~N` covering the session's commits). Improve code quality, optimize where it helps, and tighten SOLID compliance. Do not introduce new features or change public behavior. Report what you changed.

After it returns, show the user a one-paragraph summary of what changed and **wait for explicit confirmation** before proceeding. The simplifier touches working code — the user must approve before we bake those edits into a release.

Use the Agent tool:
```
Agent(subagent_type="code-simplifier", model="sonnet", prompt="<the brief above>")
```
(Sonnet on this harness is Sonnet 4.6.)

### Step 1 — Decide the new version

1. Read the current version from `pyproject.toml` (the `version = "..."` line near the top).
2. Look at `git log <last-tag>..HEAD` and the diff to judge bump type:
   - Breaking public API change → **major** (`X+1.0.0`)
   - New feature / additive change → **minor** (`0.X+1.0`)
   - Fix / docs / internal only → **patch** (`0.0.X+1`)
3. Tell the user the proposed new version and the reasoning in one line. Wait for confirmation before continuing.

### Step 2 — Delete `/dist`

```bash
rm -rf dist
```

If the directory doesn't exist, that's fine — keep going.

### Step 3 — Update `CHANGELOG.md`

Open `CHANGELOG.md` and prepend a new entry above the current top section. Match the existing format the project uses (look at the most recent entry as a template). Typical structure:

```markdown
## [NEW_VERSION] - YYYY-MM-DD

<one-paragraph summary of what shipped>

### Added / Changed / Fixed / Removed
- bullet
- bullet
```

Source the bullets from `git log <last-tag>..HEAD --oneline` and the actual diff — don't fabricate. Only include user-visible changes; skip pure refactors unless they're notable.

### Step 4 — Bump the version everywhere

Update **every** place the version string appears. At minimum:

- `pyproject.toml` — `version = "..."`
- `README.md` — the version badge (`img.shields.io/badge/version-X.Y.Z-...`)

Then sweep for stragglers:
```bash
grep -rn "<OLD_VERSION>" --include="*.toml" --include="*.md" --include="*.py" --include="*.cfg" .
```
Update any remaining hits that are clearly the package version (skip unrelated coincidences like `python_version` or third-party deps). The README badge in particular has historically gone stale — always check it.

### Step 5 — Build

```bash
uv build
```

This regenerates `dist/`. If the build fails, stop and report the error — don't proceed to commit.

### Step 6 — Commit and tag

```bash
git add -A
git commit -m "[REL] vNEW_VERSION — <one-line summary matching the CHANGELOG headline>"
git tag vNEW_VERSION
```

Match the project's existing release commit style (look at `git log --oneline | grep "^.* \[REL\]"` for examples — current convention is `[REL] vX.Y.Z — summary`).

Do **not** push. The user pushes manually when they're ready. Tell them the tag was created locally and remind them: `git push && git push --tags`.

## Why this order matters

- **Simplifier before everything** — its edits must land in the release commit, not as a follow-up.
- **Delete `/dist` before build** — stale artifacts from a previous version would otherwise ship inside the new wheel.
- **CHANGELOG before version bump** — the changelog entry references the new version number, so we need to know it; but we write the prose before the mechanical version-string sweep so we don't conflate the two.
- **Build before commit** — if the build is broken, we want to know before we've made a tagged commit that promises a working artifact.
- **Tag at the end** — a tag is a public promise. Only create it once everything else is verified.

## What to report at the end

One short summary:
- New version
- Whether simplifier ran
- New CHANGELOG entry headline
- Files touched by the version sweep
- Reminder: `git push && git push --tags` to publish
