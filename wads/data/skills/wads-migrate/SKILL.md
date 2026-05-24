---
name: wads-migrate
description: Use when migrating Python projects to modern wads setup (pyproject.toml + uv CI). Triggers on migration tasks, CI modernization, setup.cfg conversion, switching from pip to uv, or moving a repo from inline uv CI to the reusable-workflow stub.
---

# Wads Project Migration

## Overview

Wads manages Python project packaging and CI/CD. Projects exist in four formats:

| Format | pyproject? | `.github/workflows/ci.yml` | Migration command |
|---|---|---|---|
| **Old** | no — `setup.cfg` | old template | `setup-to-pyproject` then `ci-to-uv` |
| **2025** | yes | `github_ci_publish_2025.yml` (inline) | `ci-to-uv` |
| **Modern uv (inline)** | yes | `github_ci_uv.yml` (inline, ~250 lines) | `ci-to-stub` |
| **Modern uv (stub)** ★ | yes | 5-line stub → `i2mint/wads/.github/workflows/uv-ci.yml` | done |

The current default for new projects is the **stub**. The inline form is kept
as an escape valve for repos that need to customize CI beyond `[tool.wads.ci.*]`.

### Why the stub

- One file to fix bugs in across ~180 wads-managed repos.
- `pyproject.toml` is the SSOT for project config; the stub makes CI's *vehicle* SSOT too.
- Visible customization: a non-stub `ci.yml` immediately reads as "this repo customizes CI."

### Cons and how to mitigate

| Con | Mitigation |
|---|---|
| Bad wads merge breaks CI everywhere on next run | Wads's own CI runs the reusable workflow first — canary catches obvious breaks. **Crucially: broken CI ≠ broken release.** Publish is gated on workflow success, so a bad wads change blocks publication for downstream consumers until wads is fixed, but never ships a broken artifact. This is what makes floating `@master` safe by default. |
| Floating `@master` means consumers can't pin a known-good wads state | `wads-migrate ci-to-stub --pin @v0.1.81` writes the stub with a tag pin instead of `@master`. The pinned repo only picks up wads updates when explicitly re-pinned. Use for release-sensitive repos. |
| Reusable workflow has a curated env-var list (PROJECT_NAME, OPENAI_API_KEY, ANTHROPIC_API_KEY, HF_TOKEN, HUGGINGFACE_TOKEN, KAGGLE_USERNAME, KAGGLE_KEY). Other workflow-level secret env vars need to land in wads. | For one-off needs, use the escape valve (drop the stub, copy `github_ci_uv.yml` inline). For ecosystem-wide needs, PR to wads adding the var to the reusable workflow's top-level `env:` block. |
| Reusable workflow can't access caller-only secrets without `secrets: inherit` | The stub always sets `secrets: inherit`. Don't remove it. |

## Detecting Current Format

1. Check for `setup.cfg` → **Old format**
2. Check `.github/workflows/ci.yml` for `setup-python` without `setup-uv` → **2025 format**
3. Check `.github/workflows/ci.yml` for `astral-sh/setup-uv` and `i2mint/wads/actions/run-tests-uv` → **Modern uv (inline)**
4. Check `.github/workflows/ci.yml` for `i2mint/wads/.github/workflows/uv-ci.yml` → **Modern uv (stub)** ★

## Migration: Old → Modern uv (inline)

```bash
# Step 1: Convert setup.cfg to pyproject.toml
wads-migrate setup-to-pyproject setup.cfg -o pyproject.toml

# Step 2: Review pyproject.toml, add [tool.wads.ci] section if needed

# Step 3: Replace CI workflow
wads-migrate ci-to-uv .github/workflows/ci.yml -o .github/workflows/ci.yml

# Step 4: Remove old files (use git rm)
git rm setup.cfg setup.py  # after verifying pyproject.toml is correct
```

Then push, watch CI, and once it's green, **also run `ci-to-stub`** to land
on the SSOT default.

## Migration: 2025 → Modern uv (inline)

```bash
# Replace the CI workflow with the inline uv template.
wads-migrate ci-to-uv .github/workflows/ci.yml -o .github/workflows/ci.yml
```

Then push, watch CI, and once green, run `ci-to-stub`.

## Migration: Modern uv (inline) → Modern uv (stub) ★

After the repo is on the inline uv CI **and CI is green**, convert to the stub:

```bash
# Default: pin @master (floats with wads)
wads-migrate ci-to-stub

# Or freeze to a specific wads tag (for release-sensitive repos):
wads-migrate ci-to-stub --pin @v0.1.81
```

`ci-to-stub` refuses to convert workflows that aren't already on uv-CI — run
`ci-to-uv` first so the per-repo `[tool.wads.ci]` audit happens before the
inline workflow disappears.

## New Project

```bash
populate my-project --root-url https://github.com/user/my-project
# Automatically ships the 5-line stub (since wads 0.1.82).
# To opt in to the inline template instead, copy
# wads/data/github_ci_uv.yml over the generated stub afterwards.
```

## PyPI Auth Requirement

The uv template (and reusable workflow) uses token-only auth. Ensure:
- `PYPI_PASSWORD` GitHub secret is a PyPI API token (starts with `pypi-`)
- `PYPI_USERNAME` secret is no longer needed

## Key Files in Wads

- Reusable workflow (SSOT): `.github/workflows/uv-ci.yml` in i2mint/wads
- Stub template: `wads/data/github_ci_uv_stub.yml`
- Inline template (escape valve): `wads/data/github_ci_uv.yml`
- Config reader: `wads/ci_config.py` (`CIConfig` class)
- Migration: `wads/migration.py` (`migrate_ci_to_uv`, `migrate_ci_to_stub`)
- Project creation: `wads/populate.py` (`populate_pkg_dir`)
- pyproject template: `wads/data/pyproject_toml_tpl.toml`

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

[tool.wads.ci.env]
# Secrets that CI MUST have; workflow fails if missing
required_envvars = []
# Secrets CI should have; tests needing them are skipped/may fail, CI continues
# This is where things like OPENAI_API_KEY, GITHUB_TOKEN go for packages whose
# modules read those env vars at import time
test_envvars = ["OPENAI_API_KEY"]
# Optional secrets; no warnings if missing
extra_envvars = []

[tool.wads.ci.env.defaults]
# LITERAL env values (NOT secrets) injected at workflow level
# Example: PYTHONUNBUFFERED = "1"
```

### Wiring third-party secrets (OPENAI_API_KEY etc.)

If a package's source modules read env vars at *import* time (e.g.
`config2py.get_config("OPENAI_API_KEY")` at module load), the uv CI's wider
pytest collection will fail during import.

**For inline-CI repos**: add the var name to `[tool.wads.ci.env.test_envvars]`
in pyproject.toml, then `wads-migrate ci-to-uv` to re-render the workflow with
a top-level `env:` block wiring `${{ secrets.X || '' }}`. Set the GitHub secret.

**For stub repos**: the reusable workflow has a curated set of common env vars
already (OPENAI_API_KEY, ANTHROPIC_API_KEY, HF_TOKEN, HUGGINGFACE_TOKEN,
KAGGLE_USERNAME, KAGGLE_KEY). Just set the GitHub secret in the consuming
repo — no workflow edit needed. If the var isn't in the curated set, either:
- PR to wads adding it to the reusable workflow's `env:` block (ecosystem-wide), or
- Drop the stub and use inline `github_ci_uv.yml` (one-off).

Do NOT hand-edit job-level `env:` blocks in ci.yml — they'll be wiped on next
migrate. Always wire via `[tool.wads.ci.env]` (inline) or PR to wads (stub).

## Checklist After Migration

- [ ] `pyproject.toml` has correct metadata (name, version, dependencies)
- [ ] `[tool.wads.ci]` section present (or defaults are acceptable)
- [ ] `[tool.wads.ci.env.test_envvars]` lists any secrets the code needs at import time
- [ ] `.github/workflows/ci.yml` is either the 5-line stub OR uses `astral-sh/setup-uv` with a top-level `env:` block
- [ ] `PYPI_PASSWORD` secret is a PyPI API token
- [ ] `setup.cfg` and `setup.py` removed (if migrated from old format)
- [ ] Push to non-main branch to test CI before merging
