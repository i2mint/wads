# wads.scripts.set_env_vars

Set Environment Variables from GitHub Secrets

This script reads the CI configuration from pyproject.toml and sets environment
variables from GitHub Secrets, validating required variables.

Usage:

```default
python -m wads.scripts.set_env_vars [path_to_pyproject]
```

Environment:
: SECRETS_CONTEXT - JSON string of all GitHub Secrets
  GITHUB_ENV - Path to GitHub Actions environment file
  GITHUB_STEP_SUMMARY - Path to GitHub Actions step summary file

### Functions

| [`main`](#wads.scripts.set_env_vars.main)()                                      | Main entry point.                                                 |
|----------------------------------------------------------------------------------------------|-------------------------------------------------------------------|
| [`set_environment_variables`](#wads.scripts.set_env_vars.set_environment_variables)([pyproject_path]) | Set environment variables from GitHub Secrets based on CI config. |

### wads.scripts.set_env_vars.main()

Main entry point.

### wads.scripts.set_env_vars.set_environment_variables(pyproject_path='.')

Set environment variables from GitHub Secrets based on CI config.

* **Parameters:**
  **pyproject_path** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)) – Path to pyproject.toml file or directory containing it
* **Return type:**
  [`int`](https://docs.python.org/3/builtins/functions.html#int)
* **Returns:**
  Exit code (0 for success, 1 for failure)
