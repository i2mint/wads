# System Dependencies - Actual Working Implementation

This document explains the **actual** system dependencies implementation in wads, as opposed to the PEP 725 implementation that was created but not integrated.

## Summary

**Format:** `[tool.wads.ops.{name}]` in pyproject.toml
**Integration:** New composite action `install-system-deps` that reads pyproject.toml
**Status:** ✅ Fully integrated into CI workflow templates

---

## How It Works

### 1. Declare Dependencies in pyproject.toml

```toml
[tool.wads.ops.unixodbc]
description = "ODBC driver interface for database connectivity"
url = "https://www.unixodbc.org/"

# Check if installed (exit code 0 = present)
check.linux = "dpkg -s unixodbc || rpm -q unixODBC"
check.macos = "brew list unixodbc"

# Install commands (string or list of strings)
install.linux = [
    "sudo apt-get update",
    "sudo apt-get install -y unixodbc unixodbc-dev"
]
install.macos = "brew install unixodbc"

note = "On Alpine: apk add unixodbc unixodbc-dev"
alternatives = ["iodbc"]
```

### 2. CI Workflow Automatically Installs

The CI workflow template (`github_ci_publish_2025.yml`) now includes:

```yaml
- name: Install System Dependencies
  uses: i2mint/wads/actions/install-system-deps@master
  with:
    pyproject-path: .
```

This step:
1. Reads `[tool.wads.ops.*]` sections from pyproject.toml
2. Detects the platform (linux, macos, windows)
3. Checks if dependencies are already installed (using `check` commands)
4. Installs missing dependencies (using `install` commands)

---

## File Structure

### Core Implementation

**Composite Action:**
- `/Users/thorwhalen/Dropbox/py/proj/i/wads/actions/install-system-deps/action.yml`
  - Python script that reads pyproject.toml
  - Parses `[tool.wads.ops.*]` sections
  - Executes platform-specific check/install commands

**CI Workflow Template:**
- `/Users/thorwhalen/Dropbox/py/proj/i/wads/wads/data/github_ci_publish_2025.yml`
  - Updated to call `install-system-deps` action
  - Added to both `validation` and `windows-validation` jobs

**Pyproject Template:**
- `/Users/thorwhalen/Dropbox/py/proj/i/wads/wads/data/pyproject_toml_tpl.toml`
  - Includes example `[tool.wads.ops]` section (commented out)
  - References `wads_operational_dependencies_example.yml` for documentation

**Documentation:**
- `/Users/thorwhalen/Dropbox/py/proj/i/wads/wads/data/wads_operational_dependencies_example.yml`
  - Comprehensive examples of different dependency types
  - Explains check/install command formats
  - Platform-specific patterns

---

## Supported Formats

### Check Commands

**Purpose:** Verify if dependency is already installed (avoids unnecessary reinstalls)

**Formats:**
1. **Simple string:** `"which ffmpeg"`
2. **Shell OR logic:** `"dpkg -s ffmpeg || rpm -q ffmpeg"` (tries until one succeeds)
3. **List of alternatives:** `["dpkg -s ffmpeg", "rpm -q ffmpeg"]` (tries each)
4. **Empty/skip:** `""` or `[]` (means "don't check")

**Examples:**
```toml
# Executable check (works on any distro)
check.linux = "which ffmpeg"

# Package manager check (tries multiple)
check.linux = "dpkg -s unixodbc || rpm -q unixODBC || pacman -Q unixodbc"

# List format (equivalent)
check.linux = ["dpkg -s unixodbc", "rpm -q unixODBC", "pacman -Q unixodbc"]

# Homebrew check
check.macos = "brew list ffmpeg"

# Skip check
check.windows = ""
```

### Install Commands

**Purpose:** Commands to install the dependency

**Formats:**
1. **Simple string:** `"brew install ffmpeg"` (single command)
2. **List of strings:** `["cmd1", "cmd2"]` (executed in order, AND logic)
3. **Empty/manual:** `""` or `[]` (skip automated install)

**Examples:**
```toml
# Multi-step installation
install.linux = [
    "sudo apt-get update",
    "sudo apt-get install -y ffmpeg libavcodec-dev"
]

# Single command
install.macos = "brew install ffmpeg"

# Chocolatey on Windows
install.windows = "choco install ffmpeg -y"

# Manual install required
install.windows = ""
```

---

## Real-World Example: odbcdol

### pyproject.toml

```toml
[tool.wads.ops.unixodbc]
canonical_id = "dep:generic/unixodbc"
rationale = "ODBC driver interface for database connectivity"
url = "https://www.unixodbc.org/"

check.linux = [["dpkg", "-s", "unixodbc"], ["rpm", "-q", "unixODBC"]]
check.macos = ["brew", "list", "unixodbc"]

install.linux = [
    "sudo apt-get update",
    "sudo apt-get install -y unixodbc unixodbc-dev"
]
install.macos = "brew install unixodbc"

note = "On Alpine, use: apk add unixodbc unixodbc-dev"
alternatives = ["iodbc"]

[tool.wads.ops.msodbcsql18]
canonical_id = "dep:generic/msodbcsql18"
rationale = "Microsoft ODBC Driver 18 for SQL Server"
url = "https://docs.microsoft.com/sql/connect/odbc/"

install.linux = [
    "curl https://packages.microsoft.com/keys/microsoft.asc | sudo apt-key add -",
    "curl https://packages.microsoft.com/config/ubuntu/$(lsb_release -rs)/prod.list | sudo tee /etc/apt/sources.list.d/mssql-release.list",
    "sudo apt-get update",
    "sudo ACCEPT_EULA=Y apt-get install -y msodbcsql18"
]

note = "Requires accepting Microsoft EULA"
```

### .github/workflows/ci.yml

```yaml
validation:
  steps:
    - uses: actions/checkout@v4

    - name: Set up Python ${{ matrix.python-version }}
      uses: actions/setup-python@v6
      with:
        python-version: ${{ matrix.python-version }}

    - name: Install System Dependencies  # ← NEW STEP
      uses: i2mint/wads/actions/install-system-deps@master
      with:
        pyproject-path: .

    - name: Install Dependencies
      uses: i2mint/wads/actions/install-deps@master
      with:
        dependency-files: pyproject.toml
        extras: dev,test
```

### CI Output

```
::group::Installing system dependencies for linux
Reading from: /home/runner/work/odbcdol/odbcdol/pyproject.toml
Found 2 system dependencies

======================================================================
Dependency: unixodbc
Description: ODBC driver interface for database connectivity
URL: https://www.unixodbc.org/

Installing unixodbc...
  Step 1/2: sudo apt-get update
  Step 2/2: sudo apt-get install -y unixodbc unixodbc-dev
✓ unixodbc installed successfully
Note: On Alpine, use: apk add unixodbc unixodbc-dev

======================================================================
Dependency: msodbcsql18
Description: Microsoft ODBC Driver 18 for SQL Server
URL: https://docs.microsoft.com/sql/connect/odbc/

Installing msodbcsql18...
  Step 1/4: curl https://packages.microsoft.com/keys/microsoft.asc | sudo apt-key add -
  Step 2/4: curl https://packages.microsoft.com/config/ubuntu/$(lsb_release -rs)/prod.list | sudo tee /etc/apt/sources.list.d/mssql-release.list
  Step 3/4: sudo apt-get update
  Step 4/4: sudo ACCEPT_EULA=Y apt-get install -y msodbcsql18
✓ msodbcsql18 installed successfully
Note: Requires accepting Microsoft EULA

======================================================================
SUMMARY
======================================================================
✓ Installed: 2
⊘ Already present: 0
::endgroup::
```

---

## Common Dependency Patterns

### Executable/Tool (e.g., git, ffmpeg)

```toml
[tool.wads.ops.ffmpeg]
description = "Multimedia framework for video/audio processing"
url = "https://ffmpeg.org/"

# Simple executable check
check.linux = "which ffmpeg"
check.macos = "which ffmpeg"
check.windows = "where ffmpeg"

install.linux = "sudo apt-get install -y ffmpeg"
install.macos = "brew install ffmpeg"
install.windows = "choco install ffmpeg -y"
```

### Library (e.g., libsndfile, unixodbc)

```toml
[tool.wads.ops.unixodbc]
description = "ODBC driver manager"
url = "https://www.unixodbc.org/"

# Libraries don't have executables, check package manager
check.linux = "dpkg -s unixodbc-dev || rpm -q unixODBC-devel"
check.macos = "brew list unixodbc"

# Install both runtime and development packages
install.linux = "sudo apt-get install -y unixodbc unixodbc-dev"
install.macos = "brew install unixodbc"
```

### Virtual Dependency (e.g., C compiler)

```toml
[tool.wads.ops.c-compiler]
description = "C compiler for building native extensions"

# Check for any common C compiler
check.linux = "which gcc || which clang"
check.macos = "which clang || which gcc"

# Install platform's default
install.linux = "sudo apt-get install -y build-essential"
install.macos = "xcode-select --install"
```

### Complex Multi-Step (e.g., Microsoft ODBC Driver)

```toml
[tool.wads.ops.msodbcsql18]
description = "Microsoft ODBC Driver 18 for SQL Server"

check.linux = "dpkg -s msodbcsql18"

install.linux = [
    "curl https://packages.microsoft.com/keys/microsoft.asc | sudo apt-key add -",
    "curl https://packages.microsoft.com/config/ubuntu/$(lsb_release -rs)/prod.list | sudo tee /etc/apt/sources.list.d/mssql-release.list",
    "sudo apt-get update",
    "sudo ACCEPT_EULA=Y apt-get install -y msodbcsql18"
]

note = "Requires accepting Microsoft EULA"
```

---

## Platform Detection

The action automatically detects the platform:

- **Linux:** `platform_module.system().lower() == 'linux'` → uses `.linux` commands
- **macOS:** `platform_module.system().lower() == 'darwin'` → uses `.macos` commands
- **Windows:** `platform_module.system().lower() == 'windows'` → uses `.windows` commands

You can override with the `platform` input:

```yaml
- name: Install System Dependencies
  uses: i2mint/wads/actions/install-system-deps@master
  with:
    pyproject-path: .
    platform: linux  # Override auto-detection
```

---

## Command Execution Details

### Check Commands

- Executed with `subprocess.run(shell=True, capture_output=True, timeout=10)`
- Exit code 0 = dependency is present → skip install
- Non-zero exit = dependency missing → proceed to install
- Multiple check commands try in order until one succeeds (OR logic)

### Install Commands

- Executed with `subprocess.run(shell=True, capture_output=False, timeout=300)`
- Output shown in real-time
- Executed in sequence (list = AND logic)
- If any command fails (non-zero exit), entire install fails

### Error Handling

- Check command failures are ignored (assumed not installed)
- Install command failures:
  - Print error message
  - Increment failed count
  - Continue to next dependency
  - Exit with code 1 at end if any failures

---

## Optional Features

### Skip Checks

Skip the check step and always install:

```yaml
- name: Install System Dependencies
  uses: i2mint/wads/actions/install-system-deps@master
  with:
    pyproject-path: .
    skip-check: true
```

### Custom pyproject.toml Path

```yaml
- name: Install System Dependencies
  uses: i2mint/wads/actions/install-system-deps@master
  with:
    pyproject-path: custom/path/pyproject.toml
```

---

## Migration from Old Formats

### Old: Hardcoded in CI Workflow

**Before:**
```yaml
- name: Install System Dependencies
  run: |
    sudo apt-get update
    sudo apt-get install -y unixodbc-dev
    curl https://...microsoft.asc | sudo apt-key add -
    sudo ACCEPT_EULA=Y apt-get install -y msodbcsql18
```

**After:**
```toml
# In pyproject.toml
[tool.wads.ops.unixodbc]
install.linux = ["sudo apt-get update", "sudo apt-get install -y unixodbc-dev"]

[tool.wads.ops.msodbcsql18]
install.linux = [
    "curl https://...microsoft.asc | sudo apt-key add -",
    "sudo ACCEPT_EULA=Y apt-get install -y msodbcsql18"
]
```

```yaml
# In CI workflow
- name: Install System Dependencies
  uses: i2mint/wads/actions/install-system-deps@master
  with:
    pyproject-path: .
```

---

## Benefits

1. **Declarative:** Dependencies declared in pyproject.toml alongside Python deps
2. **Cross-Platform:** Single source with platform-specific commands
3. **Self-Documenting:** Description, URL, notes explain WHY dependencies exist
4. **Verifiable:** Check commands avoid unnecessary reinstalls
5. **Maintainable:** Change in pyproject.toml, not scattered CI files
6. **Portable:** Works across different projects with same pattern

---

## Testing

To test locally before pushing:

```bash
# Test that pyproject.toml parsing works
python3 - <<'EOF'
import tomllib
with open('pyproject.toml', 'rb') as f:
    data = tomllib.load(f)
ops = data.get('tool', {}).get('wads', {}).get('ops', {})
for name, config in ops.items():
    print(f"{name}: {config.get('description', 'No description')}")
EOF

# Manually test install commands
sudo apt-get update
sudo apt-get install -y unixodbc unixodbc-dev
```

---

## Future Enhancements

Potential improvements:

1. **Caching:** Cache check results to avoid redundant checks
2. **Dry Run:** Show what would be installed without executing
3. **Verbose Mode:** More detailed logging
4. **Failure Modes:** Continue-on-error vs fail-fast options
5. **Dependency Ordering:** Explicit dependency between system packages
6. **Alternative Package Managers:** Support for more platforms (Alpine apk, Arch pacman, etc.)

---

## Summary

**What works:**
- ✅ `[tool.wads.ops.{name}]` sections in pyproject.toml
- ✅ `install-system-deps` composite action
- ✅ Integrated into CI workflow template
- ✅ Automatic platform detection
- ✅ Check-before-install logic
- ✅ Multi-step install commands
- ✅ Detailed logging and error reporting

**What doesn't work (yet):**
- ❌ `generate_pre_test_steps()` in ci_config.py (not called)
- ❌ Automatic CI workflow generation from pyproject.toml deps

---

**Last Updated:** 2025-01-25
**Wads Version:** 0.1.56+
