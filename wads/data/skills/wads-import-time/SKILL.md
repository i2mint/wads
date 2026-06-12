---
name: wads-import-time
description: >-
  Audit and improve import time and import hygiene in a wads-managed Python
  repo. Measures `python -X importtime` (warm-cache, against the local
  checkout), ranks heavy modules and third-party offenders, verifies every
  module imports standalone (CI runs pytest --doctest-modules, which imports
  every module), cross-checks unguarded module-level imports of
  undeclared/extra-only packages, then makes imports lazy and clean
  (function-local imports, TYPE_CHECKING, PEP 562 module __getattr__, guarded
  optional deps). Use for "why is import so slow", "speed up import", "make
  imports lazy", "audit imports", "import hygiene check", "this module breaks
  --doctest-modules", "optional dependency breaks import", "lighten the core
  install". Also trigger when CI fails at collection with
  ImportError/ModuleNotFoundError before any test runs. Does NOT do full
  declared-vs-imported dependency drift (use the wads-deps CLI), measure test
  coverage (wads-test-coverage), or diagnose CI wiring (wads-ci-health).
metadata:
  audience: users
---

# Wads Import Time

Measure how long `import PKG` really takes, find the modules and dependencies
responsible, verify every module imports cleanly in isolation, and then make
imports lazy and guarded — without breaking load-bearing side effects. The
golden rule is **observe, don't invent**: every offender comes from an actual
`-X importtime` measurement, and every refactor is verified by a before/after
delta plus a green test suite.

Why this ecosystem cares, twice over:

- **Light imports are a design value.** wads itself splits a light core from
  the `wads[create]` extra and *pins the boundary with a test*
  (`wads/tests/test_light_install.py`: a meta-path finder blocks the
  create-only modules and asserts the light surface still imports). A package
  whose root import drags in its heaviest optional machinery taxes every
  consumer.
- **CI imports every module.** The uv CI unconditionally runs
  `pytest --doctest-modules`, which **imports every module in the package** —
  test files included. One module that reads an env var, hits the network, or
  needs an undeclared package at import time fails collection for the whole
  suite; one slow module taxes every test run.

## Step 0 — Resolve the target repo and package

Operate on the repo path the user gives, else the current working directory.
Derive the package dir and the declared dependency sets (needed for the
guard cross-check later):

```bash
cd /path/to/repo   # the target repo root; all commands below run from here
python - <<'EOF'
import pathlib
try:
    import tomllib
except ImportError:        # Python 3.10
    import tomli as tomllib
t = tomllib.load(open('pyproject.toml', 'rb'))
proj = t['project']
pkg = proj['name'].replace('-', '_')
print(f"package dir : {pkg}  (exists: {pathlib.Path(pkg).is_dir()})")
print(f"core deps   : {proj.get('dependencies', [])}")
print(f"extras      : {list(proj.get('optional-dependencies', {}))}")
EOF
```

`PKG` below means the package directory printed above (verify it exists; a
hyphenated project name maps to an underscored dir).

## Measure

### 1. Raw measurement

```bash
PYTHONPATH=. python -X importtime -c "import PKG" 2> /tmp/importtime_warmup.log
PYTHONPATH=. python -X importtime -c "import PKG" 2> /tmp/importtime.log
echo "import ok: $?"    # nonzero = import-unclean; jump to the cleanliness section
```

Two runs on purpose: `-X importtime` measures a **cold interpreter but warm
filesystem** — the first run may be paying one-time `.pyc` compilation, so its
numbers are inflated and unstable. Always measure the **second** run.

⚠️ **Pitfall: which package are you measuring?** `PYTHONPATH=.` puts the local
checkout first on `sys.path`, so you measure the working tree — usually what
you want when auditing a repo. Don't rely on the implicit cwd entry of
`python -c` for this: `PYTHONSAFEPATH=1` (or `-P`) removes it and you'd
silently profile the *installed* copy instead. For a src layout, use
`PYTHONPATH=src`. To deliberately measure the installed package, drop
`PYTHONPATH` and run from outside the repo.

### 2. Reading the output

Each stderr line is `import time: self [us] | cumulative | imported package`:

- **self** — microseconds spent executing that module's own body;
- **cumulative** — self plus everything it (transitively) imported;
- **indentation** = import depth, and children appear *above* their importer —
  the last line is your package's root, and its cumulative is the headline
  total.

Quick top-offender recipes (verified):

```bash
# top by SELF time — which module bodies are expensive
sed 's/^import time: //' /tmp/importtime.log | sort -t'|' -k1,1 -rn | head -15

# top by CUMULATIVE time — which imports drag in expensive subtrees
sort -t'|' -k2,2 -rn /tmp/importtime.log | head -15
```

⚠️ **Pitfall: environment noise in the log.** Lines like `site`,
`sitecustomize`, `_distutils_hack`, and `__editable___*_finder` are
interpreter/venv startup (`.pth` processing, editable-install finders), not
your package's cost. On dev machines with many editable installs this noise
can *dominate* the log. Never attribute it to the package.

### 3. The bundled profiler (attribution + JSON)

The one-liners can't tell package-internal from third-party from noise; the
bundled script does. It runs the two-pass measurement itself (with
`PYTHONPATH` set correctly, src layout detected) and reports top-N by self and
cumulative plus a per-top-level-package rollup — the lazy-import shortlist:

```bash
python scripts/import_profile.py /path/to/repo            # human report
python scripts/import_profile.py /path/to/repo --json     # machine-readable
python scripts/import_profile.py . --log /tmp/importtime.log   # parse an existing log
```

(`scripts/` is relative to this skill; the repo path defaults to cwd. Add
`--pkg NAME` if the import name differs from `[project].name`, `--top N` for
more rows.) Every module is categorized as `package` / `third-party` /
`stdlib` / `env-noise`; the `by top-level package` table sums self time per
dependency — a third-party entry costing tens of ms that only one feature
needs is your prime lazy-import candidate. If the import fails, the script
exits nonzero and prints the traceback: fix cleanliness first.

## Import cleanliness

### Every module must import standalone

`--doctest-modules` imports each module individually, and so does any consumer
doing `from PKG.mod import thing`. Loop over all modules (verified; mirrors
CI's default `exclude_paths` of `examples`/`scrap`):

```bash
fails=0; total=0
for f in $(find PKG -name '*.py' ! -path '*/.*' ! -path '*/scrap/*' ! -path '*/examples/*'); do
  m=$(echo "$f" | sed 's/\.py$//; s#/__init__$##; s#/#.#g')
  total=$((total+1))
  if ! PYTHONPATH=. python -c "import $m" > /tmp/import_check.log 2>&1; then
    fails=$((fails+1)); echo "FAIL: $m"; tail -3 /tmp/import_check.log
  fi
done
echo "checked: $total  failures: $fails"
```

Typical failure causes, all of which break CI collection and consumers alike:

- reading env vars at import time (`os.environ["X"]`) — move the read inside
  the function, or give a default; CI-needed vars belong in
  `[tool.wads.ci.env].test_envvars`;
- network/filesystem calls at import time — make them lazy;
- importing an optional dependency unguarded (next check);
- relative-import or `__main__`-style code that assumes a specific entry path.

### Cross-check: unguarded imports of undeclared packages

The loop above only catches optional deps that are *absent in your env* — in
a dev environment they're usually installed, so it passes while a consumer's
light install breaks. Cross-check statically: any module-level import of a
package not in `[project].dependencies` must be guarded (verified; set `PKG`):

```bash
python - <<'EOF'
import ast, pathlib, re, sys
import importlib.metadata as md
try:
    import tomllib
except ImportError:
    import tomli as tomllib

PKG = "PKG"            # the package dir from Step 0
ALLOWED = {"pytest"}   # fine in test modules: CI always installs pytest
t = tomllib.load(open("pyproject.toml", "rb"))
proj = t.get("project", {})

def norm(name):
    return re.sub(r"[-_.]+", "_", name.split("[")[0].strip()).lower()

def dist_of(req):
    return norm(re.split(r"[<>=!~; ]", req.strip())[0])

declared = {dist_of(r) for r in proj.get("dependencies", [])}
extras = {dist_of(r) for rs in proj.get("optional-dependencies", {}).values() for r in rs}
import_to_dists = md.packages_distributions()  # import name -> dists (installed only)
stdlib = set(sys.stdlib_module_names)

def dists_for(top):
    return {norm(d) for d in import_to_dists.get(top, [])} or {norm(top)}

def unguarded(body, out, guarded=False):
    for node in body:
        if isinstance(node, ast.Import) and not guarded:
            out += [(node.lineno, a.name.split(".")[0]) for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module and not guarded:
            out.append((node.lineno, node.module.split(".")[0]))
        elif isinstance(node, ast.Try):
            unguarded(node.body, out, True)       # try-block imports = guarded
            unguarded(node.orelse, out, guarded)
            for h in node.handlers:
                unguarded(h.body, out, guarded)
        elif isinstance(node, ast.If):
            tc = "TYPE_CHECKING" in ast.dump(node.test)
            unguarded(node.body, out, guarded or tc)  # TYPE_CHECKING = guarded
            unguarded(node.orelse, out, guarded)

problems = []
for p in sorted(pathlib.Path(PKG).rglob("*.py")):
    if any(d in {"scrap", "examples"} or d.startswith(".") for d in p.parts):
        continue
    out = []
    unguarded(ast.parse(p.read_text(), filename=str(p)).body, out)
    for lineno, top in out:
        if top in stdlib or top == PKG or top in ALLOWED:
            continue
        d = dists_for(top)
        if d & declared:
            continue
        status = "extra-only" if d & extras else "undeclared"
        problems.append(f"{status:11s} {top:20s} {p}:{lineno}")

print("\n".join(problems) or "all module-level imports are declared core deps or guarded")
print(f"-> {len(problems)} unguarded import(s) of non-core packages")
EOF
```

- **`extra-only`** — the import works only when that extra is installed: guard
  it (fix patterns below) or promote the dep to core (ask the user).
- **`undeclared`** — also a dependency-declaration problem; for the full
  declared-vs-imported picture, run the `wads-deps PATH` CLI (no subcommand).

⚠️ **Pitfall: import name ≠ distribution name** (`yaml` ↔ `pyyaml`,
`PIL` ↔ `pillow`). The check resolves installed packages via
`importlib.metadata.packages_distributions()`; for a *not-installed* import it
falls back to name normalization and may mislabel — confirm before reporting.

## Fix patterns (in order of preference)

**1. Move heavy imports into the functions that use them.** The default fix:
costs nothing at import, needs no new machinery, and Python caches the module
after first call (per-call overhead after that is one dict lookup).

```python
def to_dataframe(rows):
    import pandas as pd   # heavy / optional: imported on first call only
    return pd.DataFrame(rows)
```

**2. `TYPE_CHECKING` block for annotation-only imports.** If a module imports
something *only* for type annotations:

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:                            # never executed at runtime
    import pandas as pd

def to_dataframe(rows) -> "pd.DataFrame": ...   # quoted annotation — no runtime import
```

⚠️ **Pitfall**: don't reach for a blanket `from __future__ import annotations`
here — it stringifies the whole module's `__annotations__`, which breaks
runtime signature introspection (`i2.Sig`, `dol.signatures` consumers are
common in this ecosystem). Quoted annotations on the affected lines are the
surgical form; see the runtime-safety guardrail in **wads-type-coverage**
before changing annotation behavior module-wide.

**3. PEP 562 module `__getattr__` for lazy public attributes.** When the
*public API* re-exports something heavy (typically in `__init__.py`) and you
can't change call sites (verified pattern):

```python
def __getattr__(name):
    if name == "heavy_tool":
        from PKG._heavy import heavy_tool   # imported on first access only
        return heavy_tool
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

def __dir__():
    return sorted(globals()) + ["heavy_tool"]   # keep introspection honest
```

**4. Optional-dependency guard with an informative ImportError.** The
ecosystem convention is to *guide the user to the extra*, not to fail with a
bare `ModuleNotFoundError`:

```python
def parse_xml(src):
    try:
        import lxml.etree
    except ImportError as e:
        raise ImportError(
            "parse_xml requires lxml — install it with"
            " `pip install 'PKG[xml]'` (or `pip install lxml`)"
        ) from e
    ...
```

(The module-level variant — `try: import lxml / except ImportError: lxml =
None` plus a check at call time — is fine too; it's what the
`test_light_install.py` blocker expects guarded imports to look like.)

⚠️ **Pitfall: load-bearing import side effects.** Never lazify an import whose
*execution* the package depends on — registration patterns are the classic
case: importing the module populates a registry, codec table, plugin list, or
entry in a dispatch dict. Before moving an import, read the imported module's
top level (`rg -n 'register|registry|setdefault|append' PKG/heavy_mod.py` is a
quick screen, then read it) and check whether anything else relies on that
state existing after `import PKG`. If it does, either keep the import eager or
relocate the registration explicitly — and say so in the report.

## Verify

Lazy-import refactors are **behavior changes**, not pure optimizations:

1. **Importtime delta.** Re-run the profiler and report before/after totals
   and the offender tables:

   ```bash
   python scripts/import_profile.py /path/to/repo --json > /tmp/import_after.json
   ```

2. **Full suite green before AND after** — exactly as CI runs it:

   ```bash
   python -m pytest --doctest-modules \
     -o doctest_optionflags='ELLIPSIS IGNORE_EXCEPTION_DETAIL' \
     PKG > /tmp/pytest_run.log 2>&1
   rc=$?              # capture before anything else touches it
   tail -5 /tmp/pytest_run.log; echo "pytest exit: $rc"
   ```

   Never read the exit code through a pipe (`pytest | tail` reports tail's
   status). If the repo has a separate top-level `tests/` dir, append it.

3. **Re-run the standalone-import loop and the guard cross-check** — a lazy
   refactor can itself introduce a circular-import or guard regression.

4. **Note the failure-mode shift.** A guarded/lazy import means a missing
   dependency now errors at *call* time, not import time. That's the point —
   but mention it in the user-facing docs/changelog when the affected
   attribute is public, and make the deferred error informative (pattern 4).

If the repo deliberately maintains a light/extra split, propose pinning the
boundary with a `test_light_install.py`-style test (block the extra-only
modules with a meta-path finder; assert the light surface imports) so the next
eager import regression fails CI instead of reaching consumers.

## Scope guardrails

- **Diagnosis is read-only** on the target repo (importing writes ordinary
  `__pycache__` files, as any test run would; logs go to `/tmp`). Refactors
  are proposed with the measurement that justifies them before being applied.
- **Don't chase microseconds.** Stdlib imports of a few ms and anything
  smaller than the env-noise floor aren't worth a refactor. Lead with the
  biggest third-party offenders the report surfaces.
- **Never lazify past a load-bearing side effect** (see the pitfall) and never
  break existing tests — suite green before and after, no exceptions.
- **Dependency declarations are not yours to change silently.** Promoting an
  extra to core (or demoting core to extra) changes every consumer's install:
  propose, don't apply.
- Single repo only; CI-affecting changes (e.g. `[tool.wads.ci.env]` additions
  for import-time env vars) are verified on a non-default branch first.

## Related skills

- **wads-repo-doctor** — the orchestrator; runs this skill as the import-time
  step of a full repo health pass.
- **wads-test-coverage** — the `--doctest-modules` interplay from the other
  side: it measures coverage exactly as CI runs it, and an import-unclean
  module breaks that measurement; this skill is where the fix happens.
- **`wads-deps PATH` CLI** — full declared-vs-imported dependency drift
  (missing/unused declarations). The guard cross-check here flags only the
  import-time-breakage subset.
- **wads-ci-health** — whether CI is green at all; collection-time
  ImportErrors found there get fixed here.

## Closing checklist

- [ ] Target repo resolved; `PKG` dir verified; core deps + extras listed
- [ ] Measured the **second** importtime run, `PYTHONPATH` set explicitly
- [ ] Env-noise lines (`site`, `__editable__*`) excluded from attribution
- [ ] Profiler report produced (self, cumulative, per-dependency rollup)
- [ ] Standalone-import loop run; failures triaged (env var / network / dep)
- [ ] Guard cross-check run; `extra-only`/`undeclared` imports resolved or
      escalated to the user (promotion to core is their call)
- [ ] Each lazified import checked for load-bearing side effects first
- [ ] Before/after importtime delta reported; full suite green both times
- [ ] Deferred-error behavior change noted in docs/changelog where public
