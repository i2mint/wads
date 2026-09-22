# wads.scripts.validate_ci_env

CI Environment Validation Script

This script validates that all required environment variables are set
based on configuration in pyproject.toml [tool.wads.ci.env].

Usage:
: python -m wads.scripts.validate_ci_env

Exit codes:
: 0 - All required environment variables are set
  1 - One or more required environment variables are missing

### Functions

| [`main`](#wads.scripts.validate_ci_env.main)()                                    | Main entry point for CI environment validation.              |
|--------------------------------------------------------------------------------------------|--------------------------------------------------------------|
| [`validate_ci_environment`](#wads.scripts.validate_ci_env.validate_ci_environment)([pyproject_path]) | Validate that all required CI environment variables are set. |

### wads.scripts.validate_ci_env.main()

Main entry point for CI environment validation.

### wads.scripts.validate_ci_env.validate_ci_environment(pyproject_path='.')

Validate that all required CI environment variables are set.

* **Parameters:**
  **pyproject_path** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)) – Path to directory containing pyproject.toml
* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`bool`](https://docs.python.org/3/builtins/functions.html#bool), [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]
* **Returns:**
  Tuple of (success, missing_vars)
