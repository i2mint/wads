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

Needs only wads’ core dependencies. Strictly read-only: never modifies the target repo or anything
else. The `wads-repo-doctor` skill ships a thin shim (`scripts/repo_audit.py`)
that defers to this module.

### Functions

| `audit_ci`(repo, rep)                                                                            |                                                                                           |
|--------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------|
| `audit_files`(repo, rep)                                                                         |                                                                                           |
| `audit_git`(repo, rep)                                                                           |                                                                                           |
| [`audit_github`](#wads.repo_audit.audit_github)(repo_slug, rep, project, ...)      | gh-based checks; every step degrades silently when gh/network fail.                       |
| [`audit_inline_trigger_gate`](#wads.repo_audit.audit_inline_trigger_gate)(repo, rep, text)      | Flag an inline workflow copy that predates the trigger gate while pyproject is on-demand. |
| `audit_package`(repo, rep, project_name)                                                         |                                                                                           |
| `audit_pypi`(rep, project)                                                                       |                                                                                           |
| `audit_pyproject`(repo, rep)                                                                     |                                                                                           |
| [`audit_repo`](#wads.repo_audit.audit_repo)([repo, network])                     | Audit a repo and return the machine-readable report dict.                                 |
| `audit_skills`(repo, rep, project_name)                                                          |                                                                                           |
| [`audit_trigger_drift`](#wads.repo_audit.audit_trigger_drift)(repo, rep, stub_text)       | Flag a stub whose on-demand pre-filter markers differ from `[tool.wads.ci.trigger]`.      |
| [`audit_url_owners`](#wads.repo_audit.audit_url_owners)(repo, rep, project, repo_slug) | Flag URLs (pyproject urls, README) whose owner differs from the git remote's.             |
| [`classify_workflow`](#wads.repo_audit.classify_workflow)(text)                         | Classify one workflow file's text into a wads CI generation.                              |
| `find_package_dir`(repo, project_name)                                                           |                                                                                           |
| `main`([argv])                                                                                   |                                                                                           |
| [`owner_mismatched_urls`](#wads.repo_audit.owner_mismatched_urls)(text, repo_slug)          | GitHub / Pages URLs in *text* naming this repo under a different owner.                   |
| `read_pyproject`(repo)                                                                           |                                                                                           |
| `render_text`(rep)                                                                               |                                                                                           |

### Classes

| [`Report`](#wads.repo_audit.Report)(repo)   | Accumulates facts and findings; renders text or JSON.   |
|-----------------------------------------------------------------|---------------------------------------------------------|

### *class* wads.repo_audit.Report(repo)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Accumulates facts and findings; renders text or JSON.

### wads.repo_audit.audit_github(repo_slug, rep, project, docs_enabled)

gh-based checks; every step degrades silently when gh/network fail.

### wads.repo_audit.audit_inline_trigger_gate(repo, rep, text)

Flag an inline workflow copy that predates the trigger gate while pyproject is on-demand.

The inline workflow reads the trigger at run time, so it cannot go stale on a marker;
but a copy without the gate ignores `mode = "on-demand"` and runs on every push.

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

### wads.repo_audit.audit_trigger_drift(repo, rep, stub_text)

Flag a stub whose on-demand pre-filter markers differ from `[tool.wads.ci.trigger]`.

A stale pre-filter silently runs nothing for a marker pyproject declares (the
workflow behind it is fine): the fix is always a re-render.

### wads.repo_audit.audit_url_owners(repo, rep, project, repo_slug)

Flag URLs (pyproject urls, README) whose owner differs from the git remote’s.

### wads.repo_audit.classify_workflow(text)

Classify one workflow file’s text into a wads CI generation.

### wads.repo_audit.owner_mismatched_urls(text, repo_slug)

GitHub / Pages URLs in *text* naming this repo under a different owner.

A repo transferred to another owner keeps the old one in generated URLs. Only
URLs whose repo name equals the remote’s are flagged, so links to unrelated
projects are left alone.

```pycon
>>> owner_mismatched_urls("https://github.com/old/pkg and https://github.com/x/y", "new/pkg")
['github.com/old/pkg']
>>> owner_mismatched_urls("https://old.github.io/pkg/", "new/pkg")
['old.github.io/pkg']
>>> owner_mismatched_urls("https://github.com/new/pkg", "new/pkg")
[]
```
