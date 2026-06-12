---
name: wads-type-coverage
description: >-
  Type-annotation coverage for a wads-managed Python repo: diagnose, complete,
  decide py.typed. Measures public-API type completeness with pyright
  --verifytypes (per-symbol score), produces an agent-actionable
  missing-annotation work list (ruff ANN rules, JSON), checks whether py.typed
  exists and actually ships in the wheel, then writes the missing annotations
  duck-typing-first (collections.abc, Protocol) and advises when adding
  py.typed is justified. Use for "type coverage", "how typed is this package",
  "add type annotations", "annotate the public API", "should I add py.typed",
  "is this package typed", "type completeness score", "make this PEP 561
  compliant", "mypy strict cleanup". Also trigger when downstream users report
  missing-stub or Unknown-type complaints about the package. Does NOT set the
  Typing :: Typed classifier or other PyPI metadata (wads-pypi-polish),
  measure test or docstring coverage (wads-test-coverage /
  wads-docs-coverage), or fix import-time slowness found along the way
  (wads-import-time).
metadata:
  audience: users
---

# Wads Type Coverage

Measure how type-complete a package's **public API** is, write the missing
annotations without breaking the ecosystem's duck-typing contracts, and make
the py.typed call on evidence rather than vibes. Golden rule: **observe,
don't invent** — every score comes from a tool run, and every annotation you
write derives from the function's body, call sites, tests, and docstring.

Annotations here are *claims about existing behavior*, never changes to it.
A wrong-but-confident annotation is worse than none: with `py.typed` present,
downstream type-checkers trust it over their own inference.

## Step 0 — resolve the target repo and package

Operate on the repo path the user gives, else the current working directory.
Derive the package directory from pyproject.toml — never guess:

```bash
cd /path/to/repo   # the target repo root; commands below run from here
python3 -c "
import tomllib, pathlib
name = tomllib.load(open('pyproject.toml','rb'))['project']['name']
pkg = name.replace('-', '_')
print(f'project: {name}  package dir: {pkg}  exists: {pathlib.Path(pkg, \"__init__.py\").is_file()}')
"
```

`PKG` below means that package *directory* (check `src/PKG` if it's not at
the root). No pyproject.toml → not a wads-managed repo; point the user at
**wads-migrate**. (`import tomllib` needs Python ≥ 3.11; on 3.10 substitute
`import tomli as tomllib`.)

**Public-API-first framing** used throughout: a symbol is public when no
component of its dotted path is single-underscore-prefixed (dunders like
`__getitem__` follow their class's visibility). Pyright's "exported symbols"
applies the same convention plus `__all__`. Private helpers are the *last*
thing to annotate, not the first.

## Diagnose

### One-shot audit — the bundled script

```bash
python scripts/type_coverage.py /path/to/repo          # human report
python scripts/type_coverage.py /path/to/repo --json   # full machine-readable findings
```

(`scripts/` is relative to this skill; the repo path defaults to cwd. Flags:
`--skip-pyright` for quick/offline mode, `--skip-pypi` to skip the
released-wheel check.) It runs all four checks below and prints a verdict —
~5 s total on a 40-module package, longer on the very first run while uvx
downloads ruff/pyright. Real output shape (the `dol` package):

```
Type coverage — dol (…)
  py.typed: local=ABSENT, latest wheel ships it: False
  public-API completeness (pyright): 17.2%  (known 271 / ambiguous 99 / unknown 1204)
  worst modules (unknown/exported):
    dol.signatures: 161/207
    ...
  ruff missing-annotation findings: 2150 (public 1665, private 485) {'ANN001': 1193, ...}
  verdict: public API only 17% type-complete — do NOT add py.typed yet; ...
```

The script is read-only on the repo: the pyright step copies the repo to a
temp dir, adds `py.typed` *there*, and installs that copy into an ephemeral
uvx environment (see why below).

### 1. Authoritative score — `pyright --verifytypes`

The completeness score = fraction of exported (public) symbols whose type is
fully known. "Ambiguous" (inferred, but checkers could infer differently)
counts against it, so the score is stricter — and more honest — than "has an
annotation somewhere". Per-symbol diagnostics give file + line for every gap.

```bash
# Only works as-is when the package ships py.typed AND is resolvable:
uvx --with /path/to/repo pyright --verifytypes PKG --outputjson > /tmp/verifytypes.json
echo "exit: $?"   # 0 ONLY at 100% completeness — read the score, don't gate on exit code
python3 -c "import json; print(json.load(open('/tmp/verifytypes.json'))['typeCompleteness']['completenessScore'])"
```

⚠️ **Pitfall: verifytypes only resolves *installed* packages.** Running it
from the repo root without `--with` reports `Package directory: ""` and a
zero score — pyright does not pick the package up from cwd. `uvx --with
/path/to/repo` builds and installs the repo into the ephemeral env (the repo
itself is untouched; dependencies get installed too, which keeps imported
types resolvable).

⚠️ **Pitfall: no `py.typed`, no score.** On an unmarked package verifytypes
exits 1 with `No py.typed file found`, `filesAnalyzed: 0`, score 0 — for a
package you're *diagnosing for* the marker, that's every time. The bundled
script works around it read-only (temp copy + `touch py.typed` there). Don't
touch the marker in the real repo just to measure.

Notes from verified runs:

- **Speed is a non-issue**: ~1.4 s analysis for 40 modules (~2.5 s wall,
  cached). First ever run downloads pyright via uvx; if `node` isn't
  installed, the pyright wrapper auto-installs a prebuilt node (one-time,
  silent after that) — no preinstalled node required.
- `--ignoreexternal` recomputes the score ignoring unknown types that leak in
  from *imports* (measured: 17.2% → 19.4% on dol). Use it when unresolved
  third-party deps would unfairly deflate the score.
- ⚠️ **Test modules shipped inside the package count.** `PKG/tests/...` are
  public submodules to a consumer, so they appear in the score and the
  per-module table. Read the table per-module and prioritize real API
  modules; don't burn effort annotating shipped tests to move the number.

### 2. Agent-actionable work list — ruff ANN rules

```bash
uvx ruff check --select ANN001,ANN201,ANN202,ANN204,ANN205,ANN206 \
    --output-format json PKG > /tmp/ann_gaps.json
echo "exit: $?"   # 1 = findings present, 0 = fully annotated, 2 = tool error
```

Each finding has `code`, `message` (naming the function), `filename`, and
`location.row`/`column` — a precise edit list. Codes: ANN001 = unannotated
argument, ANN201/202 = missing return type on a public/private function,
ANN204/205/206 = missing return on special/static/class methods. ANN202 is
private-function territory — deprioritize it. This respects the repo's
`[tool.ruff]` config, so excluded dirs (tests/, scrap/, examples/) are
already out of the denominator. The bundled script additionally buckets every
finding public/private by its full dotted path (AST-based), which ruff's
own public/private split (function name only) can't do for nested or
underscore-module cases.

### 3. py.typed quick check — present, and *shipped*?

```bash
ls PKG/py.typed   # present in the source?
```

Present-in-source isn't the whole story — the marker must reach the wheel.
The bundled script downloads the latest PyPI wheel and lists it (reported as
`latest wheel ships it:`). After you *add* a marker (Decide phase), verify
the local build the same way:

```bash
uv build --wheel -o /tmp/whl_check && python3 -c "
import zipfile, glob
w = sorted(glob.glob('/tmp/whl_check/*.whl'))[-1]
print([n for n in zipfile.ZipFile(w).namelist() if n.endswith('py.typed')])
"
```

Hatchling (the wads default backend) ships any `py.typed` inside the package
dir automatically — verified. Non-hatchling backends may silently drop it
(setuptools needs package-data config); if the repo isn't on hatchling,
that's **wads-migrate** territory.

### 4. Deeper opt-in — `mypy --strict`

Presence (ruff) and completeness (pyright) say nothing about *correctness*.
When the user wants the deeper pass:

```bash
uvx mypy --strict --ignore-missing-imports --exclude '(tests|scrap|examples)/' PKG \
    > /tmp/mypy_strict.log 2>&1
echo "exit: $?"; tail -1 /tmp/mypy_strict.log
```

Expect a wall of errors on a mostly-untyped package (measured: 2109 errors
across 20 files on dol — that's normal, not alarming). Don't propose it as a
CI gate at that stage; use it module-by-module while completing
(`uvx mypy --strict path/to/module.py`) to catch annotations that are
*wrong*, not just missing.

## Complete — annotate the public API first

Priority order, from the diagnosis:

1. **Public API modules with the worst unknown/exported ratio** (the script's
   per-module table) — skip shipped test modules.
2. Within a module: exported functions and classes, then methods (including
   dunders), guided by the ruff public-findings list (`--json` output:
   `ruff.public_findings`, ordered by file).
3. Private helpers (ANN202 et al.) — optional, lowest value.

### Derive every annotation from evidence

Read the function body, its call sites (`rg 'func_name\('`), its tests, and
its docstring before writing a type. If you cannot determine the type from
evidence, leave it un-annotated rather than guessing — an absent annotation
is honest; a wrong one is a trap with `py.typed` on.

### Duck-typing guardrail (critical in this ecosystem)

This codebase culture is protocols-over-concrete-types — dol-style packages
*exist* to treat storage as `Mapping`s. Annotations must encode the duck
type, not the implementation:

| The body only… | Annotate the parameter | Not |
|---|---|---|
| reads `x[key]` / iterates keys | `Mapping[K, V]` | `dict` |
| also writes `x[key] = v` | `MutableMapping[K, V]` | `dict` |
| iterates once | `Iterable[T]` | `list` / `Sequence` |
| calls it | `Callable[[A], R]` | a specific function type |
| needs `.read()` (or similar) | a small `typing.Protocol` | a concrete class |

Prefer `collections.abc` imports for these. Parameters get the **widest type
the body truthfully supports**; return types get the **most precise type
that's true**. **Never narrow a signature in a way that rejects
currently-valid inputs** — if a test or call site passes a generator, the
parameter is `Iterable`, full stop.

### Runtime-safety guardrail (annotations must not change behavior)

Annotations are evaluated at function-definition time (i.e., import time) on
Python ≤ 3.13 (3.14's PEP 649 defers evaluation to annotation access; the
default wads matrix tops out at 3.12, so the import-time failure mode below
is the one your CI sees) — so they can absolutely break runtime:

- **A typo'd or unimported name in an annotation = `NameError` at import.**
  The verify step's import smoke test catches this.
- **No heavy or circular imports at module top just for typing.** Put them in
  a `TYPE_CHECKING` block and quote the annotation:

  ```python
  from typing import TYPE_CHECKING

  if TYPE_CHECKING:
      import pandas as pd

  def to_frame(rows: 'Iterable[dict]') -> 'pd.DataFrame': ...
  ```

  If you're tempted to add a real import for typing, check the cost first —
  import-time budgeting is **wads-import-time**'s job.
- ⚠️ **Pitfall: `from __future__ import annotations` is NOT a free lunch
  here.** It turns every annotation in the module into a string — which
  changes what runtime introspection sees in `__annotations__` /
  `inspect.signature`. This ecosystem introspects signatures at runtime
  (dol.signatures, i2.Sig and friends). Before adding the future import to a
  module, check for consumers:

  ```bash
  rg -ln '__annotations__|get_type_hints|\bsignature\(' PKG
  ```

  Modules that show up there (or are *consumed by* such machinery) get
  surgical `TYPE_CHECKING` + quoted annotations instead of the blanket
  future import.
- ⚠️ **Pitfall: annotating attributes of a `@dataclass` (or attrs/pydantic
  model) creates fields.** `x = 5` is a plain class attribute; `x: int = 5`
  becomes an `__init__` field with new constructor behavior. Adding an
  annotation there is a behavior change, not documentation — leave such
  attributes alone or get explicit sign-off.
- **Never touch default values** while annotating — `def f(x=()):` keeps its
  default exactly; you're adding `x: Sequence[str] = ()`, not "improving"
  defaults.

### Don't game the score

No bulk `Any` to make symbols "known", no `# type: ignore` carpets, no
`noqa: ANN`. An explicit `Any` is acceptable only where the type truly is
dynamic — and say so in the docstring.

## Decide — py.typed

`py.typed` (PEP 561) tells downstream type-checkers to **trust this
package's inline annotations instead of their own inference**. That's a
public contract: premature `py.typed` is worse than none, because consumers'
checkers start treating your unknown/wrong types as ground truth and stop
inferring around them.

Threshold heuristic, on the verifytypes score for exported symbols:

| Completeness score | Verdict |
|---|---|
| ≥ 90% | Adding `py.typed` is justified — propose it |
| 60–90% | Close the gap to ≥ 90% first (Complete phase), then add |
| < 60% | Don't add it; annotate first |
| Marker already present, score < 90% | Flag it: consumers are trusting incomplete annotations — completing them is now the priority (removing a shipped marker is a breaking change for typed consumers; discuss before suggesting it) |

To add (propose first — it changes the published artifact):

```bash
touch PKG/py.typed
```

then verify it lands in the wheel (the `uv build --wheel -o /tmp/whl_check`
command above). With hatchling no further config is needed — verified.

The matching `Typing :: Typed` trove classifier in `[project].classifiers`
is **wads-pypi-polish** territory — note the finding and delegate; don't
edit pyproject metadata here.

## Verify

Annotations can break runtime (see the runtime-safety guardrail), so the
verification bar is the same as for code changes:

```bash
python -c "import PKG"   # import smoke test — catches NameError in annotations
python -m pytest --doctest-modules \
  -o doctest_optionflags='ELLIPSIS IGNORE_EXCEPTION_DETAIL' \
  PKG > /tmp/type_cov_tests.log 2>&1
rc=$?; tail -5 /tmp/type_cov_tests.log; echo "pytest exit: $rc"
```

- Run this **before** touching anything (baseline must be green) and
  **after** every batch of edits. Never read the exit code through a pipe.
  The doctest flags mirror CI — signature-introspecting doctests are exactly
  the ones a stringified annotation breaks.
- Re-run the bundled script and report the deltas: completeness score
  before → after, and the public ruff-finding count before → after. If the
  score didn't move, the edits hit private/test code — revisit priorities.
- Run the repo's formatter on touched files only (`uvx ruff format
  path/to/touched.py`) — long signatures reflow, and CI formats anyway.
- If `py.typed` was added, the next release changes what consumers' type
  checkers do — make sure the user knows that ships with the next publish.

## Scope guardrails

- **Diagnosis is read-only.** The script writes only to temp dirs; the repo
  is never modified to take a measurement (no touching `py.typed` to make
  pyright run — that's what the temp copy is for).
- **Annotations only.** No behavior changes, no refactors, no default-value
  "fixes", no new runtime dependencies (`typing-extensions` included —
  propose it if genuinely needed), no signature changes beyond adding types.
- **Never narrow**: a type that rejects currently-valid inputs is a bug you
  introduced, even if every checker is happy.
- **Don't inflate**: no `Any`-spam, no ignore-carpets, no excluding modules
  to move the score.
- **py.typed and the Typing classifier are public-contract changes** —
  proposed with evidence, applied only on approval; the classifier itself
  belongs to wads-pypi-polish.
- Stay in your lane: import-time costs found while placing typing imports go
  to wads-import-time; docstring↔signature drift (documented args vs real
  ones) belongs to wads-docs-coverage.

## Related skills

- **wads-repo-doctor** — the orchestrator; runs this skill as the
  type-coverage step of a full repo health pass.
- **wads-pypi-polish** — owns `[project]` metadata, including the
  `Typing :: Typed` classifier that should accompany `py.typed`.
- **wads-test-coverage** — separate concern: whether code is *exercised*.
  A fully-typed function can be untested and vice versa.
- **wads-docs-coverage** — docstring presence and signature↔docstring drift
  (pydoclint/D417); types live in annotations, not docstring arg lists.
- **wads-import-time** — if typing imports tempt you to add module-top
  imports, or measurement reveals slow imports, delegate there.
- **wads-migrate** — non-hatchling backends that would drop `py.typed` from
  the wheel; legacy repos without pyproject.toml.

## Closing checklist

- [ ] Target repo resolved; `PKG` dir verified from pyproject.toml
- [ ] Script run; score, work list, and py.typed status (local + shipped) reported
- [ ] Score read from JSON, not from verifytypes' exit code
- [ ] Shipped-test modules not treated as priority annotation targets
- [ ] Baseline tests green before edits; import smoke + full suite green after
- [ ] Every annotation evidence-derived; abc/Protocol over concrete types; nothing narrowed
- [ ] No future-import added to runtime-introspected modules; no dataclass attrs annotated casually
- [ ] Score and public-finding deltas reported after edits
- [ ] py.typed only proposed at ≥ 90% completeness; wheel verified to ship it; classifier delegated to wads-pypi-polish
- [ ] Scratch artifacts in /tmp only; nothing committed, nothing modified without approval
