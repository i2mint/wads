---
name: wads-ci-health
description: >-
  Point-in-time CI health snapshot for a single wads-managed Python repo (one
  using the i2mint uv-ci stub or inline uv workflow). Checks five things and
  reports a checklist: is CI green, is ci.yml the current stub (and how it's
  pinned), are the secrets wired correctly across the two layers, is the
  version in sync between pyproject/PyPI/git tags, and is docs publishing
  (Pages, Discussions) healthy. Use when the user asks "is CI green", "check
  CI health", "why didn't it publish", "is this repo's CI up to date", "are my
  CI secrets set up right", "is PyPI in sync with pyproject", "give me a CI
  snapshot", or "health-check this repo's CI". Diagnosis only — fixes are
  delegated: format migration → wads-migrate, push-back/version-sync repair →
  wads-ci-fix, fleet/batch work → wads-ci-sweep, Pages repair → epythet-docs.
  Does NOT cover generic CI strategy or non-wads pipelines — use ci-advisor or
  ci-setup for those.
metadata:
  audience: users
---

# Wads CI Health

Take a read-only snapshot of one wads-managed repo's CI and report it as a
checklist with a verdict per item. **Observe, don't invent**: every finding
must come from a command output or a file read below — never from assumption.
This skill diagnoses and delegates; it does not edit workflows, pyproject, or
GitHub settings.

## Step 0 — resolve the target repo

The target is the path the user gives, else the current working directory.
From inside it, derive the identifiers every later check needs:

```bash
gh repo view --json nameWithOwner,defaultBranchRef,hasDiscussionsEnabled \
  --jq '{repo:.nameWithOwner, default_branch:.defaultBranchRef.name, discussions:.hasDiscussionsEnabled}'
PKG=$(python3 -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['name'])")
```

Use `OWNER/REPO` from `nameWithOwner` in all `gh` commands below. If there's
no `pyproject.toml` or no GitHub remote, stop: this isn't a wads-managed repo
yet — point the user at the **wads-migrate** skill (or **setup-py-project**).

> The `import tomllib` one-liners here and below need Python ≥ 3.11; on 3.10
> substitute `import tomli as tomllib` (pip-installable).

## The snapshot checklist

Run checks A–E, then write the report (see "Report format"). Keep section F's
semantics in mind throughout — they prevent the most common wrong findings.

### A. Is CI green?

```bash
gh run list --repo OWNER/REPO --workflow ci.yml --limit 5 \
  --json conclusion,headBranch,event,displayTitle
```

Interpretation:

- `conclusion` values: `success`, `failure`, `cancelled`, `skipped`, empty
  (still running).
- **Only `event == "push"` runs on the default branch gauge repo health.**
  A failing `pull_request` run on a feature branch is work-in-progress, not a
  health finding.
- Latest default-branch push run failed → CI is red. Delegate analysis to the
  `wads-ci-debug` CLI (part of `wads[create]`, needs `GITHUB_TOKEN`):

  ```bash
  wads-ci-debug OWNER/REPO --fix --local-repo .
  # writes CI_FIX_INSTRUCTIONS.md into the local repo
  ```

⚠️ **Pitfall**: if the workflow file isn't named `ci.yml`, the command exits 1
with `HTTP 404: workflow ci.yml not found on the default branch`. Fall back to
`gh run list --repo OWNER/REPO --limit 5 --json conclusion,headBranch,event,displayTitle,workflowName`
and note the nonstandard name in the report. The unfiltered list also includes
`pages-build-deployment` runs (event `dynamic`, branch `gh-pages`) — ignore
those; they're GitHub's Pages deploys, not the CI workflow.

### B. Workflow format & currency

Classify `.github/workflows/ci.yml` (detection heuristics match the
wads-migrate skill):

```bash
rg -n 'uv-ci\.yml@|astral-sh/setup-uv|run-tests-uv|actions/setup-python' .github/workflows/ci.yml
ls setup.cfg setup.py 2>/dev/null
```

| Signal | Format | Verdict |
|---|---|---|
| `uses: i2mint/wads/.github/workflows/uv-ci.yml@PIN` | **stub** ★ | current default — report the pin |
| `astral-sh/setup-uv` + `i2mint/wads/actions/run-tests-uv` | inline uv | works; sanctioned escape valve if intentional, else stubifiable |
| `actions/setup-python` without `setup-uv` | 2025/older | outdated |
| `setup.cfg` present | old | legacy |

Format migrations are **owned by the wads-migrate skill** — name it in the
report; don't reproduce its recipes here. Before flagging inline uv as a
defect, ask whether it's the deliberate escape valve (custom workflow edits
beyond `[tool.wads.ci.*]` are the tell).

For a stub, report the pin:

```bash
rg -o 'uv-ci\.yml(@\S+)' -r '$1' .github/workflows/ci.yml
```

- `@master` — floats with wads. **Safe by default**: a bad wads merge can
  break CI runs everywhere, but publish is gated on workflow success, so a
  broken artifact never ships ("CI failure ≠ broken release").
- `@0.1.81` (a tag) — frozen; the repo only picks up wads workflow updates
  when re-pinned (`wads-migrate ci-to-stub --pin @0.1.81`). Report how far
  behind the pin is (compare against the latest wads tag:
  `gh api repos/i2mint/wads/tags --jq '.[0].name'`). A stale pin is a note,
  not an alarm — pinning is a legitimate choice for release-sensitive repos.

⚠️ **Pitfall**: i2mint tags are bare versions (`0.1.81`), **no `v` prefix** —
a stub pinned `@v0.1.81` references a nonexistent ref and the workflow call
fails outright.

### C. Secrets — compare three sets

Secrets reach CI through two layers: the stub *passes* named secrets to the
reusable workflow (transport), and `[tool.wads.ci.env]` decides which become
job env vars (assignment). Health means the three sets line up:

```bash
# Set D — declared env vars in pyproject (assignment layer)
python3 -c "
import tomllib
env = tomllib.load(open('pyproject.toml','rb')).get('tool',{}).get('wads',{}).get('ci',{}).get('env',{})
for kind in ('required_envvars','test_envvars','extra_envvars'):
    print(kind, env.get(kind, []))
print('secret_aliases', env.get('secret_aliases', {}))
"
# (equivalent, if wads is installed: wads-secrets list)

# Set P — names the stub passes (transport layer)
rg -A 20 'secrets:' .github/workflows/ci.yml | rg -o '^\s*([A-Z][A-Z0-9_]*):' -r '$1'

# Set S — secrets actually set on GitHub (repo level AND org level)
gh secret list --repo OWNER/REPO
gh secret list --org OWNER 2>/dev/null   # may need org admin; absence of access ≠ absence of secrets
```

⚠️ **Pitfall**: `gh secret list --repo` shows **only repo-level secrets** and
exits 0 with empty output when there are none. In the i2mint org, the working
secrets (`PYPI_PASSWORD`, `SSH_PRIVATE_KEY`, …) live at the **org level** — an
empty repo list is normal, not a finding. Check both levels before reporting a
secret as missing; if you can't read org secrets, say "unverifiable", not
"missing".

Findings table (map env-var names to secret names via `secret_aliases` first):

| Condition | Verdict |
|---|---|
| declared in D, secret name not in P | **Bug** — secret never reaches the reusable workflow. `required` → CI fails fast at export-ci-env; `test`/`extra` → var silently absent. Fix: `wads-secrets add VAR [SECRET]` (updates both layers) |
| in P, not in S (neither repo nor org) | CI receives an empty value; `required` ones fail fast. Set it: `gh secret set NAME --repo OWNER/REPO` or `wads-secrets add` |
| in P, not in D | Harmless — passed but never written to the job env (no over-assignment). Optional tidy-up, not a defect |
| `PYPI_PASSWORD` not in P or not in S | **Publishing is broken.** It must be passed and set, and its value must be a PyPI **API token** (`pypi-` prefix). You can't read values — verify via the last publish job's outcome, or ask the user |
| `PYPI_USERNAME` present | Obsolete (token-only auth) — ignorable leftover, especially at org level; don't demand removal |

`wads-secrets superset` prints the universe of names the stub may pass; a name
outside it needs a one-line wads PR (`wads.ci_secrets.DEFAULT_CI_SECRETS`).

### D. Version sync — pyproject vs PyPI vs git tag

```bash
python3 -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])"
curl -s "https://pypi.org/pypi/$PKG/json" | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print(d.get('info',{}).get('version') or d.get('message','unknown'))"
gh api repos/OWNER/REPO/tags --jq '.[0].name'   # remote truth; local 'git tag' may be unfetched/stale
```

(i2mint tags are bare versions like `0.2.3`, no `v` prefix. The `/tags` API
isn't strictly semver-ordered; if it looks off, list a few and judge.)

| Observation (on the default branch) | Verdict |
|---|---|
| all three equal | In sync — healthy |
| **PyPI ahead of pyproject** | The auto-bump **push-back failure**: publish succeeded but the version-bump commit couldn't be pushed back to the branch. The repo's pyproject lags PyPI until a later push-back lands. **Not republish-unsafe** — `isee gen-semver` bumps from `max(git tag, PyPI, pyproject)`, so the next run still computes an unused version (it never retries a taken one). So this is a *housekeeping* drift (the repo's stated version is stale), not a publish-blocker. Persistent recurrence → **wads-ci-fix** (SSH deploy key). One-off → it self-heals on the next successful push-back. ⚠️ First re-fetch: `gh`/PyPI reads lag by tens of seconds after a publish, so a momentary "PyPI ahead" can just be a stale read. |
| PyPI version exists but no matching tag | Tag push failed — same push-back family → **wads-ci-fix** |
| pyproject ahead of PyPI | Not necessarily wrong: publish disabled, `[skip ci]` commits, failing validation, or simply no default-branch merge since the bump. Cross-check with checks A and F |
| PyPI says `Not Found` | Never published — confirm `[tool.wads.ci.publish].enabled` and whether that's intentional |

### E. Docs publishing & repo features

```bash
python3 -c "
import tomllib
ci = tomllib.load(open('pyproject.toml','rb')).get('tool',{}).get('wads',{}).get('ci',{})
print('docs_enabled:', ci.get('docs',{}).get('enabled', True))   # default true
"
gh api repos/OWNER/REPO/pages --jq '{branch:.source.branch, path:.source.path, build_type:.build_type}'
gh repo view OWNER/REPO --json hasDiscussionsEnabled
```

- Healthy: `docs_enabled` true, Pages = `{branch: gh-pages, path: /}`,
  Discussions `true` (the ecosystem default).
- `gh api .../pages` exits 1 with `HTTP 404` → Pages not enabled. Docs are
  being built and pushed to `gh-pages` but never served.
- Any other Pages source (different branch, non-root path,
  `build_type: workflow`) → deliberate or broken; show it and ask before
  anyone changes it.
- **Repairs are owned by the epythet-docs skill** (enable/repoint Pages, 404
  debugging); the wads-migrate skill's post-migration section has the same
  decision tree. Report the finding, delegate the fix.
- Discussions off → report as a finding; the fix is owned by
  **wads-repo-doctor**'s GitHub-metadata dimension (it proposes
  `gh repo edit OWNER/REPO --enable-discussions` with user approval).

### F. Semantics you must know (to avoid wrong findings)

These are facts about the uv-ci reusable workflow. Violating them produces
confidently wrong reports:

- **Publish gating**: the publish job runs only on the repo's **default
  branch**, and only if the Linux `validation` matrix succeeded — there is no
  `always()`/`!cancelled()` escape hatch. A red feature branch never blocks
  (or explains) a publish.
- **windows-validation never blocks publish** (`continue-on-error: true`). A
  red Windows job with a successful publish is consistent, not a contradiction.
- **Commit markers**: `[skip ci]` skips everything (the CI's own bump commits
  carry it — don't report those as "unbuilt commits"); `[publish]` is the
  opt-in marker where publishing is marker-gated.
- **`coverage_threshold` in `[tool.wads.ci.testing]` is currently DEAD
  CONFIG**: it's defined in wads's `CIConfig`, but nothing in the CI actions
  or the reusable workflow reads or enforces it (no `--cov-fail-under`
  anywhere). Never report it as protection in place; if it's set to a nonzero
  value, report that it is *not* being enforced.
- **Doctests always run in CI**: `run-tests-uv` unconditionally appends
  `--doctest-modules -o doctest_optionflags='ELLIPSIS IGNORE_EXCEPTION_DETAIL'`.
  An import-unclean module breaks CI even with no test files; doctest-only
  coverage is a legitimate category in this ecosystem, not a gap.

## Report format

Emit one compact checklist, one verdict per check, findings under it:

```markdown
## CI health — OWNER/REPO (YYYY-MM-DD)

| Check | Status | Detail |
|---|---|---|
| CI green (default branch) | ✅ / ❌ | last 5 runs… |
| Workflow format | stub @master / inline uv / 2025 / old | pin currency… |
| Secrets | ✅ / ⚠️ | D/P/S mismatches… |
| Version sync | ✅ / ❌ | pyproject X · PyPI Y · tag Z |
| Docs & Pages | ✅ / ⚠️ | Pages source, Discussions |

### Findings & next steps
- <finding> → <delegated skill or command>
```

Every ❌/⚠️ line names its delegation target from the table below.

## Scope guardrails

- **Read-only.** This skill never edits `ci.yml`, `pyproject.toml`, GitHub
  settings, or secrets. Every fix is delegated to its owning skill or CLI and
  applied only with user approval.
- Don't reproduce migration recipes, push-back fixes, or Pages repair
  procedures — name the owning skill.
- Don't report unverifiable things as facts: secret *values* are unreadable,
  org secrets may be unlistable — say "unverifiable" and how to verify.
- Single repo only. "Check all my repos" → wads-ci-sweep.

## Related skills

| Finding | Delegate to |
|---|---|
| ci.yml not the stub / outdated format / wants pin change | **wads-migrate** skill |
| PyPI ahead of pyproject; tag/commit push-back failed | **wads-ci-fix** skill |
| Failing runs need log-level analysis | `wads-ci-debug OWNER/REPO --fix --local-repo .` CLI |
| Fleet-wide or batch CI work across many repos | **wads-ci-sweep** skill |
| Pages 404 / docs not serving / docs setup | **epythet-docs** skill |
| Wants the full repo picture (tests, docs, metadata, skills) | **wads-repo-doctor** skill |
| pyproject `[project]` metadata quality | **wads-pypi-polish** skill |
| Generic (non-wads) CI strategy or new pipeline design | ci-advisor / ci-setup skills |

## Closing checklist

- [ ] Target repo resolved; OWNER/REPO, default branch, PKG derived
- [ ] A–E each ran (or marked "unverifiable" with the reason)
- [ ] Only default-branch push runs judged CI health (A)
- [ ] Org-level secrets checked before calling anything "missing" (C)
- [ ] `coverage_threshold` not reported as enforced (F)
- [ ] Report emitted; every ❌/⚠️ has a delegation target
- [ ] Nothing was modified in the repo or on GitHub
