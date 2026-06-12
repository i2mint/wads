---
name: wads-test-coverage
description: >-
  Diagnose and close test-coverage gaps in a wads-managed Python repo (pytest +
  doctests + uv CI). Measures coverage exactly as CI does (doctests included),
  adds branch coverage and per-test contexts, buckets every public
  function/class as untested / doctest-only / test-covered, then writes the
  missing tests. Use for "what's untested", "check test coverage", "coverage
  gaps", "which functions have no tests", "is this only covered by doctests",
  "improve coverage", "raise coverage", "write tests for the uncovered parts",
  "add tests for this module". Also trigger when CI coverage numbers look wrong
  or a doctest-heavy package looks untested. Does NOT analyze failing-test
  output (pipe pytest output to the wads-test-analyze CLI), measure docstring
  presence (wads-docs-coverage), or check CI workflow health (wads-ci-health).
metadata:
  audience: users
---

# Wads Test Coverage

Diagnose which parts of a package are genuinely untested — distinguishing
"covered only by doctests" from "covered by dedicated tests" — and then write
the tests that close the real gaps. The golden rule is **observe, don't
invent**: every gap claim comes from an actual coverage measurement, and every
new test is verified to pass (and to move the numbers) before you report it.

This ecosystem is doctest-first: doctests are simultaneously docs and tests,
and CI **always** runs them. A measurement that skips doctests is wrong here.

## Step 0 — Resolve the target repo and package dir

Operate on the repo path the user gives, else the current working directory.
Then establish ground truth about *what to measure* and *how CI measures it*:

```bash
cd /path/to/repo   # the target repo root; all commands below run from here
python - <<'EOF'
import pathlib
try:
    import tomllib
except ImportError:        # Python 3.10
    import tomli as tomllib
t = tomllib.load(open('pyproject.toml', 'rb'))
name = t['project']['name']
pkg = name.replace('-', '_')
print(f"project name : {name}")
print(f"package dir  : {pkg}  (exists: {pathlib.Path(pkg).is_dir()})")
tp = t.get('tool', {}).get('pytest', {}).get('ini_options', {}).get('testpaths', [])
print(f"testpaths    : {tp}  (exist: {[pathlib.Path(p).is_dir() for p in tp]})")
c = t.get('tool', {}).get('wads', {}).get('ci', {}).get('testing', {})
print(f"pytest_args  : {c.get('pytest_args', ['-v', '--tb=short'])}")
print(f"exclude_paths: {c.get('exclude_paths', ['examples', 'scrap'])}")
print(f"coverage     : enabled={c.get('coverage_enabled', True)}, "
      f"threshold={c.get('coverage_threshold', 0)} (threshold is NOT enforced by CI)")
EOF
```

`PKG` below means the package *directory* printed above. ⚠️ **Pitfall:
`--cov` must name the package dir, not `[project].name`.** A hyphenated
project name (`my-pkg`) with an underscored dir (`my_pkg`) — or a dir that
differs from the name entirely — makes `--cov=<project-name>` collect nothing
and report misleading or empty coverage. Verify the dir exists first.

⚠️ **Pitfall: stale `testpaths`.** Many repos declare `testpaths = ["tests"]`
with no top-level `tests/` dir (tests live in `PKG/tests/` instead). When the
declared dir is missing, pytest falls back to rootdir-wide collection — so CI
quietly collects more (or different) things than the config suggests. Note it
as a finding; the measurement below sidesteps it by passing paths explicitly.

## Diagnose

### 1. Measure — mirror CI, plus what CI doesn't give you

Run from the target repo root (capture output to a file — see pitfall below):

```bash
python -m pytest --doctest-modules \
  -o doctest_optionflags='ELLIPSIS IGNORE_EXCEPTION_DETAIL' \
  --cov=PKG --cov-branch --cov-context=test \
  --cov-report=term-missing --cov-report=json:coverage.json \
  PKG > /tmp/coverage_run.log 2>&1
rc=$?            # read the exit code BEFORE anything else touches it
tail -40 /tmp/coverage_run.log; echo "pytest exit: $rc"
```

Why each piece, relative to what the uv CI (`run-tests-uv`) does:

| Flag | In CI? | Why it's here |
|---|---|---|
| `--doctest-modules -o doctest_optionflags=...` | always | **Non-optional.** CI unconditionally runs doctests with exactly these flags. Omit it and every doctest-primary package looks untested — the single most misleading mistake a coverage diagnosis can make here. |
| `--cov=PKG --cov-report=term-missing` | yes (when `coverage_enabled`) | Same line-coverage CI reports. |
| `--cov-branch` | no | CI is line-only. Branch coverage exposes untested `if`/`except` arms — exactly where bugs hide in "covered" code. |
| `--cov-context=test` | no | Records *which* test or doctest executed each line — the raw data for doctest-vs-test attribution. |
| `--cov-report=json:coverage.json` | no | Machine-readable artifact (CI produces none) with per-function/class regions (coverage >= 7.5). |

For full CI fidelity, append the repo's `[tool.wads.ci.testing]` values from
Step 0: each `pytest_args` entry as-is, and each `exclude_paths` entry as
`--ignore=<path>`. Example with the defaults:

```bash
python -m pytest --doctest-modules \
  -o doctest_optionflags='ELLIPSIS IGNORE_EXCEPTION_DETAIL' \
  --cov=PKG --cov-branch --cov-context=test \
  --cov-report=term-missing --cov-report=json:coverage.json \
  --ignore=examples --ignore=scrap -v --tb=short \
  PKG > /tmp/coverage_run.log 2>&1
```

If the repo keeps its test suite *outside* the package (a real top-level
`tests/`), append that dir too (`... PKG tests`) — otherwise dedicated tests
aren't collected and everything mislabels as doctest-only or untested.

⚠️ **Pitfall: never read an exit code through a pipe.** `pytest ... | tail`
makes `$?` report tail's status, not pytest's (a verified false-green source).
Always redirect to a file, capture `$?` immediately, then inspect the file.

⚠️ **Pitfall: the suite must be green before you measure.** A collection
error or failing test truncates coverage data. If the run fails, fix or
report that first (for failure triage, pipe the log to the `wads-test-analyze`
CLI — it parses pytest *text* output, not junit XML).

### 2. Per-module gap table

```bash
python -m coverage report --format=markdown --sort=cover --skip-covered
```

Worst modules first, fully-covered files skipped — paste-ready for an issue
or report. (`--format=markdown` landed in coverage 7.0; the same data is in
`coverage.json` under `files.*.summary` if the flag is unavailable.)

### 3. Bucket the public API: untested / doctest-only / test-covered

Export contexts, then run the bundled analyzer:

```bash
python -m coverage json --show-contexts -o coverage_ctx.json
python scripts/coverage_gaps.py /path/to/repo            # human report
python scripts/coverage_gaps.py /path/to/repo --json     # machine-readable
```

(`scripts/` is relative to this skill; the repo path defaults to cwd.)
The script reads `coverage_ctx.json` and buckets every public function/class
region by its execution contexts:

- **doctest contexts** look like `pkg/mod.py::pkg.mod.func|run` — the nodeid
  file is the module itself, the item a dotted object name.
- **test contexts** look like `tests/test_x.py::test_name|run`.
- No contexts at all (or only import-time execution) → **untested**.

"Public" = no component of the dotted name starts with `_`. Test files are
excluded from the buckets. The script needs per-region data from
**coverage >= 7.5** (`files.*.functions` / `files.*.classes`) and errors
clearly if it's absent — upgrade coverage rather than approximating with AST.

⚠️ **Pitfall: `coverage.json` (from `--cov-report=json:`) has regions but NO
contexts.** Attribution needs `coverage_ctx.json` from `coverage json
--show-contexts`. The script tells you exactly this if you feed it the wrong
file.

### Doctrine: doctest-only is a category, not a verdict

In this ecosystem doctest-only coverage is **legitimate** — doctests are the
documentation *and* the tests, and CI runs them on every push. Do not report
the doctest-only bucket as a gap per se. Do flag, within it:

- **error paths and edge cases** covered only by a happy-path doctest
  (the `--cov-branch` missing-branches column points right at these);
- functions whose doctest asserts trivia (e.g. just constructs an object)
  while the meaningful behavior goes unexercised.

The **untested** bucket is the real gap list. Prioritize it.

## Complete — write the missing tests

### Priority order

1. **Untested public API** — the `untested` bucket from `coverage_gaps.py`,
   worst modules first (the script already orders them).
2. **Branch gaps in modules you're already touching** — missing branches from
   `term-missing` / `coverage.json` (`files.*.summary.missing_branches`),
   especially error paths behind `if`/`raise`/`except`.
3. Doctest-only regions whose edge cases deserve a real test (see doctrine).

### Style rules

- **Doctests for example-shaped behavior** — the happy path a reader should
  see. They double as documentation, which is the point here. Two admission
  criteria for a doctest:
  - **(a) Low setup.** A line or two of setup is fine; if the docstring fills
    up with hard-to-read scaffolding that exists only to create test
    conditions, it stops being documentation — write a pytest test instead.
  - **(b) Robust assertions.** These run on different platforms and Python
    versions. Anything whose repr is unordered or environment-dependent
    (sets, dict views, object reprs, float noise, paths) must not be
    asserted by displayed output — use an explicit comparison instead:

    ```python
    >>> result = f('x')              # BAD followup:  >>> result
    >>> assert result == {'a', 'b'}  # GOOD: order-independent
    >>> sorted(other_result)         # also GOOD: deterministic display
    ['a', 'b']
    ```

    Never show memory addresses, ids, or timestamps; use ELLIPSIS (`...`)
    where partial output is unavoidable, and `# doctest: +SKIP` only as a
    last resort (skipped examples don't count as coverage).
- **Pytest tests** (in the repo's existing test dir) for edge cases, error
  paths (`pytest.raises`), parametrized matrices, and anything needing
  fixtures/tmp dirs — things that would clutter a docstring.
- **A broken doctest is a broken test** — when the measurement run (or the
  rollout gate) fails on an existing doctest, fix it like any failing test:
  decide whether the code or the documented example is wrong, never delete
  the example just to go green.
- **Match the existing test style** — read a neighboring test file first;
  mirror its naming, imports, and assertion idioms.
- **No new dependencies.** Stdlib + pytest + what the repo already declares.
- ⚠️ **Pitfall: a package utility named `test_*` gets collected as a test**
  under this measurement (and in CI). If you write or meet a non-test helper
  named `test_*` in package code, set `__test__ = False` on it (or rename).
- ⚠️ **Pitfall: import-unclean modules break `--doctest-modules`.** It imports
  every module; one that reads env vars or hits the network at import time
  fails collection. Mitigation: declare the var in
  `[tool.wads.ci.env].test_envvars` (CI) and export it locally; longer term,
  make imports lazy — that fix is **wads-import-time**'s job. Don't "fix" it
  by dropping `--doctest-modules`.

### Verify

- Full suite **green before AND after** — run the Step 1 command both times.
  Never break an existing test; if a new test exposes a real bug, report the
  bug rather than bending the test to pass.
- Re-run the measurement and report the delta: totals
  (`python -c "import json; print(json.load(open('coverage.json'))['totals']['percent_covered'])"`),
  the per-module table, and the before/after bucket counts from
  `coverage_gaps.py --json`.

### CI enforcement (optional, propose first)

`[tool.wads.ci.testing].coverage_threshold` is **dead config today** — CI
reads it but never enforces it (no `--cov-fail-under` anywhere in the uv
actions). To actually gate, override the test command:

```toml
[tool.wads.ci.commands]
# Replaces CI's test command entirely — so it must re-include the doctest flags:
test = "pytest --doctest-modules -o doctest_optionflags='ELLIPSIS IGNORE_EXCEPTION_DETAIL' --cov=PKG --cov-report=term-missing --cov-fail-under=80"
```

This is a CI-affecting change: propose it to the user, set the bar at (or
slightly below) the measured level so it ratchets rather than blocks, and
verify on a non-default branch before merging.

## Scope guardrails

- **Diagnosis is read-only.** The measurement writes scratch artifacts into
  the repo root (`.coverage`, `coverage.json`, `coverage_ctx.json`) — never
  commit them; delete them when done unless `.gitignore` already covers them.
- **Never game the metric**: don't delete, skip, or weaken existing tests;
  don't add `# pragma: no cover` or shrink `exclude_paths`/test scope to make
  numbers look better. Coverage config changes need explicit user agreement.
- **Don't touch CI without proposing** — threshold gating and
  `[tool.wads.ci.*]` edits are verified on a non-default branch first.
- Stay in your lane: this skill measures and writes *tests*. Failing-CI
  forensics, docstring quality, and publishing are other skills' territory
  (below).

## Related skills

- **wads-repo-doctor** — the orchestrator; runs this skill as the
  test-coverage step of a full repo health pass.
- **wads-docs-coverage** — docstring *presence* and README alignment.
  Docstring presence ≠ doctest coverage: a function can have a beautiful
  docstring and still sit in the `untested` bucket (and vice versa).
- **wads-ci-health** — is CI green, current stub, secrets/publish sane.
  Coverage findings about CI wiring (dead threshold, line-only) land there.
- **`wads-test-analyze` CLI** — failure triage: pipe pytest *text* output to
  it (`pytest ... | wads-test-analyze`); it does not parse junit XML.

## Closing checklist

- [ ] Target repo resolved; `PKG` dir verified to exist (not assumed from name)
- [ ] Measurement run **with** `--doctest-modules` + CI's `pytest_args`/`--ignore`s
- [ ] Exit code captured directly (no pipes); suite green before changes
- [ ] Gap table + `coverage_gaps.py` buckets produced (regions + contexts present)
- [ ] Doctest-only bucket reviewed for unexercised error paths, not flagged wholesale
- [ ] New tests follow existing style; doctest outputs deterministic; no new deps
- [ ] Full suite green after; coverage delta and bucket delta reported
- [ ] Scratch artifacts (`.coverage`, `coverage*.json`) not committed
- [ ] Any CI gating change proposed, then verified on a non-default branch
