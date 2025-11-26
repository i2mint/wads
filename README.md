# wads

Modern Python project packaging and CI/CD tools for developers who want to focus on code, not configuration.

[![PyPI version](https://img.shields.io/pypi/v/wads.svg)](https://pypi.org/project/wads/)
[![Python versions](https://img.shields.io/pypi/pyversions/wads.svg)](https://pypi.org/project/wads/)

## What is Wads?

Wads helps you:
- **Create new Python projects** with modern tooling (pyproject.toml, GitHub Actions)
- **Manage CI/CD workflows** with configuration-driven GitHub Actions
- **Handle system dependencies** declaratively in pyproject.toml
- **Migrate legacy projects** from setup.cfg to modern formats
- **Debug CI failures** with automated diagnostics

## Installation

```bash
pip install wads
```

## Quick Start

### Create a New Project

```bash
populate my-project --root-url https://github.com/user/my-project
cd my-project
```

This creates a complete project structure with:
- `pyproject.toml` (modern build configuration)
- `README.md`, `LICENSE`, `.gitignore`
- Package directory with `__init__.py`
- GitHub Actions CI/CD workflow (optional)

### Configure CI in pyproject.toml

Edit your `pyproject.toml` to configure CI behavior:

```toml
[tool.wads.ci.testing]
python_versions = ["3.10", "3.12"]
pytest_args = ["-v", "--tb=short"]
coverage_enabled = true
test_on_windows = true

[tool.wads.ci.quality.ruff]
enabled = true

[tool.wads.ci.build]
sdist = true
wheel = true
```

### Declare System Dependencies

Need ffmpeg, ODBC drivers, or other system packages in CI? Declare them in `pyproject.toml`:

```toml
[tool.wads.ops.ffmpeg]
description = "Multimedia framework for video/audio processing"
url = "https://ffmpeg.org/"

check.linux = "which ffmpeg"
check.macos = "which ffmpeg"

install.linux = "sudo apt-get install -y ffmpeg"
install.macos = "brew install ffmpeg"
install.windows = "choco install ffmpeg -y"

note = "Required for audio processing features"
```

The `install-system-deps` action in your CI workflow will automatically install these.

## Core Features

### 1. Project Setup (`populate`)

Create new Python projects with modern best practices:

```bash
# Basic usage
populate my-project

# With custom settings
populate my-project \
  --root-url https://github.com/myorg/my-project \
  --description "My awesome project" \
  --author "Your Name" \
  --license apache
```

**Options:**
- `--root-url`: GitHub repository URL
- `--description`: Project description
- `--author`: Author name
- `--license`: License type (mit, apache, bsd, etc.)
- `--keywords`: Comma-separated keywords
- `--overwrite`: Files to overwrite if they exist

**Tip:** Configure defaults in `wads_configs.json` or use `WADS_CONFIGS_FILE` environment variable to point to your custom config.

### 2. Package and Publish (`pack`)

Build and publish packages to PyPI:

```bash
# See current configuration
pack current-configs

# Increment version and publish
pack go .

# Or step-by-step
pack increment-configs-version
pack run-setup
pack twine-upload-dist
```

### 3. Migration Tools (`wads-migrate`)

Migrate legacy projects to modern format:

```bash
# Migrate setup.cfg to pyproject.toml
wads-migrate setup-to-pyproject setup.cfg -o pyproject.toml

# Migrate old CI workflow to new format
wads-migrate ci-old-to-new .github/workflows/old-ci.yml -o .github/workflows/ci.yml
```

**Python API:**

```python
from wads.migration import migrate_setuptools_to_hatching, migrate_github_ci_old_to_new

# From setup.cfg file
pyproject_content = migrate_setuptools_to_hatching('setup.cfg')

# From setup.cfg dict
config = {'metadata': {'name': 'myproject', 'version': '1.0.0'}}
pyproject_content = migrate_setuptools_to_hatching(config)

# Migrate CI workflow
new_ci = migrate_github_ci_old_to_new('.github/workflows/ci.yml')
```

### 4. CI Debugging (`wads-ci-debug`)

Diagnose and fix GitHub Actions CI failures:

```bash
# Analyze latest failure
wads-ci-debug myorg/myrepo

# Analyze specific run
wads-ci-debug myorg/myrepo --run-id 1234567890

# Generate fix instructions
wads-ci-debug myorg/myrepo --fix --local-repo .
```

The tool will:
- Fetch CI logs from GitHub
- Parse test failures and errors
- Identify root causes
- Generate fix instructions with file locations and suggested changes

## CI Configuration Reference

Wads uses `pyproject.toml` as a single source of truth for CI configuration. Here's what you can configure:

### Python Versions and Testing

```toml
[tool.wads.ci.testing]
python_versions = ["3.10", "3.11", "3.12"]  # Test matrix
pytest_args = ["-v", "--tb=short"]           # Pytest arguments
coverage_enabled = true                      # Enable coverage
coverage_threshold = 80                      # Minimum coverage %
exclude_paths = ["examples", "scrap"]        # Paths to exclude
test_on_windows = true                       # Run Windows tests
```

### Code Quality Tools

```toml
[tool.wads.ci.quality.ruff]
enabled = true
# line_length = 88

[tool.wads.ci.quality.mypy]
enabled = false
# strict = true
```

### Custom Commands

```toml
[tool.wads.ci.commands]
pre_test = [
    "python scripts/setup_test_data.py",
]
post_test = [
    "python scripts/cleanup.py",
]
```

### Build and Publish

```toml
[tool.wads.ci.build]
sdist = true
wheel = true

[tool.wads.ci.publish]
enabled = true  # Publish to PyPI on main/master
```

## System Dependencies

System dependencies are declared using the `[tool.wads.ops.*]` format and automatically installed in CI via the `install-system-deps` action.

**Format:**

```toml
[tool.wads.ops.{package-name}]
description = "Description of the package"
url = "https://package-homepage.com"

# Check if already installed (exit code 0 = present)
check.linux = "which package-name"
check.macos = "brew list package-name"
check.windows = "where package-name"

# Install commands (string or list of strings)
install.linux = "sudo apt-get install -y package-name"
install.macos = "brew install package-name"
install.windows = "choco install package-name -y"

# Optional metadata
note = "Additional installation notes"
alternatives = ["alternative-package"]
```

**Real-world example (ODBC drivers):**

```toml
[tool.wads.ops.unixodbc]
description = "ODBC driver interface for database connectivity"
url = "https://www.unixodbc.org/"

check.linux = "dpkg -s unixodbc || rpm -q unixODBC"
check.macos = "brew list unixodbc"

install.linux = [
    "sudo apt-get update",
    "sudo apt-get install -y unixodbc unixodbc-dev"
]
install.macos = "brew install unixodbc"

note = "On Alpine: apk add unixodbc unixodbc-dev"
alternatives = ["iodbc"]
```

See [docs/SYSTEM_DEPENDENCIES.md](docs/SYSTEM_DEPENDENCIES.md) for comprehensive examples.

## Documentation

- **[System Dependencies Guide](docs/SYSTEM_DEPENDENCIES.md)** - `[tool.wads.ops.*]` format and examples
- **[CI Configuration Reference](docs/CI_CONFIG.md)** - Complete `[tool.wads.ci]` reference
- **[Migration Guide](docs/MIGRATION.md)** - Migrate from setup.cfg to pyproject.toml
- **[Utilities Reference](docs/UTILITIES.md)** - CLI tools (`wads-ci-debug`, `wads-migrate`)

## Troubleshooting

### Version Tag Misalignment

If PyPI publishing fails with "appears to already exist":

```
WARNING  Skipping mypackage-0.1.4-py3-none-any.whl because it appears to already exist
```

This means your git tags are misaligned with the version in `pyproject.toml`.

**Fix:**

1. Check the current PyPI version: https://pypi.org/project/your-package/
2. Update `version` in `pyproject.toml` to a higher number
3. Create and push git tag:
   ```bash
   git tag 0.1.5
   git push origin 0.1.5
   ```

### CI Failures

Use `wads-ci-debug` to analyze failures:

```bash
wads-ci-debug myorg/myrepo --fix
```

Common issues:
- Missing system dependencies → Add to `[tool.wads.ops.*]`
- Python version incompatibilities → Check `python_versions` in `[tool.wads.ci.testing]`
- Test failures → Review generated fix instructions

## Development

### Running Tests

```bash
pytest wads/tests/
```

### Building Documentation

```bash
pip install -e ".[docs]"
epythet build
```

## License

Apache Software License 2.0

## Links

- **PyPI:** https://pypi.org/project/wads/
- **GitHub:** https://github.com/i2mint/wads
- **Issues:** https://github.com/i2mint/wads/issues
