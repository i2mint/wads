"""Native (compiled-extension) builds: which repos get one, for which targets.

A package built with `maturin <https://www.maturin.rs/>`_ (a Rust/PyO3 extension) needs one
wheel per platform, built on that platform's runner, where a pure-Python package needs one
``uv build``. The reusable workflow (``uv-ci.yml``) has a native path for it (issue #166),
and every job on that path is gated on the setup job's ``native`` output, so pure-Python
repos run exactly what they ran before.

The path is on when ``[build-system].build-backend = "maturin"`` (auto-detected) or when
``[tool.wads.ci.build].native`` says so. ``native`` takes a backend name, ``false``, or a
table for the details::

    [tool.wads.ci.build]
    native = "maturin"            # or false: no native path even with a maturin backend

    [tool.wads.ci.build.native]   # the table form (instead of the line above)
    targets = ["linux-x86_64", "macos-arm64"]     # names from NATIVE_TARGETS, or tables
    maturin_args = ["--release", "--locked"]
    smoke_import = "mypkg._core"                  # default: [tool.maturin].module-name
    cargo_test_args = ["-p", "mypkg-core"]        # default: derived from cargo metadata

A target is a name from :data:`NATIVE_TARGETS` or a table with the same keys (``name``,
``runner``, ``target``, and optionally ``manylinux``, ``python_arch``, ``smoke``), for a
platform the registry lacks (musllinux, Windows on ARM). Everything here is standard
library only: the setup job loads this file by path, without installing wads.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Optional

#: Build backends with a native path. The value is the backend's ``build-backend`` string.
NATIVE_BACKENDS = {"maturin": "maturin"}


@dataclass(frozen=True)
class NativeTarget:
    """One wheel to build: the runner it builds on and maturin's ``--target``.

    ``smoke`` says whether the runner can import the wheel it built (a cross-compiled
    wheel, macOS x86_64 on an arm64 runner, cannot).
    """

    name: str
    runner: str
    target: str
    manylinux: str = ""
    python_arch: str = ""
    smoke: bool = True


#: The default wheel matrix: the platforms the fleet's users run. abi3 wheels, so one
#: build per platform covers every supported CPython.
NATIVE_TARGETS = {
    t.name: t
    for t in (
        NativeTarget("linux-x86_64", "ubuntu-latest", "x86_64", manylinux="auto"),
        NativeTarget("linux-aarch64", "ubuntu-24.04-arm", "aarch64", manylinux="auto"),
        NativeTarget("macos-arm64", "macos-latest", "aarch64"),
        NativeTarget("macos-x86_64", "macos-latest", "x86_64", smoke=False),
        NativeTarget("windows-x64", "windows-latest", "x64", python_arch="x64"),
    )
}
DFLT_NATIVE_TARGETS = tuple(NATIVE_TARGETS)
DFLT_MATURIN_ARGS = ("--release", "--locked")

_TARGET_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


@dataclass(frozen=True)
class NativeBuild:
    """The resolved native-build settings of one repo."""

    backend: str
    targets: tuple = field(default_factory=tuple)
    maturin_args: tuple = DFLT_MATURIN_ARGS
    smoke_import: str = ""
    #: The binding crate's Cargo.toml (``[tool.maturin].manifest-path``); cargo finds the
    #: workspace from it.
    manifest_path: str = "Cargo.toml"
    #: ``None``: derive from cargo metadata (every crate but the binding one).
    cargo_test_args: Optional[tuple] = None

    def matrix(self) -> list:
        """The ``native-wheels`` job's ``matrix.include``."""
        return [asdict(t) for t in self.targets]

    def options(self) -> dict:
        """Everything but the matrix, as the setup job's ``native-options`` output."""
        return {
            "maturin_args": " ".join(self.maturin_args),
            "smoke_import": self.smoke_import,
            "manifest_path": self.manifest_path,
            "cargo_test_args": (
                None if self.cargo_test_args is None else list(self.cargo_test_args)
            ),
        }


def _target(entry) -> NativeTarget:
    if isinstance(entry, str):
        if entry not in NATIVE_TARGETS:
            raise ValueError(
                f"unknown target {entry!r}; known: {', '.join(NATIVE_TARGETS)} "
                "(or give a table with name, runner and target)"
            )
        return NATIVE_TARGETS[entry]
    if isinstance(entry, dict):
        try:
            target = NativeTarget(**entry)
        except TypeError as e:
            raise ValueError(f"bad target table {entry!r}: {e}") from None
        if not _TARGET_NAME_RE.fullmatch(target.name):
            raise ValueError(f"bad target name {target.name!r}")
        return target
    raise ValueError(f"a target is a name or a table, got {entry!r}")


def _str_tuple(value, *, key: str) -> tuple:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ValueError(f"{key} must be a list of strings, got {value!r}")
    return tuple(value)


def _declared_backend(declared, build_backend: str) -> Optional[str]:
    """The backend a ``native`` value names (``None``: off), auto-detecting on ``None``."""
    if declared is None or declared is True:
        detected = [n for n, b in NATIVE_BACKENDS.items() if build_backend == b]
        if declared is True and not detected:
            raise ValueError(
                f"native = true, but build-backend {build_backend!r} has no native path "
                f"(known: {', '.join(NATIVE_BACKENDS)}); name the backend instead"
            )
        return detected[0] if detected else None
    if declared is False:
        return None
    if declared in NATIVE_BACKENDS:
        return declared
    raise ValueError(
        f"native must be one of {', '.join(NATIVE_BACKENDS)}, true, false or a table, "
        f"got {declared!r}"
    )


def native_build_config(pyproject: dict) -> Optional[NativeBuild]:
    """The repo's :class:`NativeBuild`, or ``None`` when it has no native path.

    Raises ``ValueError`` on a setting that does not parse: only a repo that wrote native
    settings can hit it, and a red setup job beats a release that silently builds
    something else.

    >>> native_build_config({"build-system": {"build-backend": "hatchling.build"}}) is None
    True
    >>> nb = native_build_config({
    ...     "build-system": {"build-backend": "maturin"},
    ...     "tool": {"maturin": {"module-name": "pkg._core"}},
    ... })
    >>> nb.backend, [t["name"] for t in nb.matrix()][:2], nb.smoke_import
    ('maturin', ['linux-x86_64', 'linux-aarch64'], 'pkg._core')
    """
    tool = pyproject.get("tool", {})
    declared = tool.get("wads", {}).get("ci", {}).get("build", {}).get("native")
    table = declared if isinstance(declared, dict) else {}
    build_backend = pyproject.get("build-system", {}).get("build-backend", "")
    try:
        backend = _declared_backend(
            table.get("backend") if isinstance(declared, dict) else declared,
            build_backend,
        )
        if backend is None:
            return None
        unknown = set(table) - _TABLE_KEYS
        if unknown:
            raise ValueError(
                f"unknown key(s) {sorted(unknown)}; known: {sorted(_TABLE_KEYS)}"
            )
        maturin = tool.get("maturin", {})
        module_name = maturin.get("module-name", "")
        import_name = pyproject.get("project", {}).get("name", "").replace("-", "_")
        cargo_test = table.get("cargo_test_args")
        return NativeBuild(
            backend=backend,
            targets=_targets(table.get("targets", list(DFLT_NATIVE_TARGETS))),
            maturin_args=_str_tuple(
                table.get("maturin_args", list(DFLT_MATURIN_ARGS)), key="maturin_args"
            ),
            smoke_import=_non_blank_str(
                table.get("smoke_import", module_name or import_name),
                key="smoke_import",
            ),
            manifest_path=maturin.get("manifest-path", "Cargo.toml"),
            cargo_test_args=(
                None
                if cargo_test is None
                else _str_tuple(cargo_test, key="cargo_test_args")
            ),
        )
    except ValueError as e:
        raise ValueError(f"[tool.wads.ci.build].native: {e}") from None


_TABLE_KEYS = {"backend", "targets", "maturin_args", "smoke_import", "cargo_test_args"}


def _targets(value) -> tuple:
    if not isinstance(value, list) or not value:
        raise ValueError(f"targets must be a non-empty list, got {value!r}")
    targets = tuple(_target(entry) for entry in value)
    if len({t.name for t in targets}) != len(targets):
        raise ValueError(f"target names must be unique: {[t.name for t in targets]}")
    return targets


def _non_blank_str(value, *, key: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-blank string, got {value!r}")
    return value.strip()


def cargo_test_args(metadata: dict, *, binding_manifest: str) -> list:
    """``cargo test`` arguments for every workspace crate except the binding one.

    The binding crate (the ``cdylib`` maturin builds, at ``binding_manifest``) is tested
    through Python: its own test binary needs libpython at link and load time. ``metadata``
    is ``cargo metadata --no-deps --format-version 1``. An empty list means there is no
    pure-Rust crate to test (a single-crate package).

    >>> meta = {"packages": [
    ...     {"name": "pkg-core", "manifest_path": "/r/rust/core/Cargo.toml"},
    ...     {"name": "pkg-py", "manifest_path": "/r/rust/py/Cargo.toml"},
    ... ]}
    >>> cargo_test_args(meta, binding_manifest="/r/rust/py/Cargo.toml")
    ['--workspace', '--exclude', 'pkg-py']
    >>> cargo_test_args({"packages": meta["packages"][1:]}, binding_manifest="/r/rust/py/Cargo.toml")
    []
    """
    from pathlib import Path

    binding = Path(binding_manifest).resolve()
    packages = metadata.get("packages", [])
    names = [
        p["name"] for p in packages if Path(p["manifest_path"]).resolve() == binding
    ]
    others = [p for p in packages if p["name"] not in names]
    if not others:
        return []
    return ["--workspace", *(arg for name in names for arg in ("--exclude", name))]
