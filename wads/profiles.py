"""Declarative generation *profiles* and *overlays* built on the engine.

A *profile* is a named declarative description of a project setup expressed as a
list of :class:`wads.templating.Artifact`. The default profile (``python-lib``)
is produced by :mod:`wads.populate`; this module currently provides the
``npm`` **overlay** -- a set of artifacts *added to* an existing project to
wire in NPM validation/publishing for its JS/TS components (issue #32).

The overlay never runs by default: it is opt-in via ``populate --with-npm``.
"""

from __future__ import annotations

import os
from typing import Optional

from wads import package_json_tpl_path, github_ci_npm_stub_path
from wads.templating import Artifact, FilesystemTemplateSource, generate

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


def npm_overlay_context(
    *,
    project_name: str,
    description: str = "",
    license: Optional[str] = None,
    npm_subdir: str = "js",
    npm_package_name: Optional[str] = None,
    npm_version: str = "0.0.1",
) -> dict:
    """Build the render context for the NPM overlay artifacts."""
    return {
        "npm_package_name": npm_package_name or project_name,
        "npm_version": npm_version,
        "description": description,
        "npm_license": _to_spdx(license),
        "npm_subdir": npm_subdir,
    }


def npm_overlay_artifacts(npm_subdir: str = "js") -> list:
    """Artifacts that add NPM setup + CI to a project.

    Writes ``<npm_subdir>/package.json`` (with the ``wads.ci`` config block) and
    ``.github/workflows/npm-ci.yml`` (the stub calling the reusable workflow).
    """
    # Each template file is its own one-entry filesystem source so the engine's
    # source key is just the file's basename.
    pkg_json_src = FilesystemTemplateSource(os.path.dirname(package_json_tpl_path))
    stub_src = FilesystemTemplateSource(os.path.dirname(github_ci_npm_stub_path))
    return [
        Artifact.from_jinja(
            f"{npm_subdir}/package.json",
            os.path.basename(package_json_tpl_path),
            pkg_json_src,
        ),
        Artifact.from_jinja(
            ".github/workflows/npm-ci.yml",
            os.path.basename(github_ci_npm_stub_path),
            stub_src,
        ),
    ]


def apply_npm_overlay(
    pkg_dir: str,
    *,
    project_name: str,
    description: str = "",
    license: Optional[str] = None,
    npm_subdir: str = "js",
    npm_package_name: Optional[str] = None,
    npm_version: str = "0.0.1",
    overwrite=(),
    on_add=None,
    on_skip=None,
):
    """Add NPM setup + CI to an existing project directory.

    Returns the :class:`wads.templating.GenerationResult`.
    """
    context = npm_overlay_context(
        project_name=project_name,
        description=description,
        license=license,
        npm_subdir=npm_subdir,
        npm_package_name=npm_package_name,
        npm_version=npm_version,
    )
    return generate(
        pkg_dir,
        npm_overlay_artifacts(npm_subdir),
        context,
        overwrite=overwrite,
        on_add=on_add,
        on_skip=on_skip,
    )
