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

And one in npm-ci: npm packs the commit that was pushed, which comes *before* the
bump commit of the Python release the same push cuts, so it would carry the
previous release's number with newer code. :func:`npm_publish_refusal` refuses
that publish (see its docstring).

Only ``package.json`` is supported: a Rust crate usually keeps its own version
line. This module imports only the standard library (and ``wads.ci_config``, which
does too), because the CI scripts load it by path from the wads checkout
(``wads/scripts/_checkout_import.py``).
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
    return json.loads(_read_text(path))


#: How npm reads a JSON file's layout (``json-parse-even-better-errors``): the line
#: ending(s) right after the opening bracket, then the indentation of the next line.
#: No line break there means a minified file.
_JSON_LAYOUT = re.compile(r"^\s*[{\[]((?:\r?\n)+)([ \t]*)")


def _dump_json_like(data, original: str) -> str:
    """``data`` as JSON laid out the way ``npm version`` writes ``original`` back.

    Keeps the indentation and line endings (``\\r\\n`` stays ``\\r\\n``), ends an
    indented file with one line ending, and keeps a minified file minified (no
    spaces, no final newline), byte for byte what npm writes.

    >>> _dump_json_like({"a": [1]}, '{\\r\\n\\t"a": []\\r\\n}')
    '{\\r\\n\\t"a": [\\r\\n\\t\\t1\\r\\n\\t]\\r\\n}\\r\\n'
    >>> _dump_json_like({"a": [1]}, '{"a": []}\\n')
    '{"a":[1]}'
    """
    match = _JSON_LAYOUT.match(original)
    if not match:
        return json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    newline, indent = match.groups()
    text = json.dumps(data, indent=indent, ensure_ascii=False) + "\n"
    return text.replace("\n", newline)


def _write_json_like(path: Path, data: dict, original: str) -> None:
    """Write ``data`` to ``path`` in ``original``'s layout (bytes, so no newline translation)."""
    path.write_bytes(_dump_json_like(data, original).encode("utf-8"))


def _read_text(path: Path) -> str:
    """A file's text with its line endings as they are (``read_text`` would turn CRLF into LF)."""
    return path.read_bytes().decode("utf-8")


def set_json_version(path: Path, version: str) -> None:
    """Write ``version`` into one ``package.json`` or ``package-lock.json``, as npm would.

    A lockfile carries the version twice: at the top and on its root package
    (``packages[""]``); dependencies' versions are left alone. Everything else in
    the file, and its layout, is kept. Used by the release (:func:`set_manifest_version`)
    and by the git-commit action's push-back conflict resolver.
    """
    path = Path(path)
    if not SEMVER.match(version):
        raise ValueError(
            f"version {version!r} is not semver, which npm requires; "
            f"cannot write it into {path}"
        )
    original = _read_text(path)
    data = json.loads(original)
    data["version"] = version
    if path.name == NPM_LOCKFILE:
        root_entry = data.get("packages", {}).get("")
        if isinstance(root_entry, dict):
            root_entry["version"] = version
    _write_json_like(path, data, original)


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
    written = [manifest]
    set_json_version(manifest, version)
    lockfile = manifest.with_name(NPM_LOCKFILE)
    if lockfile.is_file():
        set_json_version(lockfile, version)
        written.append(lockfile)
    return written


def sync_version(repo_dir, files: Sequence[str], version: str) -> list[Path]:
    """Write ``version`` into every listed manifest under ``repo_dir``."""
    repo = Path(repo_dir)
    written = []
    for rel in files:
        manifest = repo / rel
        if not manifest.is_file():
            raise FileNotFoundError(
                f"{_TABLE}.sync lists {rel!r}, which does not exist"
            )
        written += set_manifest_version(manifest, version)
    return written


def static_project_version(pyproject_data: Mapping) -> str:
    """``[project].version``, which ``sync`` needs: CI bumps and copies that line.

    >>> static_project_version({"project": {"version": "1.2.3"}})
    '1.2.3'
    >>> static_project_version({"project": {"dynamic": ["version"]}})
    Traceback (most recent call last):
      ...
    ValueError: [tool.wads.ci.version].sync needs a static [project].version in pyproject.toml, and this project's version is dynamic. Make it static, or remove the sync key (and keep the npm version by hand).
    """
    project = pyproject_data.get("project", {})
    version = project.get("version")
    if isinstance(version, str) and version:
        return version
    if "version" in project.get("dynamic", []):
        where = "dynamic"
    elif not project:
        where = "not in a [project] table (setup.cfg or setup.py?)"
    else:
        where = "missing"
    raise ValueError(
        f"{_TABLE}.sync needs a static [project].version in pyproject.toml, "
        f"and this project's version is {where}. Make it static, or remove the "
        "sync key (and keep the npm version by hand)."
    )


def version_mismatches(repo_dir, pyproject_data: Mapping) -> list[tuple]:
    """``(path, its version, [project].version)`` for each listed manifest that differs.

    A missing manifest counts as a mismatch (its version is ``None``).
    """
    files = sync_files(pyproject_data)
    if not files:
        return []
    expected = static_project_version(pyproject_data)
    out = []
    for rel in files:
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


# --- npm publish guard (the off-by-one of i2mint/wads#210) ---------------------
#
# npm-ci packs the commit that was pushed. When the same push also cuts a PyPI
# release, uv-ci's bump commit (which writes X.Y.Z+1 into the synced package.json)
# lands *after* it, so the tarball would carry the previous release's number with
# the newer code. Ordering npm after PyPI in one run is still open (#210 item 3);
# until then, npm-ci refuses such a publish before anything is uploaded.


def _ci_config(pyproject_data: Mapping):
    """wads' ``CIConfig`` over ``pyproject_data``: the SSOT for the publish markers.

    Imported normally when this module is ``wads.version_sync``; loaded from the
    file beside this one when a CI script loaded this module by path from a wads
    checkout (``wads/scripts/_checkout_import.py``), where there is no package.
    """
    try:
        from .ci_config import CIConfig
    except ImportError:
        import importlib.util
        import sys

        name = "_wads_checkout_ci_config"  # the name _checkout_import gives it
        module = sys.modules.get(name)
        if module is None:
            spec = importlib.util.spec_from_file_location(
                name, Path(__file__).with_name("ci_config.py")
            )
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
        CIConfig = module.CIConfig
    return CIConfig(dict(pyproject_data))


def pypi_release_expected(pyproject_data: Mapping, subject: str) -> bool:
    """Whether uv-ci's publish job releases to PyPI for a push with this commit ``subject``.

    Mirrors uv-ci's gates (markers match the subject case-insensitively, like
    GitHub's ``contains()``): the skip-ci and skip-publish markers suppress the
    release; with ``[tool.wads.ci.publish].enabled = false`` only the publish
    marker cuts one; in on-demand trigger mode only the deploy marker does, or
    the run-ci marker when ``run_ci_publishes`` is on.

    >>> pypi_release_expected({}, "Fix a typo")
    True
    >>> pypi_release_expected({}, "Fix a typo [Skip Publish]")
    False
    >>> off = {"tool": {"wads": {"ci": {"publish": {"enabled": False}}}}}
    >>> pypi_release_expected(off, "Fix a typo"), pypi_release_expected(off, "Fix [publish]")
    (False, True)
    """
    config = _ci_config(pyproject_data)
    lowered = subject.lower()

    def has(marker) -> bool:
        return isinstance(marker, str) and bool(marker) and marker.lower() in lowered

    if has(config.publish_skip_ci_marker) or has(config.publish_skip_publish_marker):
        return False
    if not (config.publish_enabled or has(config.publish_marker)):
        return False
    if config.trigger_mode == "on-demand":
        return has(config.deploy_marker) or (
            has(config.run_ci_marker) and config.run_ci_publishes
        )
    return True


def _posix_dir(path: str) -> str:
    """A repo-relative directory as ``a/b``; ``""`` for the repo root."""
    posix = PurePosixPath(str(path).replace("\\", "/")).as_posix()
    return "" if posix in (".", "/") else posix.strip("/")


def _inside(path: str, directory: str) -> bool:
    """Whether the file ``path`` lies under ``directory`` (``""``: the repo root)."""
    return not directory or path.startswith(directory + "/")


#: How many of the files changed outside the npm package a refusal names.
_SHOWN_CHANGES = 5


def npm_publish_refusal(
    pyproject_data: Mapping,
    package_dir: str,
    changed_files: Sequence[str],
    subject: str,
) -> "str | None":
    """Why npm-ci must not publish ``package_dir`` from this push, or ``None`` when it may.

    It refuses only when all of these hold:

    - ``[tool.wads.ci.version].sync`` lists a manifest inside ``package_dir`` (so
      its version comes from the Python release);
    - this push also cuts a PyPI release (:func:`pypi_release_expected`), whose
      bump commit comes after the commit npm packs;
    - the push changes files outside ``package_dir`` (``changed_files``, repo
      relative). A push that changes only the npm package publishes the version
      the last Python release wrote. When the npm package is the repo root,
      every change counts as outside it.

    >>> data = {"project": {"version": "1.2.3"},
    ...         "tool": {"wads": {"ci": {"version": {"sync": ["ts/package.json"]}}}}}
    >>> npm_publish_refusal(data, "ts", ["ts/src/a.ts"], "Release [publish-npm]") is None
    True
    >>> print(npm_publish_refusal(data, "ts", ["ts/src/a.ts", "pkg/b.py"], "Release [publish-npm]"))
    This push also releases the Python package, so npm would get the previous release's number (1.2.3) with newer code: uv-ci writes the new number into ts/package.json in its bump commit, after this one. Publish npm from a commit that changes only ts/ (or carries the skip-publish marker '[skip publish]'). Changed outside ts/: pkg/b.py
    >>> npm_publish_refusal(data, "ts", ["pkg/b.py"], "Release [publish-npm] [skip publish]") is None
    True
    >>> npm_publish_refusal({}, "ts", ["pkg/b.py"], "Release [publish-npm]") is None
    True
    """
    directory = _posix_dir(package_dir)
    synced = [f for f in sync_files(pyproject_data) if _inside(f, directory)]
    if not synced or not pypi_release_expected(pyproject_data, subject):
        return None
    # At the repo root nothing is outside the npm package, and everything ships
    # with the Python release too.
    outside = [
        f
        for f in changed_files
        if not (directory and _inside(_posix_dir(f), directory))
    ]
    if not outside:
        return None
    version = pyproject_data.get("project", {}).get("version")
    marker = _ci_config(pyproject_data).publish_skip_publish_marker
    previous = f" ({version})" if version else ""
    if directory:
        how = (
            f"Publish npm from a commit that changes only {directory}/ "
            f"(or carries the skip-publish marker {marker!r})."
        )
    else:
        how = (
            "The npm package is the repo root, so every change ships with the Python "
            f"release: publish npm from a commit carrying the skip-publish marker {marker!r}."
        )
    label = f"Changed outside {directory}/" if directory else "Changed"
    shown = ", ".join(outside[:_SHOWN_CHANGES])
    more = (
        f" and {len(outside) - _SHOWN_CHANGES} more"
        if len(outside) > _SHOWN_CHANGES
        else ""
    )
    return (
        "This push also releases the Python package, so npm would get the previous "
        f"release's number{previous} with newer code: uv-ci writes the new number "
        f"into {', '.join(synced)} in its bump commit, after this one. {how} "
        f"{label}: {shown}{more}"
    )
