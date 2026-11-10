"""Read NPM CI configuration from a ``package.json`` ``wads.ci`` block.

This is the NPM-side analog of :class:`wads.ci_config.CIConfig` (which reads
``[tool.wads.ci]`` from ``pyproject.toml``). npm ignores unknown top-level keys,
so wads namespaces its config under a top-level ``"wads"`` key:

.. code-block:: json

    {
      "name": "@scope/my-widget",
      "wads": {
        "ci": {
          "subdir": "js",
          "nodeVersions": ["20", "22", "24"],
          "publish": {"enabled": false, "marker": "[publish-npm]"}
        }
      }
    }

The reusable workflow (``i2mint/wads/.github/workflows/npm-ci.yml``) parses the
same block in CI via ``node``; this class is the parsing/validation surface used
from Python (tests, ``populate`` validation, inspection tooling).

:func:`npm_component_dirs` finds a repo's npm components (the subdirs whose
``package.json`` carries a ``wads.ci`` key), and :func:`npm_validate_commands` says
what the validate job of ``npm-ci.yml`` (or ``npm-ci-monorepo.yml``, for a pnpm
workspace root) runs in one of them: ``wads ci-local`` runs exactly that.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from dataclasses import dataclass
from typing import Union

#: Defaults applied when a field is absent from ``wads.ci``.
#:
#: ``packageManager`` is ``"npm"`` here for the typed Python accessor, but in CI
#: an *absent* field triggers auto-detection (a ``pnpm-lock.yaml`` in the
#: package dir selects pnpm); an explicit value always wins. So existing npm
#: consumers — no field, no ``pnpm-lock.yaml`` — keep byte-identical behavior.
NPM_CI_DEFAULTS = {
    "subdir": "js",
    "packageManager": "npm",
    "nodeVersions": ["20", "22", "24"],
    "publishNode": "24",
    "lintCommand": "npm run lint --if-present",
    "testCommand": "npm test --if-present",
    "buildCommand": "npm run build --if-present",
}

#: Command defaults of ``npm-ci-monorepo.yml``, used for a pnpm workspace root.
NPM_MONOREPO_COMMAND_DEFAULTS = {
    "lintCommand": "pnpm turbo run lint",
    "testCommand": "pnpm turbo run test",
    "buildCommand": "pnpm turbo run build",
}

#: The files the CI workflows look for in a component's directory.
PACKAGE_JSON = "package.json"
PNPM_LOCKFILE = "pnpm-lock.yaml"
#: Marks a pnpm workspace root, the component kind ``npm-ci-monorepo.yml`` drives.
PNPM_WORKSPACE_FILE = "pnpm-workspace.yaml"

#: Directories never searched for components (besides hidden ones).
NPM_COMPONENT_SKIP_DIRS = frozenset({"node_modules"})
#: How deep below the repo root a component named by its ``wads.ci.subdir`` may live.
DFLT_NPM_COMPONENT_MAX_DEPTH = 3

#: Package managers the reusable npm CI workflow knows how to drive.
SUPPORTED_PACKAGE_MANAGERS = ("npm", "pnpm")

#: Defaults for the nested ``wads.ci.publish`` block.
NPM_PUBLISH_DEFAULTS = {
    "enabled": False,
    "marker": "[publish-npm]",
    "registry": "https://registry.npmjs.org",
    "provenance": True,
    "trustedPublishing": True,
    "access": "public",
}

#: ``wads.ci.trigger.mode`` values the reusable workflow understands. Mirrors
#: ``wads.ci_config.TRIGGER_MODES`` (the Python/pyproject.toml side).
TRIGGER_MODES = ("auto", "on-demand")

#: Defaults for the nested ``wads.ci.trigger`` block. Same values as the Python
#: side (``wads.ci_config.DFLT_TRIGGER_MODE`` / ``DFLT_RUN_CI_MARKER``) so a repo
#: with both a pyproject.toml and a package.json can use one marker convention.
NPM_TRIGGER_DEFAULTS = {
    "mode": "auto",
    "runCiMarker": "[run ci]",
}


class NpmCIConfig:
    """Typed accessors over a ``package.json`` ``wads.ci`` configuration block."""

    def __init__(self, package_json_data: dict):
        self._data = package_json_data or {}
        self._ci = (self._data.get("wads") or {}).get("ci") or {}
        self._publish = self._ci.get("publish") or {}
        self._trigger = self._ci.get("trigger") or {}

    @classmethod
    def from_file(cls, package_json_path: Union[str, Path]) -> "NpmCIConfig":
        """Build from a ``package.json`` file path (file or its directory)."""
        path = Path(package_json_path)
        if path.is_dir():
            path = path / "package.json"
        with open(path) as f:
            return cls(json.load(f))

    def has_ci_config(self) -> bool:
        """True if the package.json declares a ``wads.ci`` block."""
        return bool(self._ci)

    # --- package identity ---

    @property
    def package_name(self) -> str:
        return self._data.get("name", "")

    @property
    def version(self) -> str:
        return self._data.get("version", "")

    # --- ci.* ---

    @property
    def subdir(self) -> str:
        return self._ci.get("subdir", NPM_CI_DEFAULTS["subdir"])

    @property
    def package_manager(self) -> str:
        """The package manager driving install/build (``"npm"`` or ``"pnpm"``).

        Returns the explicit ``wads.ci.packageManager`` if set, else the default
        (``"npm"``). Note the CI workflow additionally *auto-detects* pnpm from a
        ``pnpm-lock.yaml`` when the field is absent — this accessor reports only
        the declared value.
        """
        return self._ci.get("packageManager", NPM_CI_DEFAULTS["packageManager"])

    @property
    def node_versions(self) -> list:
        return self._ci.get("nodeVersions", NPM_CI_DEFAULTS["nodeVersions"])

    @property
    def publish_node(self) -> str:
        return str(self._ci.get("publishNode", NPM_CI_DEFAULTS["publishNode"]))

    @property
    def lint_command(self) -> str:
        return self._ci.get("lintCommand", NPM_CI_DEFAULTS["lintCommand"])

    @property
    def test_command(self) -> str:
        return self._ci.get("testCommand", NPM_CI_DEFAULTS["testCommand"])

    @property
    def build_command(self) -> str:
        return self._ci.get("buildCommand", NPM_CI_DEFAULTS["buildCommand"])

    # --- ci.publish.* ---

    @property
    def publish_enabled(self) -> bool:
        return bool(self._publish.get("enabled", NPM_PUBLISH_DEFAULTS["enabled"]))

    @property
    def publish_marker(self) -> str:
        return self._publish.get("marker", NPM_PUBLISH_DEFAULTS["marker"])

    @property
    def registry(self) -> str:
        return self._publish.get("registry", NPM_PUBLISH_DEFAULTS["registry"])

    @property
    def provenance(self) -> bool:
        return bool(self._publish.get("provenance", NPM_PUBLISH_DEFAULTS["provenance"]))

    @property
    def trusted_publishing(self) -> bool:
        return bool(
            self._publish.get(
                "trustedPublishing", NPM_PUBLISH_DEFAULTS["trustedPublishing"]
            )
        )

    @property
    def access(self) -> str:
        return self._publish.get("access", NPM_PUBLISH_DEFAULTS["access"])

    # --- ci.trigger.* (mirrors CIConfig.trigger_mode / run_ci_marker) ---

    @property
    def trigger_mode(self) -> str:
        """When CI runs: ``"auto"`` (default) or ``"on-demand"``.

        ``"on-demand"`` means nothing runs unless the commit *subject line*
        contains :attr:`run_ci_marker`, or the run is a manual
        ``workflow_dispatch``. Raises ``ValueError`` on any other value.

        >>> NpmCIConfig({}).trigger_mode
        'auto'
        >>> NpmCIConfig({"wads": {"ci": {"trigger": {"mode": "on-demand"}}}}).trigger_mode
        'on-demand'
        """
        mode = self._trigger.get("mode", NPM_TRIGGER_DEFAULTS["mode"])
        if mode not in TRIGGER_MODES:
            raise ValueError(
                f"wads.ci.trigger.mode must be one of {TRIGGER_MODES}, got {mode!r}"
            )
        return mode

    @property
    def run_ci_marker(self) -> str:
        """Commit-subject substring that runs CI in ``"on-demand"`` mode.

        Defaults to ``"[run ci]"`` (same default as the Python side). Must be a
        non-empty single line: an empty marker would match every subject and
        silently turn on-demand back into auto.
        """
        marker = self._trigger.get("runCiMarker", NPM_TRIGGER_DEFAULTS["runCiMarker"])
        if not isinstance(marker, str) or not marker.strip() or "\n" in marker:
            raise ValueError(
                "wads.ci.trigger.runCiMarker must be a non-empty, single-line "
                f"string, got {marker!r}"
            )
        return marker


# --------------------------------------------------------------------------------------
# Components in a (polyglot) repo, and what CI validates in each


def _read_package_json(path: Path):
    """The parsed ``package.json`` at ``path``, or ``None`` if absent or not JSON."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _wads_ci_block(data):
    """``data["wads"]["ci"]`` when ``data`` declares that key (even empty), else ``None``."""
    if not isinstance(data, dict):
        return None
    wads = data.get("wads")
    if isinstance(wads, dict) and isinstance(wads.get("ci"), dict):
        return wads["ci"]
    return None


def npm_component_dirs(
    repo_root: Union[str, Path] = ".",
    *,
    max_depth: int = DFLT_NPM_COMPONENT_MAX_DEPTH,
) -> list:
    """The repo's npm components: repo-relative POSIX subdirs, sorted.

    A component is a directory whose ``package.json`` has a ``wads.ci`` key: any
    direct subdirectory of ``repo_root``, or a deeper one (down to ``max_depth``
    levels) whose ``wads.ci.subdir`` names its own location, as ``populate
    --frontend`` writes it for a nested subdir. ``node_modules`` and hidden
    directories are never searched, and the members of a pnpm workspace (no
    ``wads.ci`` key of their own) are not components: their workspace root is.

    >>> import tempfile
    >>> root = Path(tempfile.mkdtemp())
    >>> for sub, data in [
    ...     ("ts", {"wads": {"ci": {"subdir": "ts"}}}),
    ...     ("docs", {"name": "no-wads-ci"}),
    ...     ("web/app", {"wads": {"ci": {"subdir": "web/app"}}}),
    ...     ("web/other", {"wads": {"ci": {"subdir": "elsewhere"}}}),
    ... ]:
    ...     (root / sub).mkdir(parents=True)
    ...     _ = (root / sub / "package.json").write_text(json.dumps(data))
    >>> npm_component_dirs(root)
    ['ts', 'web/app']
    """
    root = Path(repo_root)
    found = []

    def walk(directory: Path, depth: int):
        try:
            children = sorted(p for p in directory.iterdir() if p.is_dir())
        except OSError:
            return
        for child in children:
            if child.name.startswith(".") or child.name in NPM_COMPONENT_SKIP_DIRS:
                continue
            rel = child.relative_to(root).as_posix()
            ci = _wads_ci_block(_read_package_json(child / PACKAGE_JSON))
            if ci is not None and (depth == 1 or ci.get("subdir") == rel):
                found.append(rel)
            if depth < max_depth:
                walk(child, depth + 1)

    walk(root, 1)
    return sorted(found)


@dataclass(frozen=True)
class NpmValidateCommands:
    """The shell commands the npm validate job runs in a component, in order."""

    package_manager: str
    install: str
    lint: str
    test: str
    build: str
    monorepo: bool = False


def npm_validate_commands(package_dir: Union[str, Path]) -> NpmValidateCommands:
    """What the validate job of the npm CI workflow runs in ``package_dir``.

    Mirrors ``npm-ci.yml``: the package manager is ``wads.ci.packageManager`` when
    set, else pnpm when a ``pnpm-lock.yaml`` is present, else npm; pnpm installs with
    a frozen lockfile when one is committed and without one otherwise, npm runs
    ``npm ci || npm install``. A pnpm workspace root (``pnpm-workspace.yaml``
    present) is validated as ``npm-ci-monorepo.yml`` does it: always pnpm, with
    turbo command defaults.

    >>> import tempfile
    >>> d = Path(tempfile.mkdtemp())
    >>> _ = (d / "package.json").write_text('{"wads": {"ci": {"testCommand": "vitest"}}}')
    >>> npm_validate_commands(d)  # doctest: +NORMALIZE_WHITESPACE
    NpmValidateCommands(package_manager='npm', install='npm ci || npm install',
        lint='npm run lint --if-present', test='vitest',
        build='npm run build --if-present', monorepo=False)
    >>> _ = (d / "pnpm-lock.yaml").write_text("")
    >>> npm_validate_commands(d).install
    'pnpm install --frozen-lockfile'
    """
    directory = Path(package_dir)
    ci = _wads_ci_block(_read_package_json(directory / PACKAGE_JSON)) or {}
    monorepo = (directory / PNPM_WORKSPACE_FILE).is_file()
    has_pnpm_lock = (directory / PNPM_LOCKFILE).is_file()
    if monorepo:
        manager = "pnpm"
        defaults = {**NPM_CI_DEFAULTS, **NPM_MONOREPO_COMMAND_DEFAULTS}
    else:
        declared = ci.get("packageManager") or ("pnpm" if has_pnpm_lock else "npm")
        # The workflow's install step takes the npm branch for anything but pnpm.
        manager = "pnpm" if declared == "pnpm" else "npm"
        defaults = NPM_CI_DEFAULTS
    if manager == "pnpm":
        frozen = "--frozen-lockfile" if has_pnpm_lock else "--no-frozen-lockfile"
        install = f"pnpm install {frozen}"
    else:
        install = "npm ci || npm install"
    # `value || default`, as the workflows' node parser reads it: empty means unset.
    return NpmValidateCommands(
        package_manager=manager,
        install=install,
        lint=ci.get("lintCommand") or defaults["lintCommand"],
        test=ci.get("testCommand") or defaults["testCommand"],
        build=ci.get("buildCommand") or defaults["buildCommand"],
        monorepo=monorepo,
    )
