# Skill: Migrate a Python Project to the Wads System

Use this skill when asked to migrate a Python project from the old setup (setup.cfg/setup.py + old isee CI actions) to the modern wads system (pyproject.toml + Hatchling + wads CI actions).

## Overview

This migration converts a project to use:
- **Hatchling** build backend (replaces setuptools)
- **pyproject.toml** as the single source of truth (replaces setup.cfg)
- **Wads 2025 CI workflow** (replaces old isee-based CI)
- **Ruff** for linting and formatting (replaces pylint/black)

## Step-by-Step Procedure

### 1. Assess Current State

Read the project's existing configuration files:
- `setup.cfg` - old metadata and dependencies
- `setup.py` - usually just `from setuptools import setup; setup()`
- `pyproject.toml` - may already exist partially
- `.github/workflows/ci.yml` - old CI workflow
- `MANIFEST.in` - file inclusion rules (if any)

Identify all Python imports across the package to find undeclared dependencies.

### 2. Generate or Update pyproject.toml

If a `pyproject.toml` already exists with wads CI config, verify it's complete. Otherwise:

**Option A - Use the CLI:**
```bash
wads-migrate setup-to-pyproject setup.cfg -o pyproject.toml
```

**Option B - Manual migration:**

Use the template at `wads/data/pyproject_toml_tpl.toml` as a reference. The key sections:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "PACKAGE_NAME"
version = "CURRENT_VERSION"
description = "DESCRIPTION"
readme = "README.md"
requires-python = ">=3.10"
license = { text = "LICENSE_TYPE" }
authors = [{ name = "AUTHOR_NAME" }]
keywords = [...]
dependencies = [
    # All install_requires from setup.cfg
]

[project.urls]
Homepage = "REPO_URL"

[project.optional-dependencies]
dev = ["pytest>=7.0", "pytest-cov>=4.0", "ruff>=0.1.0"]
# Add test dependencies here too if they're heavy/optional

[tool.hatch.build.targets.wheel]
packages = ["PACKAGE_NAME"]

[tool.ruff]
line-length = 88
target-version = "py310"
exclude = ["**/*.ipynb", ".git", ".venv", "build", "dist", "tests", "examples", "scrap"]

[tool.ruff.lint]
select = ["D100"]
ignore = ["D203", "E501", "B905"]

[tool.ruff.lint.pydocstyle]
convention = "google"

[tool.ruff.lint.per-file-ignores]
"**/tests/*" = ["D"]
"**/examples/*" = ["D"]
"**/scrap/*" = ["D"]

[tool.pytest.ini_options]
minversion = "6.0"
testpaths = ["tests"]
doctest_optionflags = ["NORMALIZE_WHITESPACE", "ELLIPSIS"]

[tool.wads.ci]
project_name = ""

[tool.wads.ci.commands]
pre_test = []
test = []
post_test = []
lint = []
format = []

[tool.wads.ci.env]
required_envvars = []
test_envvars = []
extra_envvars = []

[tool.wads.ci.env.defaults]

[tool.wads.ci.quality.ruff]
enabled = true

[tool.wads.ci.quality.black]
enabled = false

[tool.wads.ci.quality.mypy]
enabled = false

[tool.wads.ci.testing]
python_versions = ["3.10", "3.12"]
pytest_args = ["-v", "--tb=short"]
coverage_enabled = true
coverage_threshold = 0
coverage_report_format = ["term", "xml"]
exclude_paths = ["examples", "scrap"]
test_on_windows = true

[tool.wads.ci.metrics]
enabled = true
config_path = ".github/umpyre-config.yml"
storage_branch = "code-metrics"
python_version = "3.10"
force_run = false

[tool.wads.ci.build]
sdist = true
wheel = true

[tool.wads.ci.publish]
enabled = true

[tool.wads.ci.docs]
enabled = true
builder = "epythet"
ignore_paths = ["tests/", "scrap/", "examples/"]
```

### 3. Replace the CI Workflow

Copy the 2025 CI template to `.github/workflows/ci.yml`:

The template is at: `wads/data/github_ci_publish_2025.yml`

Key differences from old CI:
- Uses `i2mint/wads/actions/*@master` instead of `i2mint/isee/actions/*@master`
- Configuration is read from pyproject.toml, not hardcoded
- Uses Ruff instead of pylint
- Supports matrix testing (multiple Python versions)
- Optional Windows testing
- Optional code metrics (umpyre)

### 4. Handle Dependencies

**Core dependencies** go in `[project.dependencies]`:
- Only include packages that are always needed at runtime

**Heavy/optional dependencies** go in `[project.optional-dependencies]`:
```toml
[project.optional-dependencies]
dev = ["pytest>=7.0", "pytest-cov>=4.0", "ruff>=0.1.0"]
test = ["heavy-dep1", "heavy-dep2"]
```

**Test dependencies**: If a dependency is heavy but needed for tests, put it in both `test` extras and in `[project.optional-dependencies]`. The CI installs `dev,test` extras.

### 5. Handle Test Path

If tests are inside the package directory (e.g., `tonal/tests/`), update:
```toml
[tool.pytest.ini_options]
testpaths = ["tonal/tests"]  # or just ["tests"] if at top level
```

### 6. Clean Up

- Keep `setup.cfg` and `setup.py` as backup initially (can remove after CI passes)
- Remove `MANIFEST.in` if present (Hatchling includes all package files by default)
- Ensure `.gitignore` is comprehensive

### 7. Verify

1. **Local test**: `pip install -e ".[dev]" && pytest`
2. **Push to non-main branch** to trigger CI validation without publishing
3. **Check CI results** - look for:
   - Missing dependencies (ImportError in test output)
   - Ruff format/lint failures (auto-fixable in publish job)
   - Test failures

## Expected Results

After migration:
- `pyproject.toml` contains all project metadata and CI config
- `.github/workflows/ci.yml` uses wads 2025 template
- CI runs validation on push/PR with matrix testing
- CI publishes to PyPI on main/master push
- Ruff handles formatting and linting (not pylint)
- Code metrics tracked via umpyre

## Common Issues

1. **Missing `[tool.hatch.build.targets.wheel]`**: Add `packages = ["package_name"]` if Hatchling can't auto-detect
2. **Test discovery**: Ensure `testpaths` matches actual test location
3. **Import errors in CI**: Scan all `.py` files for imports and ensure they're in dependencies
4. **Ruff D100 errors**: Add module docstrings to all Python files missing them
5. **Version mismatch**: Ensure `version` in pyproject.toml matches the latest on PyPI
