# Migrating to uv-based CI

This guide covers migrating wads-managed projects to the new uv-based CI template.

## What changes

| Before (2025 template) | After (uv template) |
|------------------------|---------------------|
| `actions/setup-python@v6` | `astral-sh/setup-uv@v5` + `uv python install` |
| `install-deps` action (pip) | `uv pip install -e ".[dev]"` (in a venv) |
| `ruff-format` action | `uvx ruff format .` |
| `ruff-lint` action | `uvx ruff check --output-format=github` |
| `run-tests` action | `python -m pytest` (inline) |
| `build-dist` action (python -m build) | `uv build` |
| `pypi-upload` action (twine) | `uv publish` |
| `PYPI_USERNAME` + `PYPI_PASSWORD` | `PYPI_PASSWORD` only (as `UV_PUBLISH_TOKEN`) |

**What stays the same**: `read-ci-config`, `install-system-deps`, `git-commit`, `git-tag`, `bump-version-number`, `epythet` GitHub Pages.

## Prerequisites

1. Project uses `pyproject.toml` (not `setup.cfg`)
2. `pyproject.toml` has a `[tool.wads.ci]` section (or uses defaults)
3. `PYPI_PASSWORD` secret is a PyPI API token (not a password)

If your project still uses `setup.cfg`, first migrate with:
```bash
wads-migrate setup-to-pyproject setup.cfg -o pyproject.toml
```

## Migration from 2025 template

```bash
# Preview the new CI template
wads-migrate ci-to-uv .github/workflows/ci.yml

# Write it to a file
wads-migrate ci-to-uv .github/workflows/ci.yml -o .github/workflows/ci.yml
```

That's it. The uv template reads configuration from `pyproject.toml` just like the 2025 template, so no changes to `pyproject.toml` are needed.

## Migration from old (setup.cfg) format

Two steps:

```bash
# 1. Migrate setup.cfg to pyproject.toml
wads-migrate setup-to-pyproject setup.cfg -o pyproject.toml

# 2. Replace CI workflow
wads-migrate ci-to-uv .github/workflows/ci.yml -o .github/workflows/ci.yml
```

After migration, review and add a `[tool.wads.ci]` section to your `pyproject.toml` if you need non-default settings. See `wads/data/pyproject_toml_tpl.toml` for the full list of options.

## PyPI authentication

The uv template uses token-based auth only:

```yaml
# In the publish job:
env:
  UV_PUBLISH_TOKEN: ${{ secrets.PYPI_PASSWORD }}
run: uv publish dist/*
```

**If you already use token auth** (your `PYPI_PASSWORD` secret is a PyPI API token starting with `pypi-`): no changes needed.

**If you use username + password**: Go to pypi.org → Account Settings → API Tokens → Create token. Replace your `PYPI_PASSWORD` GitHub secret with the token value. The `PYPI_USERNAME` secret is no longer needed.

## Troubleshooting

### `uv python install` fails

The `astral-sh/setup-uv@v5` action handles uv installation. If Python installation fails, check that your `python_versions` in `[tool.wads.ci.testing]` use valid version strings (e.g., `"3.10"`, `"3.12"`).

### `uv pip install -e ".[dev]"` fails

Ensure your `pyproject.toml` has a `[project.optional-dependencies]` section for `dev`. The `dev` extra should include pytest, pytest-cov, and ruff. If your project doesn't use extras, the CI template can be customized.

### `uv publish` authentication error

Ensure `PYPI_PASSWORD` is set as a repository secret in GitHub (Settings → Secrets and variables → Actions) and contains a valid PyPI API token.

### Windows tests fail with uv

uv has native Windows support. If Windows tests fail, it's likely a test issue, not a uv issue. The windows-validation job uses `continue-on-error: true` so it won't block the workflow.

### System dependencies not installed

System dependencies via `[tool.wads.ops.*]` are handled by the `install-system-deps` action, which is unchanged in the uv template. Verify your `pyproject.toml` has the correct `[tool.wads.ops.*]` sections.
