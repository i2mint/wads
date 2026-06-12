#!/usr/bin/env python3
"""Read-only health audit of a (wads-managed) Python repo.

Checks every health dimension a repo doctor cares about — legacy packaging
leftovers, pyproject metadata shape, CI workflow generation (uv stub / inline
uv / 2025 / legacy / none), stale test paths, module docstring presence,
GitHub metadata drift (description / homepage / topics vs pyproject), Pages
status, latest CI run conclusion, and PyPI-vs-pyproject version sync — and
prints a prioritized report grouped HIGH / MEDIUM / LOW, each finding tagged
with the specialist skill (or CLI) that owns the fix.

Usage::

    python repo_audit.py [REPO_DIR] [--json] [--no-network]

REPO_DIR defaults to the current directory. ``--json`` emits the full
machine-readable report. ``--no-network`` skips everything that leaves the
machine (gh calls and the PyPI lookup); the script also degrades gracefully
when ``gh`` is absent or offline.

Stdlib only. Strictly read-only: never modifies the target repo or anything
else.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

try:  # Python 3.11+
    import tomllib  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    try:
        import tomli as tomllib  # type: ignore
    except ModuleNotFoundError:
        tomllib = None  # degrade: skip pyproject parsing

SEVERITIES = ("HIGH", "MEDIUM", "LOW")

# Target action pins for the inline uv workflow (bump when wads bumps its CI).
TARGET_CHECKOUT = "v6"
TARGET_SETUP_UV_MAJOR = 7

# Directories never counted as package modules / docstring denominator.
_SKIP_DIRS = {
    "tests",
    "test",
    "examples",
    "scrap",
    "docs",
    "docsrc",
    "build",
    "dist",
    "__pycache__",
    "node_modules",
}

_RE_REUSABLE = re.compile(r"i2mint/wads/\.github/workflows/uv-ci\.yml@([\w.\-]+)")
_RE_NPM_STUB = re.compile(
    r"i2mint/wads/\.github/workflows/(npm-ci[\w\-]*)\.yml@([\w.\-]+)"
)
_RE_SETUP_UV = re.compile(r"astral-sh/setup-uv@([\w.\-]+)")
_RE_CHECKOUT = re.compile(r"actions/checkout@([\w.\-]+)")
_RE_SETUP_PYTHON = re.compile(r"actions/setup-python@([\w.\-]+)")
_RE_RUN_TESTS_UV = re.compile(r"i2mint/wads/actions/run-tests-uv@")
_RE_WORKFLOW_NAME = re.compile(r"^name:\s*(.+?)\s*$", re.MULTILINE)


# --- small helpers ----------------------------------------------------------


def _run(cmd, *, timeout=20):
    """Run a command; return (returncode, stdout). Never raises."""
    try:
        out = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        return out.returncode, out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return 1, ""


def _uniq(regex, text):
    seen = []
    for v in regex.findall(text):
        if v not in seen:
            seen.append(v)
    return seen


def _int_prefix(version):
    """Leading integer components of a version string: '0.3.44' -> [0, 3, 44]."""
    parts = []
    for tok in re.split(r"[.\-+]", version.strip()):
        if tok.isdigit():
            parts.append(int(tok))
        else:
            break
    return parts


def _slugify_topic(keyword):
    """GitHub topic rules: lowercase alphanumeric + hyphens, <= 35 chars."""
    slug = re.sub(r"[^a-z0-9-]+", "-", keyword.lower().replace("_", "-"))
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug[:35]


class Report:
    """Accumulates facts and findings; renders text or JSON."""

    def __init__(self, repo):
        self.repo = repo
        self.facts = {}
        self.findings = []

    def add(self, severity, dimension, summary, dispatch):
        assert severity in SEVERITIES
        self.findings.append(
            {
                "severity": severity,
                "dimension": dimension,
                "summary": summary,
                "dispatch": dispatch,
            }
        )

    def to_dict(self):
        counts = {s: 0 for s in SEVERITIES}
        for f in self.findings:
            counts[f["severity"]] += 1
        return {
            "repo": str(self.repo),
            "summary": counts,
            "findings": sorted(
                self.findings, key=lambda f: SEVERITIES.index(f["severity"])
            ),
            "facts": self.facts,
        }


# --- pyproject --------------------------------------------------------------


def read_pyproject(repo):
    path = repo / "pyproject.toml"
    if not path.exists() or tomllib is None:
        return None
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except Exception:
        return {}  # unparseable: caller flags it


def audit_pyproject(repo, rep):
    data = read_pyproject(repo)
    rep.facts["has_pyproject"] = (repo / "pyproject.toml").exists()
    if not rep.facts["has_pyproject"]:
        rep.add(
            "HIGH",
            "packaging",
            "no pyproject.toml — repo predates modern wads setup",
            "wads-migrate",
        )
        return {}
    if data is None:
        rep.facts["pyproject_parsed"] = False
        return {}
    if data == {}:
        rep.add(
            "HIGH", "packaging", "pyproject.toml fails to parse as TOML", "wads-migrate"
        )
        return {}
    rep.facts["pyproject_parsed"] = True

    project = data.get("project", {})
    backend = data.get("build-system", {}).get("build-backend", "")
    rep.facts["build_backend"] = backend
    rep.facts["project_name"] = project.get("name")
    rep.facts["project_version"] = project.get("version")
    rep.facts["has_wads_ci_section"] = "ci" in data.get("tool", {}).get("wads", {})

    if backend.startswith("setuptools"):
        rep.add(
            "MEDIUM",
            "packaging",
            f"build backend is {backend} (ecosystem standard is hatchling)",
            "wads-migrate",
        )
    elif backend and "hatchling" not in backend:
        rep.add(
            "LOW",
            "packaging",
            f"non-hatchling build backend ({backend}) — fine if intentional",
            "wads-migrate",
        )

    # license form: PEP 639 SPDX string vs deprecated table
    license_val = project.get("license")
    if isinstance(license_val, dict):
        rep.add(
            "LOW",
            "pypi-metadata",
            "license uses the deprecated table form — prefer an SPDX string "
            '(license = "MIT")',
            "wads-pypi-polish",
        )
    rep.facts["license_form"] = (
        "spdx-string"
        if isinstance(license_val, str)
        else "table"
        if isinstance(license_val, dict)
        else "missing"
    )

    missing_meta = [
        field
        for field in ("description", "urls", "classifiers", "keywords", "requires-python")
        if not project.get(field)
    ]
    if license_val is None:
        missing_meta.append("license")
    if missing_meta:
        rep.add(
            "LOW",
            "pypi-metadata",
            f"[project] metadata gaps: {', '.join(missing_meta)}",
            "wads-pypi-polish",
        )

    # testpaths: declared but nonexistent paths are a real ecosystem bug
    testpaths = (
        data.get("tool", {}).get("pytest", {}).get("ini_options", {}).get("testpaths")
    ) or []
    rep.facts["testpaths"] = testpaths
    stale = [p for p in testpaths if not (repo / p).exists()]
    if stale:
        rep.add(
            "MEDIUM",
            "tests",
            f"declared testpaths missing on disk: {stale} — pytest silently "
            "falls back to rootdir collection",
            "wads-test-coverage",
        )
    return project


# --- file presence ----------------------------------------------------------


def audit_files(repo, rep):
    legacy = [
        name
        for name in ("setup.cfg", "setup.py", "MANIFEST.in", "requirements.txt")
        if (repo / name).exists()
    ]
    rep.facts["legacy_files"] = legacy
    if legacy:
        rep.add(
            "MEDIUM",
            "packaging",
            f"legacy packaging files present: {', '.join(legacy)}",
            "wads-migrate",
        )

    rep.facts["has_readme"] = any(repo.glob("README*"))
    rep.facts["has_license_file"] = any(repo.glob("LICEN[CS]E*"))
    rep.facts["has_changelog"] = any(repo.glob("CHANGELOG*")) or any(
        repo.glob("CHANGES*")
    )
    rep.facts["has_docsrc"] = (repo / "docsrc").is_dir()

    if not rep.facts["has_readme"]:
        rep.add("MEDIUM", "docs", "no README found", "wads-docs-coverage")
    if not rep.facts["has_license_file"]:
        rep.add("MEDIUM", "pypi-metadata", "no LICENSE file found", "wads-pypi-polish")
    for name in (".gitignore", ".editorconfig"):
        present = (repo / name).exists()
        rep.facts[f"has_{name.lstrip('.')}"] = present
        if not present:
            rep.add(
                "LOW",
                "scaffolding",
                f"missing {name} (wads templates ship one)",
                "wads-repo-doctor (inline)",
            )


# --- CI workflows -----------------------------------------------------------


def classify_workflow(text):
    """Classify one workflow file's text into a wads CI generation."""
    info = {
        "reusable_pins": _uniq(_RE_REUSABLE, text),
        "setup_uv": _uniq(_RE_SETUP_UV, text),
        "checkout": _uniq(_RE_CHECKOUT, text),
        "setup_python": _uniq(_RE_SETUP_PYTHON, text),
        "names": _uniq(_RE_WORKFLOW_NAME, text),
    }
    if info["reusable_pins"]:
        info["format"] = "uv-stub"
    elif info["setup_uv"] or _RE_RUN_TESTS_UV.search(text):
        info["format"] = "uv-inline"
        checkout_ok = info["checkout"] == [TARGET_CHECKOUT]
        uv_ok = bool(info["setup_uv"]) and all(
            (m := re.match(r"v(\d+)", v)) and int(m.group(1)) >= TARGET_SETUP_UV_MAJOR
            for v in info["setup_uv"]
        )
        info["stale_pins"] = not (checkout_ok and uv_ok)
    elif info["setup_python"]:
        info["format"] = (
            "ci-2025" if any("2025" in n for n in info["names"]) else "legacy"
        )
    else:
        info["format"] = "unknown"
    return info


def audit_ci(repo, rep):
    wf_dir = repo / ".github" / "workflows"
    wf_files = (
        sorted(wf_dir.glob("*.yml")) + sorted(wf_dir.glob("*.yaml"))
        if wf_dir.is_dir()
        else []
    )
    rep.facts["workflow_files"] = [f.name for f in wf_files]
    if not wf_files:
        rep.facts["ci_format"] = "none"
        rep.add(
            "HIGH",
            "ci",
            "no CI workflows at all — nothing tests or publishes this repo",
            "wads-migrate",
        )
        return

    # npm stubs (frontend components) across all workflow files
    npm_stubs = []
    for f in wf_files:
        try:
            text = f.read_text(errors="replace")
        except OSError:
            continue
        for wf_name, pin in _RE_NPM_STUB.findall(text):
            npm_stubs.append({"file": f.name, "workflow": wf_name, "pin": pin})
    rep.facts["npm_ci_stubs"] = npm_stubs

    # primary classification: ci.yml (the wads convention)
    primary = next((f for f in wf_files if f.name in ("ci.yml", "ci.yaml")), None)
    if primary is None:
        rep.facts["ci_format"] = "unknown"
        rep.add(
            "MEDIUM",
            "ci",
            f"no ci.yml — workflows present: {rep.facts['workflow_files']}; "
            "inspect manually",
            "wads-ci-health",
        )
        return
    try:
        text = primary.read_text(errors="replace")
    except OSError:
        text = ""
    info = classify_workflow(text)
    rep.facts["ci_format"] = info["format"]
    rep.facts["ci_action_pins"] = {
        k: info[k] for k in ("reusable_pins", "setup_uv", "checkout", "setup_python")
    }

    if info["format"] == "uv-stub":
        pins = info["reusable_pins"]
        rep.facts["ci_stub_pin"] = pins
        # On the SSOT stub: nothing to flag. A tag pin is a sanctioned choice.
    elif info["format"] == "uv-inline":
        if info.get("stale_pins"):
            rep.add(
                "MEDIUM",
                "ci",
                f"inline uv CI has stale action pins (checkout={info['checkout']}, "
                f"setup-uv={info['setup_uv']}; target checkout@{TARGET_CHECKOUT}, "
                f"setup-uv@v{TARGET_SETUP_UV_MAJOR}+)",
                "wads-ci-health",
            )
        rep.add(
            "LOW",
            "ci",
            "inline uv CI could become the 5-line SSOT stub "
            "(`wads-migrate ci-to-stub`) — skip if the inline escape valve "
            "is intentional",
            "wads-migrate",
        )
    elif info["format"] in ("ci-2025", "legacy"):
        rep.add(
            "MEDIUM",
            "ci",
            f"CI is the {info['format']} generation (setup-python, no uv) — "
            "migrate to the uv stub",
            "wads-migrate",
        )
    else:
        rep.add(
            "MEDIUM",
            "ci",
            "ci.yml is not a recognized wads format — inspect manually",
            "wads-ci-health",
        )


# --- package / tests / docstrings -------------------------------------------


def find_package_dir(repo, project_name):
    candidates = []
    if project_name:
        for base in (repo, repo / "src"):
            for nm in (project_name.replace("-", "_"), project_name):
                d = base / nm
                if (d / "__init__.py").exists():
                    return d
    for child in sorted(repo.iterdir()):
        if (
            child.is_dir()
            and not child.name.startswith(".")
            and child.name.lower() not in _SKIP_DIRS
            and (child / "__init__.py").exists()
        ):
            candidates.append(child)
    return candidates[0] if candidates else None


def _package_modules(pkg_dir):
    for path in sorted(pkg_dir.rglob("*.py")):
        rel_parts = path.relative_to(pkg_dir).parts
        if any(part.lower() in _SKIP_DIRS for part in rel_parts[:-1]):
            continue
        yield path


def audit_package(repo, rep, project_name):
    pkg_dir = find_package_dir(repo, project_name)
    rep.facts["package_dir"] = str(pkg_dir.relative_to(repo)) if pkg_dir else None
    if pkg_dir is None:
        rep.add(
            "MEDIUM",
            "packaging",
            "could not locate a package directory (no __init__.py found)",
            "wads-migrate",
        )
        return

    rep.facts["has_py_typed"] = (pkg_dir / "py.typed").exists()

    modules = list(_package_modules(pkg_dir))
    rep.facts["module_count"] = len(modules)
    missing_doc = []
    for mod in modules:
        try:
            tree = ast.parse(mod.read_text(errors="replace"))
        except SyntaxError:
            continue
        if not ast.get_docstring(tree):
            missing_doc.append(str(mod.relative_to(repo)))
    rep.facts["modules_missing_docstring"] = missing_doc
    if missing_doc:
        shown = ", ".join(missing_doc[:8]) + (
            f", … (+{len(missing_doc) - 8})" if len(missing_doc) > 8 else ""
        )
        rep.add(
            "MEDIUM",
            "docs",
            f"{len(missing_doc)}/{len(modules)} modules lack a top-level "
            f"docstring: {shown}",
            "wads-docs-coverage",
        )

    # tests: declared testpaths plus the conventional locations
    test_dirs = []
    for p in rep.facts.get("testpaths", []):
        if (repo / p).is_dir():
            test_dirs.append(repo / p)
    for d in (repo / "tests", pkg_dir / "tests", pkg_dir / "test"):
        if d.is_dir() and d not in test_dirs:
            test_dirs.append(d)
    test_files = set()
    for d in test_dirs:
        for f in d.rglob("*.py"):
            if f.name.startswith("test_") or f.name.endswith("_test.py"):
                test_files.add(f)
    rep.facts["test_dirs"] = [str(d.relative_to(repo)) for d in test_dirs]
    rep.facts["test_file_count"] = len(test_files)
    if not test_files:
        rep.add(
            "MEDIUM",
            "tests",
            "no test files found (note: CI runs --doctest-modules, so doctests "
            "may still cover the code — wads-test-coverage attributes that)",
            "wads-test-coverage",
        )


# --- skills -----------------------------------------------------------------


def audit_skills(repo, rep, project_name):
    skill_dirs = []
    seen_targets = set()  # resolved paths, so symlink + target count once
    # repo-root skills/ first: it's the canonical location (wads-skillify),
    # so a compliant layout reports the real dir, not its .claude symlink.
    roots = [repo / "skills", repo / ".claude" / "skills"]
    if project_name:
        pkg = project_name.replace("-", "_")
        roots.append(repo / pkg / "data" / "skills")
    for root in roots:
        if not root.is_dir():
            continue
        for d in sorted(root.iterdir()):
            if not (d / "SKILL.md").exists():
                continue
            target = d.resolve()
            if target in seen_targets:
                continue
            seen_targets.add(target)
            skill_dirs.append(d)
    rep.facts["skills"] = [str(d.relative_to(repo)) for d in skill_dirs]
    if not skill_dirs:
        rep.add(
            "LOW",
            "skills",
            "no agent skills found (skills/, .claude/skills/, or "
            "<pkg>/data/skills/)",
            "wads-skillify",
        )
        return
    mismatched = []
    for d in skill_dirs:
        try:
            head = (d / "SKILL.md").read_text(errors="replace")[:500]
        except OSError:
            continue
        m = re.search(r"^name:\s*(\S+)", head, re.MULTILINE)
        if m:
            fm_name = m.group(1).strip("'\"")  # name: "foo" is valid YAML
            if fm_name != d.name:
                mismatched.append(f"{d.name} (frontmatter name: {fm_name})")
    if mismatched:
        rep.add(
            "LOW",
            "skills",
            f"skill frontmatter name != directory name: {', '.join(mismatched)}",
            "wads-skillify",
        )


# --- git / GitHub / PyPI ----------------------------------------------------


def audit_git(repo, rep):
    rep.facts["is_git_repo"] = (repo / ".git").exists()
    if not rep.facts["is_git_repo"]:
        rep.add(
            "HIGH", "git", "not a git repository — `git init` first", "wads-migrate"
        )
        return None
    rc, url = _run(["git", "-C", str(repo), "remote", "get-url", "origin"])
    if rc != 0 or not url:
        rep.facts["origin_url"] = None
        rep.add(
            "LOW",
            "git",
            "no origin remote — GitHub-side checks skipped",
            "wads-repo-doctor (inline)",
        )
        return None
    url = re.sub(r"^git@([^:]+):", r"https://\1/", url)
    url = url[:-4] if url.endswith(".git") else url
    rep.facts["origin_url"] = url
    _, branch = _run(["git", "-C", str(repo), "rev-parse", "--abbrev-ref", "HEAD"])
    rep.facts["current_branch"] = branch or None
    m = re.search(r"github\.com/([^/]+)/([^/]+)$", url)
    return f"{m.group(1)}/{m.group(2)}" if m else None


def _gh_json(args, *, timeout=25):
    rc, out = _run(["gh"] + args, timeout=timeout)
    if rc != 0 or not out:
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return None


def audit_github(repo_slug, rep, project, docs_enabled):
    """gh-based checks; every step degrades silently when gh/network fail."""
    rc, _ = _run(["gh", "--version"], timeout=10)
    rep.facts["gh_available"] = rc == 0
    if rc != 0 or not repo_slug:
        return

    meta = _gh_json(
        [
            "repo",
            "view",
            repo_slug,
            "--json",
            "description,homepageUrl,repositoryTopics,hasDiscussionsEnabled,"
            "defaultBranchRef",
        ]
    )
    pages = _gh_json(["api", f"repos/{repo_slug}/pages"])
    rep.facts["github_pages"] = (
        {
            "branch": pages.get("source", {}).get("branch"),
            "path": pages.get("source", {}).get("path"),
            "url": pages.get("html_url"),
        }
        if pages
        else None
    )

    if docs_enabled:
        if pages is None:
            rep.add(
                "MEDIUM",
                "docs-publishing",
                "docs publishing is enabled (default) but GitHub Pages is not "
                "configured",
                "epythet-docs",
            )
        elif (
            pages.get("source", {}).get("branch") != "gh-pages"
            or pages.get("source", {}).get("path") != "/"
        ):
            rep.add(
                "MEDIUM",
                "docs-publishing",
                f"GitHub Pages serves {rep.facts['github_pages']} instead of "
                "gh-pages / (root) — do not change without confirmation",
                "epythet-docs",
            )

    if meta is None:
        return
    default_branch = (meta.get("defaultBranchRef") or {}).get("name")
    rep.facts["default_branch"] = default_branch
    gh_desc = (meta.get("description") or "").strip()
    gh_home = (meta.get("homepageUrl") or "").strip()
    raw_topics = meta.get("repositoryTopics") or []
    gh_topics = sorted(
        t["name"] if isinstance(t, dict) else str(t) for t in raw_topics
    )
    rep.facts["github_metadata"] = {
        "description": gh_desc,
        "homepage": gh_home,
        "topics": gh_topics,
        "discussions_enabled": meta.get("hasDiscussionsEnabled"),
    }

    py_desc = (project.get("description") or "").strip()
    if py_desc and gh_desc != py_desc:
        rep.add(
            "LOW",
            "github-metadata",
            f"GitHub description ({gh_desc!r}) != pyproject description "
            f"({py_desc!r})",
            "wads-repo-doctor (inline)",
        )

    owner, name = repo_slug.split("/")
    pages_url = f"https://{owner}.github.io/{name}/"
    if docs_enabled and pages:
        expected_home = pages_url
    else:
        urls = {k.lower(): v for k, v in (project.get("urls") or {}).items()}
        expected_home = urls.get("homepage", "")
    if expected_home and gh_home.rstrip("/") != expected_home.rstrip("/"):
        rep.add(
            "LOW",
            "github-metadata",
            f"GitHub homepage ({gh_home or 'empty'}) != expected "
            f"({expected_home})",
            "wads-repo-doctor (inline)",
        )

    keywords = project.get("keywords") or []
    expected_topics = sorted({_slugify_topic(k) for k in keywords if _slugify_topic(k)})
    if expected_topics and gh_topics != expected_topics:
        rep.add(
            "LOW",
            "github-metadata",
            f"GitHub topics ({gh_topics or 'none'}) != slugified pyproject "
            f"keywords ({expected_topics})",
            "wads-repo-doctor (inline)",
        )

    if meta.get("hasDiscussionsEnabled") is False:
        rep.add(
            "LOW",
            "github-metadata",
            "GitHub Discussions disabled (ecosystem default is on)",
            "wads-repo-doctor (inline)",
        )

    # latest run of the primary CI workflow — only default-branch push runs
    # gauge repo health (a failing pull_request run on a feature branch is
    # that PR's business, not a broken-CI finding)
    run_args = [
        "run",
        "list",
        "-R",
        repo_slug,
        "--workflow",
        "ci.yml",
        "--event",
        "push",
        "--limit",
        "1",
        "--json",
        "conclusion,status,headBranch,url",
    ]
    if default_branch:
        run_args[6:6] = ["--branch", default_branch]
    runs = _gh_json(run_args)
    if runs:
        run = runs[0]
        rep.facts["latest_ci_run"] = run
        if run.get("status") == "completed" and run.get("conclusion") not in (
            "success",
            "skipped",
        ):
            rep.add(
                "HIGH",
                "ci",
                f"latest ci.yml push run on {run.get('headBranch')} concluded "
                f"{run.get('conclusion')!r} ({run.get('url')})",
                "wads-ci-health",
            )
    elif runs is not None:  # gh succeeded; the list is genuinely empty
        rep.facts["latest_ci_run"] = None
        rep.facts["ci_run_note"] = (
            f"no push runs of ci.yml found on {default_branch or 'the default branch'}"
        )


def audit_pypi(rep, project):
    name = project.get("name")
    local = project.get("version")
    if not name or not local:
        return
    url = f"https://pypi.org/pypi/{name}/json"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            rep.facts["pypi_version"] = None
            rep.add(
                "LOW",
                "publishing",
                f"{name!r} not on PyPI — never published (fine for private "
                "packages)",
                "wads-ci-health",
            )
        return
    except (OSError, ValueError):
        return  # offline: degrade silently
    pypi = data.get("info", {}).get("version")
    rep.facts["pypi_version"] = pypi
    if not pypi:
        return
    pv, lv = _int_prefix(pypi), _int_prefix(local)
    if pv > lv:
        rep.add(
            "HIGH",
            "publishing",
            f"PyPI version ({pypi}) is AHEAD of pyproject ({local}) — the CI "
            "version-bump push-back failed; next merge will collide",
            "wads-ci-health",
        )


# --- rendering --------------------------------------------------------------


def render_text(rep):
    d = rep.to_dict()
    facts = rep.facts
    lines = []
    slug = ""
    if facts.get("origin_url"):
        m = re.search(r"github\.com/(.+)$", facts["origin_url"])
        slug = f"  ({m.group(1)})" if m else ""
    lines.append(f"Repo health audit: {rep.repo}{slug}")
    lines.append(
        "ci: {ci} | pyproject: {pp} | package: {pkg} ({n} modules) | "
        "tests: {t} files".format(
            ci=facts.get("ci_format", "?"),
            pp="yes" if facts.get("has_pyproject") else "NO",
            pkg=facts.get("package_dir") or "?",
            n=facts.get("module_count", "?"),
            t=facts.get("test_file_count", "?"),
        )
    )
    counts = d["summary"]
    lines.append(
        f"findings: {counts['HIGH']} high / {counts['MEDIUM']} medium / "
        f"{counts['LOW']} low"
    )
    for sev in SEVERITIES:
        sev_findings = [f for f in d["findings"] if f["severity"] == sev]
        if not sev_findings:
            continue
        lines.append("")
        lines.append(f"{sev} ({len(sev_findings)})")
        for f in sev_findings:
            lines.append(f"  [{f['dimension']}] {f['summary']}")
            lines.append(f"      -> {f['dispatch']}")
    if not d["findings"]:
        lines.append("")
        lines.append("No findings — repo looks healthy on every audited dimension.")
    return "\n".join(lines)


# --- main -------------------------------------------------------------------


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "repo", nargs="?", default=".", help="target repo path (default: cwd)"
    )
    parser.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON"
    )
    parser.add_argument(
        "--no-network",
        action="store_true",
        help="skip gh and PyPI checks (everything that leaves the machine)",
    )
    args = parser.parse_args(argv)

    repo = Path(args.repo).resolve()
    if not repo.is_dir():
        print(f"error: {repo} is not a directory", file=sys.stderr)
        return 2

    rep = Report(repo)
    repo_slug = audit_git(repo, rep)
    project = audit_pyproject(repo, rep)
    audit_files(repo, rep)
    audit_ci(repo, rep)
    audit_package(repo, rep, project.get("name"))
    audit_skills(repo, rep, project.get("name"))
    rep.facts["network_checks"] = not args.no_network
    if not args.no_network:
        # docs job is on by default in the wads CI (CIConfig default true)
        docs_enabled = True
        if rep.facts.get("pyproject_parsed"):
            docs_cfg = (
                read_pyproject(repo)
                .get("tool", {})
                .get("wads", {})
                .get("ci", {})
                .get("docs", {})
            )
            docs_enabled = docs_cfg.get("enabled", True)
        audit_github(repo_slug, rep, project, docs_enabled)
        audit_pypi(rep, project)

    if args.json:
        print(json.dumps(rep.to_dict(), indent=2))
    else:
        print(render_text(rep))
    return 0


if __name__ == "__main__":
    sys.exit(main())
