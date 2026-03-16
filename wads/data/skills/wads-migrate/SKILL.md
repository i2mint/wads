---
name: wads-migrate
description: Use when migrating Python projects to modern wads setup (pyproject.toml + uv CI). Triggers on migration tasks, CI modernization, setup.cfg conversion, or switching from pip to uv.
---

# Wads Project Migration

## Overview

Wads manages Python project packaging and CI/CD. Projects exist in three formats:
- **Old**: `setup.cfg` + old CI template + Python 3.10 only
- **2025**: `pyproject.toml` + `github_ci_publish_2025.yml` + Python 3.10/3.12
- **Modern (uv)**: `pyproject.toml` + `github_ci_uv.yml` + uv-based CI

The target is always the **modern (uv)** format.

## Detecting Current Format

1. Check for `setup.cfg` → Old format
2. Check `.github/workflows/ci.yml` for `setup-python` without `setup-uv` → 2025 format
3. Check for `astral-sh/setup-uv` → Already modern

## Migration: Old → Modern

```bash
# Step 1: Convert setup.cfg to pyproject.toml
wads-migrate setup-to-pyproject setup.cfg -o pyproject.toml

# Step 2: Review pyproject.toml, add [tool.wads.ci] section if needed

# Step 3: Replace CI workflow
wads-migrate ci-to-uv .github/workflows/ci.yml -o .github/workflows/ci.yml

# Step 4: Remove old files
rm setup.cfg setup.py  # after verifying pyproject.toml is correct
```

## Migration: 2025 → Modern

```bash
# Just replace the CI workflow
wads-migrate ci-to-uv .github/workflows/ci.yml -o .github/workflows/ci.yml
```

## New Project

```bash
populate my-project --root-url https://github.com/user/my-project
# Automatically uses the uv CI template
```

## PyPI Auth Requirement

The uv template uses token-only auth. Ensure:
- `PYPI_PASSWORD` GitHub secret is a PyPI API token (starts with `pypi-`)
- `PYPI_USERNAME` secret is no longer needed

## Key Files in Wads

- Template: `wads/data/github_ci_uv.yml`
- Config reader: `wads/ci_config.py` (CIConfig class)
- Migration: `wads/migration.py` (migrate_ci_to_uv function)
- Project creation: `wads/populate.py` (populate_pkg_dir function)
- Template config: `wads/data/pyproject_toml_tpl.toml`

## pyproject.toml CI Config Reference

```toml
[tool.wads.ci]
installer = "uv"  # or "pip" for legacy

[tool.wads.ci.testing]
python_versions = ["3.10", "3.12"]
pytest_args = ["-v", "--tb=short"]
coverage_enabled = true
exclude_paths = ["examples", "scrap"]
test_on_windows = true

[tool.wads.ci.build]
sdist = true
wheel = true
```

## Checklist After Migration

- [ ] `pyproject.toml` has correct metadata (name, version, dependencies)
- [ ] `[tool.wads.ci]` section present (or defaults are acceptable)
- [ ] `.github/workflows/ci.yml` uses `astral-sh/setup-uv`
- [ ] `PYPI_PASSWORD` secret is a PyPI API token
- [ ] `setup.cfg` and `setup.py` removed (if migrated from old format)
- [ ] Push to non-main branch to test CI before merging
