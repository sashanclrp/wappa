# Publishing wappa to PyPI

Releases publish **automatically** via `.github/workflows/publish.yml` when a
`vX.Y.Z` tag is pushed. Authentication uses **PyPI Trusted Publishing (OIDC)** —
there is no API token in the repo, in CI secrets, or in `.env`.

## One-time setup (do this once, in a browser)

You must register this repository as a trusted publisher on PyPI. This is the
only manual step and it cannot be automated.

1. Go to <https://pypi.org/manage/project/wappa/settings/publishing/>
   (must be logged in as an owner/maintainer of the `wappa` project).
2. Under **Add a new publisher → GitHub**, enter:
   - **Owner**: `sashanclrp`
   - **Repository name**: `wappa`
   - **Workflow name**: `publish.yml`
   - **Environment name**: `pypi`
3. Save.

Optionally, in the GitHub repo (Settings → Environments), create an environment
named **`pypi`** and add protection rules (e.g. required reviewers) if you want a
manual approval gate before each publish. The workflow already targets this
environment.

## Releasing a new version

1. Run the `/bump-version` skill (bumps version, CHANGELOG, builds, commits, tags
   locally — it does **not** publish).
2. Push the commit and the tag:
   ```bash
   git push && git push --tags
   ```
3. Pushing the tag triggers the workflow, which rebuilds and publishes to PyPI.
   Watch it under the repo's **Actions** tab.

The workflow re-checks that the tag (`vX.Y.Z`) matches `pyproject.toml`'s
`version` and fails fast if they diverge, so a mistagged release can't ship.

## Why this replaces the token

The previous flow read `WAPPA_PYPI_TOKEN` from `.env` and ran `uv publish`
locally. Trusted Publishing removes the long-lived token entirely: CI mints a
short-lived, repository-scoped OIDC identity that PyPI verifies per release. You
can (and should) delete `WAPPA_PYPI_TOKEN` from `.env` once the trusted publisher
is registered and the first tag-triggered release succeeds.
