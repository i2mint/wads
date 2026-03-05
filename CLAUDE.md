# wads - Python Packaging & CI/CD Tools

## What This Project Does

Wads automates Python project setup, packaging, CI/CD, and migration. It provides:

1. **`populate`** - Create new Python projects with modern tooling (pyproject.toml + Hatchling)
2. **`pack`** - Build and publish packages to PyPI
3. **`wads-migrate`** - Migrate legacy projects (setup.cfg → pyproject.toml, old CI → new CI)
4. **CI Actions** - Reusable GitHub Actions in `actions/` directory
5. **AI Agents** - Diagnostic tools (`wads-ci-debug`, `wads-deps`, `wads-test-analyze`)

## Architecture: pyproject.toml as Single Source of Truth

The core design principle: **all project configuration lives in `pyproject.toml`**. The CI workflow template (`github_ci_publish_2025.yml`) reads configuration from `pyproject.toml` via the `read-ci-config` action, so projects don't hardcode settings in workflow files.

### Key Configuration Sections

| Section | Purpose |
|---------|---------|
| `[project]` | Standard Python project metadata |
| `[tool.wads.ci.testing]` | Python versions, pytest args, coverage, Windows testing |
| `[tool.wads.ci.commands]` | Pre-test, test, post-test, lint, format commands |
| `[tool.wads.ci.env]` | Environment variables (required, test, extra, defaults) |
| `[tool.wads.ci.quality]` | Ruff/Black/Mypy settings |
| `[tool.wads.ci.build]` | sdist/wheel build settings |
| `[tool.wads.ci.publish]` | PyPI publishing settings |
| `[tool.wads.ci.docs]` | Documentation generation (epythet) |
| `[tool.wads.ci.metrics]` | Code metrics tracking (umpyre) |
| `[tool.wads.ops.*]` | System/OS-level dependencies (ffmpeg, ODBC, etc.) |

## Project Structure

```
wads/
├── actions/              # Reusable GitHub Actions (composite actions)
│   ├── read-ci-config/   # Read [tool.wads.ci] from pyproject.toml
│   ├── install-system-deps/  # Install [tool.wads.ops.*] dependencies
│   ├── install-deps/     # Install Python dependencies
│   ├── run-tests/        # Run pytest with coverage
│   ├── ruff-format/      # Code formatting
│   ├── ruff-lint/        # Code linting
│   ├── build-dist/       # Build wheel/sdist
│   ├── pypi-upload/      # Upload to PyPI
│   ├── git-commit/       # Auto-commit (SSH)
│   └── git-tag/          # Create git tags
├── wads/                 # Main Python package
│   ├── populate.py       # Project creation (`populate` CLI)
│   ├── pack.py           # Package publishing (`pack` CLI)
│   ├── migration.py      # Migration tools (`wads-migrate` CLI)
│   ├── ci_config.py      # CIConfig class - reads pyproject.toml CI config
│   ├── install_system_deps.py  # System dependency installer
│   ├── toml_util.py      # TOML read/write helpers
│   ├── util.py           # Git, logging, path utilities
│   ├── data/             # Templates
│   │   ├── pyproject_toml_tpl.toml       # Default pyproject.toml template
│   │   ├── github_ci_publish_2025.yml    # Modern CI workflow template
│   │   └── (other templates)
│   ├── agents/           # AI diagnostic agents
│   ├── scripts/          # CI helper scripts
│   └── tests/            # Test suite
├── pyproject.toml        # Wads's own config
└── README.md
```

## How Default Setup Works

### Template Flow

1. **`populate my-project`** reads the template at `wads/data/pyproject_toml_tpl.toml`
2. Loads it as TOML, merges user-provided values (name, description, author, license, etc.)
3. Writes the resulting `pyproject.toml` with Hatchling build system
4. Copies `wads/data/github_ci_publish_2025.yml` → `.github/workflows/ci.yml`
5. Creates README.md, LICENSE, .gitignore, .gitattributes, .editorconfig, package dir

### CI Workflow Flow (github_ci_publish_2025.yml)

The CI workflow has 4-5 jobs:

1. **setup** - Reads `[tool.wads.ci]` config, exports as outputs
2. **validation** - Matrix testing across python_versions:
   - Install system deps → Install Python deps → Ruff format → Ruff lint → Pytest → Metrics
3. **windows-validation** (optional) - Same tests on Windows, `continue-on-error: true`
4. **publish** (main/master only) - Format → Bump version → Build → PyPI upload → Commit → Tag
5. **github-pages** (optional) - Publish docs via epythet

### Migration Flow

To migrate a legacy project:

1. Run `wads-migrate setup-to-pyproject setup.cfg -o pyproject.toml` (or use Python API)
2. Manually review and add `[tool.wads.ci]` section (use template as reference)
3. Replace `.github/workflows/ci.yml` with the 2025 template
4. Remove `setup.cfg` and `setup.py` (keep as backup if needed)
5. Verify with `pytest` and a push to a non-main branch

## Key Conventions

- **Build backend**: Hatchling (not setuptools)
- **Python version**: `>=3.10` default
- **Test matrix**: `["3.10", "3.12"]` default
- **Linting**: Ruff (replaces pylint, black, isort)
- **CI actions**: All from `i2mint/wads/actions/*@master`
- **Version bumping**: `i2mint/isee/actions/bump-version-number@master`
- **Docs**: epythet (GitHub Pages)
- **Metrics**: umpyre

## CLI Reference

```bash
# Create a new project
populate my-project --root-url https://github.com/user/my-project

# Build and publish
pack go .

# Migrate setup.cfg → pyproject.toml
wads-migrate setup-to-pyproject setup.cfg

# Migrate old CI → new CI
wads-migrate ci-old-to-new .github/workflows/ci.yml

# Debug CI failures
wads-ci-debug myorg/myrepo --fix

# Analyze dependencies
wads-deps scan .

# Analyze test failures
wads-test-analyze results.xml
```

## Testing

```bash
pytest wads/tests/
```

Tests are in `wads/tests/` (not the top-level `tests/` directory).

## Common Pitfalls

- The `[tool.wads.ci]` section is **not** standard TOML metadata - it's wads-specific
- `testpaths` in the template defaults to `["tests"]` but wads itself uses `["wads/tests"]`
- The CI workflow uses `i2mint/wads/actions/*@master` - these must be on GitHub
- System deps in `[tool.wads.ops.*]` only run in CI, not locally
- Version bumping happens automatically in the publish job on main/master
