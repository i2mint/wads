# CI Debugging Example: odbcdol

This document shows a real-world example of using the CI debugging agent to fix odbcdol's CI failures.

---

## The Problem

**Symptom:** odbcdol CI tests failing on GitHub Actions

**Error Message:**
```
pyodbc.Error: ('01000', "[01000] [unixODBC][Driver Manager]Can't open lib 'ODBC Driver 18 for SQL Server' : file not found (0) (SQLDriverConnect)")
```

**Test:** `odbcdol/tests/test_simple.py::test_sqlserver_persister`

---

## Step-by-Step Debugging

### Step 1: Run the CI Debug Agent

```bash
# Set up GitHub token (if not already set)
export GITHUB_TOKEN=ghp_your_token_here

# Navigate to odbcdol directory
cd /Users/thorwhalen/Dropbox/py/proj/i/dols/odbcdol

# Run the agent
python -m wads.ci_debug_agent i2mint/odbcdol --fix --local-repo .
```

### Step 2: Review the Diagnosis

**Expected Output:**
```
Analyzing failed run: 12345678 - CI
Fetching logs for run 12345678...
Found 2 test failures

======================================================================
CI FAILURE DIAGNOSIS
======================================================================

Confidence: HIGH

❌ Test Failures (2):

1. odbcdol/tests/test_simple.py::test_sqlserver_persister
   Error: pyodbc.Error
   Message: ('01000', "[01000] [unixODBC][Driver Manager]Can't open lib 'ODBC Driver 18 for SQL Server' : file not found...")

2. odbcdol/tests/test_simple.py::test_another_odbc_test
   Error: pyodbc.Error
   Message: ('01000', "[01000] [unixODBC][Driver Manager]Can't open lib 'ODBC Driver 18 for SQL Server' : file not found...")

🔧 Missing System Dependencies:
  • unixodbc
  • msodbcsql18

⚠️  Configuration Issues:
  • Missing system dependencies: unixodbc, msodbcsql18

💡 Proposed Fixes:

1. Add missing system dependencies to pyproject.toml
   Type: config
   Action: Add [external] and [tool.wads.external.ops] sections
   Packages: unixodbc, msodbcsql18

2. Add system dependency installation to CI workflow
   Type: workflow
   Action: Add installation step before tests
   Packages: unixodbc, msodbcsql18

======================================================================

✓ Fix instructions saved to: CI_FIX_INSTRUCTIONS.md
```

### Step 3: Review Generated Fix Instructions

The agent created `CI_FIX_INSTRUCTIONS.md`:

```markdown
======================================================================
FIX INSTRUCTIONS
======================================================================

## Fix System Dependencies

### Option 1: Use PEP 725 format (recommended)

Add to your `pyproject.toml`:

[external]
host-requires = [
    "dep:generic/unixodbc",
    "dep:generic/msodbcsql18",
]

Then add operational metadata for each:

[tool.wads.external.ops.unixodbc]
canonical_id = "dep:generic/unixodbc"
rationale = "ODBC driver interface for database connectivity"
install.linux = "sudo apt-get install -y unixodbc unixodbc-dev"

[tool.wads.external.ops.msodbcsql18]
canonical_id = "dep:generic/msodbcsql18"
rationale = "Microsoft ODBC Driver 18 for SQL Server"
install.linux = [
    "curl https://packages.microsoft.com/keys/microsoft.asc | sudo apt-key add -",
    "curl https://packages.microsoft.com/config/ubuntu/$(lsb_release -rs)/prod.list | sudo tee /etc/apt/sources.list.d/mssql-release.list",
    "sudo apt-get update",
    "sudo ACCEPT_EULA=Y apt-get install -y msodbcsql18"
]

### Option 2: Manual CI fix

Add this step to `.github/workflows/ci.yml`
after 'Set up Python' step:

```yaml
      - name: Install System Dependencies
        run: |
          sudo apt-get update
          sudo apt-get install -y unixodbc unixodbc-dev
          curl https://packages.microsoft.com/keys/microsoft.asc | sudo apt-key add -
          curl https://packages.microsoft.com/config/ubuntu/$(lsb_release -rs)/prod.list | sudo tee /etc/apt/sources.list.d/mssql-release.list
          sudo apt-get update
          sudo ACCEPT_EULA=Y apt-get install -y msodbcsql18
```
======================================================================
```

### Step 4: Apply the Fix (Option 1 - PEP 725)

**Add to `pyproject.toml`:**

```toml
# ============================================================================
# EXTERNAL DEPENDENCIES (PEP 725)
# ============================================================================

[external]
host-requires = [
    "dep:generic/unixodbc",
    "dep:generic/msodbcsql18"
]

# ============================================================================
# WADS EXTERNAL OPERATIONS
# ============================================================================

[tool.wads.external.ops.unixodbc]
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

[tool.wads.external.ops.msodbcsql18]
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

### Step 5: Verify the Configuration

```bash
# Check that the configuration is valid
python -m wads.setup_utils diagnose .
```

**Expected Output:**
```
======================================================================
DEPENDENCY DIAGNOSTIC REPORT
======================================================================

✓ All Python dependencies satisfied

⚠️  System Dependencies (2 total):

  • unixodbc
    DepURL: dep:generic/unixodbc
    Purpose: ODBC driver interface for database connectivity
    Info: https://www.unixodbc.org/
    Status: Not installed (or cannot verify)

  • msodbcsql18
    DepURL: dep:generic/msodbcsql18
    Purpose: Microsoft ODBC Driver 18 for SQL Server
    Info: https://docs.microsoft.com/sql/connect/odbc/
    Status: Not installed (or cannot verify)

📋 Recommendations:

1. Install system dependencies:
   python -m wads.setup_utils install-system .

======================================================================
```

### Step 6: Test Installation Locally (Optional)

```bash
# Dry run to see what would be installed
python -m wads.setup_utils install-system . --dry-run

# Actually install (on Linux)
python -m wads.setup_utils install-system .
```

### Step 7: Update CI Workflow (Temporary Manual Step)

**Until wads CI generation is updated**, manually add to `.github/workflows/ci.yml`:

```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      # ADD THIS STEP:
      - name: Install System Dependencies
        run: |
          sudo apt-get update
          sudo apt-get install -y unixodbc unixodbc-dev
          curl https://packages.microsoft.com/keys/microsoft.asc | sudo apt-key add -
          curl https://packages.microsoft.com/config/ubuntu/$(lsb_release -rs)/prod.list | sudo tee /etc/apt/sources.list.d/mssql-release.list
          sudo apt-get update
          sudo ACCEPT_EULA=Y apt-get install -y msodbcsql18

      - name: Install dependencies
        run: |
          pip install -e .
          pip install pytest

      - name: Run tests
        run: pytest
```

### Step 8: Commit and Push

```bash
git add pyproject.toml .github/workflows/ci.yml
git commit -m "Fix CI: Add ODBC system dependencies using PEP 725 format

- Added [external] section with unixodbc and msodbcsql18
- Added [tool.wads.external.ops] with install commands
- Updated CI workflow to install system dependencies
- Fixes GitHub Actions test failures with ODBC driver not found

🤖 Diagnosis generated with wads.ci_debug_agent"

git push
```

### Step 9: Monitor CI

Watch the GitHub Actions run. It should now:
1. ✅ Install system dependencies (unixodbc, msodbcsql18)
2. ✅ Install Python dependencies
3. ✅ Run tests successfully

---

## Alternative: Using Existing Configuration

If odbcdol already has `[tool.wads.ci.env.install]` format:

### Current Format:
```toml
[tool.wads.ci.env]
install.linux = [
    "curl https://packages.microsoft.com/keys/microsoft.asc | sudo apt-key add -",
    "curl https://packages.microsoft.com/config/ubuntu/$(lsb_release -rs)/prod.list | sudo tee /etc/apt/sources.list.d/mssql-release.list",
    "sudo apt-get update",
    "sudo ACCEPT_EULA=Y apt-get install -y msodbcsql18 unixodbc-dev"
]
```

### Problem:
This format exists but the CI workflow doesn't execute these commands!

### Quick Fix:
Just manually add the install commands to `.github/workflows/ci.yml` as shown in Step 7.

### Long-term Fix:
Migrate to PEP 725 format as shown above, so that when wads updates its CI generation to use `generate_pre_test_steps()`, it will automatically work.

---

## What Changed

### Before:
- ❌ CI failing with ODBC driver not found
- ❌ No system dependencies declared in standard format
- ❌ CI workflow missing system dependency installation step

### After:
- ✅ System dependencies declared in PEP 725 `[external]` format
- ✅ Operational metadata in `[tool.wads.external.ops]` with install commands
- ✅ CI workflow updated to install system dependencies
- ✅ Tests passing!

---

## Benefits of This Approach

### 1. Declarative Dependencies
Dependencies are declared in `pyproject.toml` alongside Python dependencies:
```toml
[project]
dependencies = ["pyodbc"]  # Python dependency

[external]
host-requires = [
    "dep:generic/unixodbc",    # System dependency
    "dep:generic/msodbcsql18"  # System dependency
]
```

### 2. Platform-Specific Instructions
Different install commands for different platforms:
```toml
[tool.wads.external.ops.unixodbc]
install.linux = ["sudo apt-get install -y unixodbc-dev"]
install.macos = "brew install unixodbc"
install.windows = "choco install unixodbc"
```

### 3. Self-Documenting
The `rationale` and `url` fields explain WHY dependencies are needed:
```toml
[tool.wads.external.ops.msodbcsql18]
canonical_id = "dep:generic/msodbcsql18"
rationale = "Microsoft ODBC Driver 18 for SQL Server"
url = "https://docs.microsoft.com/sql/connect/odbc/"
note = "Requires accepting Microsoft EULA"
```

### 4. Verifiable Locally
Users can verify and install dependencies on their machine:
```bash
python -m wads.setup_utils diagnose .
python -m wads.setup_utils install-system .
```

### 5. Future-Proof
Aligns with PEP 725 and prepares for PEP 804 central registry. When the central registry exists, you'll be able to remove the operational metadata and just reference the DepURLs.

---

## Lessons Learned

### 1. Legacy Formats Need CI Updates
Having `[tool.wads.ci.env.install]` in `pyproject.toml` is not enough - the CI workflow must actually execute those commands.

### 2. CI Debug Agent is Invaluable
The agent immediately identified:
- Which dependencies were missing
- How to fix the configuration
- How to update the CI workflow

### 3. PEP 725 is More Maintainable
The new format is clearer and more maintainable than scattered install commands in CI YAML files.

### 4. Diagnosis Before Fixes
Always run `wads.setup_utils diagnose` to verify configuration before pushing.

---

## Next Steps for odbcdol

1. **Remove legacy format** once PEP 725 format is verified working:
   ```toml
   # Delete this deprecated section:
   # [tool.wads.ci.env]
   # install.linux = [...]
   ```

2. **Add check commands** to verify dependencies are installed:
   ```toml
   [tool.wads.external.ops.msodbcsql18]
   check.linux = [["odbcinst", "-q", "-d", "-n", "ODBC Driver 18 for SQL Server"]]
   ```

3. **Document for contributors** in README.md:
   ```markdown
   ## Development Setup

   Install system dependencies:
   ```bash
   python -m wads.setup_utils install-system .
   ```

4. **Wait for wads CI generation update** so CI workflow can be simplified - the install commands will be generated automatically from `[external]` sections.

---

## Summary

The CI debugging agent made it trivial to:
1. **Diagnose** the problem (missing ODBC drivers)
2. **Generate** fix instructions (PEP 725 format)
3. **Verify** the fix (setup_utils)
4. **Apply** the fix (update pyproject.toml and CI workflow)

**Total time:** ~5 minutes instead of hours of manual debugging!

---

**Date:** 2025-01-25
**Repository:** i2mint/odbcdol
**Wads Version:** 0.1.56+
