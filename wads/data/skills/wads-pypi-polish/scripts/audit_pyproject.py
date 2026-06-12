#!/usr/bin/env python3
"""Audit a package's pyproject.toml for PyPI professionalism & discoverability.

Reports, grouped by impact, which metadata fields are present, weak, or missing,
validates classifiers against the canonical trove list (if ``trove-classifiers``
is installed), and surfaces repo facts (git remote, py.typed, CHANGELOG, CI
matrix) so metadata can be derived from reality rather than guessed.

Usage::

    python audit_pyproject.py [REPO] [--json]   # REPO defaults to current directory

``--json`` emits the findings + facts as machine-readable JSON instead of the
human report. Exits 2 when pyproject.toml is missing or malformed.

Stdlib only; ``trove-classifiers`` is used opportunistically for validation
(run via ``uvx --python 3.12 --with trove-classifiers python audit_pyproject.py
REPO`` to get validation without installing anything into the active
environment).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Mapping, Optional

try:  # Python 3.11+
    import tomllib  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore  # `pip install tomli` on <3.11


# --- Findings model ---------------------------------------------------------

IMPACT_ORDER = ("high", "medium", "low", "ok")


@dataclass
class Finding:
    """A single audit observation.

    >>> Finding("high", "description", "missing", "add a one-line headline").impact
    'high'
    """

    impact: str  # one of IMPACT_ORDER
    field: str
    status: str  # 'missing' | 'weak' | 'ok'
    advice: str = ""


@dataclass
class Audit:
    """Accumulated findings plus derived repo facts."""

    findings: list = field(default_factory=list)
    facts: dict = field(default_factory=dict)

    def add(self, impact: str, field_: str, status: str, advice: str = "") -> None:
        self.findings.append(Finding(impact, field_, status, advice))


# --- Repo fact gathering (truth sources) ------------------------------------


def _git_remote(repo: Path) -> Optional[str]:
    """Return a normalized https repo URL from ``git remote``, or None."""
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    url = out.stdout.strip()
    if not url:
        return None
    # git@github.com:OWNER/REPO.git -> https://github.com/OWNER/REPO
    url = re.sub(r"^git@([^:]+):", r"https://\1/", url)
    return url[:-4] if url.endswith(".git") else url


def _find_py_typed(repo: Path) -> bool:
    """True if a PEP 561 ``py.typed`` marker ships anywhere in the tree."""
    return any(repo.rglob("py.typed"))


def _find_changelog(repo: Path) -> Optional[str]:
    """Return the name of a changelog file if present."""
    for name in ("CHANGELOG.md", "CHANGELOG.rst", "CHANGES.md", "HISTORY.md"):
        if (repo / name).exists():
            return name
    return None


# Workflow lines that actually set a python version (fallback scrape filter).
_PY_VERSION_CONTEXT = re.compile(
    r"python[-_]version|uv python install", re.IGNORECASE
)


def _ci_python_versions(repo: Path, pyproject: Mapping) -> list:
    """Python minor versions CI tests against, from the most truthful source.

    Prefers ``[tool.wads.ci.testing].python_versions`` in the already-loaded
    pyproject (the SSOT for wads-managed repos, whose workflow is a stub with
    no literal versions). Only when absent, falls back to a best-effort scrape
    of ``.github/workflows/*`` — restricted to lines that set a python version
    (``python-version``, ``python_versions``, ``uv python install``) so
    unrelated ``3.N`` tokens (action versions, etc.) aren't picked up.
    """
    declared = (
        pyproject.get("tool", {})
        .get("wads", {})
        .get("ci", {})
        .get("testing", {})
        .get("python_versions")
    )
    if declared:
        return [str(v) for v in declared]
    versions: set = set()
    wf_dir = repo / ".github" / "workflows"
    if wf_dir.is_dir():
        for wf in list(wf_dir.glob("*.yml")) + list(wf_dir.glob("*.yaml")):
            text = wf.read_text(encoding="utf-8", errors="ignore")
            for line in text.splitlines():
                if not _PY_VERSION_CONTEXT.search(line):
                    continue
                for m in re.findall(r"3\.(\d{1,2})", line):
                    versions.add(f"3.{m}")
    return sorted(versions, key=lambda v: int(v.split(".")[1]))


def gather_facts(repo: Path, pyproject: Mapping) -> dict:
    """Collect ground-truth facts used to derive (not guess) metadata."""
    return {
        "git_remote": _git_remote(repo),
        "has_py_typed": _find_py_typed(repo),
        "changelog": _find_changelog(repo),
        "ci_python_versions": _ci_python_versions(repo, pyproject),
        "has_license_file": any(repo.glob("LICEN[CS]E*")),
        "has_readme": any(repo.glob("README*")),
    }


# --- Classifier validation --------------------------------------------------


def validate_classifiers(classifiers: Iterable[str]) -> dict:
    """Split classifiers into valid/invalid against the canonical trove list.

    Returns ``{'invalid': [...], 'checked': bool}``. ``checked`` is False when
    the ``trove-classifiers`` package isn't installed (so nothing is flagged).
    """
    try:
        from trove_classifiers import classifiers as canonical  # type: ignore
    except ModuleNotFoundError:
        return {"invalid": [], "checked": False}
    invalid = [c for c in classifiers if c not in canonical]
    return {"invalid": invalid, "checked": True}


# --- Field checks -----------------------------------------------------------

# Labels (lowercased) that PyPI recognizes for custom sidebar icons.
_RECOGNIZED_URL_LABELS = (
    "homepage",
    "download",
    "documentation",
    "docs",
    "repository",
    "source",
    "issues",
    "bug",
    "tracker",
    "changelog",
    "changes",
    "release notes",
    "funding",
    "sponsor",
)


def _project_table(data: Mapping) -> Mapping:
    """Return the metadata table, handling Poetry's legacy layout."""
    project = data.get("project")
    if project:
        return project
    poetry = data.get("tool", {}).get("poetry")
    return poetry or {}


def _has_recognized_url(label: str) -> bool:
    low = label.lower()
    return any(low == k or low.startswith(k) for k in _RECOGNIZED_URL_LABELS)


def audit_metadata(data: Mapping, facts: Mapping) -> Audit:
    """Produce an :class:`Audit` from parsed pyproject data and repo facts."""
    audit = Audit(facts=dict(facts))
    proj = _project_table(data)

    # description (high)
    desc = proj.get("description", "")
    if not desc:
        audit.add("high", "description", "missing", "One-line headline shown on PyPI and in search.")
    elif len(desc) > 120:
        audit.add("medium", "description", "weak", "Trim to a crisp single line (< ~100 chars).")
    else:
        audit.add("ok", "description", "ok")

    # classifiers (high)
    classifiers = list(proj.get("classifiers", []) or [])
    if not classifiers:
        audit.add("high", "classifiers", "missing", "Add Development Status, Intended Audience, Python versions, Topic, Typing.")
    else:
        present = {c.split(" :: ")[0] for c in classifiers}
        wanted = {
            "Development Status": "Signal maturity.",
            "Intended Audience": "Who it's for.",
            "Programming Language": "Per-version Python tags (search facets).",
            "Topic": "Categorize the project.",
        }
        for cat, why in wanted.items():
            if cat not in present:
                audit.add("medium", "classifiers", "weak", f"Missing '{cat} :: …'. {why}")
        if facts.get("has_py_typed") and not any(c.startswith("Typing ::") for c in classifiers):
            audit.add("medium", "classifiers", "weak", "Ships py.typed -> add 'Typing :: Typed'.")
        result = validate_classifiers(classifiers)
        if result["checked"] and result["invalid"]:
            for bad in result["invalid"]:
                audit.add("high", "classifiers", "weak", f"INVALID classifier (upload will fail): {bad!r}")
        if not any(audit_has(audit, "classifiers")):
            audit.add("ok", "classifiers", "ok")

    # project.urls (high)
    urls = proj.get("urls", {}) or {}
    if not urls:
        audit.add("high", "project.urls", "missing", "Add Homepage, Documentation, Repository, Issues, Changelog, Funding.")
    else:
        recognized = [k for k in urls if _has_recognized_url(k)]
        unrecognized = [k for k in urls if not _has_recognized_url(k)]
        if not recognized:
            audit.add("medium", "project.urls", "weak", "No PyPI-recognized labels; use Homepage/Documentation/Issues/etc. for icons.")
        for k in unrecognized:
            audit.add("low", "project.urls", "weak", f"Label {k!r} won't get a custom icon; consider a recognized label.")
        if recognized and not unrecognized:
            audit.add("ok", "project.urls", "ok")

    # keywords (medium)
    keywords = proj.get("keywords", []) or []
    if not keywords:
        audit.add("medium", "keywords", "missing", "Add 5-10 lowercase search terms users actually type.")
    elif len(keywords) < 3:
        audit.add("low", "keywords", "weak", "Add a few more keywords (aim for 5-10).")
    else:
        audit.add("ok", "keywords", "ok")

    # readme (medium)
    if not proj.get("readme") and not _is_dynamic(proj, "readme"):
        status = "missing" if not facts.get("has_readme") else "weak"
        audit.add("medium", "readme", status, "Point `readme = \"README.md\"` so the long description renders on PyPI.")
    else:
        audit.add("ok", "readme", "ok")

    # license (medium)
    lic = proj.get("license")
    if not lic:
        audit.add("medium", "license", "missing", "Add SPDX `license = \"MIT\"` (PEP 639) + license-files.")
    elif isinstance(lic, dict):
        audit.add("low", "license", "weak", "Deprecated table form; prefer SPDX string `license = \"MIT\"`.")
    else:
        audit.add("ok", "license", "ok")

    # requires-python (medium)
    if not proj.get("requires-python") and "python" not in str(proj.get("dependencies", "")):
        audit.add("medium", "requires-python", "missing", "Declare the minimum Python, e.g. `requires-python = \">=3.10\"`.")
    else:
        audit.add("ok", "requires-python", "ok")

    # authors (low)
    if not proj.get("authors") and not proj.get("maintainers"):
        audit.add("low", "authors", "missing", "Add authors = [{ name = \"...\", email = \"...\" }].")
    else:
        audit.add("ok", "authors", "ok")

    return audit


def audit_has(audit: Audit, field_: str) -> Iterable[bool]:
    """Yield True for each non-ok finding already recorded for ``field_``."""
    for f in audit.findings:
        if f.field == field_ and f.status != "ok":
            yield True


def _is_dynamic(proj: Mapping, name: str) -> bool:
    return name in (proj.get("dynamic", []) or [])


# --- Reporting --------------------------------------------------------------

_GLYPH = {"high": "🔴", "medium": "🟡", "low": "🔵", "ok": "✅"}


def render_report(audit: Audit) -> str:
    """Render a human-readable, impact-grouped report string."""
    lines = ["", "PyPI metadata audit", "=" * 60]

    facts = audit.facts
    lines.append("\nRepo facts (derive metadata from these, don't guess):")
    lines.append(f"  git remote      : {facts.get('git_remote') or '— (run inside a git repo)'}")
    lines.append(f"  ships py.typed  : {facts.get('has_py_typed')}")
    lines.append(f"  changelog file  : {facts.get('changelog') or '—'}")
    lines.append(f"  license file    : {facts.get('has_license_file')}")
    lines.append(f"  README present  : {facts.get('has_readme')}")
    ci = facts.get("ci_python_versions") or []
    lines.append(f"  CI py versions  : {', '.join(ci) if ci else '— (none detected)'}")

    for impact in IMPACT_ORDER:
        group = [f for f in audit.findings if f.impact == impact and f.status != "ok"]
        if impact == "ok":
            oks = sorted({f.field for f in audit.findings if f.status == "ok"})
            if oks:
                lines.append(f"\n{_GLYPH['ok']} OK: {', '.join(oks)}")
            continue
        if not group:
            continue
        label = {"high": "HIGH IMPACT", "medium": "MEDIUM", "low": "LOW"}[impact]
        lines.append(f"\n{_GLYPH[impact]} {label}")
        for f in group:
            lines.append(f"  • [{f.field}] {f.advice}")

    if not validate_classifiers([])["checked"]:
        lines.append(
            "\n(Tip: rerun as `uvx --python 3.12 --with trove-classifiers "
            "python audit_pyproject.py REPO` to validate classifier strings.)"
        )
    lines.append("")
    return "\n".join(lines)


def audit_to_dict(audit: Audit) -> dict:
    """JSON-serializable view of an :class:`Audit` (findings + facts)."""
    return {
        "facts": audit.facts,
        "findings": [asdict(f) for f in audit.findings],
    }


# --- CLI ----------------------------------------------------------------------


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "repo", nargs="?", default=".", help="target repo path (default: cwd)"
    )
    parser.add_argument(
        "--json", action="store_true", help="emit findings + facts as JSON"
    )
    args = parser.parse_args(argv)

    repo = Path(args.repo).resolve()
    if not repo.is_dir():
        print(f"error: {repo} is not a directory", file=sys.stderr)
        return 2
    pyproject_path = repo / "pyproject.toml"
    if not pyproject_path.is_file():
        print(f"error: no pyproject.toml found in {repo}", file=sys.stderr)
        return 2
    try:
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        print(f"error: {pyproject_path} is not valid TOML: {e}", file=sys.stderr)
        return 2

    audit = audit_metadata(data, gather_facts(repo, data))
    if args.json:
        print(json.dumps(audit_to_dict(audit), indent=2))
    else:
        print(render_report(audit))
    return 0


if __name__ == "__main__":
    sys.exit(main())
