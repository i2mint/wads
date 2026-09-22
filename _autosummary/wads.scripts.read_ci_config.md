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

| [`main`](#wads.scripts.read_ci_config.main)()                                      | Main entry point.                                   |
|----------------------------------------------------------------------------------------------|-----------------------------------------------------|
| [`read_and_export_ci_config`](#wads.scripts.read_ci_config.read_and_export_ci_config)([pyproject_path]) | Read CI configuration and export to GitHub Actions. |

### wads.scripts.read_ci_config.main()

Main entry point.

### wads.scripts.read_ci_config.read_and_export_ci_config(pyproject_path='.')

Read CI configuration and export to GitHub Actions.

* **Parameters:**
  **pyproject_path** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)) – Path to pyproject.toml file or directory containing it
* **Return type:**
  [`int`](https://docs.python.org/3/builtins/functions.html#int)
* **Returns:**
  Exit code (0 for success, 1 for failure)
