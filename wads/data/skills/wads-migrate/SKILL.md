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
| A secret your tests need isn't reaching CI | Run `wads-secrets add VAR_NAME` (see "Secrets" below). It declares the var in `[tool.wads.ci.env]` AND adds the pass-through line to the stub. No workflow edit needed unless the name is outside the wads superset (`wads.ci_secrets.DEFAULT_CI_SECRETS`), in which case the CLI warns and you either PR wads to widen the superset or use the inline escape valve. |
| Secrets must reach a reusable workflow owned by a different account | The stub passes secrets **explicitly** (NOT `secrets: inherit`, which is unreliable cross-owner). The stub's `secrets:` block lists each name; it's generated from `[tool.wads.ci.env]` at migrate time and extended by `wads-secrets add`. |

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

**Secrets are carried over automatically.** Both `ci-to-uv` and `ci-to-stub`
(and `fleet-stub`) scan the *existing* workflow's `env:` blocks for
`${{ secrets.X }}` references and inject any not-yet-declared ones into
`[tool.wads.ci.env].extra_envvars` (recording a `secret_aliases` entry when the
env-var name differs from the secret name). So a migration is **lossless** — you
don't lose secrets that were wired only in the old YAML. The command prints what
it carried; review them afterward and promote to `required`/`test` if a test
truly depends on one. Use `wads-secrets add` only for secrets the old workflow
did **not** already reference (e.g. a brand-new dependency).

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

**For stub repos** (the default since wads 0.1.82): the simplest path is

```bash
wads-secrets add OPENAI_API_KEY          # VAR == secret name
wads-secrets add HF_TOKEN HF_WRITE_TOKEN  # env var <- aliased secret
wads-secrets add DB_URL --kind required   # fail CI if unset
```

This (a) declares the var in `[tool.wads.ci.env]` so the `export-ci-env` step
writes it into the job environment, (b) adds the pass-through line to the stub's
`secrets:` block so the secret is transported to the reusable workflow, and (c)
`gh secret set`s the value if `gh` is installed (value from `$VAR_NAME` or
`--value`). See the **Secrets** section below for the full model. If the secret
name is outside the wads superset (`wads.ci_secrets.DEFAULT_CI_SECRETS`), the CLI
warns; either PR wads to widen the superset (one line, ecosystem-wide) or use the
inline `github_ci_uv.yml` escape valve.

Do NOT hand-edit job-level `env:` blocks in ci.yml. Declare via
`[tool.wads.ci.env]` (or `wads-secrets add`, which is the safe way to do both).

## Secrets (two-layer model)

Secrets reach a stub repo's CI through two coordinated layers:

1. **Transport** — the stub's `secrets:` block *passes* named secrets to the
   reusable workflow. Explicit pass-through is used (NOT `secrets: inherit`,
   which is unreliable across GitHub accounts). The *universe* of passable
   names is the superset declared in the wads-side `uv-ci.yml`
   (`on.workflow_call.secrets`), generated from `wads.ci_secrets.DEFAULT_CI_SECRETS`.
   Each repo's stub passes only `PYPI_PASSWORD` + the names it actually uses.
2. **Env-assignment** — `[tool.wads.ci.env]` (`required_envvars`,
   `test_envvars`, `extra_envvars`, `defaults`, and `secret_aliases` for
   ENV_VAR≠SECRET_NAME) decides which passed secrets become job env vars. The
   `export-ci-env` action writes exactly those to `$GITHUB_ENV` and **fails the
   build** if a `required` secret is unset. A passed-but-undeclared secret is
   never written to the env (no over-assignment).

**`wads-secrets add VAR_NAME [SECRET_NAME]`** does both layers (+ `gh secret set`)
in one step — the recommended way. `wads-secrets list` shows what's configured;
`wads-secrets superset` prints the allowed names. For a name outside the
superset: PR `wads.ci_secrets.DEFAULT_CI_SECRETS` (benefits all repos) or use the
inline `github_ci_uv.yml` escape valve.

Publishing runs only on the repo's **default branch**, when validation passes,
when the commit isn't `[skip ci]`, and when `[tool.wads.ci.publish].enabled`.

## Checklist After Migration

- [ ] `pyproject.toml` has correct metadata (name, version, dependencies)
- [ ] `[tool.wads.ci]` section present (or defaults are acceptable)
- [ ] Secrets the code needs are configured via `wads-secrets add` (declares in
      `[tool.wads.ci.env]` AND passes them in the stub's `secrets:` block)
- [ ] `.github/workflows/ci.yml` is the stub (calls `uv-ci.yml@master`) OR the
      inline `github_ci_uv.yml` escape valve
- [ ] `PYPI_PASSWORD` secret is a PyPI API token
- [ ] `setup.cfg` and `setup.py` removed (if migrated from old format)
- [ ] Push to non-main branch to test CI before merging
