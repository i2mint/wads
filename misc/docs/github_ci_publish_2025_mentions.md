# Mentions of `github_ci_publish_2025` across the project tree

Generated: 2026-03-16

Context: The new default CI template is `github_ci_uv.yml` (uv-based). The old
`github_ci_publish_2025.yml` still exists for backward compatibility. This report
lists every mention found under `/Users/thorwhalen/Dropbox/py/proj/` and recommends
whether each should be updated, kept, or deprecated.

---

## Legend

| Verdict | Meaning |
|---------|---------|
| **UPDATE** | Should be changed to reference `github_ci_uv` |
| **KEEP** | Intentionally references the 2025 template (backward compat, migration, or testing) |
| **DEPRECATE** | File/section is outdated; mark as deprecated or remove |

---

## 1. wads core package

### `wads/__init__.py` (line 31)

```
github_ci_publish_2025_path = rjoin(data_dir, "github_ci_publish_2025.yml")
```

**Verdict: KEEP.** This export is consumed by migration code and tests that still
need to reference the old template. It should remain as long as `github_ci_publish_2025.yml`
exists. The new `github_ci_uv_path` (line 33) is already the preferred export.

### `wads/populate.py` (lines 29, 922)

```python
from wads import github_ci_publish_2025_path,   # line 29 (import)
    ci_tpl_path = github_ci_uv_path              # line 922 (default)
```

**Verdict: KEEP.** The import on line 29 is present for backward-compat code paths.
The default on line 922 already uses `github_ci_uv_path`. No change needed.

### `wads/migration.py` (lines 60, 704)

```python
github_ci_publish_2025_path,                      # line 60 (import)
new_template = _load_ci_template(github_ci_publish_2025_path)  # line 704
```

**Verdict: KEEP.** `migrate_github_ci_old_to_new` migrates legacy CI files *to* the
2025 template. This is a backward-compat migration path. A separate migration to the
uv template could be added later, but the existing path should remain functional.

### `wads/ci_migration.py` (lines 14, 19, 411, 423, 530, 532, 645, 647)

All occurrences are in **docstrings/doctests** that demonstrate diagnosing old-to-2025
migration.

**Verdict: KEEP.** These document how to migrate to the 2025 template. They should
stay as long as that migration path is supported. Consider adding parallel doctests
for the uv template in the future.

### `wads/config_comparison.py` (lines 36, 339)

```python
from wads import pyproject_toml_tpl_path, github_ci_publish_2025_path  # line 36
template_path: str | Path = github_ci_publish_2025_path,               # line 339
```

**Verdict: UPDATE.** The default `template_path` should point to `github_ci_uv_path`
so that comparisons run against the current default template. The 2025 path can remain
as a supported option but should not be the default.

---

## 2. wads tests

### `wads/tests/test_workflow_template.py` (lines 1, 16)

```python
"""Test the github_ci_publish_2025.yml workflow template."""
return Path(data_dir) / "github_ci_publish_2025.yml"
```

**Verdict: KEEP.** Tests that validate the 2025 template should remain to ensure
backward compatibility. Separate tests for `github_ci_uv.yml` should exist (or be
added) as well.

### `test_integration_system_deps.py` (lines 68, 70, 75)

```python
from wads import github_ci_publish_2025_path
print(f"\n... Using CI template: {Path(github_ci_publish_2025_path).name}")
ci_tpl_path=github_ci_publish_2025_path,
```

**Verdict: KEEP.** This integration test validates the 2025 template's system-deps
support. It should remain. Consider adding a parallel test for the uv template.

---

## 3. Examples

### `examples/analyze_real_ci_files.py` (lines 15, 95)

```python
from wads import github_ci_publish_2025_path
wf, github_ci_publish_2025_path, project_name=project_name
```

**Verdict: UPDATE.** Example scripts guide users; they should demonstrate the current
default template (`github_ci_uv_path`). Either update the default or add a parallel
uv example.

### `examples/ci_migration_demo.py` (lines 17, 86, 100)

```python
from wads import github_ci_publish_2025_path
new_template = GitHubWorkflow(github_ci_publish_2025_path)
old_ci_yaml, github_ci_publish_2025_path, project_name="myproject"
```

**Verdict: KEEP.** This demo shows migration *to* the 2025 template, which is a valid
migration path. Add a note that the uv template is now the preferred target.

---

## 4. CLAUDE.md (project instructions)

### `CLAUDE.md` (lines 15, 57, 73, 76)

- Line 15: "The CI workflow template (`github_ci_publish_2025.yml`) reads configuration..."
- Line 57: directory tree showing `github_ci_publish_2025.yml`
- Line 73: "Copies `wads/data/github_ci_publish_2025.yml` -> `.github/workflows/ci.yml`"
- Line 76: "### CI Workflow Flow (github_ci_publish_2025.yml)"

**Verdict: UPDATE.** CLAUDE.md is the primary agent instruction file. It should
describe the current default (`github_ci_uv.yml`) and mention the 2025 template only
as a backward-compat option.

---

## 5. Claude skills

### `.claude/skills/setup-project.md` (line 50)

```
| `github_ci_publish_2025.yml` | `.github/workflows/ci.yml` |
```

**Verdict: UPDATE.** This skill guides agents through project setup. It should
reference `github_ci_uv.yml` as the default template.

### `.claude/skills/migrate-to-wads.md` (line 148)

```
The template is at: `wads/data/github_ci_publish_2025.yml`
```

**Verdict: UPDATE.** Migration instructions should point to the uv template as the
preferred target, with the 2025 template mentioned as an alternative.

---

## 6. Documentation (misc/docs/)

### `misc/docs/SYSTEM_DEPS_ACTUAL_IMPLEMENTATION.md` (lines 39, 67)

**Verdict: UPDATE.** Should reference the uv template as the current default and note
the 2025 template for context.

### `misc/docs/CI_TESTING_IMPLEMENTATION.md` (lines 38, 189)

**Verdict: UPDATE.** Testing documentation should reflect the current default template.

### `misc/docs/WADS_DESIGN_NOTES.md` (lines 8, 50)

Line 50 already notes: "Replaced by uv template. Keep briefly for backward compat,
then remove."

**Verdict: KEEP.** This file already acknowledges the transition. No change needed.

### `misc/docs/archive/MODERNIZATION_ANALYSIS.md` (lines 83, 281)

**Verdict: KEEP (archived).** This is in the archive directory and documents historical
decisions.

### `misc/docs/archive/MIGRATION_QUICKSTART.md` (line 71)

**Verdict: DEPRECATE.** Archived quickstart should either be updated or marked as
superseded by the uv-based workflow.

### `misc/docs/archive/CI_CONFIG_GUIDE.md` (line 419)

**Verdict: KEEP (archived).** Historical reference in archive.

### `misc/docs/archive/CI_MIGRATION_README.md` (lines 84, 89, 269, 275)

**Verdict: KEEP (archived).** Migration README in archive documents the old workflow.

---

## 7. External project: priv

### `/Users/thorwhalen/Dropbox/py/proj/t/priv/CLAUDE.md` (lines 131, 161)

- Line 131: "Library projects (`project_type='lib'`): uses `github_ci_publish_2025.yml`"
- Line 161: Table pointing to the 2025 template path

**Verdict: UPDATE.** The priv project's CLAUDE.md should reflect that `github_ci_uv.yml`
is now the default for library projects.

### `/Users/thorwhalen/Dropbox/py/proj/t/priv/priv/great_migration.py` (lines 150, 159, 474)

```python
from wads import github_ci_publish_2025_path           # line 150
/ 'github_ci_publish_2025_truly_dynamic.yml'           # line 159
template_path: str | Path = github_ci_publish_2025_path  # line 474
```

**Verdict: UPDATE.** The `great_migration.py` default template should be switched to
`github_ci_uv_path`. The 2025 path can remain importable for explicit backward-compat
usage.

### `/Users/thorwhalen/Dropbox/py/proj/t/priv/CI_APPROACHES_COMPARISON.md` (line 99)

**Verdict: KEEP.** This is a comparison document that discusses design approaches;
historical references are appropriate.

---

## Summary

| Category | Files to UPDATE | Files to KEEP | Files to DEPRECATE |
|----------|----------------|---------------|-------------------|
| Core code | `config_comparison.py` | `__init__.py`, `populate.py`, `migration.py`, `ci_migration.py` | -- |
| Tests | -- | `test_workflow_template.py`, `test_integration_system_deps.py` | -- |
| Examples | `analyze_real_ci_files.py` | `ci_migration_demo.py` | -- |
| Project docs | `CLAUDE.md`, 2 files in `misc/docs/` | `WADS_DESIGN_NOTES.md`, 4 files in `misc/docs/archive/` | `archive/MIGRATION_QUICKSTART.md` |
| Agent skills | `setup-project.md`, `migrate-to-wads.md` | -- | -- |
| External (priv) | `CLAUDE.md`, `great_migration.py` | `CI_APPROACHES_COMPARISON.md` | -- |

**Total: 10 mentions to update, 13 to keep, 1 to deprecate.**
