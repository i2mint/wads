"""Release a second package that lives in a subdirectory of the repo (i2mint/wads#220).

A repo can hold a pure-Python root package plus a maturin package in a subdirectory
(``thorwhalen/equate``: the root is ``equate``, ``rust/`` is ``equate-rust``, which has its
own ``pyproject.toml``). The root package keeps the ordinary ``publish`` job; each
subpackage listed here gets its own native release path::

    [[tool.wads.ci.packages]]
    dir = "rust"                    # holds a pyproject.toml; required
    release = "on-change"           # or "always": every release run
    tag_prefix = "equate-rust-v"    # tags are <tag_prefix><version>; default "<name>-v"

The subpackage's own ``pyproject.toml`` configures it exactly as a root package is
configured (``[tool.wads.ci.build.native]``, ``[tool.maturin]``): :func:`subpackage_configs`
resolves it with :func:`wads.native_build.native_build_config`. With no
``[[tool.wads.ci.packages]]`` nothing changes.

Release rule (:func:`plan_release`): ``on-change`` releases a package only when files under
its ``dir`` changed since its last tag (never tagged: it releases). The version is the next
patch after the last tag, or the version in the subpackage's ``pyproject.toml`` when that is
higher, so a hand-raised minor or major is honoured and a stale one never goes backwards.
Tags are ``<tag_prefix><version>``, so they do not collide with the root's bare ``X.Y.Z``.

Migrating a package that already releases from a hand-written workflow: create its first
tag (``<tag_prefix><current version>``) before enabling this, or the first run, finding no tag,
releases the version in ``pyproject.toml``. Two things are not covered yet: the Rust checks
(fmt, clippy, cargo test) run only for the root native path, not for a subpackage, and the
inline ``wads/data/github_ci_uv.yml`` has no subpackage jobs (the reusable workflow only).

Everything here is standard library only: the CI jobs load this file by path
(``wads/scripts/_checkout_import.py``), without installing wads.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable, Mapping, Optional, Sequence

#: ``release`` values: when a subpackage is released.
RELEASE_MODES = ("on-change", "always")
DFLT_RELEASE_MODE = "on-change"

_ENTRY_KEYS = {"dir", "release", "tag_prefix"}
_VERSION_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")
_TAG_PREFIX_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*")


@dataclass(frozen=True)
class SubPackage:
    """One entry of ``[[tool.wads.ci.packages]]``, resolved against its own pyproject."""

    dir: str
    name: str
    release: str
    tag_prefix: str
    native: object  # wads.native_build.NativeBuild

    def wheel_matrix(self) -> list:
        """One ``sub-wheels`` matrix row per target, each carrying what the job needs."""
        options = self.native.options()
        return [
            {
                **row,
                "package": self.name,
                "dir": self.dir,
                "smoke_import": options["smoke_import"],
                "maturin_args": options["maturin_args"],
            }
            for row in self.native.matrix()
        ]


def _clean_dir(value) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"dir must be a non-blank string, got {value!r}")
    path = PurePosixPath(value.strip())
    if path.is_absolute() or ".." in path.parts or str(path) == ".":
        raise ValueError(
            f"dir {value!r} must be a relative path inside the repo, not the root "
            "(the root package is the repo's own pyproject.toml)"
        )
    return str(path)


def _load_native_build():
    try:  # as part of the wads package
        from . import native_build
    except ImportError:  # loaded by path in CI
        import importlib.util
        import sys

        key = "_wads_checkout_native_build"
        if key in sys.modules:
            return sys.modules[key]
        spec = importlib.util.spec_from_file_location(
            key, Path(__file__).resolve().parent / "native_build.py"
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[key] = module
        spec.loader.exec_module(module)
        return module
    return native_build


def subpackage_configs(
    pyproject: Mapping,
    *,
    read_pyproject: Callable[[str], Mapping],
) -> list[SubPackage]:
    """The repo's :class:`SubPackage` list (empty when it declares none).

    ``read_pyproject(dir)`` returns the parsed ``<dir>/pyproject.toml``. Raises
    ``ValueError`` on an entry that does not parse, as :func:`native_build_config` does.

    >>> data = {"tool": {"wads": {"ci": {"packages": [{"dir": "rust"}]}}}}
    >>> sub = {"project": {"name": "pkg-rust", "version": "0.1.0"}, "build-system": {"build-backend": "maturin"}}
    >>> [(p.dir, p.name, p.release, p.tag_prefix)
    ...  for p in subpackage_configs(data, read_pyproject=lambda d: sub)]
    [('rust', 'pkg-rust', 'on-change', 'pkg-rust-v')]
    >>> subpackage_configs({}, read_pyproject=lambda d: sub)
    []
    """
    entries = (
        pyproject.get("tool", {}).get("wads", {}).get("ci", {}).get("packages", [])
    )
    if not entries:
        return []
    if not isinstance(entries, list):
        raise ValueError(
            "[tool.wads.ci.packages] must be an array of tables ([[tool.wads.ci.packages]])"
        )
    native_build = _load_native_build()
    out, seen_dirs, seen_prefixes = [], set(), set()
    for entry in entries:
        try:
            if not isinstance(entry, dict):
                raise ValueError(f"an entry is a table, got {entry!r}")
            unknown = set(entry) - _ENTRY_KEYS
            if unknown:
                raise ValueError(
                    f"unknown key(s) {sorted(unknown)}; known: {sorted(_ENTRY_KEYS)}"
                )
            dir_ = _clean_dir(entry.get("dir"))
            release = entry.get("release", DFLT_RELEASE_MODE)
            if release not in RELEASE_MODES:
                raise ValueError(
                    f"release must be one of {RELEASE_MODES}, got {release!r}"
                )
            sub = read_pyproject(dir_)
            native = native_build.native_build_config(sub)
            if native is None:
                raise ValueError(
                    f"{dir_}/pyproject.toml has no native path (build-backend = "
                    '"maturin" or [tool.wads.ci.build].native); only native '
                    "subpackages are supported"
                )
            if not isinstance(sub.get("project", {}).get("version"), str):
                raise ValueError(
                    f"{dir_}/pyproject.toml needs a literal [project].version (not "
                    'dynamic = ["version"]): the release stamps it'
                )
            name = sub.get("project", {}).get("name", "")
            if not name:
                raise ValueError(f"{dir_}/pyproject.toml has no [project].name")
            tag_prefix = entry.get("tag_prefix", f"{name}-v")
            if not isinstance(tag_prefix, str) or not _TAG_PREFIX_RE.fullmatch(
                tag_prefix
            ):
                raise ValueError(f"bad tag_prefix {tag_prefix!r}")
            if dir_ in seen_dirs or tag_prefix in seen_prefixes:
                raise ValueError(
                    f"duplicate dir or tag_prefix: {dir_!r}, {tag_prefix!r}"
                )
            seen_dirs.add(dir_)
            seen_prefixes.add(tag_prefix)
            out.append(SubPackage(dir_, name, release, tag_prefix, native))
        except ValueError as e:
            raise ValueError(f"[[tool.wads.ci.packages]]: {e}") from None
    return out


def parse_version(text: str) -> Optional[tuple]:
    """``(major, minor, patch)`` of an ``X.Y.Z`` string, else ``None``.

    >>> parse_version("1.2.3"), parse_version("1.2"), parse_version("v1.2.3")
    ((1, 2, 3), None, None)
    """
    m = _VERSION_RE.fullmatch(text.strip())
    return tuple(int(g) for g in m.groups()) if m else None


def latest_tag_version(tags: Sequence[str], tag_prefix: str) -> Optional[tuple]:
    """The highest version among ``<tag_prefix>X.Y.Z`` tags, or ``None``.

    >>> latest_tag_version(["p-v0.1.2", "p-v0.1.10", "q-v9.0.0", "p-vx"], "p-v")
    (0, 1, 10)
    """
    versions = [
        v
        for t in tags
        if t.startswith(tag_prefix)
        and (v := parse_version(t[len(tag_prefix) :])) is not None
    ]
    return max(versions, default=None)


def next_version(last_tag: Optional[tuple], committed: Optional[tuple]) -> tuple:
    """The release version: next patch after the last tag, unless the file is higher.

    >>> next_version((0, 1, 2), (0, 1, 0))      # stale file: follow the tags
    (0, 1, 3)
    >>> next_version((0, 1, 2), (0, 2, 0))      # hand-raised minor: honoured
    (0, 2, 0)
    >>> next_version(None, (0, 1, 0))           # never tagged: release what the file says
    (0, 1, 0)
    >>> next_version(None, None)
    (0, 0, 1)
    """
    if last_tag is None:
        return committed or (0, 0, 1)
    bumped = (last_tag[0], last_tag[1], last_tag[2] + 1)
    return max(bumped, committed or bumped)


def plan_release(
    package: SubPackage,
    *,
    tags: Sequence[str],
    committed_version: str,
    changed_since: Callable[[str], bool],
) -> Optional[str]:
    """The version to release for ``package`` now, or ``None`` when it does not release.

    ``changed_since(tag)`` says whether files under the package's dir changed since ``tag``
    (called only for ``on-change`` packages that have a tag).

    >>> from types import SimpleNamespace as NS
    >>> p = NS(dir="rust", release="on-change", tag_prefix="p-v")
    >>> plan_release(p, tags=["p-v0.1.0"], committed_version="0.1.0", changed_since=lambda t: False)
    >>> plan_release(p, tags=["p-v0.1.0"], committed_version="0.1.0", changed_since=lambda t: True)
    '0.1.1'
    >>> plan_release(p, tags=[], committed_version="0.1.0", changed_since=lambda t: False)
    '0.1.0'
    >>> plan_release(NS(dir="r", release="always", tag_prefix="p-v"), tags=["p-v1.0.0"],
    ...              committed_version="0.1.0", changed_since=lambda t: False)
    '1.0.1'
    """
    last = latest_tag_version(tags, package.tag_prefix)
    if package.release == "on-change" and last is not None:
        tag = f"{package.tag_prefix}{'.'.join(map(str, last))}"
        if not changed_since(tag):
            return None
    version = next_version(last, parse_version(committed_version))
    return ".".join(map(str, version))


_VERSION_LINE_RE = re.compile(r'^(version\s*=\s*)"[^"]*"', re.MULTILINE)


def stamp_version(pyproject_text: str, version: str) -> str:
    """``pyproject_text`` with ``[project].version`` set to ``version``.

    >>> stamp_version('[project]\\nname = "p"\\nversion = "0.1.0"\\n[tool.x]\\nversion = "9"\\n', "0.2.0")
    '[project]\\nname = "p"\\nversion = "0.2.0"\\n[tool.x]\\nversion = "9"\\n'
    """
    head, sep, rest = pyproject_text.partition("\n[project]")
    if not sep:
        if pyproject_text.startswith("[project]"):
            head, sep, rest = "", "[project]", pyproject_text[len("[project]") :]
        else:
            raise ValueError("no [project] table to stamp a version into")
    body, bsep, tail = rest.partition("\n[")
    stamped, n = _VERSION_LINE_RE.subn(rf'\g<1>"{version}"', body, count=1)
    if n != 1:
        raise ValueError(
            "[project].version is missing or dynamic; a subpackage needs a literal version"
        )
    return head + sep + stamped + bsep + tail
