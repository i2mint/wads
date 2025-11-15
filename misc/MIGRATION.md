# Migration Tools

The `wads.migration` module provides tools for migrating old setuptools-based projects to the modern hatching/pyproject.toml format, as well as updating CI/CD scripts.

## Overview

As Python packaging evolves, many projects still use the older `setup.cfg` format and outdated CI scripts. The migration tools help automate the transition to:

- **Modern packaging**: `pyproject.toml` with hatching backend
- **Modern CI/CD**: Updated GitHub Actions workflows using ruff and modern Python practices

## Key Features

- **Flexible input**: Accept setup.cfg as file path, content string, or dictionary
- **Rule-based transformation**: Extensible system for mapping old config to new format
- **Strict validation**: Ensures no information is lost during migration
- **Default values**: Provide defaults for missing required fields
- **CI migration**: Transform old CI scripts to new 2025 format

## Setup.cfg to pyproject.toml Migration

### Basic Usage

```python
from wads.migration import migrate_setuptools_to_hatching

# From a file
pyproject_content = migrate_setuptools_to_hatching('path/to/setup.cfg')

# From a string
setup_cfg_content = """
[metadata]
name = myproject
version = 1.0.0
...
"""
pyproject_content = migrate_setuptools_to_hatching(setup_cfg_content)

# From a dictionary
setup_cfg_dict = {
    'metadata': {
        'name': 'myproject',
        'version': '1.0.0',
        'description': 'My awesome project'
    }
}
pyproject_content = migrate_setuptools_to_hatching(setup_cfg_dict)
```

### With Defaults

If your `setup.cfg` is missing some required fields, provide defaults:

```python
pyproject_content = migrate_setuptools_to_hatching(
    'setup.cfg',
    defaults={
        'description': 'My project description',
        'url': 'https://github.com/myuser/myproject',
        'license': 'MIT'
    }
)
```

### Custom Transformation Rules

The migration uses a rule-based system. Each rule is a function that extracts a value from the setup.cfg dict:

```python
from wads.migration import migrate_setuptools_to_hatching, setup_cfg_to_pyproject_toml_rules

# Define custom rules
custom_rules = {
    'project.name': lambda cfg: cfg['metadata']['name'].upper(),
    'project.version': lambda cfg: cfg['metadata']['version'],
    # ... more rules
}

# Use custom rules
pyproject_content = migrate_setuptools_to_hatching(
    'setup.cfg',
    rules=custom_rules
)
```

### Default Rules

The module includes these built-in transformation rules:

- `project.name` - Extract project name
- `project.version` - Extract version
- `project.description` - Extract description
- `project.url` - Extract homepage URL
- `project.license` - Extract and normalize license
- `project.keywords` - Parse keywords list
- `project.authors` - Extract author information
- `project.dependencies` - Convert install_requires to dependencies
- `project.optional-dependencies` - Convert extras_require
- `project.scripts` - Convert console_scripts entry points

### Error Handling

The migration is strict by design. If required fields are missing or unmapped data exists, it raises `MigrationError`:

```python
from wads.migration import migrate_setuptools_to_hatching, MigrationError

try:
    result = migrate_setuptools_to_hatching(incomplete_cfg)
except MigrationError as e:
    print(f"Migration failed: {e}")
    # Provide missing information via defaults
```

## CI Script Migration

### Basic Usage

```python
from wads.migration import migrate_github_ci_old_to_new

# From a file
new_ci = migrate_github_ci_old_to_new('.github/workflows/ci.yml')

# From content
old_ci_content = """
name: CI
env:
  PROJECT_NAME: myproject
...
"""
new_ci = migrate_github_ci_old_to_new(old_ci_content)
```

### With Defaults

If the project name can't be extracted, provide it:

```python
new_ci = migrate_github_ci_old_to_new(
    'ci.yml',
    defaults={'project_name': 'myproject'}
)
```

### What Changes

The CI migration updates:

- **Actions versions**: checkout@v3 → v4, setup-python@v4 → v5
- **Linting**: pylint → ruff
- **Formatting**: Uses ruff-format
- **Dependencies**: Uses pyproject.toml instead of setup.cfg
- **Build**: Modern build tools via wads actions
- **Version bumping**: Updated version management

### Migration Notes

The migration adds warning comments for elements that need attention:

```yaml
# MIGRATION NOTE: Old CI uses setuptools - ensure pyproject.toml is ready
# MIGRATION NOTE: Old CI uses pylint - new CI uses ruff for linting
```

## Complete Example

Here's a complete workflow for migrating a project:

```python
from wads.migration import migrate_setuptools_to_hatching, migrate_github_ci_old_to_new
from pathlib import Path

# 1. Migrate setup.cfg
project_root = Path('/path/to/project')
setup_cfg = project_root / 'setup.cfg'

pyproject_content = migrate_setuptools_to_hatching(
    str(setup_cfg),
    defaults={
        'description': 'My project',
        'url': 'https://github.com/myuser/myproject'
    }
)

# Write the new pyproject.toml
(project_root / 'pyproject.toml').write_text(pyproject_content)

# 2. Migrate CI
old_ci = project_root / '.github' / 'workflows' / 'ci.yml'
new_ci_content = migrate_github_ci_old_to_new(str(old_ci))

# Write the new CI
(project_root / '.github' / 'workflows' / 'ci_new.yml').write_text(new_ci_content)

print("Migration complete! Review the files and test before committing.")
```

## API Reference

### migrate_setuptools_to_hatching

```python
def migrate_setuptools_to_hatching(
    setup_cfg: Union[str, Mapping],
    defaults: Optional[dict] = None,
    *,
    rules: Optional[dict] = None
) -> str:
```

**Parameters:**
- `setup_cfg`: Either a file path, file content string, or dict of setup.cfg
- `defaults`: Default values for missing required fields
- `rules`: Custom transformation rules (defaults to `setup_cfg_to_pyproject_toml_rules`)

**Returns:** String content of the generated pyproject.toml

**Raises:** `MigrationError` if required fields are missing or unmapped data exists

### migrate_github_ci_old_to_new

```python
def migrate_github_ci_old_to_new(
    old_ci: Union[str, Path],
    defaults: Optional[dict] = None,
) -> str:
```

**Parameters:**
- `old_ci`: Path to old CI file or its content as string
- `defaults`: Default values for missing fields (e.g., `{'project_name': 'myproject'}`)

**Returns:** String content of the new CI script

**Raises:** `MigrationError` if unmapped elements exist or required fields are missing

### MigrationError

Exception raised when migration cannot be completed due to missing or unmapped data.

## Examples Directory

See `wads/examples/migration_example.py` for working examples you can run and modify.

## Contributing

To add new transformation rules:

1. Define a rule function that takes a setup.cfg dict and returns the desired value
2. Add it to `setup_cfg_to_pyproject_toml_rules` dictionary with the appropriate field path
3. Add tests in `wads/tests/test_migration.py`

Example:

```python
def _rule_project_custom_field(cfg: dict) -> str:
    """Extract custom field."""
    return cfg.get('metadata', {}).get('custom_field', 'default')

setup_cfg_to_pyproject_toml_rules['project.custom-field'] = _rule_project_custom_field
```
