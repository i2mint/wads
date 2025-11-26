# Wads Setup Utilities Guide

This guide covers the setup utilities that help you install and manage dependencies based on your `pyproject.toml` configuration.

## Table of Contents

- [Overview](#overview)
- [Installation](#installation)
- [Python Dependency Management](#python-dependency-management)
- [System Dependency Management](#system-dependency-management)
- [Environment Variable Management](#environment-variable-management)
- [Diagnostic Tools](#diagnostic-tools)
- [Migration Tools](#migration-tools)
- [API Reference](#api-reference)

---

## Overview

The `wads.setup_utils` module provides command-line tools and Python APIs for:

1. **Installing Python dependencies** from `pyproject.toml` with flexible options
2. **Installing system dependencies** based on platform-specific commands in `[external]`
3. **Validating environment variables** required by your project
4. **Diagnosing** missing dependencies and configuration issues
5. **Migrating** from legacy formats to PEP 725/804

---

## Installation

The setup utils are included with wads. Ensure you have the required dependencies:

```bash
# For Python < 3.11
pip install tomli

# For writing TOML (migration tools)
pip install tomli_w
```

---

## Python Dependency Management

### Basic Usage

Install all Python dependencies from `pyproject.toml`:

```bash
python -m wads.setup_utils install-python /path/to/project
```

### Options

**Check if importable before installing** (default: enabled):
```bash
python -m wads.setup_utils install-python /path/to/project
# Only installs packages that aren't already importable
```

**Force installation (skip check)**:
```bash
python -m wads.setup_utils install-python /path/to/project --no-check
```

**Exclude specific packages**:
```bash
python -m wads.setup_utils install-python /path/to/project --exclude numpy pandas
```

**Upgrade existing packages**:
```bash
python -m wads.setup_utils install-python /path/to/project --upgrade
```

**Allow downgrades** (adds `--force-reinstall`):
```bash
python -m wads.setup_utils install-python /path/to/project --allow-downgrade
```

**Install extras**:
```bash
python -m wads.setup_utils install-python /path/to/project --extras dev test
```

**Dry run** (show what would be installed):
```bash
python -m wads.setup_utils install-python /path/to/project --dry-run
```

### Python API

```python
from wads.setup_utils import install_python_dependencies

results = install_python_dependencies(
    '/path/to/project',
    exclude=['numpy'],
    check_importable=True,
    upgrade=False,
    allow_downgrade=False,
    extras=['dev', 'test'],
    dry_run=False,
    verbose=True
)

for result in results:
    if result.success:
        print(f"✓ {result.package_name}: {result.message}")
    else:
        print(f"✗ {result.package_name}: {result.message}")
```

---

## System Dependency Management

### Basic Usage

Install system dependencies based on `[external]` and `[tool.wads.external.ops]`:

```bash
python -m wads.setup_utils install-system /path/to/project
```

This will:
1. Detect your platform (linux, macos, windows)
2. Check if dependencies are already installed (using `check` commands)
3. Prompt for confirmation before installing
4. Execute platform-specific install commands

### Options

**Specify platform** (overrides auto-detection):
```bash
python -m wads.setup_utils install-system /path/to/project --platform linux
```

**Skip existing installation check**:
```bash
python -m wads.setup_utils install-system /path/to/project --no-check
```

**Non-interactive mode** (no confirmation prompts):
```bash
python -m wads.setup_utils install-system /path/to/project --non-interactive
```

**Dry run**:
```bash
python -m wads.setup_utils install-system /path/to/project --dry-run
```

### Example Output

```
Platform: linux

======================================================================
Dependency: unixodbc
DepURL: dep:generic/unixodbc
Purpose: ODBC driver interface for database connectivity
Info: https://www.unixodbc.org/
  Checking with: dpkg -s unixodbc
✓ unixodbc is already installed

======================================================================
Dependency: git
DepURL: dep:generic/git
Purpose: Distributed version control system
Info: https://git-scm.com/

Install commands:
  1. sudo apt-get install -y git

Install git? [Y/n] y
Executing: sudo apt-get install -y git
✓ git installed successfully
```

### Python API

```python
from wads.setup_utils import install_system_dependencies

results = install_system_dependencies(
    '/path/to/project',
    platform='linux',  # or None for auto-detect
    check_first=True,
    dry_run=False,
    verbose=True,
    interactive=True
)

for result in results:
    print(f"{result.package_name}: {result.message}")
    if result.command_executed:
        print(f"  Command: {result.command_executed}")
```

---

## Environment Variable Management

### Check Required Variables

Check if all required environment variables (from `[tool.wads.ci.env.required]`) are set:

```bash
python -m wads.setup_utils check-env /path/to/project
```

**Example Output:**
```
Checking required environment variables:
  ✓ DATABASE_URL is set
  ✗ API_KEY is NOT set
    Default value available: your-api-key-here

❌ 1 environment variable(s) missing
```

### Python API

```python
from wads.setup_utils import check_environment_variables

results = check_environment_variables('/path/to/project', verbose=True)

# Returns dict: {var_name: value_or_none}
for var_name, value in results.items():
    if value is None:
        print(f"Missing: {var_name}")
        # Set it
        import os
        os.environ[var_name] = input(f"Enter value for {var_name}: ")
```

---

## Diagnostic Tools

### Comprehensive Diagnosis

Run a full diagnostic to check Python deps, system deps, and env vars:

```bash
python -m wads.setup_utils diagnose /path/to/project
```

### Example Output

```
======================================================================
DEPENDENCY DIAGNOSTIC REPORT
======================================================================

✓ All Python dependencies satisfied

❌ Missing System Dependencies:

  • ffmpeg
    DepURL: dep:generic/ffmpeg
    Purpose: Multimedia framework for audio and video processing
    Info: https://ffmpeg.org/
    Install: sudo apt-get install -y ffmpeg

  • unixodbc
    DepURL: dep:generic/unixodbc
    Purpose: ODBC driver interface for database connectivity
    Info: https://www.unixodbc.org/
    Install:
      sudo apt-get update
      sudo apt-get install -y unixodbc unixodbc-dev
    Alternatives: iodbc

❌ Missing Environment Variables:
  • API_KEY
  • DATABASE_URL

⚠️  Warnings:
  • Cannot verify if git is installed (no check command for linux)

📋 Recommendations:

1. Install system dependencies:
  python -m wads.setup_utils install-system /path/to/project

2.   Or manually for ffmpeg:
    sudo apt-get install -y ffmpeg

3. Set required environment variables:
  export API_KEY=<value>
  export DATABASE_URL=<value>

======================================================================
```

### Python API

```python
from wads.setup_utils import diagnose_setup, print_diagnostic_report

result = diagnose_setup(
    '/path/to/project',
    check_python=True,
    check_system=True,
    check_env=True,
    platform=None  # auto-detect
)

print_diagnostic_report(result)

# Access results programmatically
if result.missing_python_deps:
    print(f"Missing: {', '.join(result.missing_python_deps)}")

for dep in result.missing_system_deps:
    print(f"Need to install: {dep['name']}")
    print(f"  Command: {dep['install_command']}")
```

---

## Migration Tools

### Analyze Migration Status

Check if your project needs to be migrated to PEP 725 format:

```bash
python -m wads.external_deps_migration analyze /path/to/project
```

**Example Output:**
```
Legacy system_dependencies: True
Legacy env.install: False
Has [external]: False
Has [tool.wads.external.ops]: False
Can auto-migrate: True

Recommendations:
  - Migrate [tool.wads.ci.testing.system_dependencies] to [external] with DepURLs
```

### Generate Migration Instructions

Get detailed step-by-step instructions:

```bash
python -m wads.external_deps_migration instructions /path/to/project
```

### Preview Migration

See what the migrated TOML would look like:

```bash
python -m wads.external_deps_migration preview /path/to/project
```

**Example Output:**
```toml
# ============================================================================
# EXTERNAL DEPENDENCIES (PEP 725)
# ============================================================================
# Migrated from [tool.wads.ci.testing.system_dependencies]

[external]
# Runtime dependencies
dependencies = [
    "dep:generic/ffmpeg",
    "dep:generic/libsndfile",
]

# ============================================================================
# WADS EXTERNAL OPERATIONS
# ============================================================================

[tool.wads.external.ops.ffmpeg]
canonical_id = "dep:generic/ffmpeg"
rationale = "Multimedia framework for audio and video processing"
url = "https://ffmpeg.org/"
install.linux = "sudo apt-get install -y ffmpeg"
install.macos = "brew install ffmpeg"
install.windows = "choco install ffmpeg"

[tool.wads.external.ops.libsndfile]
canonical_id = "dep:generic/libsndfile"
rationale = "Library for reading and writing audio files"
url = "http://www.mega-nerd.com/libsndfile/"
install.linux = "sudo apt-get install -y libsndfile1"
install.macos = "brew install libsndfile"
```

### Apply Automatic Migration

Automatically migrate your `pyproject.toml`:

```bash
python -m wads.external_deps_migration apply /path/to/project
```

**Options:**

```bash
# Dry run (show what would be done)
python -m wads.external_deps_migration apply /path/to/project --dry-run

# Skip backup creation
python -m wads.external_deps_migration apply /path/to/project --no-backup
```

### Migration Python API

```python
from wads.external_deps_migration import (
    analyze_migration_needed,
    generate_migration_instructions,
    apply_migration
)

# Analyze
analysis = analyze_migration_needed('/path/to/project')

if analysis.can_auto_migrate:
    print("Can auto-migrate!")
    print(f"Will migrate: {', '.join(analysis.legacy_packages)}")

    # Apply migration
    success = apply_migration(
        '/path/to/project',
        backup=True,
        dry_run=False
    )
else:
    # Get manual instructions
    instructions = generate_migration_instructions(analysis)
    print(instructions)
```

---

## API Reference

### Core Functions

#### `install_python_dependencies()`

```python
def install_python_dependencies(
    pyproject_path: str | Path,
    exclude: Optional[List[str]] = None,
    check_importable: bool = True,
    upgrade: bool = False,
    allow_downgrade: bool = False,
    extras: Optional[List[str]] = None,
    dry_run: bool = False,
    verbose: bool = True
) -> List[InstallResult]:
    """
    Install Python dependencies from pyproject.toml.

    Returns:
        List of InstallResult(success, package_name, message, command_executed)
    """
```

#### `install_system_dependencies()`

```python
def install_system_dependencies(
    pyproject_path: str | Path,
    platform: Optional[str] = None,
    check_first: bool = True,
    dry_run: bool = False,
    verbose: bool = True,
    interactive: bool = True
) -> List[InstallResult]:
    """
    Install system dependencies based on pyproject.toml configuration.

    Returns:
        List of InstallResult objects
    """
```

#### `check_environment_variables()`

```python
def check_environment_variables(
    pyproject_path: str | Path,
    verbose: bool = True
) -> Dict[str, Optional[str]]:
    """
    Check required environment variables from pyproject.toml.

    Returns:
        Dict mapping variable names to their values (None if missing)
    """
```

#### `diagnose_setup()`

```python
def diagnose_setup(
    pyproject_path: str | Path,
    check_python: bool = True,
    check_system: bool = True,
    check_env: bool = True,
    platform: Optional[str] = None
) -> DiagnosticResult:
    """
    Diagnose missing dependencies and configuration issues.

    Returns:
        DiagnosticResult with:
            - missing_python_deps: List[str]
            - missing_system_deps: List[Dict]
            - missing_env_vars: List[str]
            - warnings: List[str]
            - recommendations: List[str]
    """
```

### Helper Functions

#### `is_package_importable()`

```python
def is_package_importable(package_name: str) -> bool:
    """Check if a Python package can be imported."""
```

#### `get_current_platform()`

```python
def get_current_platform() -> str:
    """
    Get current platform identifier (linux, macos, windows).
    """
```

#### `check_system_dependency()`

```python
def check_system_dependency(
    dep_name: str,
    dep_ops: Dict,
    platform: str,
    verbose: bool = True
) -> bool:
    """
    Check if a system dependency is installed using check commands.

    Returns:
        True if installed, False if not, None if cannot verify
    """
```

---

## Examples

### Complete Setup Script

Create a `setup.py` script for your project:

```python
#!/usr/bin/env python
"""Setup script for project dependencies."""

import sys
from pathlib import Path
from wads.setup_utils import (
    install_python_dependencies,
    install_system_dependencies,
    check_environment_variables,
    diagnose_setup,
    print_diagnostic_report
)

def main():
    project_dir = Path(__file__).parent

    print("="*70)
    print("PROJECT SETUP")
    print("="*70)

    # 1. Diagnose
    print("\n1. Running diagnostics...")
    result = diagnose_setup(project_dir)

    if not any([
        result.missing_python_deps,
        result.missing_system_deps,
        result.missing_env_vars
    ]):
        print("\n✓ All dependencies satisfied!")
        return 0

    print_diagnostic_report(result)

    # 2. Install system dependencies
    if result.missing_system_deps:
        response = input("\nInstall system dependencies? [y/N] ")
        if response.lower() == 'y':
            print("\n2. Installing system dependencies...")
            sys_results = install_system_dependencies(
                project_dir,
                interactive=True
            )

    # 3. Install Python dependencies
    if result.missing_python_deps:
        print("\n3. Installing Python dependencies...")
        py_results = install_python_dependencies(
            project_dir,
            check_importable=True
        )

    # 4. Check environment variables
    if result.missing_env_vars:
        print("\n4. Setting up environment variables...")
        env_results = check_environment_variables(project_dir)
        for var in result.missing_env_vars:
            value = input(f"Enter value for {var}: ")
            # Save to .env file or export
            with open(project_dir / '.env', 'a') as f:
                f.write(f"{var}={value}\n")

    print("\n✓ Setup complete!")
    return 0

if __name__ == '__main__':
    sys.exit(main())
```

### CI/CD Integration

Use in CI to ensure all dependencies are installed:

```yaml
# .github/workflows/ci.yml
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v6
        with:
          python-version: "3.11"

      - name: Install wads
        run: pip install wads

      - name: Diagnose dependencies
        run: python -m wads.setup_utils diagnose .

      - name: Install system dependencies
        run: python -m wads.setup_utils install-system . --non-interactive

      - name: Install Python dependencies
        run: python -m wads.setup_utils install-python .

      - name: Run tests
        run: pytest
```

---

## Troubleshooting

### Issue: "tomli package required"

**Solution:**
```bash
pip install tomli  # For Python < 3.11
```

### Issue: "Cannot write TOML (migration)"

**Solution:**
```bash
pip install tomli_w
```

### Issue: "Permission denied" during system install

**Solution:**
- Ensure install commands include `sudo` for Linux
- Run with appropriate permissions
- Or use `--dry-run` to see commands and run manually

### Issue: Package not recognized

If a package isn't in the common mappings:

1. Manually add DepURL mapping
2. Add to `[tool.wads.external.ops]` with install commands
3. Or contribute to `COMMON_PACKAGE_DEPURLS` in `external_deps_migration.py`

---

## Best Practices

1. **Always run diagnostics first**: Use `diagnose` to understand what's needed
2. **Use dry-run for testing**: Test with `--dry-run` before actual installation
3. **Create backups**: Especially when using migration tools
4. **Platform-specific testing**: Test system installs on target platforms
5. **Environment variables**: Use `.env` files for local development
6. **CI integration**: Add setup checks to CI pipelines

---

**Last Updated:** 2025-01-25
**Wads Version:** 0.1.56+
