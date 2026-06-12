# PyPI URL icons, verification, and README badges

## `project.urls`: which labels get custom icons

PyPI renders `[project.urls]` in the left sidebar and swaps the default link
icon for a custom one when the **label** (case-insensitive; `*` = prefix match)
or the **target domain** is recognized. Use these labels so the sidebar reads as
a tidy, iconed set instead of generic links.

### Recognized labels (by name)

| Use this label | Also matches | Purpose |
|---|---|---|
| `Homepage` | | Project home |
| `Download` | | Direct download link |
| `Changelog` | `Change Log`, `Changes`, `Release Notes`, `News`, `What's New`, `History` | Changelog |
| `Documentation` | `Docs*`, any Read the Docs URL, or host starting `docs.`/`documentation.` | Docs site |
| `Issues` | `Bug*`, `Issue*`, `Tracker*`, `Report*` | Issue tracker |
| `Funding` | `Sponsor*`, `Donation*`, `Donate*` | Funding/sponsorship |

`Repository` / `Source` aren't in the name table but get a **hosting-platform**
icon from their domain (see below), so they're still recognized in practice.

### Recognized by domain (icon comes from the URL host)

- **Hosting:** `github.com`, `github.io`, `gitlab.com`, `bitbucket.org`, `google.com`
- **CI / quality services:** `codecov.io`, `coveralls.io`, `circleci.com`,
  `ci.appveyor.com`, `travis-ci.com`/`travis-ci.org`
- **Python ecosystem:** `pypi.org` (+ aliases), `python.org` / `*.python.org`
- **Social:** Discord, Gitter, Mastodon, Reddit, Slack, YouTube, Twitter/X, Bluesky

So a `Coverage = "https://codecov.io/gh/OWNER/REPO"` entry surfaces a coverage icon
right on the PyPI page — a direct, legitimate quality signal.

### Recommended set

```toml
[project.urls]
Homepage = "https://github.com/OWNER/REPO"
Documentation = "https://PKG.readthedocs.io"      # only if it exists
Repository = "https://github.com/OWNER/REPO"
Issues = "https://github.com/OWNER/REPO/issues"
Changelog = "https://github.com/OWNER/REPO/blob/main/CHANGELOG.md"  # only if file exists
Funding = "https://github.com/sponsors/OWNER"      # only if it exists
```

If there's no separate docs site, point `Documentation` at the README's docs
section (e.g. `…/REPO#readme`) rather than inventing a domain.

## Verified URLs (the green ✓)

PyPI shows a **green checkmark** next to URLs it can verify at upload time:

- **Self-links** to the project's own PyPI page are auto-verified.
- **Trusted Publishing** (publishing via GitHub Actions / GitLab CI with OIDC,
  no long-lived API token) verifies the repo's hosting URLs — e.g. uploading
  from `OWNER/REPO` via GHA verifies `https://github.com/OWNER/REPO` and its
  subpaths.

This is the single highest-trust signal on the page. If the user publishes via
CI, recommend setting up **Trusted Publishing** so Homepage/Repository/Issues
all show verified. (It's a PyPI publisher config + a GitHub Actions workflow; no
secrets to store.) Verification reflects control **at upload time** only.

## README badges (the at-a-glance quality strip)

PyPI renders the README, so a top-of-README badge row is where coverage/lint/CI
status actually shows. Standard set (shields.io), in the order popular packages use:

```markdown
[![PyPI version](https://img.shields.io/pypi/v/PKG.svg)](https://pypi.org/project/PKG/)
[![Python versions](https://img.shields.io/pypi/pyversions/PKG.svg)](https://pypi.org/project/PKG/)
[![License](https://img.shields.io/pypi/l/PKG.svg)](https://github.com/OWNER/REPO/blob/main/LICENSE)
[![CI](https://github.com/OWNER/REPO/actions/workflows/ci.yml/badge.svg)](https://github.com/OWNER/REPO/actions/workflows/ci.yml)
[![Coverage](https://codecov.io/gh/OWNER/REPO/branch/main/graph/badge.svg)](https://codecov.io/gh/OWNER/REPO)
[![Downloads](https://static.pepy.tech/badge/PKG/month)](https://pepy.tech/project/PKG)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Checked with mypy](https://www.mypy-lang.org/static/mypy_badge.svg)](https://mypy-lang.org/)
```

Pick badges you can **back with reality**:

- `pypi/v`, `pypi/pyversions`, `pypi/l` — derive automatically from your
  metadata; always safe once published.
- **CI** — only if there's a workflow; link the real workflow file.
- **Coverage** (Codecov/Coveralls) — only if coverage is uploaded in CI.
- **Downloads** (pepy/PePy) — vanity but common; fine to include.
- **Ruff / Black / mypy** — only if that tool is actually configured and run.

A badge for a check you don't run is worse than no badge. The skill proposes the
badge block but **does not edit the README** unless the user asks.

## Quality signals beyond the page

These don't render as metadata but are what "recognized as quality" rests on;
mention them when relevant:

- **`py.typed` marker** + `Typing :: Typed` classifier — ships type info (PEP 561).
- **Tests + coverage in CI**, surfaced via a Codecov/Coveralls URL and badge.
- **Lint/format config** (`[tool.ruff]`, etc.) committed and enforced in CI.
- **Trusted Publishing** for verified URLs and supply-chain trust.
- **A real `CHANGELOG.md`** linked via the `Changelog` URL.
- **A README that front-loads value** (one-liner → quickstart → details).
