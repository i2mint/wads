---
name: wads-pypi-polish
description: >
  Audit and improve a package's pyproject.toml so its PyPI page looks
  professional, is discoverable in search, and signals quality. Use when the
  user wants to "polish pyproject.toml", "make my PyPI page look professional",
  "improve PyPI discoverability", "add classifiers / keywords / project URLs",
  "add badges", "review my package metadata", "why does my PyPI page look
  bare", or prepare a package for publishing/release. Adds and validates
  description, readme, license (SPDX), requires-python, keywords, trove
  classifiers, and project.urls with PyPI-recognized labels; recommends README
  badges and quality signals (coverage, lint, typing). Does NOT change code,
  dependencies, or versions; CI/publishing state belongs to wads-ci-health,
  docs publishing (Pages/Sphinx) to epythet-docs.
metadata:
  audience: users
---

# PyPI Polish

Make a package's `pyproject.toml` metadata professional, discoverable, and
quality-signalling — the way the most popular packages (pydantic, httpx, rich,
…) do it. You **observe facts from the repo**, then **fill metadata gaps**. You
never fabricate URLs, audiences, or claims you can't verify.

## What a "professional" PyPI page actually needs

PyPI renders metadata from `[project]` into the page. The fields below are the
levers. Three of them drive almost all of the perceived quality:

1. **`description`** — the one-line headline under the name and in search results.
2. **`classifiers`** — the faceted badges + what powers PyPI's filtered search.
3. **`project.urls`** — the left-sidebar links; PyPI gives *recognized labels*
   custom icons (and a green ✓ when verified via Trusted Publishing).

Everything else (`keywords`, `readme`, `license`, `requires-python`, README
badges) supports discovery and trust.

## Golden rule: observe, don't invent

Before writing anything, gather ground truth from the repo. Run the audit
script — it reads the repo and reports exactly what's present, weak, or missing:

```bash
python scripts/audit_pyproject.py [REPO] [--json]   # REPO defaults to cwd
# classifier validation needs trove-classifiers — get it via uvx, never pip install:
uvx --python 3.12 --with trove-classifiers python scripts/audit_pyproject.py REPO
```

Then derive each metadata field from a **real source**, never a guess:

| Field | Derive from (in order) |
|---|---|
| repo / source URL | `git remote get-url origin` (normalize `git@`→`https`, strip `.git`) |
| Python versions for classifiers | the CI test matrix → else `requires-python` lower bound up to latest tested |
| `Development Status` | existing value → version number → ask if unclear (don't promote to Stable on a guess) |
| `Typing :: Typed` | only if a `py.typed` marker file exists in the package |
| `Documentation` URL | a real docs site only (Read the Docs, `docs.*`, project site). If none, link the README section, not a fabricated domain |
| `Changelog` URL | an actual `CHANGELOG.md` in the repo |
| `Funding` URL | an existing GitHub Sponsors / funding link only |
| `Intended Audience`, `Topic` | the README's actual description of who/what it's for |

If a fact can't be established, **leave the field out and note it** rather than
inventing. A wrong "Production/Stable" or a dead docs link looks *less*
professional, not more.

## Workflow

0. **Resolve the target repo.** The target is the path the user gives; if none,
   the current working directory. All commands below run against that path —
   never assume a particular repo.
1. **Locate & read.** Find `pyproject.toml`. Read `[project]`, `[build-system]`,
   the README, the `LICENSE` file, and detect the package layout (src/flat) and
   whether a `py.typed` marker exists.
2. **Run the audit** (`scripts/audit_pyproject.py`) for a prioritized gap report.
   It also validates existing classifiers against the canonical trove list.
3. **Gather ground truth** for each missing/weak field using the table above
   (git remote, CI matrix, file existence). Use `git remote -v`, `ls`, grep CI
   workflow files under `.github/workflows/` for the Python matrix.
4. **Propose changes** as a concise diff-style summary grouped by impact (high:
   description, classifiers, urls; medium: keywords, license SPDX, requires-python;
   low: badges). For anything requiring a judgement call (dev status, audience,
   keywords), state your inference and its source; ask only if genuinely ambiguous.
5. **Apply edits** to `pyproject.toml`, preserving the user's existing formatting,
   quote style, comments, and table order. Add new tables near related ones
   (`urls` after `classifiers`). Don't reorder or restyle untouched content. If
   the project uses Poetry's legacy `[tool.poetry]` layout, edit in that schema
   (see references/build-backends.md) rather than forcing `[project]`.
6. **Validate** after editing: re-run the audit; if build tooling is available,
   `python -m build` (or the project's backend) to confirm metadata parses.
7. **Recommend README badges & quality signals** (see references/pypi-icons.md) —
   propose, don't auto-insert into the README unless asked.
8. **Report** what changed and what still needs a human decision (e.g. "no docs
   site found — point Documentation at the README, or set up Read the Docs?").

> ⚠️ **Pitfall:** classifiers are a controlled vocabulary — a single invalid
> string doesn't fail locally; **twine/PyPI rejects the whole upload** at
> release time. Always validate (step 2's audit, run via uvx so
> `trove-classifiers` is available) before anything ships.

> ⚠️ **Pitfall:** under PEP 639 the SPDX `license = "MIT"` string is the source
> of truth, and some newer backends error when a deprecated
> `License :: OSI Approved :: …` classifier coexists with it — keep that
> classifier only as an optional search facet, never contradicting the SPDX
> expression. Similarly, never auto-promote `Development Status` (e.g. to
> `5 - Production/Stable`) from a hunch; confirm with the user.

## The full target shape

A complete, professional `[project]` block (static-version variant):

```toml
[project]
name = "your-package"
version = "0.3.2"                      # or: dynamic = ["version"]
description = "One crisp line: what it does, for whom."   # < ~100 chars, no period needed
readme = "README.md"
requires-python = ">=3.10"
license = "MIT"                        # SPDX expression (PEP 639), not the old table form
license-files = ["LICENSE"]
authors = [{ name = "Your Name", email = "you@example.com" }]
keywords = ["...", "..."]              # 5–10, lowercase, search terms users actually type
classifiers = [
  "Development Status :: 4 - Beta",
  "Intended Audience :: Developers",
  "License :: OSI Approved :: MIT License",   # optional alongside SPDX; many keep it for search facets
  "Operating System :: OS Independent",
  "Programming Language :: Python :: 3",
  "Programming Language :: Python :: 3 :: Only",
  "Programming Language :: Python :: 3.10",
  "Programming Language :: Python :: 3.11",
  "Programming Language :: Python :: 3.12",
  "Programming Language :: Python :: 3.13",
  "Topic :: Software Development :: Libraries :: Python Modules",
  "Typing :: Typed",                  # only if py.typed ships
]
dependencies = ["..."]                 # leave as-is; this skill doesn't touch deps

[project.urls]                         # labels below get custom PyPI icons
Homepage = "https://github.com/you/your-package"
Documentation = "https://your-package.readthedocs.io"
Repository = "https://github.com/you/your-package"
Issues = "https://github.com/you/your-package/issues"
Changelog = "https://github.com/you/your-package/blob/main/CHANGELOG.md"
Funding = "https://github.com/sponsors/you"
```

See **references/classifiers.md** for the full classifier menu and how to choose,
and **references/pypi-icons.md** for the exact labels/domains PyPI gives icons to
plus the README badge set.

## Scope guardrails

- **Do not** add, remove, pin, or unpin dependencies. **Do not** bump versions.
- **Do not** invent a docs site, audience, funding link, or "Stable" status.
- **Prefer SPDX** `license = "MIT"` (PEP 639) over the deprecated
  `license = { text = ... }` table. Keep an `License :: OSI Approved :: …`
  classifier only if the user wants the extra search facet; it's no longer
  required and PEP 639 deprecates relying on it for license info.
- Keep `requires-python` as the source of truth for install gating; classifiers
  are search-only and must not contradict it.
- Preserve the user's existing style (house style: un-versioned deps by default,
  `argh`-based scripts — leave those untouched).

## Related skills

- **wads-repo-doctor** — full-repo health entry point; runs this skill as its PyPI-metadata dimension.
- **wads-ci-health** — CI/publishing state of a wads-managed repo (stub currency, secrets, publish/version sync).
- **epythet-docs** — docs publishing (GitHub Pages, Sphinx/epythet); where the `Documentation` URL should point.

## Closing checklist

- [ ] Audit script run on the target repo before proposing anything.
- [ ] Every added/changed field traces to a verified source (git remote, CI
      matrix / `[tool.wads.ci.testing]`, file existence) — nothing invented.
- [ ] Classifiers validated against the canonical trove list (uvx run).
- [ ] Existing formatting, quote style, comments, and table order preserved.
- [ ] Re-audit after edits comes back clean (remaining gaps are explicit user
      decisions, not oversights).
- [ ] README badges proposed to the user, not auto-inserted.
- [ ] No dependency or version changes slipped in.
