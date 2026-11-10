"""One version number for a Python package and its npm twin (i2mint/wads#210).

A repo that publishes the same code to PyPI and npm lists, in ``pyproject.toml``,
the manifests that carry the Python version too::

    [tool.wads.ci.version]
    sync = ["ts/package.json"]

Two things follow, both in uv-ci:

- **Release:** right after the publish job bumps ``[project].version``, it writes
  that version into each listed manifest (and the ``package-lock.json`` beside
  it), so the bump commit carries all of them.
- **Check:** the setup job fails when a listed manifest's version differs from
  ``[project].version``, so a hand edit on one side shows up before a release.

Only ``package.json`` is supported: a Rust crate usually keeps its own version
line. This module imports only the standard library, because the CI scripts load
it by path from the wads checkout (``wads/scripts/_checkout_import.py``).
"""

from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath
from typing import Mapping, Sequence

#: Manifest file names ``[tool.wads.ci.version].sync`` may list.
SYNCABLE_MANIFESTS = ("package.json",)
#: The lockfile npm keeps beside a ``package.json``; its own version fields follow.
NPM_LOCKFILE = "package-lock.json"
#: A semver version, the only kind npm accepts (PEP 440 forms like ``1.0rc1`` are not).
SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
_TABLE = "[tool.wads.ci.version]"


def sync_files(pyproject_data: Mapping) -> list[str]:
    """The manifests ``[tool.wads.ci.version].sync`` lists, validated.

    >>> sync_files({"tool": {"wads": {"ci": {"version": {"sync": ["ts/package.json"]}}}}})
    ['ts/package.json']
    >>> sync_files({})
    []
    >>> sync_files({"tool": {"wads": {"ci": {"version": {"sync": ["rust/core/Cargo.toml"]}}}}})
    Traceback (most recent call last):
      ...
    ValueError: [tool.wads.ci.version].sync: 'rust/core/Cargo.toml' is not one of ('package.json',); a Rust crate keeps its own version line.
    """
    table = pyproject_data.get("tool", {}).get("wads", {}).get("ci", {})
    files = table.get("version", {}).get("sync", [])
    if isinstance(files, str) or not isinstance(files, list):
        raise ValueError(f"{_TABLE}.sync must be a list of paths, got {files!r}")
    for path in files:
        posix = PurePosixPath(str(path))
        if posix.is_absolute() or ".." in posix.parts or "\\" in str(path):
            raise ValueError(
                f"{_TABLE}.sync: {path!r} must be a relative path inside the repo "
                "(forward slashes, no '..')"
            )
        if posix.name not in SYNCABLE_MANIFESTS:
            raise ValueError(
                f"{_TABLE}.sync: {path!r} is not one of {SYNCABLE_MANIFESTS}; "
                "a Rust crate keeps its own version line."
            )
    return [str(p) for p in files]


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _indent_of(text: str) -> "int | str":
    """The indentation a JSON file uses (what ``npm version`` keeps), default 2."""
    match = re.search(r'^\{\s*\n([ \t]+)"', text)
    if not match:
        return 2
    indent = match.group(1)
    return len(indent) if set(indent) == {" "} else indent


def _write_json_like(path: Path, data: dict, original: str) -> None:
    """Write ``data`` with the original's indentation and final newline."""
    text = json.dumps(data, indent=_indent_of(original), ensure_ascii=False)
    if original.endswith("\n"):
        text += "\n"
    path.write_text(text, encoding="utf-8")


def set_manifest_version(manifest: Path, version: str) -> list[Path]:
    """Write ``version`` into ``manifest`` and the npm lockfile beside it.

    Returns the files written. Refuses a version npm would reject, before writing.

    >>> import tempfile
    >>> d = Path(tempfile.mkdtemp())
    >>> _ = (d / "package.json").write_text('{\\n  "name": "x",\\n  "version": "0.0.1"\\n}\\n')
    >>> [p.name for p in set_manifest_version(d / "package.json", "0.0.2")]
    ['package.json']
    >>> print((d / "package.json").read_text(), end="")
    {
      "name": "x",
      "version": "0.0.2"
    }
    """
    if not SEMVER.match(version):
        raise ValueError(
            f"version {version!r} is not semver, which npm requires; "
            f"cannot write it into {manifest}"
        )
    written = []
    original = manifest.read_text(encoding="utf-8")
    data = json.loads(original)
    data["version"] = version
    _write_json_like(manifest, data, original)
    written.append(manifest)
    lockfile = manifest.with_name(NPM_LOCKFILE)
    if lockfile.is_file():
        original = lockfile.read_text(encoding="utf-8")
        lock = json.loads(original)
        lock["version"] = version
        root_entry = lock.get("packages", {}).get("")
        if isinstance(root_entry, dict):
            root_entry["version"] = version
        _write_json_like(lockfile, lock, original)
        written.append(lockfile)
    return written


def sync_version(repo_dir, files: Sequence[str], version: str) -> list[Path]:
    """Write ``version`` into every listed manifest under ``repo_dir``."""
    repo = Path(repo_dir)
    written = []
    for rel in files:
        manifest = repo / rel
        if not manifest.is_file():
            raise FileNotFoundError(f"{_TABLE}.sync lists {rel!r}, which does not exist")
        written += set_manifest_version(manifest, version)
    return written


def version_mismatches(repo_dir, pyproject_data: Mapping) -> list[tuple]:
    """``(path, its version, [project].version)`` for each listed manifest that differs.

    A missing manifest counts as a mismatch (its version is ``None``).
    """
    expected = pyproject_data.get("project", {}).get("version")
    out = []
    for rel in sync_files(pyproject_data):
        manifest = Path(repo_dir) / rel
        found = _read_json(manifest).get("version") if manifest.is_file() else None
        if found != expected:
            out.append((rel, found, expected))
    return out


def check_versions_agree(repo_dir, pyproject_data: Mapping) -> None:
    """Raise ``ValueError`` naming every listed manifest whose version differs."""
    mismatches = version_mismatches(repo_dir, pyproject_data)
    if mismatches:
        lines = "; ".join(
            f"{rel} has {found!r}, pyproject.toml has {expected!r}"
            for rel, found, expected in mismatches
        )
        raise ValueError(
            f"{_TABLE}.sync: versions disagree ({lines}). CI writes the version into "
            "these files at each release; set them to [project].version by hand once."
        )
