# CI Debugging Agent Guide

The CI Debugging Agent automatically analyzes failed GitHub Actions runs, diagnoses issues, and proposes fixes.

## Features

- ✅ Fetches GitHub Actions logs via API
- ✅ Parses pytest test failures with tracebacks
- ✅ Detects missing system dependencies (ODBC, ffmpeg, libsndfile, etc.)
- ✅ Detects missing Python dependencies from import errors
- ✅ Generates both PEP 725 format fixes and manual CI workflow fixes
- ✅ Saves detailed fix instructions to file

---

## Prerequisites

### 1. Install Required Dependencies

```bash
pip install requests
```

### 2. Set Up GitHub Token

The agent requires a GitHub token to access the GitHub Actions API:

```bash
# Option 1: GITHUB_TOKEN
export GITHUB_TOKEN=ghp_your_token_here

# Option 2: GH_TOKEN (if you use gh CLI)
export GH_TOKEN=ghp_your_token_here
```

**To create a GitHub token:**
1. Go to https://github.com/settings/tokens
2. Click "Generate new token (classic)"
3. Select scopes: `repo` (for private repos) or `public_repo` (for public repos)
4. Copy the token and export it as shown above

---

## Usage

### Basic Usage: Analyze Latest Failed Run

```bash
python -m wads.ci_debug_agent owner/repo
```

This will:
1. Find the most recent failed workflow run
2. Download and analyze the logs
3. Report test failures and diagnose issues

**Example:**
```bash
python -m wads.ci_debug_agent i2mint/odbcdol
```

**Output:**
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
   Location: odbcdol/tests/test_simple.py:42

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
```

### Generate Fix Instructions

Add the `--fix` flag to generate detailed fix instructions:

```bash
python -m wads.ci_debug_agent owner/repo --fix --local-repo /path/to/repo
```

This will:
1. Perform the diagnosis
2. Generate detailed step-by-step fix instructions
3. Save instructions to `CI_FIX_INSTRUCTIONS.md`

**Example:**
```bash
cd /path/to/odbcdol
python -m wads.ci_debug_agent i2mint/odbcdol --fix --local-repo .
```

**Generated `CI_FIX_INSTRUCTIONS.md`:**
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

### Analyze a Specific Run

```bash
python -m wads.ci_debug_agent owner/repo --run-id 12345678
```

Use this when you want to analyze a specific workflow run instead of the latest failed one.

---

## Detected Issues

The agent can detect:

### System Dependency Issues

**Detected patterns:**
- **unixodbc**: "Can't open lib.*ODBC.*Driver", "libodbc.*not found"
- **msodbcsql17/18**: "ODBC Driver 17/18 for SQL Server.*not found"
- **ffmpeg**: "ffmpeg.*not found", "libav.*not found"
- **libsndfile**: "libsndfile.*not found", "sndfile.*not found"
- **portaudio**: "portaudio.*not found", "libportaudio.*not found"

### Python Dependency Issues

**Detected patterns:**
- **ModuleNotFoundError**: Extracts missing module names from import errors

---

## Integration with Other Wads Tools

The CI debugging agent works seamlessly with other wads tools:

### 1. Diagnose → Fix → Migrate

```bash
# Step 1: Diagnose the CI failure
python -m wads.ci_debug_agent owner/repo --fix --local-repo .

# Step 2: Review CI_FIX_INSTRUCTIONS.md

# Step 3: Add dependencies to pyproject.toml (use the generated instructions)

# Step 4: Verify the migration
python -m wads.setup_utils diagnose .
```

### 2. CI Debugging Workflow

```bash
# When CI fails:

# 1. Run the debugging agent
python -m wads.ci_debug_agent owner/repo --fix

# 2. If migration is needed
python -m wads.external_deps_migration instructions .

# 3. Apply the fixes to pyproject.toml

# 4. Test locally
python -m wads.setup_utils install-system . --dry-run
python -m wads.setup_utils install-python .

# 5. Push and watch CI pass!
git add pyproject.toml .github/workflows/ci.yml
git commit -m "Fix CI: Add missing system dependencies"
git push
```

### 3. Automated in CI

You can even add the debugging agent to your CI workflow to automatically comment on PRs with fix suggestions:

```yaml
# .github/workflows/debug-failures.yml
name: Debug CI Failures

on:
  workflow_run:
    workflows: ["CI"]
    types: [completed]

jobs:
  debug:
    if: ${{ github.event.workflow_run.conclusion == 'failure' }}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install wads
        run: pip install wads requests

      - name: Analyze failure
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          python -m wads.ci_debug_agent ${{ github.repository }} \
            --run-id ${{ github.event.workflow_run.id }} \
            --fix --local-repo .

      - name: Comment on PR
        if: github.event.workflow_run.event == 'pull_request'
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            const instructions = fs.readFileSync('CI_FIX_INSTRUCTIONS.md', 'utf8');
            github.rest.issues.createComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.payload.workflow_run.pull_requests[0].number,
              body: `## 🤖 CI Failure Analysis\n\n${instructions}`
            });
```

---

## Python API

You can also use the agent programmatically:

```python
from wads.ci_debug_agent import (
    diagnose_ci_failure,
    print_diagnosis,
    generate_fix_instructions
)
from pathlib import Path

# Diagnose the latest failed run
diagnosis = diagnose_ci_failure('owner/repo')

# Print the diagnosis
print_diagnosis(diagnosis)

# Access results programmatically
if diagnosis.missing_system_deps:
    print(f"Missing system dependencies: {', '.join(diagnosis.missing_system_deps)}")

for fix in diagnosis.proposed_fixes:
    print(f"Fix: {fix['description']}")
    if fix['type'] == 'config':
        print("  → Update pyproject.toml")
    elif fix['type'] == 'workflow':
        print("  → Update .github/workflows/ci.yml")

# Generate fix instructions
repo_path = Path('/path/to/repo')
instructions = generate_fix_instructions(diagnosis, repo_path)
print(instructions)
```

---

## Troubleshooting

### Issue: "GITHUB_TOKEN environment variable required"

**Solution:** Export your GitHub token:
```bash
export GITHUB_TOKEN=ghp_your_token_here
```

### Issue: "requests library required"

**Solution:** Install requests:
```bash
pip install requests
```

### Issue: "No failed runs found"

**Solution:** Check that:
1. The repository name is correct (format: `owner/repo`)
2. There are actually failed runs in the repository
3. Your token has access to the repository

### Issue: "403 Forbidden" or "404 Not Found"

**Solution:** Ensure your GitHub token has the correct scopes:
- `repo` scope for private repositories
- `public_repo` scope for public repositories

### Issue: Agent doesn't detect the missing dependency

**Solution:** The agent uses pattern matching on error messages. If a dependency isn't detected:
1. Check the logs manually for the error message
2. Add a new pattern to `diagnose_missing_system_deps()` in `ci_debug_agent.py`
3. Submit a PR to wads to help others!

---

## Real-World Examples

### Example 1: odbcdol CI Failure

**Problem:** Tests failing with ODBC driver not found

**Command:**
```bash
python -m wads.ci_debug_agent i2mint/odbcdol --fix
```

**Diagnosis:**
- Missing: unixodbc, msodbcsql18
- Confidence: HIGH

**Fix Applied:**
Added PEP 725 format to pyproject.toml with install commands for both dependencies.

### Example 2: Audio Processing Library

**Problem:** Tests failing with libsndfile not found

**Command:**
```bash
python -m wads.ci_debug_agent yourorg/audioproc --fix --local-repo .
```

**Diagnosis:**
- Missing: libsndfile, portaudio
- Confidence: HIGH

**Fix Applied:**
```toml
[external]
host-requires = [
    "dep:generic/libsndfile",
    "dep:generic/portaudio",
]

[tool.wads.external.ops.libsndfile]
canonical_id = "dep:generic/libsndfile"
rationale = "Library for reading and writing audio files"
install.linux = "sudo apt-get install -y libsndfile1"
install.macos = "brew install libsndfile"

[tool.wads.external.ops.portaudio]
canonical_id = "dep:generic/portaudio"
rationale = "Audio I/O library"
install.linux = "sudo apt-get install -y portaudio19-dev"
install.macos = "brew install portaudio"
```

---

## Best Practices

1. **Run diagnostics immediately when CI fails** - The agent works best on fresh failures
2. **Review the diagnosis before applying fixes** - Ensure the detected issues are correct
3. **Use PEP 725 format (Option 1)** - This is more maintainable and portable
4. **Test locally first** - Use `wads.setup_utils` to verify fixes work on your machine
5. **Keep GitHub token secure** - Never commit tokens to version control
6. **Update patterns as needed** - If the agent misses a dependency, add the pattern

---

## Contributing

Found a missing dependency pattern? Want to improve the diagnosis?

1. Add patterns to `diagnose_missing_system_deps()` in `ci_debug_agent.py`
2. Add test cases to verify detection works
3. Submit a PR!

Common patterns to add:
- Database drivers (PostgreSQL, MySQL, SQLite)
- Graphics libraries (libpng, libjpeg)
- Compression libraries (zlib, bzip2)
- Cryptographic libraries (OpenSSL, libsodium)

---

**Last Updated:** 2025-01-25
**Wads Version:** 0.1.56+
