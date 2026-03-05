# Skill: Debug CI Failures

Use this skill when a project's GitHub Actions CI is failing and you need to diagnose and fix it.

## Quick Diagnosis

### Using the CLI tool
```bash
wads-ci-debug OWNER/REPO --fix --local-repo .
```

This fetches CI logs, parses failures, and generates fix instructions.

### Manual Diagnosis

1. **Check the CI run**: `gh run list --repo OWNER/REPO` then `gh run view RUN_ID --log-failed`
2. **Common failure categories**:

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `ModuleNotFoundError: No module named 'X'` | Missing dependency | Add to `[project.dependencies]` or `[project.optional-dependencies]` |
| `D100: Missing docstring in public module` | Ruff lint failure | Add module docstring to the file |
| `error: Ruff format check failed` | Code not formatted | Ruff auto-formats in publish job; this may be cosmetic |
| `ImportError` on system package | Missing system dep | Add `[tool.wads.ops.X]` section |
| Test failures | Actual bugs or env issues | Read pytest output, fix tests or add missing test deps |
| `Version already exists on PyPI` | Version tag mismatch | Bump version in pyproject.toml |

## Fixing Missing Dependencies

### Find all imports in a project
```bash
wads-deps scan .
```

Or manually:
```bash
grep -rn "^import \|^from " PACKAGE_NAME/ --include="*.py" | grep -v __pycache__
```

### Classify dependencies

- **Always needed at runtime** → `[project.dependencies]`
- **Heavy but needed for some features** → `[project.optional-dependencies]` extras
- **Only for testing** → `[project.optional-dependencies.test]`
- **System-level (apt/brew)** → `[tool.wads.ops.*]`

### Common import-to-package mappings

| Import Name | Package Name |
|-------------|-------------|
| `PIL` | `Pillow` |
| `cv2` | `opencv-python` |
| `sklearn` | `scikit-learn` |
| `yaml` | `pyyaml` |
| `bs4` | `beautifulsoup4` |
| `gi` | `PyGObject` |
| `lxml.etree` | `lxml` |

## Fixing Ruff Lint Issues

The default wads config only enables `D100` (missing module docstring). Fix by adding:
```python
"""Brief module description."""
```
to the top of every `.py` file.

## Monitoring CI After Fix

```bash
# Push fix
git add . && git commit -m "Fix CI: add missing dependencies" && git push

# Wait ~2 minutes, then check
gh run list --repo OWNER/REPO --limit 1
gh run view RUN_ID --log-failed  # if it failed
```

## Expected Results

After fixing:
- Validation job passes on all Python versions in the matrix
- No lint or format errors
- All tests pass
- Publish job succeeds on main/master (version bump + PyPI upload)
