# Actions to Scripts Migration

This document describes the extraction of complex inline code from GitHub Actions workflows into reusable Python scripts.

## Overview

Large amounts of inline Python and bash code in `.github/actions/*/action.yml` files have been extracted into proper Python scripts in `wads/scripts/`. This improves:

- **Testability**: Scripts can be unit tested independently
- **Maintainability**: Easier to read, debug, and modify Python code in dedicated files
- **Reusability**: Scripts can be used outside of GitHub Actions
- **Development**: Better IDE support, type checking, and linting

## Migrated Actions

### 1. `read-ci-config` → `wads/scripts/read_ci_config.py`

**Before**: ~80 lines of inline Python in action.yml  
**After**: Dedicated script with proper structure

The script:
- Reads CI configuration from `pyproject.toml`
- Exports values as GitHub Actions outputs
- Sets environment variables
- Creates GitHub Actions step summary

**Usage in action.yml**:
```yaml
- name: Read CI Configuration
  shell: bash
  run: |
    python3 -m wads.scripts.read_ci_config "${{ inputs.pyproject-path }}"
```

**Standalone usage**:
```bash
python -m wads.scripts.read_ci_config /path/to/pyproject.toml
```

### 2. `set-env-vars` → `wads/scripts/set_env_vars.py`

**Before**: ~120 lines of inline Python in action.yml  
**After**: Dedicated script with comprehensive validation

The script:
- Reads CI environment variable configuration
- Sets variables from GitHub Secrets
- Validates required variables
- Handles reserved variable names
- Creates detailed summary

**Usage in action.yml**:
```yaml
- name: Set Environment Variables
  env:
    SECRETS_CONTEXT: ${{ toJson(secrets) }}
  shell: bash
  run: |
    python3 -m wads.scripts.set_env_vars "${{ inputs.pyproject-path }}"
```

**Standalone usage**:
```bash
export SECRETS_CONTEXT='{"API_KEY": "value"}'
python -m wads.scripts.set_env_vars
```

### 3. `build-dist` → `wads/scripts/build_dist.py`

**Before**: Multiple bash steps with complex logic  
**After**: Single Python script handling all build logic

The script:
- Installs build tools (pip, build)
- Installs project dependencies
- Builds distributions (sdist and/or wheel)
- Reports built packages with sizes

**Usage in action.yml**:
```yaml
- name: Build Distributions
  shell: bash
  run: |
    python3 -m wads.scripts.build_dist \
      --output-dir=dist \
      --sdist \
      --wheel
```

**Standalone usage**:
```bash
python -m wads.scripts.build_dist --output-dir=dist --no-sdist
```

### 4. `install_deps.py` (New Utility)

**Purpose**: Consolidate dependency installation logic

The script:
- Installs packages from PyPI
- Installs from various dependency files (requirements.txt, pyproject.toml, setup.cfg)
- Handles extras from pyproject.toml
- Shows installed package versions

**Usage**:
```bash
# Install from PyPI
python -m wads.scripts.install_deps --pypi-packages pytest pytest-cov

# Install from files
python -m wads.scripts.install_deps --dependency-files pyproject.toml --extras "test,dev"

# Combined
python -m wads.scripts.install_deps \
  --pypi-packages pytest \
  --dependency-files requirements.txt,pyproject.toml \
  --extras testing
```

## Actions Not Migrated (Yet)

These actions have moderate complexity but weren't migrated in this phase:

- **install-deps/action.yml**: Mostly bash logic, could be simplified
- **run-tests/action.yml**: Mostly pytest argument building
- **git-commit/action.yml**: Pure git commands, minimal complexity
- **git-tag/action.yml**: Pure git commands, minimal complexity
- **pypi-upload/action.yml**: Simple twine wrapper
- **ruff-format/action.yml**: Simple ruff wrapper
- **ruff-lint/action.yml**: Simple ruff wrapper
- **version-bump/action.yml**: Uses isee CLI
- **windows-tests/action.yml**: PowerShell-specific

## Benefits Achieved

1. **Reduced action.yml complexity**: Files now primarily define inputs/outputs and call scripts
2. **Better error handling**: Python scripts have proper exception handling
3. **Easier testing**: Scripts can be imported and tested with pytest
4. **Better documentation**: Scripts have docstrings and argparse help
5. **IDE support**: Full IDE features (autocomplete, type checking, refactoring)

## Testing Scripts

The extracted scripts can be tested independently:

```python
# test_read_ci_config.py
from wads.scripts.read_ci_config import read_and_export_ci_config

def test_read_ci_config(tmp_path, monkeypatch):
    # Create test pyproject.toml
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("""
    [project]
    name = "test-project"
    """)
    
    # Mock GitHub Actions environment
    output_file = tmp_path / "output"
    output_file.touch()
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
    
    # Run script
    exit_code = read_and_export_ci_config(tmp_path)
    
    assert exit_code == 0
    assert "project-name=test-project" in output_file.read_text()
```

## Future Work

Consider migrating more actions to scripts if:
1. The action logic becomes more complex
2. The same logic needs to be reused elsewhere
3. Better testing coverage is needed
4. The action needs to support multiple platforms with different shell syntax
