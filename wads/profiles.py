"""Declarative generation *profiles* and *overlays* built on the engine.

A *profile* is a named declarative description of a project setup expressed as a
list of :class:`wads.templating.Artifact`. The default profile (``python-lib``)
is produced by :mod:`wads.populate`.

This module hosts two opt-in overlays added *on top of* an existing project:

- The **frontend profile registry** (issue #39): a small registry of
  language/toolchain profiles -- ``js`` (the original #32 overlay, the
  back-compat anchor), ``ts`` (single-package TypeScript), and ``ts-monorepo``
  (pnpm workspaces + turbo). A project may declare several frontend components
  (e.g. ``js`` *and* ``ts``); each lives in its own subdir with its own
  path-filtered workflow, so they never collide. Selected via
  ``populate --frontend <profile>[,<profile>]`` (``--with-npm`` stays as an
  alias for ``--frontend js``). Profiles are extensible through
  :func:`register_frontend_profile`.
- The **tests-folder overlay** (issue #4): scaffolds a ``tests/`` package.
- The **native-core registry** (issue #214): a Rust core built by maturin behind
  a Python facade (``populate --native maturin``); see :func:`apply_native`.

Nothing here runs by default; the Python ``populate`` path and the
``name/name/`` root layout are untouched.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, Mapping, Optional

from wads import (
    package_json_tpl_path,
    github_ci_npm_stub_path,
    package_json_ts_tpl_path,
    tsconfig_tpl_path,
    tsconfig_test_tpl_path,
    ts_index_tpl_path,
    ts_index_test_tpl_path,
    pnpm_workspace_tpl_path,
    turbo_tpl_path,
    package_json_monorepo_root_tpl_path,
    tsconfig_base_tpl_path,
    package_json_monorepo_pkg_tpl_path,
    tsconfig_monorepo_pkg_tpl_path,
    tests_init_tpl_path,
    test_smoke_tpl_path,
    tests_util_tpl_path,
)
from wads.templating import (
    Artifact,
    FilesystemTemplateSource,
    GenerationResult,
    generate,
)

# Map common license identifiers to SPDX identifiers npm expects.
_SPDX_BY_NAME = {
    "mit": "MIT",
    "apache": "Apache-2.0",
    "apache-2.0": "Apache-2.0",
    "apache software license": "Apache-2.0",
    "bsd": "BSD-3-Clause",
    "bsd-3-clause": "BSD-3-Clause",
    "gpl": "GPL-3.0-or-later",
    "gpl-3.0": "GPL-3.0-or-later",
}


def _to_spdx(license_name: Optional[str]) -> str:
    if not license_name:
        return "MIT"
    return _SPDX_BY_NAME.get(license_name.strip().lower(), license_name)


# --------------------------------------------------------------------------------------
# Frontend profile registry (issue #39)
#
# Each profile is a declarative description of one frontend component: where it
# lives (``default_subdir``), which package manager drives it
# (``default_package_manager``), and an ``artifacts(context) -> list[Artifact]``
# builder. Profiles are registered in :data:`FRONTEND_PROFILES` and selected by
# name. A single :func:`apply_frontend` call applies one component; a project may
# apply several (e.g. ``js`` and ``ts``) without collision because each component
# owns its own subdir and a per-subdir workflow file.
# --------------------------------------------------------------------------------------

#: Where a Python package and its npm twin keep the golden cases both test suites
#: run (i2mint/wads#209). A change there runs the npm CI as well as the Python CI.
DFLT_SHARED_FIXTURES_DIR = "fixtures"
#: Where a Rust core lives in the native (maturin) layout; when present, a change
#: there runs the npm CI too (a wasm build may compile it).
DFLT_RUST_DIR = "rust"


def default_npm_watch_paths(repo_dir: Optional[str] = None) -> list:
    """Inputs outside its subdir an npm component's CI should run on.

    The shared fixtures directory always (a pattern that matches nothing costs
    nothing), and the Rust core when ``repo_dir`` has one.

    >>> default_npm_watch_paths()
    ['fixtures/**']
    """
    paths = [f"{DFLT_SHARED_FIXTURES_DIR}/**"]
    if repo_dir and os.path.isdir(os.path.join(repo_dir, DFLT_RUST_DIR)):
        paths.append(f"{DFLT_RUST_DIR}/**")
    return paths


# The reusable workflow each profile's stub calls (hosted in this repo).
_SINGLE_PACKAGE_REUSABLE = "npm-ci.yml"
_MONOREPO_REUSABLE = "npm-ci-monorepo.yml"


def _workflow_basename(subdir: str) -> str:
    """Per-component workflow filename, collision-free across subdirs.

    Back-compat anchor: the historical single overlay (subdir ``js``) keeps the
    bare ``npm-ci.yml`` name, so existing ``js`` output stays byte-compatible;
    every other component gets ``npm-ci-<subdir>.yml`` (slashes flattened),
    path-filtered to its own subdir.

    >>> _workflow_basename("js")
    'npm-ci.yml'
    >>> _workflow_basename("ts")
    'npm-ci-ts.yml'
    """
    if subdir == "js":
        return "npm-ci.yml"
    slug = subdir.strip("/").replace("/", "-")
    return f"npm-ci-{slug}.yml"


def _workflow_name(subdir: str) -> str:
    """Human-facing workflow ``name:`` -- ``NPM CI`` for the ``js`` anchor."""
    return "NPM CI" if subdir == "js" else f"NPM CI ({subdir})"


def frontend_context(
    *,
    profile_name: str,
    project_name: str,
    description: str = "",
    license: Optional[str] = None,
    subdir: str,
    package_name: Optional[str] = None,
    version: str = "0.0.1",
    package_manager: str = "npm",
    workspace_glob: str = "packages/*",
    example_package_name: Optional[str] = None,
    license_file: Optional[tuple] = None,
    watch_paths: Optional[list] = None,
) -> dict:
    """Build the render context shared by all frontend-profile templates.

    The returned mapping is a superset: it carries the keys every profile's
    templates may reference (single-package and monorepo). Unused keys are
    harmless under Jinja ``StrictUndefined`` because that only errors on keys a
    template *references* yet are missing.
    """
    reusable = (
        _MONOREPO_REUSABLE
        if profile_name == "ts-monorepo"
        else _SINGLE_PACKAGE_REUSABLE
    )
    return {
        "npm_package_name": package_name or project_name,
        "npm_version": version,
        "description": description,
        "npm_license": _to_spdx(license),
        "npm_subdir": subdir,
        "npm_package_manager": package_manager,
        # Stub workflow wiring (per-component, collision-free):
        "npm_workflow_name": _workflow_name(subdir),
        "npm_workflow_file": _workflow_basename(subdir),
        # Shared inputs outside the subdir that also run this component's CI:
        "npm_watch_paths": (
            default_npm_watch_paths() if watch_paths is None else list(watch_paths)
        ),
        "reusable_workflow": reusable,
        # Monorepo-only context (ignored by single-package templates):
        "npm_workspace_glob": workspace_glob,
        "example_package_name": example_package_name or (package_name or project_name),
        # The repo's root licence as ``(file name, text)``, copied next to each
        # published package.json (npm packs a LICENSE found there; the root one
        # is outside the tarball). ``None`` when the repo has none.
        "license_file": license_file,
    }


#: Root licence file names a frontend component copies, in order of preference.
LICENSE_FILENAMES = ("LICENSE", "LICENSE.md", "LICENSE.txt", "LICENCE", "COPYING")


def find_license_file(
    repo_dir: str, *, names: tuple = LICENSE_FILENAMES
) -> Optional[tuple]:
    """``(file name, text)`` of the repo's root licence, or ``None`` if it has none.

    >>> import tempfile
    >>> d = tempfile.mkdtemp()
    >>> find_license_file(d) is None
    True
    >>> _ = open(os.path.join(d, "LICENSE.md"), "w").write("MIT")
    >>> find_license_file(d)
    ('LICENSE.md', 'MIT')
    """
    for name in names:
        path = os.path.join(repo_dir, name)
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                return name, f.read()
    return None


def _src(tpl_path: str) -> FilesystemTemplateSource:
    """One-entry filesystem source whose key is the template's basename."""
    return FilesystemTemplateSource(os.path.dirname(tpl_path))


def _jinja(target: str, tpl_path: str) -> Artifact:
    return Artifact.from_jinja(target, os.path.basename(tpl_path), _src(tpl_path))


def _copy(target: str, tpl_path: str) -> Artifact:
    return Artifact.from_copy(target, os.path.basename(tpl_path), _src(tpl_path))


def _license_artifacts(package_dir: str, ctx: Mapping) -> list:
    """Copy the repo's root licence into ``package_dir`` (nothing when there is none).

    npm always packs a LICENSE that sits next to ``package.json``, but a component
    in a subdir does not see the repo root's, so its tarball shipped without one.
    The copy is derived: :func:`apply_frontend` rewrites it whenever it differs.
    """
    if not ctx.get("license_file"):
        return []
    name, text = ctx["license_file"]
    return [Artifact(f"{package_dir}/{name}", lambda _ctx: text)]


def _stub_artifact(subdir: str) -> Artifact:
    """The ``.github/workflows/<file>.yml`` stub for a component in ``subdir``.

    The target filename is resolved in Python (collision-free per subdir); the
    stub *content* renders the same filename into its own path filter via the
    ``npm_workflow_file`` context key.
    """
    return _jinja(
        f".github/workflows/{_workflow_basename(subdir)}", github_ci_npm_stub_path
    )


# --- per-profile artifact builders --------------------------------------------


def _js_artifacts(ctx: Mapping) -> list:
    """``js`` profile: the original #32 overlay (back-compat anchor)."""
    subdir = ctx["npm_subdir"]
    return [
        _jinja(f"{subdir}/package.json", package_json_tpl_path),
        *_license_artifacts(subdir, ctx),
        _stub_artifact(subdir),
    ]


def _ts_artifacts(ctx: Mapping) -> list:
    """``ts`` profile: single-package TypeScript (tsconfig + src + build/test)."""
    subdir = ctx["npm_subdir"]
    return [
        _jinja(f"{subdir}/package.json", package_json_ts_tpl_path),
        _copy(f"{subdir}/tsconfig.json", tsconfig_tpl_path),
        _copy(f"{subdir}/tsconfig.test.json", tsconfig_test_tpl_path),
        *_license_artifacts(subdir, ctx),
        _copy(f"{subdir}/src/index.ts", ts_index_tpl_path),
        # Ship a passing starter test so the `test` step is green out of the
        # box: `vitest run` exits 1 when it finds *no* test files (issue #41).
        _copy(f"{subdir}/src/index.test.ts", ts_index_test_tpl_path),
        _stub_artifact(subdir),
    ]


def _ts_monorepo_artifacts(ctx: Mapping) -> list:
    """``ts-monorepo`` profile: pnpm workspaces + turbo, one example package.

    The workspace root lives at ``<subdir>/`` and an example package at
    ``<subdir>/packages/core/``. The stub calls the reusable *monorepo* workflow,
    which discovers and matrixes over the workspace packages.
    """
    subdir = ctx["npm_subdir"]
    pkg_dir = f"{subdir}/packages/core"
    return [
        _jinja(f"{subdir}/package.json", package_json_monorepo_root_tpl_path),
        _jinja(f"{subdir}/pnpm-workspace.yaml", pnpm_workspace_tpl_path),
        _copy(f"{subdir}/turbo.json", turbo_tpl_path),
        _copy(f"{subdir}/tsconfig.base.json", tsconfig_base_tpl_path),
        _jinja(f"{pkg_dir}/package.json", package_json_monorepo_pkg_tpl_path),
        _copy(f"{pkg_dir}/tsconfig.json", tsconfig_monorepo_pkg_tpl_path),
        _copy(f"{pkg_dir}/tsconfig.test.json", tsconfig_test_tpl_path),
        *_license_artifacts(pkg_dir, ctx),
        _copy(f"{pkg_dir}/src/index.ts", ts_index_tpl_path),
        # Passing starter test so `turbo run test` is green out of the box (#41).
        _copy(f"{pkg_dir}/src/index.test.ts", ts_index_test_tpl_path),
        _stub_artifact(subdir),
    ]


@dataclass(frozen=True)
class FrontendProfile:
    """A declarative frontend language/toolchain profile.

    :param name: registry key (e.g. ``"js"``, ``"ts"``, ``"ts-monorepo"``).
    :param default_subdir: subdir the component lives in when unspecified.
    :param default_package_manager: ``"npm"`` or ``"pnpm"``.
    :param artifacts: ``context -> list[Artifact]`` builder for this profile.
    :param description: one-line human summary.
    """

    name: str
    default_subdir: str
    default_package_manager: str
    artifacts: Callable[[Mapping], list]
    description: str = ""


#: The frontend profile registry. Extend it via :func:`register_frontend_profile`.
FRONTEND_PROFILES: dict = {}


def register_frontend_profile(profile: FrontendProfile) -> FrontendProfile:
    """Register (or override) a frontend profile by name. Returns the profile."""
    FRONTEND_PROFILES[profile.name] = profile
    return profile


def get_frontend_profile(name: str) -> FrontendProfile:
    """Look up a registered profile, with an informative error if unknown."""
    try:
        return FRONTEND_PROFILES[name]
    except KeyError:
        available = ", ".join(sorted(FRONTEND_PROFILES)) or "(none registered)"
        raise ValueError(
            f"Unknown frontend profile {name!r}. Available: {available}."
        ) from None


register_frontend_profile(
    FrontendProfile(
        name="js",
        default_subdir="js",
        default_package_manager="npm",
        artifacts=_js_artifacts,
        description="JavaScript single package (the original #32 overlay).",
    )
)
register_frontend_profile(
    FrontendProfile(
        name="ts",
        default_subdir="ts",
        default_package_manager="npm",
        artifacts=_ts_artifacts,
        description="TypeScript single package (tsconfig + tsup build + vitest).",
    )
)
register_frontend_profile(
    FrontendProfile(
        name="ts-monorepo",
        default_subdir="ts",
        default_package_manager="pnpm",
        artifacts=_ts_monorepo_artifacts,
        description="TypeScript monorepo (pnpm workspaces + turbo).",
    )
)


def apply_frontend(
    pkg_dir: str,
    *,
    profile: str = "js",
    project_name: str,
    description: str = "",
    license: Optional[str] = None,
    subdir: Optional[str] = None,
    package_name: Optional[str] = None,
    version: str = "0.0.1",
    package_manager: Optional[str] = None,
    workspace_glob: str = "packages/*",
    example_package_name: Optional[str] = None,
    watch_paths: Optional[list] = None,
    overwrite=(),
    on_add=None,
    on_skip=None,
) -> GenerationResult:
    """Apply one frontend profile component to an existing project directory.

    ``subdir`` and ``package_manager`` default to the selected profile's
    defaults. ``watch_paths`` are the inputs outside the subdir that also run the
    component's CI (default :func:`default_npm_watch_paths` of ``pkg_dir``).
    Returns the :class:`wads.templating.GenerationResult`.

    >>> import tempfile
    >>> d = tempfile.mkdtemp()
    >>> res = apply_frontend(d, profile="ts", project_name="widget")
    >>> sorted(res.added)  # doctest: +NORMALIZE_WHITESPACE
    ['.github/workflows/npm-ci-ts.yml', 'ts/package.json', 'ts/src/index.test.ts',
     'ts/src/index.ts', 'ts/tsconfig.json', 'ts/tsconfig.test.json']
    """
    prof = get_frontend_profile(profile)
    subdir = subdir or prof.default_subdir
    package_manager = package_manager or prof.default_package_manager
    context = frontend_context(
        profile_name=prof.name,
        project_name=project_name,
        description=description,
        license=license,
        subdir=subdir,
        package_name=package_name,
        version=version,
        package_manager=package_manager,
        workspace_glob=workspace_glob,
        example_package_name=example_package_name,
        license_file=find_license_file(pkg_dir),
        watch_paths=(
            default_npm_watch_paths(pkg_dir) if watch_paths is None else watch_paths
        ),
    )
    artifacts = prof.artifacts(context)
    return generate(
        pkg_dir,
        artifacts,
        context,
        overwrite=_with_stale_license_copies(pkg_dir, artifacts, context, overwrite),
        on_add=on_add,
        on_skip=on_skip,
    )


def _with_stale_license_copies(pkg_dir, artifacts, context, overwrite) -> set:
    """``overwrite`` plus every package licence copy that no longer matches the root."""
    overwrite = {overwrite} if isinstance(overwrite, str) else set(overwrite)
    if not context.get("license_file"):
        return overwrite
    name, text = context["license_file"]
    for art in artifacts:
        if os.path.basename(art.target) == name:
            path = os.path.join(pkg_dir, art.target)
            if os.path.isfile(path):
                with open(path, encoding="utf-8") as f:
                    if f.read() != text:
                        overwrite.add(art.target)
    return overwrite


# --- back-compat shims (the pre-#39 npm-overlay surface) -----------------------


def npm_overlay_context(
    *,
    project_name: str,
    description: str = "",
    license: Optional[str] = None,
    npm_subdir: str = "js",
    npm_package_name: Optional[str] = None,
    npm_version: str = "0.0.1",
    npm_package_manager: str = "npm",
) -> dict:
    """Deprecated: render context for the ``js`` overlay. Use :func:`apply_frontend`."""
    return frontend_context(
        profile_name="js",
        project_name=project_name,
        description=description,
        license=license,
        subdir=npm_subdir,
        package_name=npm_package_name,
        version=npm_version,
        package_manager=npm_package_manager,
    )


def npm_overlay_artifacts(npm_subdir: str = "js") -> list:
    """Deprecated: the ``js`` overlay artifacts. Use the ``js`` frontend profile."""
    return _js_artifacts({"npm_subdir": npm_subdir})


def apply_npm_overlay(
    pkg_dir: str,
    *,
    project_name: str,
    description: str = "",
    license: Optional[str] = None,
    npm_subdir: str = "js",
    npm_package_name: Optional[str] = None,
    npm_version: str = "0.0.1",
    npm_package_manager: str = "npm",
    overwrite=(),
    on_add=None,
    on_skip=None,
):
    """Deprecated alias for ``apply_frontend(profile="js", ...)`` (issue #32 surface).

    Kept so existing callers and tests keep working; new code should call
    :func:`apply_frontend`.
    """
    return apply_frontend(
        pkg_dir,
        profile="js",
        project_name=project_name,
        description=description,
        license=license,
        subdir=npm_subdir,
        package_name=npm_package_name,
        version=npm_version,
        package_manager=npm_package_manager,
        overwrite=overwrite,
        on_add=on_add,
        on_skip=on_skip,
    )


# --------------------------------------------------------------------------------------
# Tests-folder overlay (issue #4): scaffold a ``tests/`` package with a smoke
# test and a ``tests/data`` accessor utility.
# --------------------------------------------------------------------------------------


def make_tests_overlay_artifacts(
    project_name: str, *, with_data_util: bool = True
) -> list:
    """Artifacts that scaffold a ``tests/`` folder for a project.

    Writes ``tests/__init__.py``, ``tests/test_<project_name>.py`` (a smoke
    test), and optionally ``tests/util.py`` (a ``tests/data`` accessor, per #4).
    The smoke-test filename embeds the package name, so it is built here where
    the name is known.
    """
    init_src = FilesystemTemplateSource(os.path.dirname(tests_init_tpl_path))
    smoke_src = FilesystemTemplateSource(os.path.dirname(test_smoke_tpl_path))
    util_src = FilesystemTemplateSource(os.path.dirname(tests_util_tpl_path))

    artifacts = [
        Artifact.from_copy(
            "tests/__init__.py", os.path.basename(tests_init_tpl_path), init_src
        ),
        Artifact.from_jinja(
            f"tests/test_{project_name}.py",
            os.path.basename(test_smoke_tpl_path),
            smoke_src,
        ),
    ]
    if with_data_util:
        artifacts.append(
            Artifact.from_jinja(
                "tests/util.py", os.path.basename(tests_util_tpl_path), util_src
            )
        )
    return artifacts


def apply_tests_overlay(
    pkg_dir: str,
    *,
    project_name: str,
    with_data_util: bool = True,
    overwrite=(),
    on_add=None,
    on_skip=None,
):
    """Scaffold a ``tests/`` folder in an existing project (issue #4)."""
    return generate(
        pkg_dir,
        make_tests_overlay_artifacts(project_name, with_data_util=with_data_util),
        {"name": project_name},
        overwrite=overwrite,
        on_add=on_add,
        on_skip=on_skip,
    )


# --------------------------------------------------------------------------------------
# Native-core overlay (issue #214): a Python package whose hot path is a compiled Rust
# extension. The layout is the one wads' native CI path builds (issue #166,
# ``wads.native_build``): a Cargo workspace at the root (``rust/core`` pure Rust,
# ``rust/py`` the PyO3 binding cdylib that maturin builds as ``<pkg>._core``), a pinned
# ``rust-toolchain.toml``, abi3 wheels, and ``[tool.maturin]`` in pyproject.toml.
#
# A backend's templates are a folder holding the files at their target paths, named with
# the tokens ``tmpl_pkg`` (import name, Rust identifiers), ``tmpl-pkg`` (Cargo package
# names) and ``tmpl-license`` (SPDX licence id), so the folder is itself a Cargo
# workspace. pyproject.toml is not in it: the tables a backend needs are a fragment
# (``<backend>_pyproject.toml``) that is merged into a NEW pyproject and only *reported*
# for an existing one. What the merge replaces or drops is declared by the profile.
# --------------------------------------------------------------------------------------

import ast
import copy
import re
import shutil
import subprocess
import warnings

from wads import native_tpl_dir
from wads.templating import apply_placeholders

_SNAKE_TOKEN, _KEBAB_TOKEN, _LICENSE_TOKEN = "tmpl_pkg", "tmpl-pkg", "tmpl-license"
# Build and cache residue never copied out of a template folder.
_RESIDUE_PARTS = {"__pycache__", "target", ".pytest_cache", ".hypothesis", ".venv"}
_RESIDUE_SUFFIXES = (".pyc", ".so", ".pyd", ".dylib", ".lock")
_NATIVE_NAME_RE = re.compile(r"[a-z][a-z0-9_]*")


@dataclass(frozen=True)
class NativeProfile:
    """A native (compiled-extension) backend that ``populate --native`` can scaffold.

    Paths are template paths (with the tokens); pyproject tables are dotted
    (``"tool.hatch"``).

    :param name: registry key; also the backend name ``wads.native_build`` knows.
    :param template_dir: folder of files written at their (token-substituted) paths.
    :param pyproject_fragment: TOML file of the pyproject tables the backend needs.
    :param replaces: fragment tables that replace the pyproject's whole (rather than
        merge into it), e.g. ``"build-system"``.
    :param drops: tables a NEW pyproject loses, because they configure what
        ``replaces`` replaced (e.g. ``"tool.hatch"``); an existing one is told to.
    :param facade: the package's ``__init__.py`` template. A missing or blank one is
        written; a real one is kept and the lines the template tests need are reported.
    :param new_package_only: files written only when the package is new (no real facade).
    :param gitignore_patterns: ``.gitignore`` entries the layout relies on.
    :param lockfile: lockfile the build needs (``--locked``), generated when missing.
    :param lockfile_command: command generating ``lockfile``, run in the project root.
    :param lockfile_env: ``(name, value)`` pairs added to that command's environment.
    :param missing_toolchain: ``(marker, command)``: when the lockfile command's stderr
        has ``marker``, the pinned toolchain is missing and ``command`` installs it.
    :param toolchain_pin: ``(file, table, key)`` naming the pinned toolchain channel
        (checked against ``toolchain_list`` before the lockfile command runs).
    :param toolchain_list: command listing the installed toolchains, one per line.
    :param unlicensed: ``(text, replacement)`` pairs applied to the templates when the
        package's licence cannot be determined (the crates then declare none).
    :param description: one-line human summary.
    """

    name: str
    template_dir: str
    pyproject_fragment: str
    replaces: tuple = ()
    drops: tuple = ()
    facade: str = ""
    new_package_only: tuple = ()
    gitignore_patterns: tuple = ()
    lockfile: str = ""
    lockfile_command: tuple = ()
    lockfile_env: tuple = ()
    missing_toolchain: tuple = ()
    toolchain_pin: tuple = ()
    toolchain_list: tuple = ()
    unlicensed: tuple = ()
    description: str = ""


#: The native-backend registry. Extend it via :func:`register_native_profile`.
NATIVE_PROFILES: dict = {}


def register_native_profile(profile: NativeProfile) -> NativeProfile:
    """Register (or override) a native profile by name. Returns the profile."""
    NATIVE_PROFILES[profile.name] = profile
    return profile


def get_native_profile(name: str) -> NativeProfile:
    """Look up a registered native profile, with an informative error if unknown."""
    try:
        return NATIVE_PROFILES[name]
    except KeyError:
        available = ", ".join(sorted(NATIVE_PROFILES)) or "(none registered)"
        raise ValueError(
            f"Unknown native backend {name!r}. Available: {available}."
        ) from None


register_native_profile(
    NativeProfile(
        name="maturin",
        template_dir=os.path.join(native_tpl_dir, "maturin"),
        pyproject_fragment=os.path.join(native_tpl_dir, "maturin_pyproject.toml"),
        replaces=("build-system",),
        drops=("tool.hatch",),
        facade="tmpl_pkg/__init__.py",
        new_package_only=("tmpl_pkg/py.typed",),
        gitignore_patterns=("target", "*.so"),
        lockfile="Cargo.lock",
        lockfile_command=("cargo", "generate-lockfile", "--quiet"),
        # Never download a toolchain as a side effect of scaffolding.
        lockfile_env=(("RUSTUP_AUTO_INSTALL", "0"),),
        missing_toolchain=("is not installed", "rustup toolchain install"),
        # rustup < 1.28 ignores RUSTUP_AUTO_INSTALL: look before running cargo.
        toolchain_pin=("rust-toolchain.toml", "toolchain", "channel"),
        toolchain_list=("rustup", "toolchain", "list"),
        unlicensed=(
            ('license = "tmpl-license"', '# license = "<SPDX id>"'),
            ("license.workspace = true", "# license.workspace = true"),
        ),
        description="Rust core (rust/core) + PyO3 binding (rust/py) built by maturin.",
    )
)


def native_names(
    project_name: str, *, license: Optional[str] = None, backend: str = "maturin"
) -> dict:
    """Map the template tokens to their values for ``project_name``.

    The project name is the import name (``populate`` makes ``<name>/<name>/``), so it
    must be a lowercase identifier; Cargo package names are its kebab-case form.
    ``license`` is the package's SPDX id; without one the crates declare no licence
    (the profile's ``unlicensed`` edits) rather than a guessed one.

    >>> native_names("fast_thing", license="Apache-2.0")
    {'tmpl_pkg': 'fast_thing', 'tmpl-pkg': 'fast-thing', 'tmpl-license': 'Apache-2.0'}
    >>> native_names("fast_thing")['license = "tmpl-license"']
    '# license = "<SPDX id>"'
    """
    if not _NATIVE_NAME_RE.fullmatch(project_name):
        raise ValueError(
            f"A native package needs a lowercase importable name (letters, digits, '_', "
            f"starting with a letter), got {project_name!r}: it becomes the Python import "
            f"name, the extension module <name>._core and the Cargo crate names."
        )
    names = {
        _SNAKE_TOKEN: project_name,
        _KEBAB_TOKEN: project_name.replace("_", "-"),
    }
    if license:
        return {**names, _LICENSE_TOKEN: license}
    return {**dict(get_native_profile(backend).unlicensed), **names}


def native_licence(pkg_dir: str) -> Optional[str]:
    """The SPDX id of the package at ``pkg_dir``, or ``None`` when nothing says.

    In order: a PEP 639 ``[project].license`` string, a ``{text = ...}`` table naming a
    licence, the ``License ::`` classifiers, then the licence file (``{file = ...}`` or
    a root ``LICENSE``-like file) recognised by its opening lines.

    >>> import tempfile
    >>> d = tempfile.mkdtemp()
    >>> native_licence(d) is None
    True
    >>> _ = open(os.path.join(d, "COPYING"), "w").write("Apache License\\nVersion 2.0, January 2004")
    >>> native_licence(d)
    'Apache-2.0'
    """
    from wads.licensing import spdx_from_licence_name, spdx_from_licence_text

    text = _read_text(os.path.join(pkg_dir, "pyproject.toml"))
    project = _load_toml_text(text).get("project", {}) if text else {}
    declared = project.get("license")
    if isinstance(declared, str) and declared.strip():
        return declared.strip()
    table = declared if isinstance(declared, dict) else {}
    candidates = [table.get("text") or ""] + [
        c for c in project.get("classifiers", []) if c.startswith("License ::")
    ]
    for name in candidates:
        spdx = name and spdx_from_licence_name(name)
        if spdx:
            return spdx
    if table.get("file"):
        licence_text = _read_text(os.path.join(pkg_dir, table["file"]))
    else:
        found = find_license_file(pkg_dir)
        licence_text = found[1] if found else None
    return spdx_from_licence_text(licence_text) if licence_text else None


def native_artifacts(
    backend: str, project_name: str, *, license: Optional[str] = None, skip=()
) -> list:
    """The :class:`Artifact` list a native backend writes for ``project_name``.

    ``skip`` names template paths to leave out.

    >>> sorted(a.target for a in native_artifacts("maturin", "fast_thing"))[:3]
    ['Cargo.toml', 'clippy.toml', 'fast_thing/__init__.py']
    """
    profile = get_native_profile(backend)
    names = native_names(project_name, license=license, backend=backend)
    src = FilesystemTemplateSource(profile.template_dir)

    def is_residue(rel: str) -> bool:
        return bool(_RESIDUE_PARTS.intersection(rel.split("/"))) or rel.endswith(
            _RESIDUE_SUFFIXES
        )

    return [
        Artifact.from_placeholder(
            apply_placeholders(rel, names), rel, src, placeholders=lambda ctx: ctx
        )
        for rel in sorted(src)
        if not is_residue(rel) and rel not in skip
    ]


def _load_toml_text(text: str) -> dict:
    try:
        import tomllib
    except ImportError:  # Python < 3.11
        import tomli as tomllib
    return tomllib.loads(text)


def native_pyproject_fragment(project_name: str, *, backend: str = "maturin") -> dict:
    """The pyproject tables ``backend`` needs, for ``project_name``.

    >>> frag = native_pyproject_fragment("fast_thing")
    >>> frag["build-system"]["build-backend"], frag["tool"]["maturin"]["module-name"]
    ('maturin', 'fast_thing._core')
    """
    profile = get_native_profile(backend)
    with open(profile.pyproject_fragment, encoding="utf-8") as f:
        text = f.read()
    return _load_toml_text(apply_placeholders(text, native_names(project_name)))


def _dotted_get(data: dict, dotted: str):
    for key in dotted.split("."):
        if not isinstance(data, dict) or key not in data:
            return None
        data = data[key]
    return data


def _dotted_set(data: dict, dotted: str, value) -> None:
    *parents, last = dotted.split(".")
    for key in parents:
        data = data.setdefault(key, {})
    data[last] = value


def _dotted_pop(data: dict, dotted: str) -> None:
    *parents, last = dotted.split(".")
    parent = _dotted_get(data, ".".join(parents)) if parents else data
    if isinstance(parent, dict):
        parent.pop(last, None)


def _merge_into(dst: dict, src: dict) -> None:
    """Merge ``src`` into ``dst``: tables recursively, lists gain missing items."""
    for key, value in src.items():
        have = dst.get(key)
        if isinstance(value, dict) and isinstance(have, dict):
            _merge_into(have, value)
        elif isinstance(value, list) and isinstance(have, list):
            have.extend(copy.deepcopy(v) for v in value if v not in have)
        else:
            dst[key] = copy.deepcopy(value)


def _without(fragment: dict, dotted_tables) -> dict:
    rest = copy.deepcopy(fragment)
    for dotted in dotted_tables:
        _dotted_pop(rest, dotted)
    return rest


def merge_native_pyproject(
    pyproject: dict, fragment: dict, *, backend: str = "maturin"
) -> dict:
    """A copy of ``pyproject`` with a native ``fragment`` merged in (for a NEW package).

    The profile's ``replaces`` tables are replaced and its ``drops`` tables removed; the
    other tables merge, lists gaining the items they lack.

    >>> new = merge_native_pyproject(
    ...     {"build-system": {"requires": ["hatchling"], "build-backend": "hatchling.build"},
    ...      "project": {"optional-dependencies": {"dev": ["pytest"]}},
    ...      "tool": {"hatch": {"build": {}}, "ruff": {}}},
    ...     native_pyproject_fragment("fast_thing"),
    ... )
    >>> new["build-system"]["build-backend"], sorted(new["tool"])
    ('maturin', ['maturin', 'pytest', 'ruff', 'uv'])
    >>> new["project"]["optional-dependencies"]["dev"]
    ['pytest', 'hypothesis']
    """
    profile = get_native_profile(backend)
    out = copy.deepcopy(pyproject)
    for dotted in profile.drops:
        _dotted_pop(out, dotted)
    for dotted in profile.replaces:
        table = _dotted_get(fragment, dotted)
        if table is not None:
            _dotted_set(out, dotted, copy.deepcopy(table))
    _merge_into(out, _without(fragment, profile.replaces))
    return out


def _gaps(have, want: dict):
    """``(missing, added, differing)``: what ``have`` lacks of ``want``, as trees.

    ``missing``: keys ``have`` does not have; ``added``: list items it lacks;
    ``differing``: values it set otherwise.
    """
    missing, added, differing = {}, {}, {}
    for key, value in want.items():
        if not isinstance(have, dict) or key not in have:
            missing[key] = copy.deepcopy(value)
            continue
        current = have[key]
        if isinstance(value, dict) and isinstance(current, dict):
            for tree, sub in zip((missing, added, differing), _gaps(current, value)):
                if sub:
                    tree[key] = sub
        elif isinstance(value, list) and isinstance(current, list):
            items = [copy.deepcopy(v) for v in value if v not in current]
            if items:
                added[key] = items
        elif current != value:
            differing[key] = copy.deepcopy(value)
    return missing, added, differing


def native_pyproject_gaps(
    pyproject: dict, project_name: str, *, backend: str = "maturin"
) -> tuple:
    """``(required, recommended)``: what an EXISTING pyproject lacks for ``backend``.

    Required: absent keys and missing list items, and a ``replaces`` table whose
    scalars differ (another build backend) or are absent, given whole. Recommended:
    values set otherwise than the template's (a deliberate choice stays yours), and a
    ``replaces`` table that only lacks list items (e.g. an older ``requires`` pin).

    >>> required, recommended = native_pyproject_gaps(
    ...     {"build-system": {"requires": ["maturin>=1.9.4,<2"], "build-backend": "maturin"}},
    ...     "fast_thing",
    ... )
    >>> "build-system" in required, recommended["build-system"]["build-backend"]
    (False, 'maturin')
    """
    profile = get_native_profile(backend)
    fragment = native_pyproject_fragment(project_name, backend=backend)
    required, recommended = {}, {}
    for dotted in profile.replaces:
        want = _dotted_get(fragment, dotted)
        if want is None:
            continue
        missing, added, differing = _gaps(_dotted_get(pyproject, dotted) or {}, want)
        if missing or differing:
            _dotted_set(required, dotted, copy.deepcopy(want))
        elif added:
            _dotted_set(recommended, dotted, copy.deepcopy(want))
    missing, added, differing = _gaps(pyproject, _without(fragment, profile.replaces))
    _merge_into(required, missing)
    _merge_into(required, added)
    _merge_into(recommended, differing)
    return required, recommended


def native_pyproject_todo(
    pyproject: dict, project_name: str, *, backend: str = "maturin"
) -> str:
    """What an EXISTING pyproject needs for ``backend``, as TOML text ('' if nothing).

    ``populate`` never rewrites an existing pyproject.toml; it reports this instead. Two
    blocks, each valid TOML: ``# Required`` and ``# Recommended``
    (:func:`native_pyproject_gaps`).

    >>> print(native_pyproject_todo({}, "fast_thing"))  # doctest: +ELLIPSIS
    # Required: merge into pyproject.toml (lists: add the items shown).
    # [build-system] replaces yours.
    [build-system]
    requires = [...]
    build-backend = "maturin"
    ...
    module-name = "fast_thing._core"
    ...
    >>> pyproject = merge_native_pyproject({}, native_pyproject_fragment("fast_thing"))
    >>> native_pyproject_todo(pyproject, "fast_thing")
    ''
    """
    import tomli_w

    profile = get_native_profile(backend)
    required, recommended = native_pyproject_gaps(
        pyproject, project_name, backend=backend
    )
    blocks = []
    if required:
        header = ["# Required: merge into pyproject.toml (lists: add the items shown)."]
        replaced = [d for d in profile.replaces if _dotted_get(required, d) is not None]
        header += [f"# [{d}] replaces yours." for d in replaced]
        if replaced:
            header += [
                f"# [{d}] configures the build backend being replaced: carry its "
                f"include/exclude rules over to the new backend's table, then delete it."
                for d in profile.drops
                if _dotted_get(pyproject, d) is not None
            ]
        blocks.append("\n".join(header) + "\n" + tomli_w.dumps(required))
    if recommended:
        blocks.append(
            "# Recommended: these differ from the template's (keep yours if deliberate).\n"
            + tomli_w.dumps(recommended)
        )
    return "\n".join(blocks)


def _read_text(path: str) -> Optional[str]:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return None


def _facade_body(template_text: str) -> str:
    """The template facade without its module docstring: the lines to add to a real one."""
    tree = ast.parse(template_text)
    lines = template_text.splitlines(keepends=True)
    first = tree.body[0] if tree.body else None
    is_docstring = (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant)
        and isinstance(first.value.value, str)
    )
    start = first.end_lineno if is_docstring else 0
    return "".join(lines[start:]).strip("\n") + "\n"


def native_facade_todo(
    pkg_dir: str,
    project_name: str,
    *,
    backend: str = "maturin",
    license: Optional[str] = None,
) -> str:
    """The lines a kept (real) facade lacks for the template's tests ('' if none).

    >>> import tempfile
    >>> d = tempfile.mkdtemp()
    >>> os.makedirs(os.path.join(d, "fast_thing"))
    >>> _ = open(os.path.join(d, "fast_thing", "__init__.py"), "w").write("X = 1\\n")
    >>> print(native_facade_todo(d, "fast_thing"))  # doctest: +ELLIPSIS
    from importlib.metadata import version as _version
    <BLANKLINE>
    from fast_thing import _core
    ...
    def hamming(a: str, b: str) -> int:
    ...
    """
    profile = get_native_profile(backend)
    if not profile.facade:
        return ""
    names = native_names(project_name, license=license, backend=backend)
    existing = _read_text(
        os.path.join(pkg_dir, apply_placeholders(profile.facade, names))
    )
    if existing is None or not existing.strip():
        return ""
    template = FilesystemTemplateSource(profile.template_dir)[profile.facade]
    body = _facade_body(apply_placeholders(template, names))
    have = {line.strip() for line in existing.splitlines()}
    lacking = [
        line for line in body.splitlines() if line.strip() and line.strip() not in have
    ]
    return body if lacking else ""


def _gitignore_todo(pkg_dir: str, patterns) -> list:
    """The ``patterns`` the project's ``.gitignore`` lacks (``/x``, ``x/``, ``x`` agree)."""
    text = _read_text(os.path.join(pkg_dir, ".gitignore")) or ""
    lines = {line.strip().strip("/") for line in text.splitlines()}
    return [p for p in patterns if p.strip("/") not in lines]


def _find_executable(name: str) -> Optional[str]:
    """``name`` on PATH, else in ``~/.cargo/bin`` (rustup may not have edited PATH)."""
    found = shutil.which(name)
    if found:
        return found
    fallback = os.path.join(os.path.expanduser("~"), ".cargo", "bin", name)
    return fallback if os.path.isfile(fallback) else None


def _pinned_toolchain_missing(pkg_dir: str, profile: NativeProfile, *, env, timeout):
    """True when the project pins a toolchain the toolchain manager lists as absent.

    ``False`` whenever it cannot tell (no pin, no manager, a listing that fails): the
    lockfile command then runs and its own error, if any, is reported.
    """
    if not (profile.toolchain_pin and profile.toolchain_list):
        return False
    file, table, key = profile.toolchain_pin
    text = _read_text(os.path.join(pkg_dir, file))
    channel = _load_toml_text(text).get(table, {}).get(key) if text else None
    lister = _find_executable(profile.toolchain_list[0])
    if not channel or lister is None:
        return False
    try:
        proc = subprocess.run(
            [lister, *profile.toolchain_list[1:]],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if proc.returncode != 0:
        return False
    installed = [line.split()[0] for line in proc.stdout.splitlines() if line.strip()]
    return not any(t == channel or t.startswith(f"{channel}-") for t in installed)


def _generate_lockfile(pkg_dir: str, profile: NativeProfile, *, timeout: float):
    """Run the profile's lockfile command; ``None`` on success, else the reason."""
    tool, *args = profile.lockfile_command
    command = " ".join(profile.lockfile_command)
    then_commit = f"commit {profile.lockfile} (CI builds with --locked)"
    exe = _find_executable(tool)
    if exe is None:
        return (
            f"{tool} not found: run `{command}` once it is installed, and {then_commit}"
        )
    env = {**os.environ, **dict(profile.lockfile_env)}
    missing_toolchain = (
        f"the pinned toolchain is not installed: run "
        f"`{(profile.missing_toolchain or ('', 'its installer'))[1]}`, then "
        f"`{command}`, and {then_commit}"
    )
    if _pinned_toolchain_missing(pkg_dir, profile, env=env, timeout=timeout):
        return missing_toolchain
    try:
        proc = subprocess.run(
            [exe, *args],
            cwd=pkg_dir,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"`{command}` did not complete: {e}"
    if proc.returncode == 0:
        return None
    if profile.missing_toolchain and profile.missing_toolchain[0] in proc.stderr:
        return missing_toolchain
    tail = (proc.stderr.strip().splitlines() or ["(no output)"])[-1]
    return f"`{command}` failed: {tail}"


def _warn_attention(filename: str, reason: str) -> None:
    warnings.warn(f"{filename}: {reason}", stacklevel=3)


def apply_native(
    pkg_dir: str,
    *,
    backend: str = "maturin",
    project_name: str,
    license: Optional[str] = None,
    overwrite=(),
    generate_lockfile: bool = True,
    lockfile_timeout: float = 300,
    on_add=None,
    on_skip=None,
    on_error=None,
    on_attention: Optional[Callable[[str, str], None]] = _warn_attention,
) -> GenerationResult:
    """Scaffold a native core (``backend``) into the project at ``pkg_dir``.

    Writes the backend's template files that do not exist yet (``overwrite`` names the
    ones to replace). A missing or blank facade (``__init__.py``) is written; a real one
    is kept, the files of a new package only (``py.typed``) are left out, and the lines
    the template's tests need are reported. ``on_attention(filename, reason)`` also gets
    missing ``.gitignore`` entries and a lockfile it could not generate. pyproject.toml is
    not touched here: ``populate`` merges :func:`native_pyproject_fragment` into a new
    one and reports :func:`native_pyproject_todo` for an existing one.

    >>> import tempfile
    >>> d = tempfile.mkdtemp()
    >>> res = apply_native(
    ...     d, project_name="fast_thing", generate_lockfile=False, on_attention=None
    ... )
    >>> [t for t in res.added if t.startswith("rust/")]  # doctest: +NORMALIZE_WHITESPACE
    ['rust/core/Cargo.toml', 'rust/core/src/lib.rs', 'rust/py/Cargo.toml',
     'rust/py/src/lib.rs']
    """
    profile = get_native_profile(backend)
    on_attention = on_attention or (lambda filename, reason: None)
    license = license or native_licence(pkg_dir)
    names = native_names(project_name, license=license, backend=backend)
    overwrite = {overwrite} if isinstance(overwrite, str) else set(overwrite)

    facade = apply_placeholders(profile.facade, names) if profile.facade else ""
    existing = _read_text(os.path.join(pkg_dir, facade)) if facade else None
    new_package = existing is None or not existing.strip()
    if facade and existing is not None and new_package:
        overwrite.add(facade)  # a blank __init__.py, e.g. the one populate just made
    result = generate(
        pkg_dir,
        native_artifacts(
            backend,
            project_name,
            license=license,
            skip=() if new_package else profile.new_package_only,
        ),
        names,
        overwrite=overwrite,
        on_add=on_add,
        on_skip=on_skip,
        on_error=on_error,
    )
    lines = native_facade_todo(pkg_dir, project_name, backend=backend, license=license)
    if lines:
        on_attention(
            facade,
            "kept as it was; the template's tests (tests/) call the example API below. "
            "Add it, then replace the example with your own functions:\n" + lines,
        )
    if not license:
        unlicensed = [
            t
            for t in result.added
            if any(
                r in (_read_text(os.path.join(pkg_dir, t)) or "")
                for _, r in profile.unlicensed
            )
        ]
        if unlicensed:
            on_attention(
                unlicensed[0],
                "the package's licence could not be determined (pyproject.toml "
                "[project].license, its License classifiers, a LICENSE file), so the "
                f"crates declare none: set it, and uncomment the licence lines in "
                f"{', '.join(unlicensed)}",
            )
    lacking = _gitignore_todo(pkg_dir, profile.gitignore_patterns)
    if lacking:
        on_attention(
            ".gitignore",
            f"add {', '.join(lacking)} (build output and compiled modules of a "
            f"{backend} build must never be committed)",
        )
    if generate_lockfile and profile.lockfile:
        if not os.path.isfile(os.path.join(pkg_dir, profile.lockfile)):
            problem = _generate_lockfile(pkg_dir, profile, timeout=lockfile_timeout)
            if problem is None:
                result.added.append(profile.lockfile)
                if on_add:
                    on_add(profile.lockfile)
            else:
                on_attention(profile.lockfile, problem)
    return result
