# CI/CD Scripts

This directory contains Python scripts that implement complex logic for GitHub Actions workflows.

## Why Scripts Instead of Inline Code?

Extracting complex logic from action YAML files into Python scripts provides several benefits:

1. **Testability**: Scripts can be unit tested independently
2. **Maintainability**: Easier to read, debug, and modify
3. **Reusability**: Can be used outside of GitHub Actions
4. **IDE Support**: Full IDE features (autocomplete, type checking, linting)
5. **Error Handling**: Better exception handling and error messages

## Available Scripts

### `build_dist.py`
Build Python distribution packages (sdist and/or wheel).

```bash
python -m wads.scripts.build_dist --output-dir=dist --no-sdist
```

**Used by**: `actions/build-dist/action.yml`

### `install_deps.py`
Install Python dependencies from various sources.

```bash
python -m wads.scripts.install_deps \
  --pypi-packages pytest pytest-cov \
  --dependency-files pyproject.toml \
  --extras "test,dev"
```

**Used by**: Can be used in any action that needs dependency installation

### `read_ci_config.py`
Read CI configuration from pyproject.toml and export to GitHub Actions.

```bash
python -m wads.scripts.read_ci_config /path/to/pyproject.toml
```

**Used by**: `actions/read-ci-config/action.yml`

### `set_env_vars.py`
Set environment variables from GitHub Secrets with validation.

```bash
export SECRETS_CONTEXT='{"API_KEY": "value"}'
python -m wads.scripts.set_env_vars
```

**Used by**: `actions/set-env-vars/action.yml`

### `validate_ci_env.py`
Validate that required CI environment variables are set.

```bash
python -m wads.scripts.validate_ci_env
```

**Used by**: Can be used in any action that needs environment validation

## Usage Patterns

### In GitHub Actions

Scripts are designed to be called from GitHub Actions workflows:

```yaml
- name: Read CI Configuration
  shell: bash
  run: |
    python3 -m wads.scripts.read_ci_config "${{ inputs.pyproject-path }}"
```

### Standalone

Scripts can also be run directly for testing or local development:

```bash
# All scripts support --help
python -m wads.scripts.build_dist --help

# Most scripts work with current directory by default
python -m wads.scripts.read_ci_config

# Or specify a path
python -m wads.scripts.read_ci_config /path/to/project
```

## Testing

Scripts can be tested independently using pytest:

```python
from wads.scripts.validate_ci_env import validate_ci_environment

def test_validation(tmp_path):
    # Create test configuration
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("""
    [tool.wads.ci.env]
    required = ["API_KEY"]
    """)
    
    # Test validation
    success, missing = validate_ci_environment(tmp_path)
    assert not success
    assert "API_KEY" in missing
```

## Development

When adding new scripts:

1. Add proper docstring with usage examples
2. Use argparse for command-line arguments
3. Return proper exit codes (0 for success, 1 for failure)
4. Handle GitHub Actions environment variables when needed
5. Make the script executable: `chmod +x script.py`
6. Add to `__all__` in `__init__.py`
7. Update this README

## GitHub Actions Environment Variables

Scripts that integrate with GitHub Actions can use these environment variables:

- `GITHUB_OUTPUT`: Path to file for setting action outputs
- `GITHUB_ENV`: Path to file for setting environment variables
- `GITHUB_STEP_SUMMARY`: Path to file for step summary markdown
- `SECRETS_CONTEXT`: JSON string of all secrets (for `set_env_vars.py`)

Example:

```python
import os

# Set an output
with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
    f.write(f"version={version}\n")

# Set an environment variable
with open(os.environ['GITHUB_ENV'], 'a') as f:
    f.write(f"VERSION={version}\n")
```

## Migration Guide

See [ACTIONS_TO_SCRIPTS_MIGRATION.md](../../misc/docs/ACTIONS_TO_SCRIPTS_MIGRATION.md) for details on the migration from inline code to scripts.
