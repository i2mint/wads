# System Dependencies Guide

This guide explains how to declare and manage system (OS-level) dependencies for your Python projects using wads.

## Overview

System dependencies are non-Python packages that your project needs to run, such as:
- **Libraries:** libffi, unixodbc, openssl
- **Tools:** ffmpeg, git, postgresql
- **Compilers:** gcc, clang
- **Drivers:** ODBC drivers, database clients

Wads provides a declarative way to specify these dependencies in `pyproject.toml` using the `[tool.wads.ops.*]` format. The `install-system-deps` GitHub Action automatically installs them in CI workflows.

## Quick Start

Add system dependencies to your `pyproject.toml`:

```toml
[tool.wads.ops.ffmpeg]
description = "Multimedia framework for video/audio processing"
url = "https://ffmpeg.org/"

check.linux = "which ffmpeg"
check.macos = "which ffmpeg"

install.linux = "sudo apt-get install -y ffmpeg"
install.macos = "brew install ffmpeg"
install.windows = "choco install ffmpeg -y"
```

The CI workflow template automatically includes:

```yaml
- name: Install System Dependencies
  uses: i2mint/wads/actions/install-system-deps@master
  with:
    pyproject-path: .
```

That's it! Dependencies are automatically installed before tests run.

## Format Specification

### Basic Structure

```toml
[tool.wads.ops.{dependency-name}]
description = "Human-readable description"
url = "https://homepage.com"           # Optional

# Platform-specific check commands
check.linux = "command to check if installed"
check.macos = "command to check if installed"
check.windows = "command to check if installed"

# Platform-specific install commands
install.linux = "command to install"
install.macos = "command to install"
install.windows = "command to install"

# Optional metadata
note = "Additional notes or platform-specific guidance"
alternatives = ["alternative1", "alternative2"]
```

### Field Descriptions

| Field | Required | Description |
|-------|----------|-------------|
| `description` | Recommended | What the dependency is and why it's needed |
| `url` | Optional | Homepage or documentation URL |
| `check.{platform}` | Optional | Command to verify if already installed (exit 0 = present) |
| `install.{platform}` | Required | Command(s) to install the dependency |
| `note` | Optional | Additional information (e.g., Alpine instructions) |
| `alternatives` | Optional | Alternative packages that provide similar functionality |

### Supported Platforms

- `linux` - Ubuntu, Debian, RHEL, CentOS, Fedora, etc.
- `macos` - macOS (using Homebrew)
- `windows` - Windows (using Chocolatey)

## Check Commands

Check commands verify if a dependency is already installed. They should exit with code 0 if present, non-zero otherwise.

### Single Command

```toml
check.linux = "which ffmpeg"
```

### Multiple Alternatives (OR logic)

Try commands in order until one succeeds:

```toml
# Shell OR syntax
check.linux = "dpkg -s unixodbc || rpm -q unixODBC || pacman -Q unixodbc"

# List syntax (equivalent)
check.linux = ["dpkg -s unixodbc", "rpm -q unixODBC", "pacman -Q unixodbc"]
```

### Skip Checking

If you can't reliably check for installation, use an empty string:

```toml
check.windows = ""  # Can't reliably check, always install
```

### Common Patterns

**Executable check (works across distros):**
```toml
check.linux = "which git"
check.macos = "which git"
check.windows = "where git"
```

**Package manager check:**
```toml
check.linux = "dpkg -s libffi-dev"       # Debian/Ubuntu
check.linux = "rpm -q libffi-devel"      # RHEL/Fedora
check.macos = "brew list libffi"         # Homebrew
```

## Install Commands

Install commands should install the dependency. They can be a single command or a list of commands.

### Single Command

```toml
install.macos = "brew install ffmpeg"
```

### Multiple Commands (AND logic)

Commands execute in order. If any fails, the entire install fails:

```toml
install.linux = [
    "sudo apt-get update",
    "sudo apt-get install -y ffmpeg libavcodec-dev"
]
```

### Platform-Specific Package Managers

**Linux (apt-get):**
```toml
install.linux = [
    "sudo apt-get update",
    "sudo apt-get install -y package-name"
]
```

**Linux (yum/dnf):**
```toml
install.linux = "sudo yum install -y package-name"
# or
install.linux = "sudo dnf install -y package-name"
```

**macOS (Homebrew):**
```toml
install.macos = "brew install package-name"
```

**Windows (Chocolatey):**
```toml
install.windows = "choco install package-name -y"
```

## Real-World Examples

### Example 1: Simple Tool (ffmpeg)

```toml
[tool.wads.ops.ffmpeg]
description = "Multimedia framework for video/audio processing"
url = "https://ffmpeg.org/"

check.linux = "which ffmpeg"
check.macos = "which ffmpeg"
check.windows = "where ffmpeg"

install.linux = "sudo apt-get install -y ffmpeg"
install.macos = "brew install ffmpeg"
install.windows = "choco install ffmpeg -y"

note = "Required for audio processing features"
```

### Example 2: Library with Development Headers (unixODBC)

```toml
[tool.wads.ops.unixodbc]
description = "ODBC driver interface for database connectivity"
url = "https://www.unixodbc.org/"

# Check across different distros
check.linux = "dpkg -s unixodbc || rpm -q unixODBC"
check.macos = "brew list unixodbc"

# Install runtime + development packages
install.linux = [
    "sudo apt-get update",
    "sudo apt-get install -y unixodbc unixodbc-dev"
]
install.macos = "brew install unixodbc"

note = "On Alpine: apk add unixodbc unixodbc-dev"
alternatives = ["iodbc"]
```

### Example 3: Complex Multi-Step (Microsoft ODBC Driver)

```toml
[tool.wads.ops.msodbcsql18]
description = "Microsoft ODBC Driver 18 for SQL Server"
url = "https://docs.microsoft.com/sql/connect/odbc/"

check.linux = "dpkg -s msodbcsql18"

install.linux = [
    "curl https://packages.microsoft.com/keys/microsoft.asc | sudo apt-key add -",
    "curl https://packages.microsoft.com/config/ubuntu/$(lsb_release -rs)/prod.list | sudo tee /etc/apt/sources.list.d/mssql-release.list",
    "sudo apt-get update",
    "sudo ACCEPT_EULA=Y apt-get install -y msodbcsql18"
]

note = "Requires accepting Microsoft EULA. Not available on macOS/Windows (use native drivers)."
```

### Example 4: Virtual Dependency (C Compiler)

```toml
[tool.wads.ops.c-compiler]
description = "C compiler for building native extensions"

# Accept any common C compiler
check.linux = "which gcc || which clang"
check.macos = "which clang || which gcc"

install.linux = "sudo apt-get install -y build-essential"
install.macos = "xcode-select --install"

note = "Required for packages with C extensions (e.g., numpy, psycopg2)"
```

### Example 5: Database Client (PostgreSQL)

```toml
[tool.wads.ops.postgresql-client]
description = "PostgreSQL client tools and libraries"
url = "https://www.postgresql.org/"

check.linux = "which psql"
check.macos = "brew list postgresql"

install.linux = "sudo apt-get install -y postgresql-client libpq-dev"
install.macos = "brew install postgresql"
install.windows = "choco install postgresql -y"
```

## CI Integration

The system dependencies are automatically installed in your GitHub Actions workflows.

### Workflow Configuration

The standard wads CI workflow template includes:

```yaml
validation:
  steps:
    - uses: actions/checkout@v4

    - name: Set up Python
      uses: actions/setup-python@v6
      with:
        python-version: ${{ matrix.python-version }}

    - name: Install System Dependencies
      uses: i2mint/wads/actions/install-system-deps@master
      with:
        pyproject-path: .

    - name: Install Dependencies
      uses: i2mint/wads/actions/install-deps@master
      with:
        dependency-files: pyproject.toml
```

### Action Inputs

The `install-system-deps` action accepts these inputs:

| Input | Default | Description |
|-------|---------|-------------|
| `pyproject-path` | `.` | Path to pyproject.toml or directory containing it |
| `platform` | auto-detected | Override platform detection (linux, macos, windows) |
| `skip-check` | `false` | Skip check commands, always install |

### Action Behavior

1. **Read Configuration:** Parses `[tool.wads.ops.*]` from pyproject.toml
2. **Detect Platform:** Automatically detects linux/macos/windows
3. **Check Each Dependency:** Runs `check.{platform}` commands
4. **Install Missing Dependencies:** Runs `install.{platform}` commands for dependencies not already present
5. **Report Results:** Prints summary with installed/skipped/failed counts

### Example Output

```
::group::Installing system dependencies for linux
Reading from: /home/runner/work/myrepo/myrepo/pyproject.toml
Found 2 system dependencies

======================================================================
Dependency: unixodbc
Description: ODBC driver interface for database connectivity
URL: https://www.unixodbc.org/

Installing unixodbc...
  Step 1/2: sudo apt-get update
  Step 2/2: sudo apt-get install -y unixodbc unixodbc-dev
✓ unixodbc installed successfully
Note: On Alpine: apk add unixodbc unixodbc-dev

======================================================================
Dependency: ffmpeg
Description: Multimedia framework
✓ ffmpeg is already installed

======================================================================
SUMMARY
======================================================================
✓ Installed: 1
⊘ Already present: 1
::endgroup::
```

## Platform-Specific Notes

### Linux

**Package Manager Detection:**
The action doesn't automatically detect your package manager. Use check commands with OR logic to support multiple distros:

```toml
check.linux = "dpkg -s package || rpm -q package || pacman -Q package"
```

**Alpine Linux:**
Since Alpine uses `apk` instead of `apt-get`, add a note:

```toml
install.linux = "sudo apt-get install -y package"
note = "On Alpine: apk add package"
```

### macOS

**Homebrew Required:**
All macOS installs assume Homebrew is available (standard on GitHub Actions macOS runners).

**Xcode Command Line Tools:**
Some packages require Xcode CLI tools. They're pre-installed on GitHub Actions, but for local dev:

```bash
xcode-select --install
```

### Windows

**Chocolatey Required:**
Chocolatey is pre-installed on GitHub Actions Windows runners.

**Administrator Privileges:**
Most installs require admin rights (automatically granted in GitHub Actions).

## Best Practices

### 1. Always Include Description and URL

Help future maintainers understand why dependencies exist:

```toml
[tool.wads.ops.graphviz]
description = "Graph visualization software for generating diagrams"
url = "https://graphviz.org/"
# ... rest of config
```

### 2. Use Check Commands

Avoid unnecessary reinstalls and speed up CI:

```toml
check.linux = "which package-name"
```

### 3. Support Multiple Distros

Use OR logic for cross-distro compatibility:

```toml
check.linux = "dpkg -s pkg || rpm -q pkg || pacman -Q pkg"
```

### 4. Include Development Packages

For libraries, install both runtime and development packages:

```toml
install.linux = "sudo apt-get install -y libfoo libfoo-dev"
```

### 5. Document Platform Limitations

Use `note` for platform-specific guidance:

```toml
note = "Not available on Windows - use alternative package"
```

### 6. Group Related Dependencies

Keep related dependencies together in your pyproject.toml:

```toml
# Database dependencies
[tool.wads.ops.postgresql-client]
# ...

[tool.wads.ops.unixodbc]
# ...

# Media processing
[tool.wads.ops.ffmpeg]
# ...

[tool.wads.ops.imagemagick]
# ...
```

## Troubleshooting

### Dependency Not Installing

**Check the logs:**
GitHub Actions shows full output from install commands. Look for error messages.

**Common issues:**
- Wrong package name for the distro
- Missing repository (especially for Microsoft packages)
- Permission issues (use `sudo` where needed)

### Check Command Always Fails

**Test locally:**
```bash
which package-name; echo $?  # Should print 0 if found
```

**Use multiple alternatives:**
```toml
check.linux = "which pkg || dpkg -s pkg || rpm -q pkg"
```

### Installation Timeout

**Default timeout:** 5 minutes per dependency

**If installing from source or large packages:**
Consider pre-building or using a Docker image instead.

## Migration from Legacy Format

### Old Format (DEPRECATED)

```toml
[tool.wads.ci.testing]
system_dependencies = ["unixodbc", "ffmpeg"]
```

### New Format

```toml
[tool.wads.ops.unixodbc]
description = "ODBC driver interface"
install.linux = "sudo apt-get install -y unixodbc unixodbc-dev"

[tool.wads.ops.ffmpeg]
description = "Multimedia framework"
install.linux = "sudo apt-get install -y ffmpeg"
```

**Benefits of new format:**
- Cross-platform support (Linux, macOS, Windows)
- Check-before-install optimization
- Self-documenting with descriptions and URLs
- Fine-grained control over installation

## See Also

- [CI Configuration Reference](CI_CONFIG.md) - Configure test environments
- [Utilities Reference](UTILITIES.md) - CLI tools for debugging
- [wads_operational_dependencies_example.yml](../wads/data/wads_operational_dependencies_example.yml) - Comprehensive examples
