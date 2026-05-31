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
    ts_index_tpl_path,
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
        "reusable_workflow": reusable,
        # Monorepo-only context (ignored by single-package templates):
        "npm_workspace_glob": workspace_glob,
        "example_package_name": example_package_name or (package_name or project_name),
    }


def _src(tpl_path: str) -> FilesystemTemplateSource:
    """One-entry filesystem source whose key is the template's basename."""
    return FilesystemTemplateSource(os.path.dirname(tpl_path))


def _jinja(target: str, tpl_path: str) -> Artifact:
    return Artifact.from_jinja(target, os.path.basename(tpl_path), _src(tpl_path))


def _copy(target: str, tpl_path: str) -> Artifact:
    return Artifact.from_copy(target, os.path.basename(tpl_path), _src(tpl_path))


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
        _stub_artifact(subdir),
    ]


def _ts_artifacts(ctx: Mapping) -> list:
    """``ts`` profile: single-package TypeScript (tsconfig + src + build/test)."""
    subdir = ctx["npm_subdir"]
    return [
        _jinja(f"{subdir}/package.json", package_json_ts_tpl_path),
        _copy(f"{subdir}/tsconfig.json", tsconfig_tpl_path),
        _copy(f"{subdir}/src/index.ts", ts_index_tpl_path),
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
        _copy(f"{pkg_dir}/src/index.ts", ts_index_tpl_path),
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
    overwrite=(),
    on_add=None,
    on_skip=None,
) -> GenerationResult:
    """Apply one frontend profile component to an existing project directory.

    ``subdir`` and ``package_manager`` default to the selected profile's
    defaults. Returns the :class:`wads.templating.GenerationResult`.

    >>> import tempfile
    >>> d = tempfile.mkdtemp()
    >>> res = apply_frontend(d, profile="ts", project_name="widget")
    >>> sorted(res.added)  # doctest: +NORMALIZE_WHITESPACE
    ['.github/workflows/npm-ci-ts.yml', 'ts/package.json', 'ts/src/index.ts',
     'ts/tsconfig.json']
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
    )
    return generate(
        pkg_dir,
        prof.artifacts(context),
        context,
        overwrite=overwrite,
        on_add=on_add,
        on_skip=on_skip,
    )


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
