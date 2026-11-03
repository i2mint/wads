# wads.scripts.read_ci_config

Read CI Configuration and Export to GitHub Actions

This script reads CI configuration from pyproject.toml and exports it as
GitHub Actions outputs and environment variables.

Usage:

```default
python -m wads.scripts.read_ci_config [path_to_pyproject]
```

Environment:
: GITHUB_OUTPUT - Path to GitHub Actions output file
  GITHUB_ENV - Path to GitHub Actions environment file
  GITHUB_STEP_SUMMARY - Path to GitHub Actions step summary file

### Functions

| [`main`](#wads.scripts.read_ci_config.main)()                                      | Main entry point.                                                           |
|----------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------|
| [`pinned_runs_matrix_include`](#wads.scripts.read_ci_config.pinned_runs_matrix_include)(config)          | The validation matrix's `include` entries, one per pinned run (issue #189). |
| [`read_and_export_ci_config`](#wads.scripts.read_ci_config.read_and_export_ci_config)([pyproject_path]) | Read CI configuration and export to GitHub Actions.                         |

### wads.scripts.read_ci_config.main()

Main entry point.

### wads.scripts.read_ci_config.pinned_runs_matrix_include(config)

The validation matrix’s `include` entries, one per pinned run (issue #189).

Each is self-contained, `{"python-version": ..., "pinned": {name, requirements,
pytest_args}}`: the `pinned` object overwrites the matrix’s base `pinned: false`,
so GitHub adds it as a new leg instead of merging it into an existing one.
`pytest_args` is joined, as `run-tests-uv` takes it. Invalid entries raise
(`CIConfig.pinned_test_runs` fails closed); nothing runs when tests are off.

```pycon
>>> from wads.ci_config import CIConfig
>>> pinned = [{"name": "old", "requirements": ["attrs==22.1.0"], "pytest_args": ["-x", "t"]}]
>>> config = CIConfig({"tool": {"wads": {"ci": {"testing": {"pinned": pinned}}}}})
>>> pinned_runs_matrix_include(config)
[{'python-version': '3.10',
  'pinned': {'name': 'old', 'requirements': ['attrs==22.1.0'], 'pytest_args': '-x t'}}]
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)]

### wads.scripts.read_ci_config.read_and_export_ci_config(pyproject_path='.')

Read CI configuration and export to GitHub Actions.

* **Parameters:**
  **pyproject_path** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)) – Path to pyproject.toml file or directory containing it
* **Return type:**
  [`int`](https://docs.python.org/3/builtins/functions.html#int)
* **Returns:**
  Exit code (0 for success, 1 for failure)
