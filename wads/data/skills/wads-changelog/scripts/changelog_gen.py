#!/usr/bin/env python3
"""Generate and maintain CHANGELOG.md from git history and version tags.

Designed for wads-managed repos, where CI auto-bumps the version on every
default-branch merge and tags each release with a bare version tag (e.g.
``0.2.3`` -- no ``v`` prefix). Each changelog section is derived from the
first-parent commits between consecutive version tags, with CI noise
(version-bump commits, ``[skip ci]`` housekeeping, bare merge commits)
filtered out. Commit subjects and PR titles are kept verbatim -- the script
observes history, it never rewrites it.

Modes
-----
default        READ-ONLY. Diagnose: does CHANGELOG.md exist, which versions
               it covers vs. the repo's version tags, which are missing --
               plus a rendered preview of the missing sections.
--json         READ-ONLY. Same data, machine-readable (version -> entries).
--write        *** THE ONLY MODE THAT WRITES, and the only sanctioned write
               in the wads skill suite. *** It INSERTS (version-ordered,
               purely additive) sections for versions not yet present in
               CHANGELOG.md (creating the file if absent). It NEVER rewrites,
               reorders, or deletes existing content, so hand-edits survive
               regeneration; once the backfill is complete, re-running is a
               no-op (with --max-versions N each run adds N more versions).

Usage
-----
    python changelog_gen.py [REPO_PATH] [--json] [--write] [--max-versions N]

REPO_PATH defaults to the current working directory.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

FS = "\x1f"  # field separator in git log --format
RS = "\x1e"  # record separator in git log --format

VERSION_TAG_RE = re.compile(r"^v?\d+(\.\d+)+$")
SKIP_CI_RE = re.compile(r"\[skip ci\]", re.IGNORECASE)
MERGE_PR_RE = re.compile(r"^Merge pull request #(\d+)")
BARE_MERGE_RE = re.compile(r"^Merge (branch|remote-tracking branch)\b")
PR_REF_RE = re.compile(r"(?<!\[)#(\d+)\b")
# A changelog version heading: "## [0.2.3] - 2026-06-02", "## 0.2.3", "## v0.2.3 ..."
HEADING_VERSION_RE = re.compile(r"^##\s+\[?v?(\d+(?:\.\d+)+)\]?")

# Conventional-commit prefix -> Keep-a-Changelog-ish category. Only these
# four are mapped; anything else stays uncategorized (never invent).
CATEGORY_PATTERNS = [
    ("Added", re.compile(r"^feat(?:\([^)]*\))?!?:", re.IGNORECASE)),
    ("Fixed", re.compile(r"^fix(?:\([^)]*\))?!?:", re.IGNORECASE)),
    ("Docs", re.compile(r"^docs(?:\([^)]*\))?!?:", re.IGNORECASE)),
    ("Changed", re.compile(r"^refactor(?:\([^)]*\))?!?:", re.IGNORECASE)),
]
CATEGORY_ORDER = ["Added", "Changed", "Fixed", "Docs"]

DEFAULT_HEADER = """\
# Changelog

All notable changes to this project are documented in this file.

The format is inspired by [Keep a Changelog](https://keepachangelog.com/);
each section corresponds to a git version tag (which is also the release
published to PyPI). Entries are commit subjects and PR titles, verbatim.
"""


def _git(repo: Path, *args: str, timeout: int = 120) -> str:
    """Run a git command in *repo* and return stdout; raise on failure."""
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed (exit {result.returncode}): "
            f"{result.stderr.strip()}"
        )
    return result.stdout


def _version_key(version: str) -> tuple:
    """Sortable key for a version string like '0.1.102' or 'v1.2'."""
    return tuple(int(p) for p in version.lstrip("vV").split("."))


def _normalize_version(version: str) -> str:
    """Canonical form used to compare tags with changelog headings."""
    return version.lstrip("vV")


def collect_version_tags(repo: Path) -> list[dict]:
    """Return version tags as [{'tag', 'date'}, ...], newest version first.

    'date' is the tag's creatordate (tag-creation date for annotated tags,
    commit date for lightweight tags) -- i.e. when the release was cut.
    """
    out = _git(
        repo,
        "for-each-ref",
        "refs/tags",
        f"--format=%(refname:short){FS}%(creatordate:short)",
    )
    tags = []
    for line in out.splitlines():
        if FS not in line:
            continue
        name, date = line.split(FS, 1)
        if VERSION_TAG_RE.match(name):
            tags.append({"tag": name, "date": date})
    tags.sort(key=lambda t: _version_key(t["tag"]), reverse=True)
    return tags


def github_repo_url(repo: Path) -> str | None:
    """https://github.com/OWNER/REPO derived from origin, else None."""
    try:
        url = _git(repo, "config", "--get", "remote.origin.url").strip()
    except RuntimeError:
        return None
    m = re.match(r"^git@github\.com:([^/]+)/(.+?)(?:\.git)?$", url)
    if not m:
        m = re.match(r"^(?:ssh://git@|https://)github\.com/([^/]+)/(.+?)(?:\.git)?/?$", url)
    if m:
        return f"https://github.com/{m.group(1)}/{m.group(2)}"
    return None


def commit_entries(repo: Path, range_spec: str) -> list[str]:
    """Filtered, transformed entry texts for first-parent commits in a range.

    - drops version-bump and other ``[skip ci]`` commits (CI housekeeping)
    - drops bare merge commits ('Merge branch ...')
    - replaces 'Merge pull request #NN ...' with the PR title (the first
      body line of a GitHub merge commit) + '(#NN)'
    - keeps every other subject verbatim
    """
    out = _git(
        repo, "log", "--first-parent", f"--format=%s{FS}%b{RS}", range_spec
    )
    entries = []
    for record in out.split(RS):
        if not record.strip():
            continue
        subject, _, body = record.partition(FS)
        subject = subject.strip()
        if not subject or SKIP_CI_RE.search(subject):
            continue  # CI bump commits + [skip ci] housekeeping
        pr_merge = MERGE_PR_RE.match(subject)
        if pr_merge:
            title = next(
                (ln.strip() for ln in body.splitlines() if ln.strip()), ""
            )
            if title and not SKIP_CI_RE.search(title):
                entries.append(f"{title} (#{pr_merge.group(1)})")
            elif not title:
                entries.append(subject)  # no body: keep the merge subject
            continue
        if BARE_MERGE_RE.match(subject):
            continue  # bare merge, no PR reference -- noise
        entries.append(subject)
    return entries


def categorize(entries: list[str]) -> dict:
    """Bucket entries by conventional-commit prefix; '' = uncategorized."""
    buckets: dict[str, list[str]] = {}
    for entry in entries:
        for category, pattern in CATEGORY_PATTERNS:
            if pattern.match(entry):
                buckets.setdefault(category, []).append(entry)
                break
        else:
            buckets.setdefault("", []).append(entry)
    return buckets


def link_pr_refs(text: str, gh_url: str | None) -> str:
    """Turn bare #NN references into markdown PR links (when URL is known)."""
    if not gh_url:
        return text
    return PR_REF_RE.sub(
        lambda m: f"[#{m.group(1)}]({gh_url}/pull/{m.group(1)})", text
    )


def render_section(
    tag: str, date: str, buckets: dict, gh_url: str | None
) -> str:
    """One '## [TAG] - DATE' markdown section, ending with a blank line."""
    lines = [f"## [{tag}] - {date}", ""]
    if not any(buckets.values()):
        lines += [
            "- Maintenance only (all commits in this range were CI "
            "version bumps / housekeeping).",
            "",
        ]
        return "\n".join(lines)
    # Uncategorized bullets go directly under the version heading...
    for entry in buckets.get("", []):
        lines.append(f"- {link_pr_refs(entry, gh_url)}")
    if buckets.get(""):
        lines.append("")
    # ...then the conventional-commit categories.
    for category in CATEGORY_ORDER:
        if buckets.get(category):
            lines += [f"### {category}", ""]
            lines += [
                f"- {link_pr_refs(e, gh_url)}" for e in buckets[category]
            ]
            lines.append("")
    return "\n".join(lines)


def parse_changelog(text: str) -> tuple[list[str], list[dict]]:
    """Split changelog text into lines + section-heading index.

    Returns (lines_with_endings, sections) where each section is
    {'version': normalized-version-or-None, 'start': line-index}.
    """
    lines = text.splitlines(keepends=True)
    sections = []
    for i, line in enumerate(lines):
        if line.startswith("## "):
            m = HEADING_VERSION_RE.match(line)
            sections.append(
                {"version": _normalize_version(m.group(1)) if m else None,
                 "start": i}
            )
    return lines, sections


def weave_sections(
    lines: list[str], sections: list[dict], new_sections: list[tuple[str, str]]
) -> str:
    """Insert rendered sections into existing changelog lines, additively.

    Each new section goes immediately before the first existing *version*
    section that is older than it (so an '## [Unreleased]' block stays on
    top), or at the end of the file if every existing version is newer.
    Existing lines are never modified, reordered, or removed.
    """
    insert_at: dict[int, list[str]] = {}
    for version, rendered in new_sections:
        key = _version_key(version)
        anchor = len(lines)
        for section in sections:
            if section["version"] and _version_key(section["version"]) < key:
                anchor = section["start"]
                break
        insert_at.setdefault(anchor, []).append(rendered)
    out: list[str] = []
    for i, line in enumerate(lines):
        for rendered in insert_at.get(i, []):
            out.append(rendered + "\n")
        out.append(line)
    if insert_at.get(len(lines)):
        if out and not out[-1].endswith("\n"):
            out.append("\n")
        if out and out[-1].strip():
            out.append("\n")
        for rendered in insert_at[len(lines)]:
            out.append(rendered + "\n")
    return "".join(out)


def remote_version_tags(repo: Path) -> set | None:
    """Version tags on origin (read-only network call), or None if unknown."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "ls-remote", "--tags", "origin"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    tags = set()
    for line in result.stdout.splitlines():
        ref = line.split("\t")[-1]
        name = ref.removeprefix("refs/tags/").removesuffix("^{}")
        if VERSION_TAG_RE.match(name):
            tags.add(name)
    return tags


def build_report(repo: Path, *, max_versions: int, check_remote: bool) -> dict:
    """Gather everything: diagnosis + per-version entries for missing tags."""
    tags = collect_version_tags(repo)
    gh_url = github_repo_url(repo)
    changelog_path = repo / "CHANGELOG.md"
    changelog_text = (
        changelog_path.read_text(encoding="utf-8")
        if changelog_path.exists()
        else None
    )
    covered: list[str] = []
    if changelog_text is not None:
        _, sections = parse_changelog(changelog_text)
        covered = [s["version"] for s in sections if s["version"]]
    covered_set = set(covered)

    missing = [
        t for t in tags if _normalize_version(t["tag"]) not in covered_set
    ]
    to_generate = missing[: max_versions] if max_versions else missing

    # Per-version commit entries (range = previous version tag .. this tag;
    # the very first release has no predecessor: root..TAG).
    tag_names = [t["tag"] for t in tags]  # newest first
    generated = []
    for t in to_generate:
        idx = tag_names.index(t["tag"])
        prev = tag_names[idx + 1] if idx + 1 < len(tag_names) else None
        range_spec = f"{prev}..{t['tag']}" if prev else t["tag"]
        entries = commit_entries(repo, range_spec)
        generated.append(
            {
                "version": _normalize_version(t["tag"]),
                "tag": t["tag"],
                "date": t["date"],
                "range": range_spec,
                "buckets": categorize(entries),
                "entries": entries,
            }
        )

    unreleased = (
        commit_entries(repo, f"{tag_names[0]}..HEAD") if tag_names else []
    )

    remote_only = None
    if check_remote:
        remote = remote_version_tags(repo)
        if remote is not None:
            remote_only = sorted(
                remote - {t["tag"] for t in tags}, key=_version_key
            )

    return {
        "changelog_path": str(changelog_path),
        "changelog_exists": changelog_text is not None,
        "github_url": gh_url,
        "latest_tag": tags[0]["tag"] if tags else None,
        "latest_covered": covered[0] if covered else None,
        "n_version_tags": len(tags),
        "covered_versions": covered,
        "missing_versions": [t["tag"] for t in missing],
        "remote_tags_not_local": remote_only,
        "unreleased_entries": unreleased,
        "generated": generated,
        "_changelog_text": changelog_text,  # internal, stripped from --json
    }


def write_missing_sections(repo: Path, report: dict) -> str:
    """THE SINGLE SANCTIONED WRITE: insert missing sections into CHANGELOG.md
    (version-ordered, purely additive).

    Creates the file (with a standard header) if it doesn't exist. Existing
    content is never modified -- only new sections are inserted. Returns a
    one-line summary of what happened.
    """
    changelog_path = repo / "CHANGELOG.md"
    new_sections = [
        (g["version"], render_section(g["tag"], g["date"], g["buckets"],
                                      report["github_url"]))
        for g in report["generated"]
    ]
    if not new_sections:
        return "CHANGELOG.md is up to date -- nothing written."
    if report["_changelog_text"] is None:
        body = "\n".join(rendered for _, rendered in new_sections)
        changelog_path.write_text(
            DEFAULT_HEADER + "\n" + body, encoding="utf-8"
        )
        return (
            f"Created {changelog_path.name} with "
            f"{len(new_sections)} version section(s)."
        )
    lines, sections = parse_changelog(report["_changelog_text"])
    changelog_path.write_text(
        weave_sections(lines, sections, new_sections), encoding="utf-8"
    )
    return (
        f"Inserted {len(new_sections)} missing version section(s) into "
        f"{changelog_path.name}; existing content untouched."
    )


def human_report(report: dict, *, wrote: str | None) -> str:
    """Render the diagnosis (and preview / write summary) for humans."""
    out = ["# Changelog diagnosis", ""]
    out.append(f"- CHANGELOG.md exists : {report['changelog_exists']}")
    out.append(f"- version tags        : {report['n_version_tags']} "
               f"(latest: {report['latest_tag']})")
    out.append(f"- latest covered      : {report['latest_covered']}")
    missing = report["missing_versions"]
    preview_n = len(report["generated"])
    out.append(f"- missing versions    : {len(missing)}"
               + (f" (showing {preview_n})" if preview_n < len(missing) else ""))
    if missing:
        shown = ", ".join(missing[:8])
        out.append(f"    {shown}{', ...' if len(missing) > 8 else ''}")
    if report["remote_tags_not_local"]:
        out.append(
            f"- WARNING: {len(report['remote_tags_not_local'])} version "
            f"tag(s) on origin are not local "
            f"(e.g. {report['remote_tags_not_local'][-1]}). "
            "Run `git fetch --tags` and re-run."
        )
    if report["unreleased_entries"]:
        out.append(
            f"- unreleased          : {len(report['unreleased_entries'])} "
            "commit(s) since the latest tag (not written -- no tag yet)"
        )
    out.append("")
    if wrote is not None:
        out.append(wrote)
    elif report["generated"]:
        out.append("## Preview of missing sections (read-only; "
                   "use --write to apply)")
        out.append("")
        for g in report["generated"]:
            out.append(render_section(g["tag"], g["date"], g["buckets"],
                                      report["github_url"]))
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Generate and maintain CHANGELOG.md from git version tags. "
            "READ-ONLY by default (diagnose + preview)."
        ),
        epilog=(
            "*** --write is the ONLY mode that modifies anything, and the "
            "only sanctioned write in the wads skill suite: it INSERTS "
            "missing version sections into CHANGELOG.md (version-ordered, "
            "purely additive) and never rewrites existing content — "
            "hand-edits survive; once the backfill is complete, re-running "
            "is a no-op (with --max-versions N each run adds N more). ***"
        ),
    )
    parser.add_argument(
        "repo", nargs="?", default=".",
        help="path to the target repo (default: current directory)",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="machine-readable output (version -> entries)",
    )
    parser.add_argument(
        "--write", action="store_true",
        help="insert missing version sections into CHANGELOG.md "
             "(additive only -- see epilog)",
    )
    parser.add_argument(
        "--max-versions", type=int, default=0, metavar="N",
        help="generate at most the N newest missing versions (0 = all)",
    )
    parser.add_argument(
        "--no-remote-check", action="store_true",
        help="skip the read-only `git ls-remote --tags origin` "
             "unfetched-tags check (e.g. offline)",
    )
    args = parser.parse_args(argv)

    repo = Path(args.repo).resolve()
    try:
        _git(repo, "rev-parse", "--git-dir")
        toplevel = Path(
            _git(repo, "rev-parse", "--show-toplevel").strip()
        ).resolve()
    except (RuntimeError, FileNotFoundError) as exc:
        print(f"error: {repo} is not a git repo ({exc})", file=sys.stderr)
        return 2
    if toplevel != repo:
        print(
            f"error: {repo} is inside the repo {toplevel} but is not its "
            f"root — pass the repo root (CHANGELOG.md belongs there)",
            file=sys.stderr,
        )
        return 2

    report = build_report(
        repo,
        max_versions=args.max_versions,
        check_remote=not args.no_remote_check,
    )
    if report["n_version_tags"] == 0:
        print(
            "error: no version tags (like 0.2.3) found -- nothing to "
            "generate. If the repo has releases, run `git fetch --tags`.",
            file=sys.stderr,
        )
        return 1

    wrote = write_missing_sections(repo, report) if args.write else None

    if args.json:
        payload = {k: v for k, v in report.items() if k != "_changelog_text"}
        payload["sections"] = {
            g["version"]: {
                "date": g["date"],
                "range": g["range"],
                "entries": {
                    (cat or "uncategorized"): items
                    for cat, items in g["buckets"].items()
                },
            }
            for g in report["generated"]
        }
        del payload["generated"]
        if wrote is not None:
            payload["write_result"] = wrote
        print(json.dumps(payload, indent=2))
    else:
        print(human_report(report, wrote=wrote))
    return 0


if __name__ == "__main__":
    sys.exit(main())
