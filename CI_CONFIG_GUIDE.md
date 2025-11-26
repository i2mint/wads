# CI Configuration Guide

## Overview

**wads** now supports using `pyproject.toml` as the **single source of truth** for CI configuration. This eliminates the need to hardcode project-specific settings in CI workflow files.

## Quick Start

### 1. Define CI Configuration in pyproject.toml

Add a `[tool.wads.ci]` section to your `pyproject.toml`:

```toml
[tool.wads.ci]
project_name = "myproject"

[tool.wads.ci.commands]
pre_test = [
    "python scripts/setup_test_data.py",
]

[tool.wads.ci.env]
required = ["DATABASE_URL"]
defaults = {"LOG_LEVEL" = "DEBUG"}

[tool.wads.ci.testing]
python_versions = ["3.10", "3.11", "3.12"]
pytest_args = ["-v", "--tb=short", "--cov=myproject"]
coverage_enabled = true
coverage_threshold = 80
exclude_paths = ["examples", "scrap", "benchmarks"]
```

### 2. Generate CI Workflow

Run `populate` to generate or update your CI workflow:

```bash
python -m wads.populate /path/to/your/project
```

The populate function will:
1. Read your `[tool.wads.ci]` configuration
2. Generate a customized CI workflow based on your settings
3. Create `.github/workflows/ci.yml` with all your configurations applied

### 3. Validate Environment (Optional)

Add this step to your CI workflow to validate required environment variables:

```yaml
- name: Validate Environment
  run: python -m wads.scripts.validate_ci_env
```

## Configuration Reference

### Project Settings

```toml
[tool.wads.ci]
# Project name used throughout CI (defaults to package name)
project_name = "myproject"
```

### ⚙️ Execution Flow and Commands

Define commands executed during different CI phases:

```toml
[tool.wads.ci.commands]
# Pre-test setup - run before testing/linting
pre_test = [
    "python scripts/migrate_db.py",
    "python -m playwright install",
]

# Test commands (defaults to ["pytest"])
test = [
    "pytest",
    "pytest --integration",
]

# Post-test commands
post_test = [
    "python scripts/upload_coverage.py",
]

# Custom lint commands (optional)
lint = [
    "ruff check .",
]

# Custom format commands (optional)
format = [
    "ruff format --check .",
]
```

### 🌍 Environment Variables

Control required and default environment variables:

```toml
[tool.wads.ci.env]
# Required variables - CI fails if these aren't set
required = [
    "DATABASE_URL",
    "API_KEY",
    "AWS_REGION",
]

# Default variables - set if not provided
defaults = {
    "LOG_LEVEL" = "DEBUG",
    "TESTING" = "true",
    "PYTHONUNBUFFERED" = "1",
}
```

### ✅ Code Quality and Formatting

Configure code quality tools:

```toml
[tool.wads.ci.quality.ruff]
enabled = true
output_format = "github"  # GitHub Actions annotations

[tool.wads.ci.quality.mypy]
enabled = true
strict = true
python_version = "3.10"
```

### 🧪 Test Configuration

Control test execution:

```toml
[tool.wads.ci.testing]
# Python versions to test against
python_versions = ["3.10", "3.11", "3.12"]

# Pytest arguments
pytest_args = ["-v", "--tb=short", "--cov=myproject"]

# Coverage settings
coverage_enabled = true
coverage_threshold = 80  # Fail if below this percentage
coverage_report_format = ["term", "xml", "html"]

# Paths to exclude from testing
exclude_paths = ["examples", "scrap", "benchmarks"]

# Enable Windows testing (informational, non-blocking)
test_on_windows = true

# System dependencies (OS packages needed for tests)
# Simple form (Ubuntu only):
system_dependencies = ["ffmpeg", "libsndfile1", "portaudio19-dev"]

# Platform-specific form:
# system_dependencies = { 
#     ubuntu = ["ffmpeg", "libsndfile1", "portaudio19-dev"],
#     macos = ["ffmpeg", "libsndfile", "portaudio"],
#     windows = ["ffmpeg"]  # Installed via chocolatey
# }
```

#### System Dependencies

If your tests require system-level packages (like `ffmpeg`, `libsndfile`, etc.), you can declare them in your CI configuration:

**Simple form** (Ubuntu only):
```toml
[tool.wads.ci.testing]
system_dependencies = ["ffmpeg", "libsndfile1", "portaudio19-dev"]
```

This generates:
```yaml
- name: Install System Dependencies
  run: |
    sudo apt-get update
    sudo apt-get install -y ffmpeg libsndfile1 portaudio19-dev
```

**Platform-specific form** (for cross-platform testing):
```toml
[tool.wads.ci.testing]
system_dependencies = {
    ubuntu = ["ffmpeg", "libsndfile1", "portaudio19-dev"],
    macos = ["ffmpeg", "libsndfile", "portaudio"],
    windows = ["ffmpeg"]  # Installed via chocolatey on Windows
}
```

This automatically:
- Installs Ubuntu packages via `apt-get` in the main validation job
- Installs Windows packages via `choco` in the Windows validation job
- Installs macOS packages via `brew` if macOS testing is enabled (future feature)

**Combined with custom commands:**
```toml
[tool.wads.ci.commands]
pre_test = [
    "python scripts/download_test_data.py",
    "python scripts/setup_environment.py"
]

[tool.wads.ci.testing]
system_dependencies = ["ffmpeg", "libsndfile1"]
```

The system dependencies are installed **first**, then your custom pre-test commands run.

See `examples/system_deps_example.py` for complete examples.
```

### 📦 Build and Publish

Control build artifacts and publication:

```toml
[tool.wads.ci.build]
sdist = true
wheel = true

[tool.wads.ci.publish]
enabled = true
```

### 📄 Documentation

Configure documentation generation:

```toml
[tool.wads.ci.docs]
enabled = true
builder = "epythet"  # or "sphinx", "mkdocs"
ignore_paths = ["tests/", "scrap/", "examples/"]
```

## Advanced Usage

### Using CI Config Programmatically

You can read and use CI configuration in your own scripts:

```python
from wads.ci_config import CIConfig

# Read config from pyproject.toml
config = CIConfig.from_file(".")

# Access configuration
print(f"Project: {config.project_name}")
print(f"Python versions: {config.python_versions}")
print(f"Pre-test commands: {config.commands_pre_test}")

# Check if tools are enabled
if config.is_mypy_enabled():
    print("Mypy is enabled")

# Get required environment variables
required_vars = config.env_vars_required
print(f"Required env vars: {required_vars}")
```

### Validating Environment Variables

The validation script can be used standalone:

```bash
# Validate current environment
python -m wads.scripts.validate_ci_env

# Use in CI (will exit with code 1 if validation fails)
```

### Template Substitution

When `populate` generates CI workflows, it performs these substitutions:

- `#ENV_BLOCK#` → Generated environment variables section
- `#PYTHON_VERSIONS#` → JSON array of Python versions
- `#PRE_TEST_STEPS#` → YAML steps for pre-test commands
- `#PYTEST_ARGS#` → Pytest arguments string
- `#COVERAGE_ENABLED#` → true/false
- `#EXCLUDE_PATHS#` → Comma-separated exclude paths
- And more...

## Migration Guide

### From Hardcoded CI to pyproject.toml

1. **Extract configuration** from your existing `.github/workflows/ci.yml`
2. **Add to pyproject.toml** under `[tool.wads.ci]`
3. **Re-run populate** to regenerate the CI workflow
4. **Test** that CI still works as expected

Example migration:

**Before** (in `.github/workflows/ci.yml`):
```yaml
env:
  PROJECT_NAME: myproject
  LOG_LEVEL: DEBUG

strategy:
  matrix:
    python-version: ["3.10", "3.12"]

- name: Run Tests
  run: pytest -v --cov=myproject
```

**After** (in `pyproject.toml`):
```toml
[tool.wads.ci]
project_name = "myproject"

[tool.wads.ci.env]
defaults = {"LOG_LEVEL" = "DEBUG"}

[tool.wads.ci.testing]
python_versions = ["3.10", "3.12"]
pytest_args = ["-v", "--cov=myproject"]
```

## Benefits

### ✅ Single Source of Truth
- All CI configuration lives in `pyproject.toml`
- No need to edit YAML files directly
- Configuration is versioned with your code

### ✅ Type Safety and Validation
- TOML provides structure and validation
- Easier to catch configuration errors

### ✅ DRY (Don't Repeat Yourself)
- Define once, use everywhere
- No duplication between CI providers

### ✅ Better Developer Experience
- Configuration is discoverable
- IDE support for TOML
- Clear documentation in one place

### ✅ Flexibility
- Works with existing CI workflows
- Gradual migration supported
- Falls back to defaults gracefully

## Examples

### Minimal Configuration

```toml
[tool.wads.ci]
# Use all defaults - just specify project name
project_name = "myproject"
```

### Database Testing

```toml
[tool.wads.ci]
project_name = "mydb"

[tool.wads.ci.commands]
pre_test = [
    "docker-compose up -d postgres",
    "python scripts/wait_for_db.py",
    "alembic upgrade head",
]
post_test = [
    "docker-compose down",
]

[tool.wads.ci.env]
required = ["DATABASE_URL"]
defaults = {"POSTGRES_VERSION" = "15"}

[tool.wads.ci.testing]
pytest_args = ["-v", "--tb=short", "--integration"]
```

### Multi-Tool Setup

```toml
[tool.wads.ci.quality.ruff]
enabled = true

[tool.wads.ci.quality.mypy]
enabled = true
strict = true

[tool.wads.ci.quality.black]
enabled = false  # Using Ruff formatter instead
```

## Troubleshooting

### CI workflow not updating

Make sure to run `populate` after changing `pyproject.toml`:

```bash
python -m wads.populate .
```

### Dynamic template not used

The dynamic template is only used if:
1. `pyproject.toml` exists with `[tool.wads.ci]` section
2. The dynamic template file exists (`github_ci_publish_2025_v2.yml`)

### Environment validation failing

Check that:
1. Required variables are set in CI secrets
2. Variable names match exactly (case-sensitive)
3. Validation script has access to pyproject.toml

### Missing dependencies

If you get import errors:

```bash
pip install tomli tomli-w  # For Python < 3.11
```

## See Also

- [pyproject.toml specification](https://packaging.python.org/en/latest/specifications/pyproject-toml/)
- [GitHub Actions documentation](https://docs.github.com/en/actions)
- [wads populate documentation](README.md)
