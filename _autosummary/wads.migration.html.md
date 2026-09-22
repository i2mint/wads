# wads.migration

Migration tools for converting old setuptools/CI configurations to modern formats.

This module provides functions to migrate:

- setup.cfg files to pyproject.toml (hatching format)
- Old GitHub CI workflows to modern 2025 format

Key Functions:
: migrate_setuptools_to_hatching: Convert setup.cfg to pyproject.toml
  migrate_github_ci_old_to_new: Convert old CI scripts to new format

### Example

```pycon
>>> from wads.migration import migrate_setuptools_to_hatching
>>> # From a file (use actual file path)
>>> pyproject = migrate_setuptools_to_hatching('setup.cfg')
>>>
>>> # From a dict with complete metadata
>>> cfg = {
...     'metadata': {
...         'name': 'myproject',
...         'version': '0.1.0',
...         'description': 'A sample project',
...         'url': 'https://github.com/user/myproject',
...         'license': 'MIT'
...     }
... }
>>> result = migrate_setuptools_to_hatching(cfg)
>>> 'name = "myproject"' in result
True
```

### Functions

| [`analyze_manifest_in`](#wads.migration.analyze_manifest_in)(manifest_path)                | Analyze MANIFEST.in file and provide migration guidance for Hatchling.    |
|----------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------|
| [`carry_ci_env_into_pyproject`](#wads.migration.carry_ci_env_into_pyproject)(ci_text, ...[, kind]) | Merge secret-backed env vars from `ci_text` into `[tool.wads.ci.env]`.    |
| [`extract_ci_env_vars`](#wads.migration.extract_ci_env_vars)(ci_text)                      | Extract secret-backed env vars from a CI workflow's `env:` blocks.        |
| [`main`](#wads.migration.main)()                                            | CLI entry point for wads migration tools.                                 |
| [`migrate_ci_to_stub`](#wads.migration.migrate_ci_to_stub)([old_ci, pin, transport, ...]) | Return the SSOT stub CI workflow that calls i2mint/wads's reusable uv-ci. |
| [`migrate_ci_to_uv`](#wads.migration.migrate_ci_to_uv)(old_ci, \*[, defaults])          | Migrate a CI workflow (old or 2025 format) to the uv-based template.      |
| [`migrate_github_ci_old_to_new`](#wads.migration.migrate_github_ci_old_to_new)(old_ci[, defaults])  | Migrate old GitHub CI script to new 2025 format.                          |
| [`migrate_setuptools_to_hatching`](#wads.migration.migrate_setuptools_to_hatching)(setup_cfg[, ...])  | Migrate setup.cfg to pyproject.toml format using hatching.                |

### Exceptions

| [`MigrationError`](#wads.migration.MigrationError)   | Raised when migration cannot be completed due to missing or unmapped data.   |
|-------------------------------------------------------------------|------------------------------------------------------------------------------|

### *exception* wads.migration.MigrationError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

Raised when migration cannot be completed due to missing or unmapped data.

### wads.migration.analyze_manifest_in(manifest_path)

Analyze MANIFEST.in file and provide migration guidance for Hatchling.

* **Parameters:**
  **manifest_path** (`Union`[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)]) – Path to MANIFEST.in file
* **Returns:**
  - exists: bool - whether file exists
  - needs_migration: bool - whether migration is needed
  - directives: list of (command, pattern) tuples
  - recommendations: list of strings with migration guidance
  - hatchling_config: suggested pyproject.toml configuration
* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### Example

```pycon
>>> # If MANIFEST.in doesn't exist
>>> result = analyze_manifest_in('nonexistent/MANIFEST.in')
>>> result['exists']
False
>>> result['needs_migration']
False
```

### wads.migration.carry_ci_env_into_pyproject(ci_text, pyproject_path, , kind='extra')

Merge secret-backed env vars from `ci_text` into `[tool.wads.ci.env]`.

Adds only env vars not already declared (in any bucket), into the `kind`
bucket (default `extra` — available-if-set, never fails the build), and
records a `secret_aliases` entry when the env var name differs from the
backing secret. Returns the list of newly-added var names (`[]` if there
was nothing to carry). This is what makes `ci-to-stub` / `ci-to-uv`
*lossless*: secrets wired only in the old workflow YAML are preserved in
`pyproject.toml` instead of silently dropped.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)

### wads.migration.extract_ci_env_vars(ci_text)

Extract secret-backed env vars from a CI workflow’s `env:` blocks.

Returns a mapping `{ENV_VAR: SECRET_NAME}` for every workflow/job/step
`env:` entry whose value references `${{ secrets.X }}`. This is the
per-repo signal of which secrets the tests actually consume.

Deliberately excluded:

* Literal env vars (`PROJECT_NAME`, `LOG_LEVEL: DEBUG` …) — no secret ref.
* Infra secrets (`GITHUB_TOKEN`, `PYPI_PASSWORD`, `TEST_PYPI_PASSWORD`).
* Reusable-workflow `secrets:` pass-through blocks — that’s *transport*,
  not a signal of usage, and scanning it would re-introduce the very
  over-assignment the new model removes.

```pycon
>>> ci = '''
... env:
...   PROJECT_NAME: myproj
...   OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY || '' }}
...   HF_TOKEN: ${{ secrets.HF_WRITE_TOKEN }}
... jobs:
...   publish:
...     steps:
...       - uses: x
...         with:
...           pypi-token: ${{ secrets.PYPI_PASSWORD }}
... '''
>>> extract_ci_env_vars(ci) == {
...     "OPENAI_API_KEY": "OPENAI_API_KEY", "HF_TOKEN": "HF_WRITE_TOKEN"}
True
```

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### wads.migration.main()

CLI entry point for wads migration tools.

### wads.migration.migrate_ci_to_stub(old_ci=None, , pin='@master', transport='json', trigger_mode=None, run_ci_marker=None)

Return the SSOT stub CI workflow that calls i2mint/wads’s reusable uv-ci.

The stub is ~5 lines and replaces a repo’s full inline CI with a single
`uses:` of `i2mint/wads/.github/workflows/uv-ci.yml`. All per-repo
configuration continues to come from `[tool.wads.ci.*]` in
`pyproject.toml` — the reusable workflow reads it via the
`i2mint/wads/actions/read-ci-config` action.

* **Parameters:**
  * **old_ci** (`Union`[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)]) – Optional path or content of the existing CI workflow. Used only
    to locate a nearby pyproject.toml when `transport="named"`;
    with the default JSON transport the stub is the same regardless of
    what was there.
  * **pin** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – The wads ref the stub points at. Defaults to `"@master"`
    (floats with wads). For release-sensitive repos, pin to a tag,
    e.g. `pin="@0.2.15"` (wads tags have no `v` prefix). With the
    default JSON transport the pinned ref’s `uv-ci.yml` must declare
    `WADS_CI_SECRETS_JSON` (releases after 0.2.14) — pinning an
    older tag produces a workflow GitHub rejects at parse time, so a
    warning is emitted for any non-master pin. Must start with `"@"`.
  * **transport** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – `"json"` (default) passes the repo’s whole secrets
    context as one `WADS_CI_SECRETS_JSON` secret — any secret name
    works, nothing to enumerate. `"named"` passes an explicit subset
    (PYPI_PASSWORD + the [tool.wads.ci.env]-declared secrets) for
    repos that want a minimal secret surface; every name must then be
    in the frozen wads superset or GitHub rejects the workflow at
    parse time (issue #63) — out-of-superset names trigger a loud
    warning.
  * **trigger_mode** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – `"auto"` or `"on-demand"`. `None` (default) takes
    `[tool.wads.ci.trigger].mode` from the pyproject.toml of the repo
    holding `old_ci` (`"auto"` when there is none). On-demand stubs
    run nothing unless the commit subject carries the run-ci marker or
    the run is a `workflow_dispatch`; see [`wads.ci_trigger`](wads.ci_trigger.html.md#module-wads.ci_trigger).
  * **run_ci_marker** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – The on-demand marker; `None` takes it from the same
    pyproject (default `"[run ci]"`).
* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
* **Returns:**
  The stub workflow content as a string.

### Example

```pycon
>>> stub = migrate_ci_to_stub()
>>> 'i2mint/wads/.github/workflows/uv-ci.yml@master' in stub
True
>>> 'WADS_CI_SECRETS_JSON: ${{ toJSON(toJSON(secrets)) }}' in stub
True
>>> pinned = migrate_ci_to_stub(pin='@0.2.15')  # warns on stderr
>>> 'uv-ci.yml@0.2.15' in pinned
True
>>> named = migrate_ci_to_stub(transport='named')
>>> 'PYPI_PASSWORD: ${{ secrets.PYPI_PASSWORD }}' in named
True
>>> 'WADS_CI_SECRETS_JSON' in named
False
```

### wads.migration.migrate_ci_to_uv(old_ci, , defaults=None)

Migrate a CI workflow (old or 2025 format) to the uv-based template.

Since the uv template reads all configuration from pyproject.toml
(via the read-ci-config action), the migration is straightforward:
replace the workflow file with the uv template.

* **Parameters:**
  * **old_ci** (`Union`[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)]) – Path to the existing CI workflow file, or its content as a string.
  * **defaults** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)]) – Optional dict with ‘project_name’ if it cannot be extracted
    from the old CI file.
* **Returns:**
  The uv CI template content as a string.

### Example

```pycon
>>> result = migrate_ci_to_uv('name: CI\non: push')
>>> 'astral-sh/setup-uv' in result
True
>>> 'build-dist-uv' in result
True
```

### wads.migration.migrate_github_ci_old_to_new(old_ci, defaults=None)

Migrate old GitHub CI script to new 2025 format.

* **Parameters:**
  * **old_ci** (`Union`[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)]) – Path to old CI file or its content as string
  * **defaults** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)]) – Default values for missing fields (e.g., {‘project_name’: ‘myproject’})
* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
* **Returns:**
  String content of the new CI script
* **Raises:**
  [**MigrationError**](#wads.migration.MigrationError) – If unmapped elements exist or required fields are missing

#### NOTE
The 2025 CI template is fully config-driven via pyproject.toml.
Migration now primarily involves setting up proper [tool.wads.ci] configuration
rather than doing template substitution. For new projects, use populate_pkg_dir()
to generate proper configuration.

### Example

```pycon
>>> # Migration is now about configuration, not template substitution
>>> # For new projects, use populate_pkg_dir() instead
>>> # Old migration approach with placeholders is deprecated
>>> pass
```

### wads.migration.migrate_setuptools_to_hatching(setup_cfg, defaults=None, , rules=None)

Migrate setup.cfg to pyproject.toml format using hatching.

* **Parameters:**
  * **setup_cfg** (`Union`[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Mapping`](https://docs.python.org/3/library/typing.html#typing.Mapping)]) – Either a file path, file content string, or dict of setup.cfg
  * **defaults** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)]) – Default values to use for missing required fields
  * **rules** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)]) – Custom transformation rules (defaults to setup_cfg_to_pyproject_toml_rules)
* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
* **Returns:**
  String content of the generated pyproject.toml
* **Raises:**
  [**MigrationError**](#wads.migration.MigrationError) – If required fields are missing or unmapped data exists

### Example

```pycon
>>> # From file path
>>> pyproject = migrate_setuptools_to_hatching('setup.cfg')
>>>
>>> # From dict with all required fields
>>> cfg = {
...     'metadata': {
...         'name': 'myproj',
...         'version': '0.1.0',
...         'description': 'My project',
...         'url': 'https://github.com/user/myproj',
...         'license': 'MIT'
...     }
... }
>>> result = migrate_setuptools_to_hatching(cfg)
>>> 'name = "myproj"' in result
True
>>>
>>> # With defaults for missing fields
>>> minimal = {'metadata': {'name': 'test', 'version': '1.0'}}
>>> result = migrate_setuptools_to_hatching(
...     minimal,
...     defaults={
...         'description': 'Test project',
...         'url': 'https://test.com',
...         'license': 'MIT'
...     }
... )
>>> 'name = "test"' in result
True
```
