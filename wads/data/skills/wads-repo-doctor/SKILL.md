---
name: wads-repo-doctor
description: >-
  Full health diagnosis and improvement dispatch for a wads-managed Python repo
  (uv-ci stub, i2mint conventions). One read-only audit across every dimension
  — legacy packaging, CI generation and status, PyPI/pyproject version sync,
  PyPI metadata, tests, docstrings, docs publishing, GitHub metadata drift,
  type annotations/py.typed, import time, changelog, agent skills — then a
  prioritized health report and dispatch to specialist skills one dimension at
  a time. Use for "diagnose this repo", "repo health check", "what's wrong
  with this repo", "audit this package", "doctor this repo", "how healthy is
  this project", "bring this repo up to standard", "what should I improve
  here". Also trigger when the user names a repo and wants a general
  improvement pass. Does NOT itself migrate, debug CI, write tests, or fix
  docstrings — it diagnoses, prioritizes, and routes to the owning specialist
  skills. Only GitHub metadata alignment is fixed inline.
metadata:
  audience: users
---

# Wads Repo Doctor

Point at a repo, get a prioritized health report across every dimension, then
dispatch improvements to specialist skills one at a time. This skill is the
orchestrator of the repo-improvement suite: it diagnoses and routes; the
specialists fix. Golden rule: **observe, don't invent** — every finding in the
report derives from a verifiable source (the audit script's output, a file
read, a `gh` query), never from an assumption about what a repo "probably" has.

Diagnosis is strictly read-only. The only fixes applied by this skill itself
are GitHub metadata edits (description / homepage / topics), and only after
showing the proposed values and getting confirmation.

## Step 0 — resolve the target repo

Operate on the path the user gives; otherwise the current working directory.
Then sanity-check it is auditable:

```bash
ls -d .git pyproject.toml setup.cfg setup.py 2>/dev/null
```

- Has `.git` and a `pyproject.toml` → proceed.
- Has `.git` and only legacy setup files (`setup.cfg` / `setup.py`) → proceed;
  the report will lead with migration.
- No `.git`, or none of those files → not an auditable Python package repo.
  Stop and ask the user what they meant.

## Step 1 — run the audit

```bash
python scripts/repo_audit.py /path/to/repo            # human report
python scripts/repo_audit.py /path/to/repo --json     # machine-readable
python scripts/repo_audit.py /path/to/repo --no-network  # offline: skips gh + PyPI
```

The script is stdlib-only, read-only, and degrades gracefully: without `gh` or
network it silently skips the GitHub-side and PyPI checks and still reports
everything file-based. It checks: legacy packaging files, pyproject shape
(backend, metadata fields, license form, stale `testpaths`), CI workflow
generation (uv stub with pin / inline uv with action-pin staleness / 2025 /
legacy / none, plus npm-ci stubs), package modules missing docstrings, test
file count, CHANGELOG and `py.typed` presence (recorded as facts, not
findings — see Step 2), skills presence and name compliance, GitHub
description/homepage/topics/Discussions/Pages, latest `ci.yml` run conclusion,
and PyPI-vs-pyproject version sync.

One dimension the script does not cover — dependency drift. If the `wads`
package is installed, cover it with:

```bash
wads-deps /path/to/repo     # bare path argument; read-only without --fix
```

Read the audit output in full before proposing anything.

## Step 2 — dimension → specialist map

Each finding class has exactly one owner. Dispatch there; never re-derive a
specialist's content here.

| Finding class | Owner |
|---|---|
| Legacy packaging (`setup.cfg`, `setup.py`, `MANIFEST.in`, `requirements.txt`); old/2025 CI format; no pyproject | **wads-migrate** skill |
| CI run failing; stale action pins; secrets not reaching CI; PyPI version ahead of pyproject (push-back) | **wads-ci-health** skill |
| PyPI metadata gaps (description, license form, classifiers, keywords, urls, requires-python, LICENSE file) | **wads-pypi-polish** skill |
| Test coverage gaps; no tests found; stale `testpaths` | **wads-test-coverage** skill |
| Docstring/README coverage and alignment (missing module docstrings, README drift from the API) | **wads-docs-coverage** skill |
| Docstring rendering symptoms (italic code, literal `Returns:` headers, red asterisks on published docs) | **wads-docstring-render** skill |
| Docs publishing (Pages 404, gh-pages config, docs build failures) | **epythet-docs** skill |
| Missing or noncompliant skills (no skills; frontmatter name ≠ dirname; layout) | **wads-skillify** skill |
| Missing or weak type annotations on the public API; `py.typed` absent or shipping questions | **wads-type-coverage** skill |
| Slow or unclean imports (`python -X importtime` hot spots, `--doctest-modules` import failures, heavy top-level dependencies) | **wads-import-time** skill |
| Missing or stale `CHANGELOG.md` | **wads-changelog** skill |
| Dependency drift (declared vs imported) | `wads-deps /path/to/repo` CLI |
| GitHub metadata drift (description / homepage / topics vs pyproject) | **handled inline here** (see below) |

Two of these the audit script records as **facts, not findings**: `has_changelog`
and `has_py_typed` (in the `--json` facts block). When either is `false`, treat
it as a LOW finding and dispatch per the table — **wads-changelog** /
**wads-type-coverage** respectively — never generic "add a CHANGELOG" or
"add py.typed" advice.

## Step 3 — prioritize

Order the report (and the dispatch sequence) by:

1. **Broken CI / publishing** — failing `ci.yml` runs, PyPI ahead of pyproject,
   no CI at all. Everything else is moot while the pipeline is broken.
   Dispatch by cause: pipeline/publishing wiring (stub, secrets, push-back) →
   wads-ci-health's delegation map; code-caused collection failures (e.g.
   `--doctest-modules` can't import a module) → wads-import-time.
2. **Legacy migration** — setup.cfg/setup.py, old/2025 CI generations.
   Migrating first avoids polishing files that migration will replace.
3. **Correctness / alignment** — docstring rendering symptoms, README claims
   that no longer match the API, stale testpaths.
4. **Coverage** — test coverage gaps, missing docstrings.
5. **Polish / discoverability** — PyPI metadata, GitHub metadata, agent skills,
   type-annotation coverage / `py.typed` (wads-type-coverage), import-time
   tuning (wads-import-time, when CI is unaffected), and CHANGELOG
   generation/maintenance (wads-changelog).

The script's HIGH/MEDIUM/LOW grouping approximates this; apply the ordering
above when sequencing work within a severity band.

## Step 4 — present the health report

Present findings grouped by severity. For each finding: what was observed (the
evidence), why it matters (one line), and the owner from the Step 2 table.
End with a proposed dispatch order per Step 3.

Then **offer — don't auto-do** — to save the report as a GitHub issue on the
target repo:

```bash
gh issue create -R OWNER/REPO --title "Repo health report" --body-file report.md
```

Only after explicit confirmation. Before writing the body, strip anything
machine-local: absolute paths, hostnames, usernames. Use repo-relative paths
(`dol/caching.py`, `.github/workflows/ci.yml`) and public URLs only.

## Dispatching improvements

- Ask the user which dimension to start with (default: the Step 3 order).
- Invoke the specialist skill for that one dimension and let it run to
  completion — including its own verification steps.
- **Never apply two dimensions at once.** Parallel edits make it impossible to
  attribute a CI break or a regression to its cause.
- **Re-run the audit after each dispatched improvement** and diff against the
  previous report: confirm the finding cleared and nothing new appeared.
- Repeat until the user stops or the report is clean.

## GitHub metadata alignment (the one dimension fixed inline)

Read–compare–propose–apply. Read both sides:

```bash
gh repo view OWNER/REPO --json description,homepageUrl,repositoryTopics,hasDiscussionsEnabled
python3 -c "import tomllib; p=tomllib.load(open('pyproject.toml','rb'))['project']; \
print(p.get('description')); print(p.get('keywords')); print(p.get('urls'))"
```

Mapping (pyproject is the source of truth):

| GitHub field | Derive from |
|---|---|
| description | `[project].description` |
| homepage | the Pages URL (`https://OWNER.github.io/REPO/`) when docs publishing is enabled (`[tool.wads.ci.docs]`, default on) and Pages is configured; else `[project.urls].Homepage` |
| topics | slugified `[project].keywords` — lowercase, alphanumeric + hyphens, max 35 chars each |

**Always show the proposed values to the user before mutating** — these are
public-facing fields. Then apply:

```bash
gh repo edit OWNER/REPO --description "..." --homepage "https://OWNER.github.io/REPO/"
gh repo edit OWNER/REPO --add-topic storage --add-topic interface
# replace the whole topic set atomically instead:
gh api -X PUT repos/OWNER/REPO/topics -f "names[]=storage" -f "names[]=interface"
# Discussions (ecosystem default is on):
gh repo edit OWNER/REPO --enable-discussions
```

Re-run the audit afterwards to confirm the drift findings cleared.

## ⚠️ Pitfalls

- ⚠️ **An inline uv `ci.yml` is a sanctioned escape valve, not a defect.** The
  audit suggests `wads-migrate ci-to-stub` as LOW, but if the workflow has
  custom edits beyond the stock template, the repo owns its CI on purpose —
  ask before recommending conversion.
- ⚠️ **`wads-deps` takes a bare path** (`wads-deps .`). There is no `scan`
  subcommand — older docs showing `wads-deps scan .` are wrong.
- ⚠️ **No `tests/` dir does not mean untested.** The wads CI always runs
  `--doctest-modules`; doctest-only coverage is a legitimate category in this
  ecosystem. Let wads-test-coverage attribute it before calling it a gap.
- ⚠️ **PyPI ahead of pyproject is a symptom, not a version typo.** It means
  the CI version-bump push-back failed. Do NOT hand-bump the version to "fix"
  it — dispatch to wads-ci-health, which routes the root cause to wads-ci-fix.
- ⚠️ **Missing `docsrc/` is normal.** epythet's CI action scaffolds docs on
  the fly; many repos publish full docs sites with no committed `docsrc/`.
  The audit records it as a fact, not a finding — keep it that way.
- ⚠️ **Don't read exit codes through a pipe.** `cmd | tail; echo $?` reports
  tail's status. Capture output to a file and test `$?` directly when a
  command's success matters.
- ⚠️ **GitHub topics have hard rules**: lowercase alphanumeric + hyphens,
  max 35 chars. Slugify keywords first or `gh repo edit` rejects them.

## Scope guardrails

- Diagnosis is **read-only**. The audit script never writes; neither do you
  during Steps 0–4.
- This skill fixes nothing except GitHub metadata — every other improvement is
  dispatched to its specialist.
- Public-facing mutations (`gh repo edit`, `gh issue create`, Pages changes)
  require explicit user confirmation with the proposed values shown first.
- One dimension at a time; re-audit between dimensions.
- Never write secrets, absolute local paths, hostnames, or usernames into
  issues or any committed file.

## Related skills

- **wads-migrate** — legacy → modern wads migration (setup.cfg, old CI, stub).
- **wads-ci-health** — single-repo CI snapshot: green? current? secrets? sync?
- **wads-ci-fix** — the CI push-back failure (PyPI ahead of pyproject).
- **wads-pypi-polish** — pyproject/PyPI metadata polish.
- **wads-test-coverage** — coverage gaps, doctest attribution, writing tests.
- **wads-docs-coverage** — docstring/README coverage and alignment.
- **wads-docstring-render** — docstrings that render wrong under epythet/Sphinx.
- **epythet-docs** — docs publishing, GitHub Pages, Sphinx setup.
- **wads-skillify** — give the repo compliant agent skills.
- **wads-type-coverage** — public-API type-annotation coverage and the `py.typed` decision.
- **wads-import-time** — import-time measurement, heavy/lazy imports, import hygiene.
- **wads-changelog** — generate and maintain CHANGELOG.md from git history and version tags.
- **wads-ci-sweep** — fleet-wide batch migration (many repos, not one).

## Closing checklist

- [ ] Target repo resolved and verified (git + pyproject or legacy setup files)
- [ ] Audit run; output read in full (plus `wads-deps` if wads is installed)
- [ ] Report presented grouped by severity, each finding with evidence + owner
- [ ] Dispatch order proposed per the Step 3 priority
- [ ] GitHub issue offered, created only on confirmation, no machine-local info
- [ ] Each dispatched improvement followed by a re-audit
- [ ] GitHub metadata edits (if any) proposed before applied
- [ ] No two dimensions touched at once
