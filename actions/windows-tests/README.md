# Windows Tests Action (Non-blocking)

Runs pytest tests on Windows for informational purposes only. This action uses `continue-on-error: true` at both the step and job level to ensure Windows test failures don't block the CI pipeline.

## Purpose

- Provides visibility into Windows compatibility issues
- Does not block publishing or deployment if tests fail
- Runs only on Python 3.10 (minimum viable testing)
- Uses PowerShell for better Windows compatibility

## Usage

```yaml
- name: Run Windows Tests
  uses: i2mint/wads/actions/windows-tests@master
  with:
    root-dir: mypackage
    exclude: examples,scrap
    pytest-args: -v --tb=short
```

## Inputs

- `root-dir`: Root directory containing tests (default: `.`)
- `exclude`: Comma-separated paths to exclude (e.g., `examples,scrap`)
- `pytest-args`: Additional pytest arguments (default: `-v`)
- `python-version`: Python version to use (default: `3.10`)

## Job Configuration

When using this action in a workflow job, add:

```yaml
jobs:
  windows-validation:
    runs-on: windows-latest
    continue-on-error: true  # Critical: Don't fail workflow on Windows test failures
    steps:
      # ... your steps using this action
```

## Key Features

1. **Non-blocking**: All steps use `continue-on-error: true`
2. **PowerShell**: Uses `pwsh` shell for Windows compatibility
3. **Clear output**: Shows ✅ for pass, ⚠️ for failures with explanation
4. **Minimal**: Only tests what's necessary, doesn't bloat the pipeline

## Example Output

```
✅ Windows tests PASSED
```

or

```
⚠️ Windows tests FAILED (exit code: 1)
Note: This is informational only and won't block the pipeline
```
