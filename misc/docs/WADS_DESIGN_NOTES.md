# Wads Design Notes: Simplification & Modernization

## Current State (March 2026)

Wads has accumulated layers of tooling over the years to support multiple project formats:

1. **Old format**: `setup.cfg` + `setup.py` + old CI templates (single Python 3.10)
2. **2025 format**: `pyproject.toml` (Hatchling) + `github_ci_publish_2025.yml` + matrix testing (3.10, 3.12)
3. **Target format**: `pyproject.toml` (Hatchling) + uv-based CI template

Once all i2mint projects are migrated to the uv format, a significant cleanup is possible.

---

## What to Keep (Core)

These are well-designed, actively used, and should be the foundation of a simplified wads:

### Templates
- `pyproject_toml_tpl.toml` — Good. pyproject.toml is tool-agnostic, works with uv and pip.
- `github_ci_uv.yml` — The new default CI template (to be created).
- `.gitignore_tpl`, `.gitattributes_tpl`, `.editorconfig_tpl` — Simple, useful.
- Issue/PR templates, dependabot config — Low maintenance, good to keep.

### Python Modules
- **`populate.py`** — Core project creation. Worth cleaning up once old format support is dropped (remove setup.cfg generation paths, simplify `_resolve_ci_def_and_tpl_path`).
- **`ci_config.py`** (`CIConfig` class) — Clean design, reads `[tool.wads.ci]` from pyproject.toml. This is the SSOT reader.
- **`toml_util.py`** — Small, focused TOML helpers.
- **`util.py`** — Git utilities, logging. Review for dead code but mostly useful.
- **`pack.py`** — Package building/publishing CLI. May be largely replaceable by `uv build && uv publish` but keeping a thin wrapper is fine for the `pack go .` UX.

### Actions (to keep)
- `read-ci-config/` — Reads `[tool.wads.ci]`, exports as GitHub outputs. Complex enough to warrant encapsulation.
- `install-system-deps/` — Handles `[tool.wads.ops.*]` for apt-get/brew packages. Not pip-related.
- `git-commit/` — SSH-based git push. Non-trivial SSH agent setup.
- `git-tag/` — Simple but useful.

### Scripts
- `read_ci_config.py` — Backing script for read-ci-config action.
- `set_env_vars.py` — Environment variable management from secrets.
- `validate_ci_env.py` — Standalone validator.

---

## What to Remove (After Migration)

### Templates (legacy)
- `github_ci_tpl.yml` — Old CI template (pre-2025). No longer needed once all projects migrated.
- `github_ci_tpl_publish.yml` — Old publish variant.
- `github_ci_publish_2025.yml` — Replaced by uv template. Keep briefly for backward compat, then remove.
- `gitlab_ci_tpl.yml` — Check if any projects use GitLab CI. If not, remove.
- `setup_tpl/` — Old setup.cfg/setup.py templates. Not needed with pyproject.toml.

### Actions (become trivial with uv)
These actions exist primarily to wrap `pip install X && X` patterns. With uv, they're one-liners in the CI template:

| Action | uv replacement | Notes |
|--------|---------------|-------|
| `install-deps/` | `uv pip install -e ".[dev]"` (in a venv) | The most complex action, but uv makes it trivial |
| `ruff-format/` | `uvx ruff format .` | 4 lines of YAML → 1 line |
| `ruff-lint/` | `uvx ruff check` | Same |
| `run-tests/` | `uv run pytest [args]` | Pytest arg building could move to a script if needed |
| `build-dist/` | `uv build` | Replaces `python -m build` + the build_dist.py script |
| `pypi-upload/` | `uv publish` | Replaces twine |
| `windows-tests/` | Inline in template | |
| `set-env-vars/` | Keep the script, remove the action wrapper if not used |

### Python Modules (legacy support)
- **`migration.py`** — Keep migration functions for old→uv and 2025→uv. Remove setup.cfg parsing helpers once all projects migrated.
- **`ci_migration.py`** — CI workflow comparison/diagnosis. Useful during migration, removable after.
- **`config_comparison.py`** — Template comparison tools. Useful during migration.
- **`install_system_deps.py`** — Keep (still used by the install-system-deps action).

### Scripts (legacy)
- `build_dist.py` — Replaced by `uv build`. Remove once no action references it.
- `install_deps.py` — Replaced by `uv sync`. Remove once no action references it.

### Agents
- `wads-ci-debug`, `wads-deps`, `wads-test-analyze` — Review usage. If rarely used, consider removing or moving to a separate package.

---

## Simplification Roadmap

### Phase 1: Add uv support (current work)
- Create `github_ci_uv.yml` template
- Make it the default in `populate`
- Add migration commands

### Phase 2: Migrate i2mint projects
- Run `wads-migrate ci-2025-to-uv` on all 2025-format projects
- Run `wads-migrate setup-to-pyproject` then `ci-2025-to-uv` on old-format projects
- Verify CI passes for each

### Phase 3: Deprecation period
- Add deprecation warnings to old code paths
- Log which actions/templates are still being used
- Keep old actions working but stop maintaining them

### Phase 4: Cleanup
- Remove legacy CI templates (old, 2025)
- Remove `setup_tpl/` directory
- Remove setup.cfg parsing from migration.py
- Remove composite actions replaced by uv one-liners
- Remove `build_dist.py` and `install_deps.py` scripts
- Simplify `populate.py` (remove old format branches)
- Simplify `pack.py` (use uv directly)
- Target: wads should be ~50% smaller in LOC

### Phase 5: Potential further simplification
- Consider whether `pack.py` is still needed (vs just `uv build && uv publish`)
- Consider whether `read-ci-config` action is still needed if the CI template becomes simple enough
- Consider moving agents to a separate package (`wads-agents` or similar)

---

## Testing Strategy for Simplified Wads

Once cleanup is done, ensure these scenarios are covered:

1. **`populate new-project`** → generates valid pyproject.toml + uv CI + all scaffolding
2. **Push to GitHub** → uv CI runs: format, lint, test, publish
3. **Matrix testing** → Python 3.10 and 3.12 both pass
4. **Windows testing** → Optional Windows job works with uv
5. **System deps** → `[tool.wads.ops.*]` packages get installed
6. **Version bumping** → isee semver works, pyproject.toml updated
7. **PyPI publish** → `uv publish` succeeds with token auth
8. **`pack go .`** → Still works as a local build+publish shortcut

---

## Architecture Notes

### Good patterns to preserve
- **pyproject.toml as SSOT** — All config in one place, CI reads it dynamically
- **`CIConfig` class** — Clean Python interface to `[tool.wads.ci]` config
- **`PopulateTracker`** — Nice UX for project creation feedback
- **Template-based approach** — CI workflow is a static template, not generated code

### Patterns to reconsider
- **Composite actions for trivial operations** — With uv, most actions are one-liners. Inline them.
- **Multiple CI template variants** — Aim for ONE template (uv). App/deploy is the only legitimate variant.
- **`isee` dependency for version bumping** — Consider whether version bumping logic should live in wads instead, reducing cross-repo dependencies.
