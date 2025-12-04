# Example Migration Output

This shows what the agent would produce for a typical project migration.

## Input Project: odbcdol

### Original `pyproject.toml` (partial):
```toml
[project]
name = "odbcdol"
version = "0.0.3"
description = "odbc (through pyodbc) with a simple (dict-like or list-like) interface"
dependencies = [
    "dol",
    "pyodbc",
]
```

### Original `.github/workflows/ci.yml` (partial):
```yaml
name: CI
on: [push]
env:
  PROJECT_NAME: odbcdol

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.10", "3.12"]
    steps:
      - name: Install system dependencies
        run: |
          sudo apt-get update
          sudo apt-get install -y unixodbc unixodbc-dev
          curl https://packages.microsoft.com/keys/microsoft.asc | sudo apt-key add -
          sudo apt-get install -y msodbcsql18
      
      - name: Run tests
        run: pytest -v --tb=short
```

## Agent Output: `pyproject.toml.migrated`

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "odbcdol"
version = "0.0.3"
description = "odbc (through pyodbc) with a simple (dict-like or list-like) interface"
readme = "README.md"
requires-python = ">=3.10"
license = {text = "Apache-2.0"}
keywords = []
authors = []
dependencies = [
    "dol",
    "pyodbc",
]

[project.urls]
Homepage = "https://github.com/i2mint/odbcdol"

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
    "ruff>=0.1.0",
]

# ============================================================================
# EXTERNAL DEPENDENCIES (PEP 725)
# ============================================================================
# System dependencies required for this project

[external]
# Host dependencies: needed during build and at runtime
# These libraries are linked against and required for the package to function
host-requires = [
    "dep:generic/unixodbc",
    "dep:generic/msodbcsql18"
]

# ============================================================================
# WADS EXTERNAL OPERATIONS (Project-Local Operational Metadata)
# ============================================================================

[tool.wads.external.ops]

# UnixODBC - Core ODBC driver manager
[tool.wads.external.ops.unixodbc]
canonical_id = "dep:generic/unixodbc"
rationale = "Provides ODBC driver manager interface, required by pyodbc for database connectivity"
url = "https://www.unixodbc.org/"

# Check commands - verify if package is installed
check.linux = [
    ["dpkg", "-s", "unixodbc"],
    ["rpm", "-q", "unixODBC"]
]
check.macos = ["brew", "list", "unixodbc"]
check.windows = []  # Windows typically uses native ODBC

# Install commands - platform-specific installation
install.linux = [
    "sudo apt-get update",
    "sudo apt-get install -y unixodbc unixodbc-dev"
]
install.macos = "brew install unixodbc"
install.windows = ""  # Windows has ODBC built-in

note = "On Alpine Linux: apk add unixodbc unixodbc-dev"
alternatives = ["iodbc"]  # iODBC is an alternative ODBC implementation

# Microsoft ODBC Driver 18 for SQL Server
[tool.wads.external.ops.msodbcsql18]
canonical_id = "dep:generic/msodbcsql18"
rationale = "Microsoft's ODBC driver for SQL Server connectivity, provides optimized performance for SQL Server databases"
url = "https://docs.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server"

check.linux = [["dpkg", "-s", "msodbcsql18"]]
check.macos = ["brew", "list", "msodbcsql18"]
check.windows = []  # Typically pre-installed or managed separately on Windows

install.linux = [
    "curl https://packages.microsoft.com/keys/microsoft.asc | sudo apt-key add -",
    "curl https://packages.microsoft.com/config/ubuntu/$(lsb_release -rs)/prod.list | sudo tee /etc/apt/sources.list.d/mssql-release.list",
    "sudo apt-get update",
    "sudo ACCEPT_EULA=Y apt-get install -y msodbcsql18"
]
install.macos = "brew tap microsoft/mssql-release && brew install msodbcsql18"
install.windows = ""  # Download from Microsoft

note = "Requires accepting Microsoft EULA during installation"

# ============================================================================
# CI CONFIGURATION
# ============================================================================

[tool.wads.ci]
project_name = "odbcdol"

[tool.wads.ci.commands]
pre_test = []
test = []
post_test = []
lint = []
format = []

[tool.wads.ci.env]
# Environment variables (if any are required at runtime)
required = []
defaults = {}

[tool.wads.ci.quality.ruff]
enabled = true

[tool.wads.ci.quality.black]
enabled = false

[tool.wads.ci.quality.mypy]
enabled = false

[tool.wads.ci.testing]
# Python versions extracted from original CI matrix
python_versions = ["3.10", "3.12"]

# Pytest arguments from original CI
pytest_args = ["-v", "--tb=short"]

# Coverage settings
coverage_enabled = true
coverage_threshold = 0
coverage_report_format = ["term", "xml"]

# Paths to exclude
exclude_paths = ["examples", "scrap"]

# Platform testing
test_on_linux = true
test_on_macos = false
test_on_windows = true  # Test on Windows to ensure ODBC compatibility

[tool.wads.ci.build]
sdist = true
wheel = true

[tool.wads.ci.publish]
enabled = true

[tool.wads.ci.docs]
enabled = true
builder = "epythet"
ignore_paths = ["tests/", "scrap/", "examples/"]

# ============================================================================
# TOOL CONFIGURATION
# ============================================================================

[tool.ruff]
line-length = 88
target-version = "py310"
exclude = [
    "**/*.ipynb", 
    ".git", 
    ".venv", 
    "build", 
    "dist",
    "tests",
    "examples",
    "scrap",
]

[tool.ruff.lint]
select = ["D100"]
ignore = ["D203", "E501", "B905"]

[tool.ruff.lint.pydocstyle]
convention = "google"

[tool.ruff.lint.per-file-ignores]
"tests/*" = ["D"]
"examples/*" = ["D"]
"scrap/*" = ["D"]

[tool.pytest.ini_options]
minversion = "6.0"
testpaths = ["tests"]
doctest_optionflags = ["NORMALIZE_WHITESPACE", "ELLIPSIS"]
```

## Agent Explanation

### Key Changes Made:

1. **External Dependencies Declaration (PEP 725)**
   - Moved system dependencies from CI to `[external]` section
   - Used `host-requires` category since ODBC libraries are needed at both build and runtime
   - Declared as DepURLs: `dep:generic/unixodbc` and `dep:generic/msodbcsql18`

2. **Operational Metadata (`[tool.wads.external.ops]`)**
   - Created detailed configuration for each dependency
   - Included rationale explaining why each dependency is needed
   - Provided platform-specific check and install commands
   - Added URLs for documentation reference
   - Noted alternatives and special considerations

3. **CI Configuration (`[tool.wads.ci]`)**
   - Extracted `PROJECT_NAME` from old CI env vars
   - Preserved Python version matrix: 3.10 and 3.12
   - Kept pytest arguments: `-v --tb=short`
   - Enabled Windows testing (important for ODBC projects)
   - Configured coverage, build, and publish settings

4. **Preservation**
   - All original project metadata maintained
   - Dependencies preserved exactly
   - Tool configurations (ruff, pytest) kept intact

### Design Decisions:

1. **`host-requires` vs `dependencies`**
   - Used `host-requires` because ODBC libraries are linked against (not just runtime tools)
   - These are needed both when building (headers) and at runtime (shared libraries)

2. **Development vs Runtime Dependencies**
   - `unixodbc-dev` merged into single `dep:generic/unixodbc` entry
   - Install commands specify both runtime and dev packages for Linux

3. **Windows Testing**
   - Enabled `test_on_windows = true` because ODBC behavior differs on Windows
   - This is informational only and won't fail the CI if Windows tests fail

4. **EULA Acceptance**
   - Noted Microsoft EULA requirement in `msodbcsql18` metadata
   - Included `ACCEPT_EULA=Y` in install command

### Next Steps:

1. Review the migrated `pyproject.toml`
2. Test locally to ensure dependencies install correctly
3. Replace your `.github/workflows/ci.yml` with the v3 template
4. Commit and push to test the new CI configuration

### Potential Improvements:

1. **Consider adding optional dependencies**:
   ```toml
   [external.optional-dependencies]
   sqlserver = ["dep:generic/msodbcsql18"]  # Make SQL Server driver optional
   ```

2. **Add documentation about ODBC configuration**:
   - Document required `odbc.ini` and `odbcinst.ini` setup
   - Provide example connection strings

3. **Consider connection pooling dependencies**:
   - If using connection pooling, might need additional system libraries

4. **Test data requirements**:
   - Add `pre_test` commands if test database setup is needed
