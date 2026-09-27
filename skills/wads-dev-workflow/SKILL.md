---
name: wads-dev-workflow
description: >-
  How to change the wads package itself (i2mint/wads) safely: install the right
  extras, run the test suite exactly the way CI does (package doctests
  included, on Python 3.10/3.11/3.12), regenerate the populate goldens after an
  intended output change, exercise the git-commit push-back script, and keep
  the reusable workflow, actions, stub template and secrets superset in sync.
  Use when editing wads source, actions/*, .github/workflows/uv-ci.yml,
  wads/data templates or the shipped skills, when a wads test fails, when
  "regenerate the goldens", "run wads tests like CI", or "is this wads change
  safe to merge" comes up. Every merge to master publishes wads to PyPI and
  goes live for every repo whose stub floats on @master. Not for USING wads in
  another repo (see wads-migrate, wads-ci-health, setup-py-project).
metadata:
  audience: developers
---

# Working on wads itself

wads is a foundation package: its reusable workflow (`.github/workflows/uv-ci.yml`) and composite actions (`actions/*`) run from `@master` in every wads-managed repo, and a merge to `master` publishes to PyPI. Treat any change to a workflow, action, or stub template as a fleet-wide change.

## Setup

```bash
uv venv -q .venv && . .venv/bin/activate
uv pip install -e ".[create,docs,skills,test]" pytest pip
```

The default `.[test,dev]` is not enough: the suite builds and scaffolds packages, which needs the `create` extra (`requests`, `build`, `ruamel.yaml`, `tomlkit`).

## Run the tests the way CI does

CI (`actions/run-tests-uv`) runs pytest with **no path**, so `[tool.pytest.ini_options].testpaths = ["wads"]` decides what is collected: `wads/tests` plus every package doctest. The root `conftest.py` keeps the `wads/data` templates out.

```bash
python -m pytest --doctest-modules -o doctest_optionflags='ELLIPSIS IGNORE_EXCEPTION_DETAIL' --ignore=examples --ignore=scrap -q
```

- The `-o doctest_optionflags=...` **replaces** the repo's `NORMALIZE_WHITESPACE`, so a doctest whose expected output wraps across lines needs an inline `# doctest: +NORMALIZE_WHITESPACE`.
- The CI matrix is 3.10 and 3.12, but users run 3.11 too. Before a merge, run the command on all three (`uv venv -p python3.10 …`); 3.11 alone rejects unhashable dataclass defaults, and 3.10's `mock.patch` resolves dotted paths by attribute, which catches `sys.modules` leaks between tests.
- `wads/tests/test_collection_scope.py` pins that package doctests stay collected.

## Goldens: intended output changes

`wads/tests/test_populate_characterization.py` compares a default `populate` byte-for-byte with `wads/tests/data/golden/python_lib/`. When you change default output on purpose, regenerate from the real output and review the diff:

```python
import subprocess, tempfile, shutil
from pathlib import Path
from wads.populate import populate_pkg_dir

with tempfile.TemporaryDirectory() as d:
    pkg = Path(d) / "mypkg"; pkg.mkdir()
    for cmd in (["git", "init", "-q"], ["git", "config", "user.email", "t@e.com"],
                ["git", "config", "user.name", "t"],
                ["git", "remote", "add", "origin", "https://github.com/myorg/mypkg"]):
        subprocess.run(cmd, cwd=pkg, check=True)
    populate_pkg_dir(str(pkg), description="Test package", root_url="https://github.com/myorg",
                     author="John Doe", version="1.2.3", verbose=False)
    for rel in ("pyproject.toml", ".github/workflows/ci.yml"):
        shutil.copy(pkg / rel, Path("wads/tests/data/golden/python_lib") / rel)
```

`git diff wads/tests/data/golden/` must show only the change you meant. The `frontend_js` golden is byte-identical by contract; don't regenerate it casually.

## The push-back script (`actions/git-commit`)

`wads/tests/test_git_commit_push_retry.py` runs the action's real "Push Changes" bash step (read out of `action.yml`) against throwaway bare repos, including concurrent version-bump races (issues #81, #83, #89, #98). Add a case there for any change to that step. Keep the script portable: no `sed -i` (GNU and BSD differ), POSIX `awk` only (`ubuntu-latest` has mawk).

## Things that move together

- **Reusable workflow vs inline template**: `.github/workflows/uv-ci.yml` and `wads/data/github_ci_uv.yml` mirror each other; change both.
- **Secrets interface**: `on.workflow_call.secrets` in `uv-ci.yml` is pinned to `wads.ci_secrets.WORKFLOW_CALL_SECRETS` by `test_ci_secrets.py`; the named superset is frozen.
- **Stub template** `wads/data/github_ci_uv_stub.yml` keeps the JSON-transport region because `stub_with_named_transport` rewrites it; new stubs are rendered with the named transport (issue #74).
- **A new `read-ci-config` output** is empty until a wads release carrying it reaches PyPI (the action `pip install`s wads), while `uv-ci.yml@master` changes go live at merge. Guard new `if:` clauses against an empty output.

## Before merging

1. The CI-exact command passes on 3.10, 3.11 and 3.12.
2. `uvx ruff check .` and `uvx ruff format --check .` pass (CI formats on publish, but keep diffs clean).
3. If packaging changed, build from tracked files only and run `twine check` (a stray local venv leaks into a local sdist).
4. Run the dependent `i2mint/isee` tests with this checkout installed editable over it.
5. Never write CI markers (the publish or skip markers) in commit messages or PR text; they are directives.
