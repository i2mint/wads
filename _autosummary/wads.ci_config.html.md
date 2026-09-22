# wads.ci_config

Utilities for reading and applying CI configuration from pyproject.toml.

This module provides the infrastructure for using pyproject.toml as the single
source of truth for CI configuration, eliminating hardcoded project-specific
settings in CI workflow files.

### Functions

| [`get_ci_config_or_defaults`](#wads.ci_config.get_ci_config_or_defaults)(pyproject_path[, ...])   | Read CI configuration from pyproject.toml, using defaults if file doesn't exist.                                                                                                                                 |
|-----------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`read_ci_config`](#wads.ci_config.read_ci_config)(pyproject_path)                     | Read CI configuration from pyproject.toml.                                                                                                                                                                       |
| [`render_minimal_env_placeholders`](#wads.ci_config.render_minimal_env_placeholders)(...)               | Render the inline template's env placeholders without a [tool.wads.ci] config: workflow-level env gets PROJECT_NAME only, and the test-job placeholders render empty (there are no declared secret-backed vars). |

### Classes

| [`CIConfig`](#wads.ci_config.CIConfig)(pyproject_data[, project_name])   | Represents CI configuration extracted from pyproject.toml.   |
|---------------------------------------------------------------------------------------------|--------------------------------------------------------------|

### *class* wads.ci_config.CIConfig(pyproject_data, project_name=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Represents CI configuration extracted from pyproject.toml.

#### *property* build_config *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)*

Get build configuration.

#### *property* build_sdist *: [bool](https://docs.python.org/3/builtins/functions.html#bool)*

Check if source distribution should be built.

#### *property* build_wheel *: [bool](https://docs.python.org/3/builtins/functions.html#bool)*

Check if wheel should be built.

#### *property* commands_format *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]*

Get format commands.

#### *property* commands_lint *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]*

Get lint commands.

#### *property* commands_post_test *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]*

Get post-test commands.

#### *property* commands_pre_test *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]*

Get pre-test setup commands.

#### *property* commands_test *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]*

Get test commands (defaults to [‘pytest’]).

#### *property* coverage_enabled *: [bool](https://docs.python.org/3/builtins/functions.html#bool)*

Check if coverage is enabled.

#### *property* coverage_threshold *: [int](https://docs.python.org/3/builtins/functions.html#int)*

Get minimum coverage threshold (0 = no enforcement).

#### *property* docs_builder *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

Get documentation builder name.

#### *property* docs_config *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)*

Get documentation configuration.

#### *property* docs_enabled *: [bool](https://docs.python.org/3/builtins/functions.html#bool)*

Check if documentation generation is enabled.

#### *property* docs_ignore_paths *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]*

Get paths to ignore during documentation generation.

#### *property* env_secret_aliases *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str)]*

Map of env-var name -> backing GitHub *secret* name.

Lets a repo expose a secret under a different env-var name in CI, e.g.
read `secrets.HF_WRITE_TOKEN` but expose it to tests as `HF_TOKEN`:

```default
[tool.wads.ci.env.secret_aliases]
HF_TOKEN = "HF_WRITE_TOKEN"
```

Env-var names not listed here are backed by an identically-named secret.

#### *property* env_vars_all *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]*

Get all environment variable names (required + test + extra).

#### *property* env_vars_defaults *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str)]*

Get default environment variables.

#### *property* env_vars_extra *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]*

Get extra/optional environment variable names (no warning if missing).

#### *property* env_vars_required *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]*

Get required environment variable names (CI fails if not in secrets).

#### *property* env_vars_test *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]*

Get test environment variable names (CI warns if not in secrets).

#### *property* exclude_paths *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]*

Get test paths to exclude.

#### *classmethod* from_file(pyproject_path)

Load CI configuration from a pyproject.toml file.

* **Parameters:**
  **pyproject_path** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)) – Path to pyproject.toml file or directory containing it
* **Return type:**
  [`CIConfig`](#wads.ci_config.CIConfig)
* **Returns:**
  CIConfig instance

#### generate_env_block()

Generate the workflow-level YAML env block for GitHub Actions.

Contains ONLY non-secret values:

- PROJECT_NAME (from config)
- Literal defaults from [tool.wads.ci.env.defaults]

Secret-backed vars are deliberately NOT emitted at workflow level: a
workflow-level secret is in scope for the setup job too, and GitHub
refuses to emit any job OUTPUT containing a secret’s value — a short
value (e.g. a test level of “3”) silently blanks `python-versions`
and empties the test matrix (issue #61). Secret-backed vars are
scoped to the jobs that run tests via generate_test_env_block /
generate_test_env_vars.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
* **Returns:**
  YAML string for the workflow-level env section

#### generate_env_vars_yaml()

Generate YAML lines for all environment variables to be set from secrets.
This is used in the #ENV_VARS# placeholder in CI templates.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
* **Returns:**
  YAML string with conditional env var assignments

#### generate_github_pages_job()

Generate YAML for GitHub Pages job.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
* **Returns:**
  YAML string for GitHub Pages job, or empty string if disabled

#### generate_pre_test_steps(platform='linux')

Generate YAML steps for pre-test commands and system dependencies.

Supports legacy [tool.wads.ci.testing.system_dependencies] format.

* **Parameters:**
  **platform** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Platform identifier (‘linux’, ‘macos’, ‘windows’)
* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
* **Returns:**
  YAML string for pre-test steps, or empty string if no commands/deps

#### generate_stub_secrets_block()

Render the caller-stub `secrets:` pass-through for this repo.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

#### generate_test_env_block()

Generate a whole job-level `env:` block for the validation job.

Returns ‘’ when no secret-backed vars are left to emit, so the
rendered job simply has no `env:` key (an empty `env:` mapping is
invalid).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

#### generate_test_env_vars(, indent=6, exclude=())

Generate job-level env entry lines for secret-backed vars.

One `VAR: ${{ secrets.NAME || '' }}` line per name declared in
required_envvars / test_envvars / extra_envvars, honoring
[tool.wads.ci.env.secret_aliases] (env-var name -> backing secret
name). An unset secret renders as an empty string. Returns ‘’ when
nothing is left to emit.

Names also present in [tool.wads.ci.env].defaults are skipped: the
committed default is authoritative (matching the reusable workflow’s
export-ci-env), and it already reaches every job from workflow level
— re-emitting `${{ secrets.X || '' }}` at job level would override
the default with ‘’ in exactly the jobs that run tests.

* **Parameters:**
  * **indent** ([`int`](https://docs.python.org/3/builtins/functions.html#int)) – leading spaces per line (6 = entries of a job-level
    `env:` block)
  * **exclude** ([`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)) – additional names to skip (e.g. keys the target job
    already sets literally)
* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

#### generate_windows_validation_job()

Generate YAML for Windows validation job.

Supports legacy system_dependencies format.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
* **Returns:**
  YAML string for Windows job, or empty string if disabled

#### has_ci_config()

Check if any CI configuration is present.

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

#### *property* install_extras *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

Extras to install in CI, as a comma-separated string for pip’s
`.[extras]` syntax.

Read from `[tool.wads.ci.install].extras` (accepts a list or a
comma-separated string). Returns `""` when unset, in which case CI
installs only the package’s core dependencies. Example: a project whose
tests need its heavier extra can set `extras = "create"` so the CI job
installs `.[create]`.

#### *property* installer *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

Get the package installer to use in CI (‘uv’ or ‘pip’).

#### is_black_enabled()

Check if Black formatter is enabled.

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

#### is_mypy_enabled()

Check if Mypy type checker is enabled.

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

#### is_ruff_enabled()

Check if Ruff linter is enabled.

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

#### *property* licence_config *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)*

The `[tool.wads.licence]` table.

Note it sits under `[tool.wads]`, NOT under `[tool.wads.ci]`: the
policy is a fact about the package’s dependency perimeter, and
[`wads.licence_check`](wads.licence_check.html.md#module-wads.licence_check) is useful outside CI. Only the `enabled`
flag below is a CI concern.

#### *property* licence_enabled *: [bool](https://docs.python.org/3/builtins/functions.html#bool)*

Whether CI should run the licence-perimeter gate.

Defaults to **False**. This one is opt-in rather than opt-out, unlike
every other gate here, and deliberately so: the reusable workflow is
called by the whole fleet, and turning a new failing check on for all
of them at once reddens every caller’s CI in one merge. Set
`[tool.wads.licence].enabled = true` per repo, once its exposures are
resolved.

#### *property* metrics_config *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)*

Get code metrics configuration.

#### *property* metrics_config_path *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

Get path to umpyre config file.

#### *property* metrics_enabled *: [bool](https://docs.python.org/3/builtins/functions.html#bool)*

Check if code metrics tracking is enabled.

#### *property* metrics_force_run *: [bool](https://docs.python.org/3/builtins/functions.html#bool)*

Check if metrics should run even on workflow failure.

#### *property* metrics_python_version *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

Get Python version for metrics collection.

#### *property* metrics_storage_branch *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

Get git branch to store metrics data.

#### *property* ops *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)*

Get system dependencies configuration from [tool.wads.ops.\*] sections.

* **Returns:**
  Dictionary mapping dependency names to their configuration

#### *property* project_name *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

Get the project name for CI.

#### *property* publish_config *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)*

Get publish configuration.

#### *property* publish_enabled *: [bool](https://docs.python.org/3/builtins/functions.html#bool)*

Check if publishing is enabled.

When True (the default), the publish job runs on main/master unless the
commit *subject line* contains [`publish_skip_ci_marker`](#wads.ci_config.CIConfig.publish_skip_ci_marker). When
False, the publish job is skipped unless the commit *subject line*
contains [`publish_marker`](#wads.ci_config.CIConfig.publish_marker).

Both markers are matched against the first line of the commit message
only. A squash-merge folds the entire PR body into the squash commit
message, so a full-message match fires on a PR that merely writes
about a marker.

#### *property* publish_marker *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

Commit-subject substring that forces publishing.

Used when publishing is disabled: a commit whose *subject line* (the
first line of its message) contains this marker still runs the publish
job. Defaults to `"[publish]"`.

#### *property* publish_skip_ci_marker *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

Commit-subject substring that suppresses publishing.

Used when publishing is enabled: a commit whose *subject line* (the
first line of its message) contains this marker skips the publish job.
Defaults to `"[skip ci]"` (which GitHub also natively recognises to
skip the whole workflow).

#### *property* pytest_args *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]*

Get pytest arguments.

#### *property* python_versions *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]*

Get Python versions to test against.

#### *property* quality_config *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)*

Get code quality tool configuration.

#### *property* run_ci_marker *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

Commit-subject substring that runs CI in `"on-demand"` mode.

Defaults to `"[run ci]"`. Matched against the first line of the
commit message only (a squash-merge folds the PR body into the rest).
Must be a non-empty single line: an empty marker would match every
subject and silently turn on-demand back into auto.

#### stub_secret_names(, always=('PYPI_PASSWORD',))

GitHub *secret* names the caller stub should pass to the reusable workflow.

This is the per-repo transport list (kept small): `PYPI_PASSWORD` (for
the publish job) plus the backing secret of every env var the repo
declares in `[tool.wads.ci.env]` (required/test/extra), resolved
through `secret_aliases`. Order-preserving, de-duplicated.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

#### *property* system_dependencies *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict) | [list](https://docs.python.org/3/builtins/stdtypes.html#list)*

Get system dependencies for CI environments (DEPRECATED).

DEPRECATED: Use [tool.wads.ops.\*] format with install-system-deps action instead.
This property is maintained for backward compatibility with legacy format.

Returns either:

- A list of package names (Ubuntu only)
- A dict with platform keys: ubuntu, macos, windows

#### *property* test_on_windows *: [bool](https://docs.python.org/3/builtins/functions.html#bool)*

Check if Windows testing is enabled.

#### *property* testing_config *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)*

Get testing configuration.

#### *property* tests_enabled *: [bool](https://docs.python.org/3/builtins/functions.html#bool)*

Check if the CI test step should run.

Defaults to True. Set `[tool.wads.ci.testing].enabled = false` to skip
the pytest/doctest step entirely — useful for apps or repos that have
no real test suite and whose modules are not import-clean.

#### to_ci_env_block()

Generate YAML env block for GitHub Actions.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
* **Returns:**
  YAML string for env section

#### to_ci_template_substitutions()

Generate all template substitutions for CI workflow generation.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]
* **Returns:**
  Dictionary mapping placeholder names to their values

#### to_pre_test_step()

Generate YAML step for pre-test commands.

* **Return type:**
  [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]
* **Returns:**
  YAML string for pre-test step, or None if no commands

#### *property* trigger_config *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)*

Get the `[tool.wads.ci.trigger]` table.

#### *property* trigger_mode *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

`"auto"` (the default) or `"on-demand"`.

`"auto"` runs on every push and pull request, as wads always has.
`"on-demand"` means **nothing runs unless asked**: every job (tests,
publish, Pages) runs only when the commit *subject line* contains
[`run_ci_marker`](#wads.ci_config.CIConfig.run_ci_marker), or on a manual `workflow_dispatch`.

Raises `ValueError` on any other value, so a typo fails the CI setup
job loudly rather than silently choosing a mode.

```pycon
>>> CIConfig({}).trigger_mode
'auto'
>>> CIConfig({"tool": {"wads": {"ci": {"trigger": {"mode": "on-demand"}}}}}).trigger_mode
'on-demand'
```

* **Type:**
  When CI runs

#### *property* windows_blocking *: [bool](https://docs.python.org/3/builtins/functions.html#bool)*

Whether a failing Windows leg should turn the CI run red.

Defaults to False — the historical behaviour, where the Windows job is
informational (`continue-on-error`) and a Windows-only defect merges
behind a green tick. Opt in with `windows_blocking = true` under
`[tool.wads.ci.testing]`.

Takes effect in the uv workflows (the reusable
`.github/workflows/uv-ci.yml` and its `wads/data/github_ci_uv.yml`
mirror), via the `windows-blocking` output of the read-ci-config
action. It makes the RUN red; it does not gate publication —
`publish` does not depend on the Windows job.

### wads.ci_config.get_ci_config_or_defaults(pyproject_path, project_name=None)

Read CI configuration from pyproject.toml, using defaults if file doesn’t exist.

* **Parameters:**
  * **pyproject_path** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)) – Path to pyproject.toml file or directory containing it
  * **project_name** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Default project name if not found in config
* **Return type:**
  [`CIConfig`](#wads.ci_config.CIConfig)
* **Returns:**
  CIConfig instance with defaults if file doesn’t exist

### wads.ci_config.read_ci_config(pyproject_path)

Read CI configuration from pyproject.toml.

* **Parameters:**
  **pyproject_path** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)) – Path to pyproject.toml file or directory containing it
* **Return type:**
  [`CIConfig`](#wads.ci_config.CIConfig)
* **Returns:**
  CIConfig instance with project configuration

Usage:

```default
config = read_ci_config("path/to/project")
print(config.project_name)        # Project name from pyproject.toml
print(config.python_versions)     # Python versions to test
```

### wads.ci_config.render_minimal_env_placeholders(template_text, project_name)

Render the inline template’s env placeholders without a [tool.wads.ci]
config: workflow-level env gets PROJECT_NAME only, and the test-job
placeholders render empty (there are no declared secret-backed vars).

Used by the no-pyproject fallbacks in migration and populate so a shipped
workflow never carries literal placeholder lines.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
