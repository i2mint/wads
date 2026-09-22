# wads.repo_audit

Read-only health audit of a (wads-managed) Python repo.

Checks every health dimension a repo doctor cares about — legacy packaging
leftovers, pyproject metadata shape, CI workflow generation (uv stub / inline
uv / 2025 / legacy / none), stale test paths, module docstring presence,
GitHub metadata drift (description / homepage / topics vs pyproject), Pages
status, latest CI run conclusion, and PyPI-vs-pyproject version sync — and
prints a prioritized report grouped HIGH / MEDIUM / LOW, each finding tagged
with the specialist skill (or CLI) that owns the fix.

This module is the **single source of truth** for the ecosystem’s “what is a
modern wads repo” classification. Import it:

```default
from wads.repo_audit import audit_repo
report = audit_repo("/path/to/repo", network=False)   # dict: facts + findings
```

or run it as a script / module:

```default
python -m wads.repo_audit [REPO_DIR] [--json] [--no-network]
```

REPO_DIR defaults to the current directory. `--json` emits the full
machine-readable report. `--no-network` skips everything that leaves the
machine (gh calls and the PyPI lookup); it also degrades gracefully when
`gh` is absent or offline.

Stdlib only. Strictly read-only: never modifies the target repo or anything
else. The `wads-repo-doctor` skill ships a thin shim (`scripts/repo_audit.py`)
that defers to this module.

### Functions

| `audit_ci`(repo, rep)                                                                       |                                                                     |
|---------------------------------------------------------------------------------------------|---------------------------------------------------------------------|
| `audit_files`(repo, rep)                                                                    |                                                                     |
| `audit_git`(repo, rep)                                                                      |                                                                     |
| [`audit_github`](#wads.repo_audit.audit_github)(repo_slug, rep, project, ...) | gh-based checks; every step degrades silently when gh/network fail. |
| `audit_package`(repo, rep, project_name)                                                    |                                                                     |
| `audit_pypi`(rep, project)                                                                  |                                                                     |
| `audit_pyproject`(repo, rep)                                                                |                                                                     |
| [`audit_repo`](#wads.repo_audit.audit_repo)([repo, network])                | Audit a repo and return the machine-readable report dict.           |
| `audit_skills`(repo, rep, project_name)                                                     |                                                                     |
| [`classify_workflow`](#wads.repo_audit.classify_workflow)(text)                    | Classify one workflow file's text into a wads CI generation.        |
| `find_package_dir`(repo, project_name)                                                      |                                                                     |
| `main`([argv])                                                                              |                                                                     |
| `read_pyproject`(repo)                                                                      |                                                                     |
| `render_text`(rep)                                                                          |                                                                     |

### Classes

| [`Report`](#wads.repo_audit.Report)(repo)   | Accumulates facts and findings; renders text or JSON.   |
|-----------------------------------------------------------------|---------------------------------------------------------|

### *class* wads.repo_audit.Report(repo)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Accumulates facts and findings; renders text or JSON.

### wads.repo_audit.audit_github(repo_slug, rep, project, docs_enabled)

gh-based checks; every step degrades silently when gh/network fail.

### wads.repo_audit.audit_repo(repo='.', , network=True)

Audit a repo and return the machine-readable report dict.

This is the importable entry point (the SSOT classifier). It returns the
same structure as `python -m wads.repo_audit <repo> --json`:

```default
{"repo": ..., "summary": {HIGH/MEDIUM/LOW counts},
 "findings": [...], "facts": {...}}
```

`network=False` skips everything that leaves the machine (`gh` + PyPI),
matching the `--no-network` CLI flag.

### wads.repo_audit.classify_workflow(text)

Classify one workflow file’s text into a wads CI generation.
