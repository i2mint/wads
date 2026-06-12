---
name: wads-docs-coverage
description: >-
  Documentation coverage for a wads-managed Python repo: diagnose, align,
  complete. Measures docstring presence (every module, class, and function),
  executes the README's code blocks to prove they still run, cross-checks
  README names and install lines against the live API, and detects
  signature↔docstring drift; then proposes removals for obsolete docs and
  writes missing Google-style docstrings (with doctests) and README sections.
  Use when the user says "audit the docs", "docs coverage", "what's missing
  docstrings", "write the missing docstrings", "is the README up to date",
  "check the README examples", "the README mentions things that don't exist",
  or "docstring coverage report". Also trigger after a refactor or rename that
  may have stranded docs, or when CI lint flags D1xx missing-docstring errors.
  Does NOT fix RST/Sphinx rendering mistakes (use wads-docstring-render), does
  NOT cover docs publishing, GitHub Pages, or 404s (use epythet-docs), and
  does NOT measure test coverage (use wads-test-coverage).
metadata:
  audience: users
---

# Docs Coverage: Diagnose, Align, Complete

Measure how completely and truthfully a repo is documented — docstring
presence, README examples that actually run, README claims that match the
live API — then retire what's obsolete and write what's missing. Golden rule:
**observe, don't invent** — every finding comes from a command output or a
file read, and every edit derives from a verifiable source (the function's
signature and behavior, the package's real API, a command you ran).

## Step 0 — resolve the target repo and package

Everything below operates on a TARGET repo: the path the user gives, else the
current working directory. Derive the importable package name (`PKG` in all
commands below) from the repo, never by guessing:

```bash
python -c "
import tomllib
print(tomllib.load(open('pyproject.toml', 'rb'))['project']['name'])
"
```

The package *directory* is usually the project name with hyphens replaced by
underscores — confirm it exists and contains `__init__.py` before running
anything against it. Run all commands from the repo root.

> `import tomllib` one-liners need Python ≥ 3.11; on 3.10 substitute
> `import tomli as tomllib` (pip-installable).

## Diagnose

Run the full diagnosis before proposing anything. Each check is read-only
(except the README runner, which executes README code — see its warning).

### 1. Docstring presence — agent-actionable list (ruff)

```bash
uvx ruff check --select D100,D101,D102,D103,D104,D105,D106,D107 \
    --output-format json PKG > /tmp/docstring_gaps.json
echo "exit: $?"   # 1 = findings present, 0 = fully documented
```

Each finding has `code`, `message` (e.g. "Missing docstring in public
function"), `filename`, and `location.row`/`location.column` — a precise
work list for the Complete phase. This respects the ecosystem's configured
`[tool.ruff]` per-file-ignores, so tests/examples/scrap are already excluded
from the denominator.

**Dedicated module-docstring pass** (house policy: EVERY module needs a
top-level docstring — they're auto-extracted into the published docs):

```bash
uvx ruff check --select D100,D104 --output-format json PKG
```

⚠️ **Pitfall**: never silence D100 with a `noqa` or per-file-ignore — the fix
is always to *write* the module docstring. A missing module docstring is a
hole in the published documentation, not a lint style preference.

### 2. Docstring presence — human summary + threshold (interrogate)

```bash
uvx interrogate -vv PKG
```

Prints a per-file, per-symbol COVERED/MISSED table with line numbers,
explicit module-docstring rows, and a total percentage (gate with
`--fail-under N`). Use this for the human-facing summary; use the ruff JSON
for the actionable work list.

⚠️ **Pitfall**: interrogate (and pydoclint) `ast.parse` every `.py` file under
the path and **crash on non-Python `.py` files** — e.g. wads's own
`wads/data/` holds Jinja2 templates with `<< >>` delimiters that are
syntactically invalid Python. Exclude template/data dirs:
`uvx interrogate -vv --exclude PKG/data PKG`.

### 3. README truth — execute the examples

A README is a promise that its code runs. Verify it with the bundled runner:

```bash
python scripts/readme_runner.py /path/to/repo          # human report
python scripts/readme_runner.py /path/to/repo --json   # machine-readable
```

(The path may also point directly at any markdown file. Exit 0 = no failing
block.)

⚠️ **This EXECUTES the README's code. Only run it on trusted repos.** By
default blocks run in a throwaway temp directory (README code that writes
files can't touch the repo) with the repo root on `sys.path`; pass
`--run-in-repo` only when examples need repo-relative files.

What the runner does:

- Extracts fenced ` ```python `/` ```py ` blocks (info-string extras and the
  ecosystem's ` ```pydocstring ` convention tolerated) in document order.
- Blocks containing `>>>` run as doctests (`ELLIPSIS | NORMALIZE_WHITESPACE`);
  other blocks run via `exec`.
- **Globals are shared across blocks in document order** — READMEs are
  sequential narratives, so an import in block 1 is visible in block 3.
- Reports per-block PASS/FAIL/SKIP with README line numbers.
- Skips a block when the line(s) immediately before its fence carry
  `<!-- wads-docs: skip -->` (append a reason after `skip`), and
  auto-classifies obvious placeholders — ALL_CAPS path segments
  (`Files('PATH_TO_TARGET_FOLDER')`), example.com URLs, angle-bracket or fake
  credentials — as SKIP (placeholder) rather than FAIL.

⚠️ **Pitfall**: NEVER use bare `pytest --doctest-glob='*.md'` on READMEs.
doctest treats everything up to the next blank line as expected output, so a
closing ` ``` ` fence without a preceding blank line gets swallowed into the
expectation and the block false-fails — verified on real ecosystem READMEs.

### 4. API cross-check — does the README describe the real package?

Three passes, highest precision first:

1. **Run the README's import lines.** Already covered by the runner above —
   an `ImportError: cannot import name 'removed_function'` in a block is the
   strongest possible stale-docs signal.
2. **Diff documented names against the live API:**

   ```bash
   python -c "import PKG; print('\n'.join(n for n in dir(PKG) if not n.startswith('_')))" \
       | sort > /tmp/live_api.txt
   rg -o '\bPKG\.[A-Za-z_][A-Za-z0-9_]*' README.md -N | sed 's/^PKG\.//' \
       | sort -u > /tmp/readme_refs.txt
   comm -23 /tmp/readme_refs.txt /tmp/live_api.txt   # dotted refs gone from the API
   # Plus a judgment pass over backticked names (many are legit non-PKG terms):
   rg -o '`([A-Za-z_][A-Za-z0-9_]+)`' -r '$1' README.md -N | sort -u
   ```

   (grep fallback: `grep -oE '\bPKG\.[A-Za-z_][A-Za-z0-9_]*' README.md`.)
   A backticked name absent from `dir(PKG)` is a *candidate*, not a verdict —
   check whether it's a submodule attribute, a CLI name, or another package
   before flagging.
3. **Check install lines:** every `pip install ...` in the README must match
   `[project].name`, and every `pkg[extra]` must name a declared extras key:

   ```bash
   rg -n 'pip install' README.md
   python -c "
   import tomllib
   p = tomllib.load(open('pyproject.toml', 'rb'))['project']
   print('name:', p['name'])
   print('extras:', list(p.get('optional-dependencies', {})))
   "
   ```

### 5. Signature ↔ docstring drift

```bash
uvx pydoclint --style=google --arg-type-hints-in-docstring=False \
    --exclude '\.git|\.tox|PKG/data|PKG/tests' PKG
```

Catches args documented but not in the signature (DOC102/DOC103), return
sections that contradict annotations (DOC202/DOC203), and more. For params
missing *from* the docstring, ruff D417 is the precise check:

```bash
uvx ruff check --select D417 --output-format json PKG
```

⚠️ **Pitfall**: darglint is dead (unmaintained) — don't adopt it. Ruff's
preview `DOC` rules are a partial port that misses the
extraneous-argument case; use pydoclint for full drift detection.
`--arg-type-hints-in-docstring=False` matches house style (types live in
annotations, not docstring arg lists).

## Align — retire or update obsolete docs

Compare diagnosis output against reality and propose changes. **Propose,
never silently delete** — show the user what's stale and why before editing.

| Finding | Source of truth | Action |
|---|---|---|
| README block fails on a removed/renamed import | runner FAIL + `comm` diff | Unambiguous → propose the rename (if the symbol moved) or removal of the passage |
| `setup.py` / `setup.cfg` / `python setup.py install` mentioned in a migrated repo | files absent from the repo | Unambiguous → propose updated install/dev instructions (`pip install PKG`, pyproject-based) |
| `pip install` name or extra doesn't match `[project]` | pyproject.toml | Unambiguous → propose the correct line |
| Badge URL 404s or points at a dead CI service | `curl -sI URL` status | Unambiguous → propose removal or the current equivalent |
| Backticked name not in `dir(PKG)` | judgment pass | Ambiguous → check git history for a rename; ask the user if intent is unclear |
| Docstring describes behavior the code no longer has | reading the function | Ambiguous → ask the user which is wrong, the doc or the code |
| Stale placeholder block that *should* run | runner SKIP (placeholder) | Ambiguous → ask whether to make it runnable or mark it `<!-- wads-docs: skip -->` |

For prose that references old architecture (pre-migration CI, removed
modules), quote the stale passage and the evidence in your proposal so the
user can decide fast.

## Complete — write what's missing

Work through the ruff JSON gap list, highest-visibility first (package
`__init__`, public modules, public classes, public functions, then methods).

**Docstrings** — Google style (napoleon is enabled ecosystem-wide):

- Derive content from the code: read the function, its tests, and its call
  sites before writing a word. Don't document what you can't verify.
- Include a doctest example wherever the function is example-shaped (pure-ish,
  cheap to call, illustrative output). This ecosystem is doctest-first:
  doctests are simultaneously docs and tests, and CI runs
  `--doctest-modules`, so every example you write must pass. Two admission
  criteria: **low setup** (heavy scaffolding belongs in a pytest test, not a
  docstring) and **robust assertions** (unordered/platform-varying reprs —
  sets, dicts, object reprs — get `assert expr == expected` or `sorted(...)`,
  never raw displayed output). Full style rules: **wads-test-coverage**'s
  "Style rules" section.
- Follow the rendering rules in **wads-docstring-render** (blank lines before
  doctests, double-backtick inline code, section formatting) — apply them
  while writing; don't restate them here.
- **Module docstrings** describe the module's purpose and key exports in a
  few lines — they're auto-extracted into the published docs, so write them
  for a reader browsing the docs site, not for maintainers.

**README** — follow progressive disclosure: the essentials in a few lines,
then paragraphs, then details; easy examples first, advanced examples after.
When adding examples, write them as runnable blocks and verify immediately:

```bash
python scripts/readme_runner.py /path/to/repo
```

If a new example genuinely can't run in isolation (needs credentials, a
server, a local folder), make that explicit with
`<!-- wads-docs: skip - reason -->` on the line before the fence rather than
shipping a silently-broken block.

**Verification loop** (after every batch of edits):

```bash
python -m pytest --doctest-modules \
  -o doctest_optionflags='ELLIPSIS IGNORE_EXCEPTION_DETAIL' \
  PKG/path/to/touched_module.py > /tmp/doctest_check.txt 2>&1
echo "exit: $?"   # the optionflags mirror CI — without them, ELLIPSIS-reliant doctests false-fail
uvx ruff check --select D100,D101,D102,D103,D104,D105,D106,D107 PKG
python scripts/readme_runner.py /path/to/repo   # if the README changed
```

Run the touched module's tests before AND after editing — never break
existing tests; if a docstring edit changes doctest output, that's a
behavior-affecting change and needs the user's sign-off.

## Scope guardrails

- **Diagnosis is read-only.** The only execution is the README runner, which
  is contained (temp-dir cwd) and prominently flagged — never run it on an
  untrusted repo.
- **Do not change code behavior.** This skill writes docstrings and README
  text only; if completing docs reveals a bug, report it — don't fix it here.
- **Do not silence findings.** No `noqa: D...`, no per-file-ignores to make
  numbers look better; the fix for a missing docstring is the docstring.
- **Do not touch rendering repair.** RST/Sphinx mistakes (single backticks,
  missing blank lines before `>>>`, broken section headers) belong to
  **wads-docstring-render** — flag them, don't fix them here.
- **Do not touch publishing.** GitHub Pages, 404s, docs CI, epythet setup
  belong to **epythet-docs**.
- **Propose before applying** anything user-facing: README restructures and
  doc deletions are shown as proposals first.

## Related skills

- **wads-docstring-render** — docstrings render wrong on the docs site
  (RST/Sphinx mistakes); this skill writes content, that one fixes form.
- **epythet-docs** — docs publishing, GitHub Pages, 404s, docsrc setup.
- **wads-test-coverage** — code/test coverage gaps (including doctest-only
  attribution); this skill measures docs, not tests.
- **wads-repo-doctor** — full repo health pass; docs coverage is one section.
- **wads-pypi-polish** — pyproject/PyPI metadata (description, classifiers,
  URLs) rather than docs content.
- **wads-migrate** — if the Align phase finds setup.cfg-era leftovers beyond
  the README, the repo may need a real migration.

## Closing checklist

- [ ] `PKG` resolved from pyproject.toml, commands run from the repo root
- [ ] ruff D1xx JSON gap list produced; module-docstring pass (D100/D104) clean
      or every gap has a written docstring (never a `noqa`)
- [ ] interrogate summary reported (with template/data dirs excluded)
- [ ] README runner: every block PASS or intentionally SKIP (marker or
      placeholder) — zero FAIL
- [ ] README names, install lines, and extras verified against the live API
      and pyproject.toml
- [ ] pydoclint + D417 drift findings triaged (fixed or reported)
- [ ] Obsolete-docs changes proposed with evidence, applied only on approval
- [ ] New docstrings are Google style with passing doctests;
      `pytest --doctest-modules` green on every touched module
- [ ] Rendering issues handed to wads-docstring-render; publishing issues to
      epythet-docs; test-coverage gaps to wads-test-coverage
