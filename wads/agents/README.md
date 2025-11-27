# Wads Agents

Autonomous AI agents for diagnosing and fixing common development issues.

## Available Agents

### 1. CI Debug Agent (`wads-ci-debug`)

Analyzes failed GitHub Actions CI runs, diagnoses issues, and proposes fixes.

**Features:**
- Fetches CI logs automatically via GitHub API
- Parses pytest failures and collection errors
- Detects missing system and Python dependencies
- Identifies configuration issues
- Generates detailed fix instructions

**Usage:**
```bash
# Analyze latest failed run
wads-ci-debug owner/repo

# Analyze specific run
wads-ci-debug owner/repo --run-id 12345

# Generate fix instructions file
wads-ci-debug owner/repo --fix
```

**Example Output:**
```
CI FAILURE DIAGNOSIS
======================================================================

Confidence: HIGH

❌ Test Failures (2):
1. ERROR collecting wads/setup_utils.py
   Error: ImportError
   Message: cannot import name '_depurl_to_simple_name' from 'wads.ci_config'

⚠️  CI Warnings (1):
  • Warning: tomli package required for Python < 3.11

💡 Proposed Fixes:
1. Fix ImportError in setup_utils.py
   Type: code
   Action: Remove deprecated imports
```

### 2. Dependency Resolver (`wads-deps`)

Analyzes import errors, missing dependencies, and suggests package additions.

**Features:**
- Scans project files for imports
- Detects missing packages (imported but not declared)
- Identifies unused packages (declared but not imported)
- Maps import names to package names (e.g., `PIL` → `Pillow`)
- Parses error messages to extract missing dependencies

**Usage:**
```bash
# Analyze current project
wads-deps

# Analyze specific project
wads-deps /path/to/project

# Analyze with error log
wads-deps --error-log ci_errors.txt

# Skip checking for unused dependencies
wads-deps --no-check-unused
```

**Example Output:**
```
DEPENDENCY ANALYSIS REPORT
======================================================================

📦 Missing Packages (3):

  pillow (✗ not installed)
    Import: import PIL
    Used in: src/image_utils.py:15

  requests (✓ installed)
    Import: import requests
    Used in: src/api.py:7

🗑️  Potentially Unused Packages (2):
  • boto3
  • sqlalchemy

💡 Recommendations:
  Add 3 missing packages to pyproject.toml:
    - pillow (needs installation)
    - requests (already installed, add to dependencies)
    - pytest (already installed, add to dev dependencies)
```

### 3. Test Analyzer (`wads-test-analyze`)

Analyzes pytest failures, categorizes them by pattern, and suggests fixes.

**Features:**
- Categorizes failures (assertions, timeouts, setup/teardown, exceptions)
- Identifies failure patterns across multiple tests
- Detects slow tests (>5 seconds)
- Provides context-specific fix suggestions
- Prioritizes failures by severity

**Usage:**
```bash
# Analyze pytest output from file
wads-test-analyze pytest_output.txt

# Analyze from stdin (pipe pytest output)
pytest 2>&1 | wads-test-analyze

# Verbose mode
wads-test-analyze pytest_output.txt --verbose
```

**Example Output:**
```
TEST FAILURE ANALYSIS
======================================================================

📊 Summary:
  Failures: 15
  Errors: 3
  Total: 18

🔍 Failure Patterns:

  🔴 ASSERTION (8 occurrences)
    Severity: high
    Fix: Review test expectations and actual values. Check if the test logic is correct.
    Examples:
      - test_api_response: AssertionError: assert 200 == 404
      - test_data_parsing: AssertionError: expected 10, got 5

  🟡 ATTRIBUTE_ERROR (5 occurrences)
    Severity: medium
    Fix: Check object attributes. Ensure objects are properly initialized. (Possible None value - add null check)
    Examples:
      - test_user_profile: 'NoneType' object has no attribute 'name'

🐌 Slow Tests (3):
  - test_database_migration (12.45s)
  - test_file_processing (8.23s)
  - test_api_integration (6.78s)

💡 Recommendations:
  Most common failure: assertion (8 occurrences)
    Fix: Review test expectations and actual values. Check if the test logic is correct.
  Found 3 slow tests (>5s). Consider optimization or mocking.
```

## Python API

All agents can also be used programmatically:

```python
from wads.agents import (
    diagnose_ci_failure,
    analyze_dependencies,
    parse_pytest_output,
)

# CI Debug Agent
diagnosis = diagnose_ci_failure('owner/repo', run_id=12345)
print(f"Found {len(diagnosis.failures)} failures")

# Dependency Resolver
report = analyze_dependencies(
    project_path='.',
    error_logs=error_text,
    check_unused=True
)
print(f"Missing: {len(report.missing_packages)} packages")

# Test Analyzer
with open('pytest_output.txt') as f:
    report = parse_pytest_output(f.read())
print(f"Total failures: {report.total_failures}")
```

## Configuration

### GitHub Token (for CI Debug Agent)

Set the `GITHUB_TOKEN` or `GH_TOKEN` environment variable:

```bash
export GITHUB_TOKEN=ghp_your_token_here
```

Or use the GitHub CLI's token:
```bash
gh auth status  # Ensures you're authenticated
```

## Integration with CI

### Auto-diagnose on CI Failure

Add to your GitHub Actions workflow:

```yaml
- name: Diagnose CI Failures
  if: failure()
  run: |
    pip install wads
    wads-ci-debug ${{ github.repository }} --run-id ${{ github.run_id }} --fix
  env:
    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

### Dependency Check in CI

```yaml
- name: Check Dependencies
  run: |
    pip install wads
    wads-deps --error-log <(pytest 2>&1) || true
```

## Development

To create a new agent:

1. Create a new file in `wads/agents/` (e.g., `my_agent.py`)
2. Implement the agent logic with a `main()` function for CLI
3. Add exports to `wads/agents/__init__.py`
4. Add CLI entry point to `pyproject.toml`
5. Update this README with usage examples

Example agent template:

```python
"""
My Agent

Description of what this agent does.
"""

import sys
from dataclasses import dataclass
from typing import List

@dataclass
class MyReport:
    """Result of my agent's analysis."""
    issues: List[str]
    recommendations: List[str]

def analyze_something(input_data: str) -> MyReport:
    """Main analysis function."""
    # ... implementation
    return MyReport(issues=[], recommendations=[])

def main():
    """CLI entry point."""
    import argparse
    parser = argparse.ArgumentParser(description='My Agent')
    parser.add_argument('input', help='Input to analyze')
    args = parser.parse_args()

    report = analyze_something(args.input)
    print(f"Found {len(report.issues)} issues")
    sys.exit(1 if report.issues else 0)

if __name__ == '__main__':
    main()
```

## See Also

- [UTILITIES.md](../../docs/UTILITIES.md) - Complete utilities reference
- [CI_DEBUG_AGENT.md](../../docs/archive/CI_DEBUG_AGENT_GUIDE.md) - Archived detailed guide
