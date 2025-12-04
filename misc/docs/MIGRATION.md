# Migration Guide

This guide walks you through migrating legacy Python projects to modern formats using wads.

## Overview

Wads provides tools to migrate:
1. **setup.cfg → pyproject.toml** (modern build configuration)
2. **Old CI workflows → Modern GitHub Actions** (updated actions, ruff linting)
3. **MANIFEST.in → Hatchling config** (declarative package data)

## Quick Start

```bash
# Install wads
pip install wads

# Migrate setup.cfg to pyproject.toml
wads-migrate setup-to-pyproject setup.cfg -o pyproject.toml

# Migrate CI workflow
wads-migrate ci-old-to-new .github/workflows/ci.yml -o .github/workflows/ci-new.yml
```

## Why Migrate?

### Benefits of pyproject.toml

- **Single source of truth:** All configuration in one file
- **Modern build backends:** Hatchling, Flit, PDM (faster than setuptools)
- **Better tooling support:** Modern tools read pyproject.toml
- **PEP 517/518 compliant:** Future-proof build system

### Benefits of Modern CI

- **Faster builds:** Updated actions, better caching
- **Modern linting:** Ruff is 10-100x faster than pylint/flake8
- **Composite actions:** Reusable, tested workflow components
- **Configuration-driven:** CI behavior controlled by pyproject.toml

## Migration Walkthrough

### Step 1: Backup Your Project

```bash
# Create a git branch
git checkout -b migrate-to-modern-format

# Or backup files
cp setup.cfg setup.cfg.backup
cp .github/workflows/ci.yml .github/workflows/ci.yml.backup
```

### Step 2: Migrate setup.cfg

#### Using CLI

```bash
wads-migrate setup-to-pyproject setup.cfg -o pyproject.toml
```

#### Using Python

```python
from wads.migration import migrate_setuptools_to_hatching

# From file
pyproject_content = migrate_setuptools_to_hatching('setup.cfg')

# Write to file
with open('pyproject.toml', 'w') as f:
    f.write(pyproject_content)
```

#### What Gets Migrated

**Metadata:**
- `name`, `version`, `description`
- `author`, `author_email`
- `url` → `project.urls.Homepage`
- `license`
- `keywords`, `classifiers`
- `python_requires`

**Dependencies:**
- `install_requires` → `project.dependencies`
- `extras_require` → `project.optional-dependencies`

**Entry Points:**
- `console_scripts` → `project.scripts`
- `gui_scripts` → `project.gui-scripts`

**Package Discovery:**
- `packages` → `tool.hatch.build.targets.wheel.packages`
- `py_modules` → Hatchling auto-discovery

#### Example

**Before (setup.cfg):**
```ini
[metadata]
name = mypackage
version = 1.2.3
description = My awesome package
author = John Doe
author_email = john@example.com
url = https://github.com/john/mypackage
license = MIT
keywords = python, tools
classifiers =
    Programming Language :: Python :: 3
    License :: OSI Approved :: MIT License

[options]
packages = find:
python_requires = >=3.8
install_requires =
    requests>=2.28.0
    click>=8.0

[options.extras_require]
dev =
    pytest>=7.0
    ruff>=0.1.0

[options.entry_points]
console_scripts =
    mytool = mypackage.cli:main
```

**After (pyproject.toml):**
```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "mypackage"
version = "1.2.3"
description = "My awesome package"
readme = "README.md"
requires-python = ">=3.8"
license = {text = "MIT"}
keywords = ["python", "tools"]
authors = [
    {name = "John Doe", email = "john@example.com"}
]
dependencies = [
    "requests>=2.28.0",
    "click>=8.0",
]

[project.urls]
Homepage = "https://github.com/john/mypackage"

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "ruff>=0.1.0",
]

[project.scripts]
mytool = "mypackage.cli:main"

[tool.hatch.build.targets.wheel]
packages = ["mypackage"]
```

### Step 3: Migrate MANIFEST.in (if present)

Hatchling uses `tool.hatch.build` configuration instead of MANIFEST.in.

#### Common Patterns

**Include package data:**
```toml
[tool.hatch.build.targets.wheel]
include = [
    "mypackage/data/*.json",
    "mypackage/templates/**/*",
]
```

**Exclude files:**
```toml
[tool.hatch.build.targets.wheel]
exclude = [
    "tests/",
    "*.pyc",
    "__pycache__/",
]
```

**Include non-Python files:**
```toml
[tool.hatch.build.targets.wheel]
packages = ["mypackage"]
include = [
    "mypackage/static/**/*",
    "mypackage/data/*.csv",
]
```

### Step 4: Update CI Workflow

```bash
wads-migrate ci-old-to-new .github/workflows/ci.yml -o .github/workflows/ci-new.yml
```

#### What Gets Updated

**Action Versions:**
- `actions/checkout@v2` → `@v4`
- `actions/setup-python@v2` → `@v6`
- `actions/cache@v2` → `@v3`

**Linting/Formatting:**
- `pylint` → `ruff check`
- `black` → `ruff format`
- `flake8` → `ruff check`

**Workflow Structure:**
- Adds configuration-reading step
- Uses composite actions for common tasks
- Supports system dependencies

#### Example

**Before (old CI):**
```yaml
name: CI
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: 3.9

      - name: Install dependencies
        run: |
          pip install -e .
          pip install pytest pylint

      - name: Lint
        run: pylint mypackage

      - name: Test
        run: pytest
```

**After (modern CI):**
```yaml
name: Continuous Integration
on: [push, pull_request]

jobs:
  setup:
    runs-on: ubuntu-latest
    outputs:
      python-versions: ${{ steps.config.outputs.python-versions }}
      # ... other config outputs
    steps:
      - uses: actions/checkout@v4
      - uses: i2mint/wads/actions/read-ci-config@master
        id: config

  validation:
    needs: setup
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ${{ fromJson(needs.setup.outputs.python-versions) }}

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v6
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install System Dependencies
        uses: i2mint/wads/actions/install-system-deps@master

      - uses: i2mint/wads/actions/install-deps@master
        with:
          dependency-files: pyproject.toml

      - uses: i2mint/wads/actions/ruff-lint@master

      - uses: i2mint/wads/actions/run-tests@master
```

### Step 5: Remove Legacy Files

After verifying everything works:

```bash
# Remove setup.cfg
git rm setup.cfg

# Remove setup.py if present and not needed
git rm setup.py

# Remove MANIFEST.in if migrated to Hatchling
git rm MANIFEST.in

# Remove old CI workflow
git rm .github/workflows/ci.yml

# Rename new CI workflow
git mv .github/workflows/ci-new.yml .github/workflows/ci.yml
```

### Step 6: Test Locally

```bash
# Install in development mode
pip install -e .

# Run tests
pytest

# Build package
python -m build

# Check distribution
twine check dist/*
```

### Step 7: Test CI

```bash
# Commit changes
git add pyproject.toml .github/workflows/ci.yml
git commit -m "Migrate to pyproject.toml and modern CI"

# Push to trigger CI
git push origin migrate-to-modern-format
```

Monitor the CI run to ensure everything works.

### Step 8: Merge and Clean Up

```bash
# Create pull request and merge
gh pr create --title "Migrate to modern build system"

# After merge, delete backup files
rm setup.cfg.backup
rm .github/workflows/ci.yml.backup
```

## Common Migration Scenarios

### Scenario 1: Simple Package

**Original:**
- setup.cfg with basic metadata
- No entry points
- No package data

**Steps:**
1. Run `wads-migrate setup-to-pyproject setup.cfg`
2. Review and commit pyproject.toml
3. Remove setup.cfg
4. Test build

**Time:** ~5 minutes

### Scenario 2: Package with CLI Tools

**Original:**
- setup.cfg with console_scripts
- Multiple entry points

**Steps:**
1. Run migration
2. Verify entry points in `[project.scripts]`
3. Test CLI tools after install
4. Commit changes

**Time:** ~10 minutes

### Scenario 3: Package with Data Files

**Original:**
- MANIFEST.in with data file includes
- setup.cfg with package_data

**Steps:**
1. Run migration
2. Manually add `[tool.hatch.build.targets.wheel]` includes
3. Test package installation
4. Verify data files are included in wheel

**Time:** ~15 minutes

### Scenario 4: Complex Multi-Package Project

**Original:**
- Multiple packages
- Namespace packages
- Complex MANIFEST.in
- Old CI with custom steps

**Steps:**
1. Run migration
2. Manually configure `packages` in Hatchling
3. Migrate CI workflow
4. Add custom CI steps to `[tool.wads.ci.commands]`
5. Thorough testing

**Time:** ~1-2 hours

## Migration Checklist

- [ ] Backup original files (setup.cfg, CI workflows)
- [ ] Run `wads-migrate setup-to-pyproject`
- [ ] Review generated pyproject.toml
- [ ] Migrate MANIFEST.in → Hatchling config (if needed)
- [ ] Run `wads-migrate ci-old-to-new`
- [ ] Add system dependencies to `[tool.wads.ops.*]` (if needed)
- [ ] Test local installation (`pip install -e .`)
- [ ] Test building (`python -m build`)
- [ ] Test CLI tools (if any)
- [ ] Push and verify CI passes
- [ ] Remove legacy files
- [ ] Update documentation to reference pyproject.toml

## Troubleshooting

### "No module named 'hatchling'"

**Issue:** Build backend not installed.

**Solution:**
```bash
pip install hatchling
```

### Build fails with "No such file or directory"

**Issue:** Package data not included.

**Solution:** Add to pyproject.toml:
```toml
[tool.hatch.build.targets.wheel]
include = [
    "mypackage/data/**/*",
]
```

### Entry points don't work

**Issue:** Scripts not in correct format.

**Solution:** Check `[project.scripts]` syntax:
```toml
[project.scripts]
mytool = "mypackage.cli:main"  # package.module:function
```

### CI fails after migration

**Issue:** Missing dependencies or configuration.

**Solution:**
1. Check CI logs for specific errors
2. Add missing dependencies to pyproject.toml
3. Add system dependencies to `[tool.wads.ops.*]`
4. Use `wads-ci-debug` to diagnose

### Version conflicts

**Issue:** Version specified in multiple places.

**Solution:** Use single-source versioning:
```toml
[project]
version = "1.2.3"  # Or use dynamic versioning
```

## Advanced Topics

### Dynamic Versioning

Let Hatchling read version from your package:

```toml
[project]
dynamic = ["version"]

[tool.hatch.version]
path = "mypackage/__init__.py"
```

In `mypackage/__init__.py`:
```python
__version__ = "1.2.3"
```

### Custom Build Steps

Add build hooks:

```toml
[tool.hatch.build.hooks.custom]
path = "build_hook.py"
```

### Namespace Packages

Configure namespace packages:

```toml
[tool.hatch.build.targets.wheel]
packages = ["src/myns/mypackage"]
```

## See Also

- [Hatchling Documentation](https://hatch.pypa.io/latest/config/build/)
- [PEP 517](https://peps.python.org/pep-0517/) - Build system interface
- [PEP 518](https://peps.python.org/pep-0518/) - pyproject.toml specification
- [Utilities Reference](UTILITIES.md) - wads-migrate CLI documentation
- [System Dependencies Guide](SYSTEM_DEPENDENCIES.md) - Modern system dependency management
