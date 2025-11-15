# Config Comparison Tools

The `wads.config_comparison` module provides tools to compare project configuration files against modern templates, helping you keep projects up-to-date with best practices.

## Features

### 1. Compare `pyproject.toml` Against Template

Check if your project's `pyproject.toml` aligns with the modern template:

```python
from wads.config_comparison import compare_pyproject_toml

# Compare your project's config
result = compare_pyproject_toml('path/to/pyproject.toml')

if result['needs_attention']:
    print("Missing sections:", result['missing_sections'])
    for rec in result['recommendations']:
        print(f"  • {rec}")
```

**What it checks:**
- Missing tool configurations (ruff, pytest, etc.)
- Outdated build backends
- Structural differences from template

### 2. Check `setup.cfg` (Deprecation Warning)

Analyze `setup.cfg` and get migration recommendations:

```python
from wads.config_comparison import compare_setup_cfg

result = compare_setup_cfg('path/to/setup.cfg')

if result['should_migrate']:
    print("setup.cfg is deprecated!")
    for rec in result['recommendations']:
        print(f"  • {rec}")
```

**Output:**
```
setup.cfg is deprecated in favor of pyproject.toml (PEP 621)
To migrate, run: populate . --migrate
Or use: from wads.migration import migrate_setuptools_to_hatching
```

### 3. Check `MANIFEST.in` (Hatchling Migration)

Analyze `MANIFEST.in` and get Hatchling configuration recommendations:

```python
from wads.config_comparison import compare_manifest_in

result = compare_manifest_in('path/to/MANIFEST.in')

if result['needs_migration']:
    print("MANIFEST.in needs migration to Hatchling!")
    for rec in result['recommendations']:
        print(f"  • {rec}")
    
    # Get suggested pyproject.toml configuration
    if result['hatchling_config']:
        print("\nSuggested configuration:")
        print(result['hatchling_config'])
```

**What it does:**
- Parses MANIFEST.in directives (include, graft, prune, etc.)
- Converts to equivalent Hatchling configuration
- Suggests `[tool.hatch.build.targets.wheel]` settings

**Example output:**
```toml
[tool.hatch.build.targets.wheel]
include = [
  "mypackage/data/**/*.json",
  "docs/**/*"
]
exclude = [
  "tests/",
  "**/*.pyc"
]
```

### 4. Compare CI Workflow

Check if your GitHub Actions workflow is up-to-date:

```python
from wads.config_comparison import compare_ci_workflow

result = compare_ci_workflow('.github/workflows/ci.yml')

if result['needs_attention']:
    for rec in result['recommendations']:
        print(f"  • {rec}")
```

**What it checks:**
- Outdated action versions (@v3 vs @v4)
- Missing modern tools (ruff)
- CI structure alignment

### 5. Overall Project Health Check

Get a comprehensive status of all config files:

```python
from wads.config_comparison import summarize_config_status

status = summarize_config_status('/path/to/project')

print(f"Has pyproject.toml: {status['has_pyproject']}")
print(f"Has setup.cfg: {status['has_setup_cfg']}")
print(f"Has MANIFEST.in: {status['has_manifest_in']}")

if status['needs_attention']:
    print("Files needing attention:")
    for file in status['needs_attention']:
        print(f"  - {file}")
```

## Integration with `populate`

The `populate_pkg_dir` function now automatically compares config files against templates and shows an **emoji-based summary** at the end:

```bash
$ populate /path/to/project --verbose
```

**Output:**

```
============================================================
POPULATE SUMMARY
============================================================

✓ Skipped (already exists):
  • README.md
  • pyproject.toml

👀 Needs attention:
  • pyproject.toml
    └─ Missing sections: tool.ruff.lint, tool.pytest
  • setup.cfg
    └─ Deprecated format. Run: populate . --migrate

✅ Added:
  • .gitignore
  • .gitattributes
  • LICENSE

❌ Errors:
  (none)

============================================================
```

### Summary Sections

1. **✓ Skipped** - Files that already exist (not overwritten)
2. **👀 Needs attention** - Files with issues or misalignments
3. **✅ Added** - Files that were created
4. **❌ Errors** - Operations that failed

## Command Line Usage

### Check existing project

```bash
# Navigate to project
cd /path/to/my_project

# Run populate with verbose to see detailed checks
populate . --verbose
```

### Migrate old project

```bash
# Migrate setup.cfg → pyproject.toml and old CI → new CI
populate . --migrate --verbose
```

### Create new project with checks

```bash
# Populate will automatically check alignment
populate /path/to/new_project \
  --description "My project" \
  --root-url https://github.com/myorg \
  --verbose
```

## Python API

### Detailed comparison

```python
from wads.config_comparison import (
    compare_pyproject_toml,
    compare_setup_cfg,
    compare_ci_workflow,
    summarize_config_status,
)

# Individual file checks
pyproject_status = compare_pyproject_toml('pyproject.toml')
setup_cfg_status = compare_setup_cfg('setup.cfg')
ci_status = compare_ci_workflow('.github/workflows/ci.yml')

# Or get everything at once
overall_status = summarize_config_status('.', check_ci=True)

# Access detailed information
if overall_status['needs_attention']:
    # Get project-specific status
    if 'pyproject_status' in overall_status:
        pyproject = overall_status['pyproject_status']
        print("Missing:", pyproject['missing_sections'])
        print("Outdated:", pyproject['outdated_sections'])
```

### Custom ignore patterns

```python
# Ignore specific keys during comparison
comparison = compare_pyproject_toml(
    'pyproject.toml',
    ignore_keys={'project.custom-field', 'tool.myapp'}
)
```

## When to Use

✅ **Use config_comparison when:**
- Updating existing projects to modern standards
- Checking if project configs are up-to-date
- Before submitting PRs (ensure config consistency)
- Auditing multiple projects for compliance

✅ **Use populate with comparison when:**
- Setting up new projects (automatic checks)
- Migrating old projects (`--migrate` flag)
- Synchronizing with latest templates
- Adding missing config files

## Examples

See [`examples/config_comparison_demo.py`](config_comparison_demo.py) for complete working examples.

## Related

- **Migration tools**: [`wads.migration`](../MIGRATION.md) - For converting setup.cfg → pyproject.toml
- **CI comparison**: [`wads.ci_migration`](CI_MIGRATION_README.md) - For CI-specific analysis
- **Populate**: [`wads.populate`](../README.md#populate) - Project scaffolding with checks
