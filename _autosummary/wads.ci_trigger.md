# wads.ci_trigger

On-demand CI: render a repo’s caller stub from `[tool.wads.ci.trigger]`, and flip
a repo to on-demand in one idempotent command.

`[tool.wads.ci.trigger].mode` decides whether CI runs at all:

- `"auto"` (the default): every push and pull request, as wads always has. The stub
  renders byte-identical to `wads/data/github_ci_uv_stub.yml`.
- `"on-demand"`: **nothing runs unless asked** – the commit subject carries
  `run_ci_marker` (default `"[run ci]"`), or someone starts a `workflow_dispatch`.

Two gates, because workflow expressions cannot split a string:

1. The stub’s job-level `if:` is a zero-cost pre-filter. An ordinary push schedules
   no runner at all, but the pre-filter can only ask whether the marker is *anywhere*
   in the commit message.
2. The reusable workflow’s setup job extracts the subject line, and every other job
   gates on the marker being in *that* (the TRIGGER GATE note in
   `.github/workflows/uv-ci.yml`). A marker quoted only in a squash-merged PR body
   passes gate 1, costs one setup job, and runs nothing else.

The flip ([`flip_to_on_demand()`](#wads.ci_trigger.flip_to_on_demand), CLI `wads-migrate ci-on-demand`) sets the mode
plus a cheap test matrix and re-renders the stub. Everything is computed in a shadow
copy of the repo first, so a dry run and a real run take the same path.

### Functions

| [`classify_ci_workflow`](#wads.ci_trigger.classify_ci_workflow)(text)                      | Classify a `ci.yml`: `'missing'`, `'stub'`, `'inline-uv'` or `'other'`.         |
|--------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------|
| [`commit_paths`](#wads.ci_trigger.commit_paths)(repo, paths, \*, message)          | Commit exactly `paths` and return the new commit's short sha.                   |
| [`flip_to_on_demand`](#wads.ci_trigger.flip_to_on_demand)([repo, python_versions, ...]) | Flip a repo to on-demand CI: pyproject settings plus a re-rendered stub.        |
| [`render_stub_inputs`](#wads.ci_trigger.render_stub_inputs)(stub, inputs)                | Add a `with:` block (the reusable workflow's inputs) under the stub's `uses:`.  |
| [`render_stub_trigger`](#wads.ci_trigger.render_stub_trigger)(stub, \*[, mode, ...])      | Render the caller stub for a trigger mode.                                      |
| [`repo_pyproject_for`](#wads.ci_trigger.repo_pyproject_for)(ci_path)                     | The `pyproject.toml` of the repo holding workflow file `ci_path`, if any.       |
| [`run_ci_on_demand`](#wads.ci_trigger.run_ci_on_demand)([repo, dry_run, ...])          | `wads-migrate ci-on-demand`: flip, report, optionally commit.                   |
| [`set_on_demand_in_pyproject`](#wads.ci_trigger.set_on_demand_in_pyproject)(text, \*[, ...])     | Return pyproject.toml `text` with the on-demand settings applied.               |
| [`stub_customizations`](#wads.ci_trigger.stub_customizations)(text)                       | Split what a stub holds beyond the template into `(with_inputs, dropped)`.      |
| [`stub_if_expression`](#wads.ci_trigger.stub_if_expression)([run_ci_marker])             | The on-demand stub's job-level pre-filter, as a workflow expression.            |
| [`stub_inputs_of`](#wads.ci_trigger.stub_inputs_of)(ci_path)                         | The `with:` inputs an existing stub file passes; `{}` if none or not a stub.    |
| [`stub_shape`](#wads.ci_trigger.stub_shape)(ci_text)                             | The `pin` and secrets `transport` of a stub, which a re-render must keep.       |
| [`trigger_for_workflow`](#wads.ci_trigger.trigger_for_workflow)(ci_path)                   | The `(mode, run_ci_marker)` declared by the repo holding `ci_path`.             |
| [`unasked_workflows`](#wads.ci_trigger.unasked_workflows)(repo, \*[, workflow])         | Other workflow files in `repo` that run without anyone asking (push, PR, cron). |
| [`uncommitted`](#wads.ci_trigger.uncommitted)(repo, paths)                        | Which of `paths` have uncommitted changes (`git status --porcelain` lines).     |
| [`validate_trigger`](#wads.ci_trigger.validate_trigger)(mode, run_ci_marker)           | Validate a (mode, marker) pair with the same rules the CI setup job applies.    |

### Classes

| [`FlipResult`](#wads.ci_trigger.FlipResult)(repo[, status, changes, notes])   | What [`flip_to_on_demand()`](#wads.ci_trigger.flip_to_on_demand) changed or, on a dry run, would change.   |
|-----------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------|

### *class* wads.ci_trigger.FlipResult(repo, status='unchanged', changes=<factory>, notes=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

What [`flip_to_on_demand()`](#wads.ci_trigger.flip_to_on_demand) changed or, on a dry run, would change.

`status` is `"changed"`, `"unchanged"` (already on-demand) or `"refused"`
(nothing written; `notes` says why). `changes` maps a repo-relative path to its
`(old, new)` text.

#### diff()

Unified diff of every change.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### wads.ci_trigger.classify_ci_workflow(text)

Classify a `ci.yml`: `'missing'`, `'stub'`, `'inline-uv'` or `'other'`.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> classify_ci_workflow(None)
'missing'
>>> classify_ci_workflow("uses: i2mint/wads/.github/workflows/uv-ci.yml@master")
'stub'
>>> classify_ci_workflow("uses: i2mint/wads/actions/run-tests-uv@master")
'inline-uv'
>>> classify_ci_workflow("uses: actions/setup-python@v5")
'other'
```

### wads.ci_trigger.commit_paths(repo, paths, , message)

Commit exactly `paths` and return the new commit’s short sha.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### wads.ci_trigger.flip_to_on_demand(repo='.', , python_versions=('3.12',), test_on_windows=False, run_ci_marker=None, workflow='.github/workflows/ci.yml', dry_run=False)

Flip a repo to on-demand CI: pyproject settings plus a re-rendered stub.

- a **stub** `ci.yml` is re-rendered keeping its pin, secrets transport and
  `with:` inputs, or **refused** if it holds anything else a re-render would drop
  (extra jobs, custom triggers);
- an **inline uv** workflow becomes the stub, carrying its secret-backed env vars
  into `[tool.wads.ci.env]` first (as `wads-migrate ci-to-stub` does);
- **no** `ci.yml`: only pyproject changes (nothing runs on push anyway);
- anything else (2025/legacy/custom workflow) is **refused** and nothing is
  written, because it would ignore the setting and keep running on every push.

Idempotent: a second run reports `"unchanged"` and writes nothing.

* **Return type:**
  [`FlipResult`](#wads.ci_trigger.FlipResult)

### wads.ci_trigger.render_stub_inputs(stub, inputs)

Add a `with:` block (the reusable workflow’s inputs) under the stub’s `uses:`.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### wads.ci_trigger.render_stub_trigger(stub, , mode='auto', run_ci_marker='[run ci]')

Render the caller stub for a trigger mode.

`"auto"` returns `stub` unchanged. `"on-demand"` replaces the push/PR trigger
with push + `workflow_dispatch`, puts the plain-language explanation above it, and
adds the pre-filter `if:` to the `ci` job.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### wads.ci_trigger.repo_pyproject_for(ci_path)

The `pyproject.toml` of the repo holding workflow file `ci_path`, if any.

Walks up from the workflow, stopping at the first directory that holds a `.git`
so an enclosing project’s pyproject is never mistaken for this repo’s.

* **Return type:**
  [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)]

### wads.ci_trigger.run_ci_on_demand(repo='.', , dry_run=False, python_versions=('3.12',), test_on_windows=False, run_ci_marker=None, workflow='.github/workflows/ci.yml', commit=False, out=None, err=None)

`wads-migrate ci-on-demand`: flip, report, optionally commit. Returns an exit code.

`0` changed or already on-demand, `2` refused (nothing written).

* **Return type:**
  [`int`](https://docs.python.org/3/builtins/functions.html#int)

### wads.ci_trigger.set_on_demand_in_pyproject(text, , python_versions=('3.12',), test_on_windows=False, run_ci_marker=None)

Return pyproject.toml `text` with the on-demand settings applied.

Sets `[tool.wads.ci.trigger].mode = "on-demand"` (and `run_ci_marker` when
given), `[tool.wads.ci.testing].python_versions` and `test_on_windows`.
Comments and layout survive (tomlkit), and a key already holding its target value
is not touched, so applying this twice returns the first result unchanged.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### wads.ci_trigger.stub_customizations(text)

Split what a stub holds beyond the template into `(with_inputs, dropped)`.

`with_inputs` (a flat `with:` mapping, e.g. `project-name`) survives a
re-render; `dropped` names everything else a re-render would silently lose.
Raises `yaml.YAMLError` when the text does not parse.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict), [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)]

```pycon
>>> stub_customizations(
...     "on: [push, pull_request]\njobs:\n  ci:\n    uses: x\n"
...     "    with:\n      project-name: my_pkg\n"
... )
({'project-name': 'my_pkg'}, [])
>>> stub_customizations("on: [push]\njobs:\n  ci:\n    uses: x\n  lint:\n    runs-on: y\n")[1]
['`on: ["push"]`', 'job `lint`']
```

### wads.ci_trigger.stub_if_expression(run_ci_marker='[run ci]')

The on-demand stub’s job-level pre-filter, as a workflow expression.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> stub_if_expression("[run ci]")
"github.event_name == 'workflow_dispatch' || contains(github.event.head_commit.message, '[run ci]')"
```

A quote in the marker is doubled, which is how workflow expressions escape it:

```pycon
>>> stub_if_expression("it's")
"github.event_name == 'workflow_dispatch' || contains(github.event.head_commit.message, 'it''s')"
```

### wads.ci_trigger.stub_inputs_of(ci_path)

The `with:` inputs an existing stub file passes; `{}` if none or not a stub.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### wads.ci_trigger.stub_shape(ci_text)

The `pin` and secrets `transport` of a stub, which a re-render must keep.

Defaults (`@master`, `json`) for anything that is not a stub.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

```pycon
>>> stub_shape("uses: i2mint/wads/.github/workflows/uv-ci.yml@0.2.30")
{'pin': '@0.2.30', 'transport': 'named'}
>>> stub_shape(None)
{'pin': '@master', 'transport': 'json'}
```

### wads.ci_trigger.trigger_for_workflow(ci_path)

The `(mode, run_ci_marker)` declared by the repo holding `ci_path`.

Defaults when there is no such file or no pyproject. An invalid trigger table
raises: a stub must never silently render `auto` for a repo that asked for
`on-demand`.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### wads.ci_trigger.unasked_workflows(repo, , workflow='.github/workflows/ci.yml')

Other workflow files in `repo` that run without anyone asking (push, PR, cron).

The flip only governs `workflow`; these keep running and are worth knowing about.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### wads.ci_trigger.uncommitted(repo, paths)

Which of `paths` have uncommitted changes (`git status --porcelain` lines).

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### wads.ci_trigger.validate_trigger(mode, run_ci_marker)

Validate a (mode, marker) pair with the same rules the CI setup job applies.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

```pycon
>>> validate_trigger("on-demand", "[run ci]")
('on-demand', '[run ci]')
>>> validate_trigger("sometimes", "[run ci]")
Traceback (most recent call last):
  ...
ValueError: [tool.wads.ci.trigger].mode must be one of ('auto', 'on-demand'), got 'sometimes'
```
