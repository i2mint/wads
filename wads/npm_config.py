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

:func:`npm_components` finds a repo's npm components the way CI does, from the
``.github/workflows`` stubs that call a wads ``npm-ci*.yml`` reusable workflow, and
:func:`npm_validate_commands` says what that workflow's validate job runs in one of
them: ``wads ci-local`` runs exactly that.
"""

from __future__ import annotations

import json
import os
import posixpath
from dataclasses import dataclass
from pathlib import Path
from typing import Union

import yaml

from wads.npm_trust import WORKFLOWS_DIR, is_monorepo_reusable, wads_reusable_call

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

#: Command defaults of ``npm-ci-monorepo.yml`` (pnpm + turbo), which is pnpm-only.
NPM_MONOREPO_COMMAND_DEFAULTS = {
    "packageManager": "pnpm",
    "lintCommand": "pnpm turbo run lint",
    "testCommand": "pnpm turbo run test",
    "buildCommand": "pnpm turbo run build",
}

#: The files the CI workflows look for in a component's directory.
PACKAGE_JSON = "package.json"
NPM_LOCKFILE = "package-lock.json"
PNPM_LOCKFILE = "pnpm-lock.yaml"

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

    def __init__(self, package_json_data: dict, *, monorepo: bool = False):
        """``monorepo``: read as ``npm-ci-monorepo.yml`` does (pnpm, turbo commands)."""
        self._data = package_json_data or {}
        self._defaults = (
            {**NPM_CI_DEFAULTS, **NPM_MONOREPO_COMMAND_DEFAULTS}
            if monorepo
            else NPM_CI_DEFAULTS
        )
        self.monorepo = monorepo
        self._ci = (self._data.get("wads") or {}).get("ci") or {}
        self._publish = self._ci.get("publish") or {}
        self._trigger = self._ci.get("trigger") or {}

    @classmethod
    def from_file(
        cls, package_json_path: Union[str, Path], *, monorepo: bool = False
    ) -> "NpmCIConfig":
        """Build from a ``package.json`` file path (file or its directory)."""
        path = Path(package_json_path)
        if path.is_dir():
            path = path / PACKAGE_JSON
        with open(path) as f:
            return cls(json.load(f), monorepo=monorepo)

    def _get(self, key: str):
        """``wads.ci.<key>``, or its default when absent or empty (CI's ``x || default``)."""
        return self._ci.get(key) or self._defaults[key]

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
        if self.monorepo:
            return self._defaults["packageManager"]
        return self._get("packageManager")

    def resolved_package_manager(self, package_dir: Union[str, Path]) -> str:
        """The package manager CI's install step uses in ``package_dir``.

        As the workflow: pnpm for a monorepo; else the declared ``packageManager``,
        else pnpm when a ``pnpm-lock.yaml`` is present, else npm; and anything but
        pnpm takes the npm branch.

        >>> NpmCIConfig({}).resolved_package_manager("/nonexistent")
        'npm'
        >>> NpmCIConfig({"wads": {"ci": {"packageManager": "pnpm"}}}).resolved_package_manager(".")
        'pnpm'
        """
        if self.monorepo:
            return "pnpm"
        declared = self._ci.get("packageManager") or (
            "pnpm" if (Path(package_dir) / PNPM_LOCKFILE).is_file() else "npm"
        )
        return "pnpm" if declared == "pnpm" else "npm"

    @property
    def node_versions(self) -> list:
        return self._ci.get("nodeVersions", NPM_CI_DEFAULTS["nodeVersions"])

    @property
    def publish_node(self) -> str:
        return str(self._ci.get("publishNode", NPM_CI_DEFAULTS["publishNode"]))

    @property
    def lint_command(self) -> str:
        return self._get("lintCommand")

    @property
    def test_command(self) -> str:
        return self._get("testCommand")

    @property
    def build_command(self) -> str:
        return self._get("buildCommand")

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
        # `trig.mode || 'auto'`, as the workflows read it: empty means unset.
        mode = self._trigger.get("mode") or NPM_TRIGGER_DEFAULTS["mode"]
        if mode not in TRIGGER_MODES:
            raise ValueError(
                f"wads.ci.trigger.mode must be one of {TRIGGER_MODES}, got {mode!r}"
            )
        return mode

    @property
    def run_ci_marker(self) -> str:
        """Commit-subject substring that runs CI in ``"on-demand"`` mode.

        Defaults to ``"[run ci]"`` (same default as the Python side), also when
        empty, as the workflows' ``runCiMarker || '[run ci]'`` reads it. Must be a
        single line, and not blank: a blank marker would match nearly every subject
        and silently turn on-demand back into auto.

        >>> NpmCIConfig({"wads": {"ci": {"trigger": {"runCiMarker": ""}}}}).run_ci_marker
        '[run ci]'
        """
        marker = self._trigger.get("runCiMarker") or NPM_TRIGGER_DEFAULTS["runCiMarker"]
        if not isinstance(marker, str) or not marker.strip() or "\n" in marker:
            raise ValueError(
                "wads.ci.trigger.runCiMarker must be a non-empty, single-line "
                f"string, got {marker!r}"
            )
        return marker


# --------------------------------------------------------------------------------------
# Components in a (polyglot) repo, and what CI validates in each


@dataclass(frozen=True)
class NpmComponent:
    """An npm component CI validates: one caller of a wads ``npm-ci*.yml`` workflow.

    ``dir`` is repo-relative POSIX (``"."`` for the repo root), ``workflow`` the
    caller stub's file name (e.g. ``"npm-ci-ts.yml"``), ``monorepo`` whether it calls
    ``npm-ci-monorepo.yml`` (pnpm + turbo) rather than ``npm-ci.yml``.
    """

    dir: str
    workflow: str
    monorepo: bool = False


def npm_components(repo_root: Union[str, Path] = ".") -> list:
    """The repo's npm components, as CI finds them: sorted :class:`NpmComponent`\\ s.

    One per job, in a ``.github/workflows/*.yml`` (or ``.yaml``) file, that calls a
    wads ``npm-ci*.yml`` reusable workflow: its ``package-dir`` input, or the
    reusable workflow's default dir when absent (:func:`wads.npm_trust.wads_reusable_call`).
    An unreadable or invalid workflow file is skipped, and so is a ``package-dir``
    holding a ``${{ }}`` expression (not a directory until Actions evaluates it).

    Not deduplicated by dir: one entry per calling stub, so a dir two stubs call
    appears twice (with their two ``workflow`` names).

    >>> import tempfile
    >>> root = Path(tempfile.mkdtemp())
    >>> (root / ".github/workflows").mkdir(parents=True)
    >>> _ = (root / ".github/workflows/npm-ci-ts.yml").write_text(
    ...     "jobs:\\n  npm-ci:\\n"
    ...     "    uses: i2mint/wads/.github/workflows/npm-ci.yml@master\\n"
    ...     "    with:\\n      package-dir: ./ts/\\n"
    ... )
    >>> npm_components(root)
    [NpmComponent(dir='ts', workflow='npm-ci-ts.yml', monorepo=False)]
    """
    workflows_dir = Path(repo_root) / WORKFLOWS_DIR
    found = set()
    for path in [*workflows_dir.glob("*.yml"), *workflows_dir.glob("*.yaml")]:
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            continue
        jobs = doc.get("jobs") if isinstance(doc, dict) else None
        for job in (jobs or {}).values():
            call = wads_reusable_call(job) if isinstance(job, dict) else None
            if call and "${{" not in call[1]:
                reusable, directory = call
                found.add(
                    NpmComponent(
                        posixpath.normpath(directory.strip()),
                        path.name,
                        is_monorepo_reusable(reusable),
                    )
                )
    return sorted(found, key=lambda c: (c.dir, c.workflow))


@dataclass(frozen=True)
class NpmValidateCommands:
    """The shell commands the npm validate job runs in a component, in order."""

    package_manager: str
    install: str
    lint: str
    test: str
    build: str


def npm_validate_commands(
    package_dir: Union[str, Path], *, monorepo: bool = False
) -> NpmValidateCommands:
    """What the npm CI validate job runs in ``package_dir``, read through :class:`NpmCIConfig`.

    ``monorepo``: as ``npm-ci-monorepo.yml`` (pnpm, turbo defaults), else as
    ``npm-ci.yml``. pnpm installs with a frozen lockfile when ``pnpm-lock.yaml`` is
    present and without one otherwise. npm uses ``npm ci`` when a
    ``package-lock.json`` is present, else ``npm install``: the branch CI's
    ``npm ci || npm install`` ends up taking. The trigger block is validated as the
    workflow's setup job does, so an invalid config fails here as it fails CI
    (``ValueError``; ``OSError`` / ``ValueError`` for a missing or broken file).

    >>> import tempfile
    >>> d = Path(tempfile.mkdtemp())
    >>> _ = (d / "package.json").write_text('{"wads": {"ci": {"testCommand": "vitest"}}}')
    >>> npm_validate_commands(d)  # doctest: +NORMALIZE_WHITESPACE
    NpmValidateCommands(package_manager='npm', install='npm install',
        lint='npm run lint --if-present', test='vitest',
        build='npm run build --if-present')
    >>> _ = (d / "pnpm-lock.yaml").write_text("")
    >>> npm_validate_commands(d).install
    'pnpm install --frozen-lockfile'
    """
    directory = Path(package_dir)
    config = NpmCIConfig.from_file(directory, monorepo=monorepo)
    config.trigger_mode, config.run_ci_marker  # raise as CI's setup job would
    manager = config.resolved_package_manager(directory)
    if manager == "pnpm":
        frozen = (directory / PNPM_LOCKFILE).is_file()
        install = (
            f"pnpm install {'--frozen-lockfile' if frozen else '--no-frozen-lockfile'}"
        )
    else:
        install = "npm ci" if (directory / NPM_LOCKFILE).is_file() else "npm install"
    return NpmValidateCommands(
        package_manager=manager,
        install=install,
        lint=config.lint_command,
        test=config.test_command,
        build=config.build_command,
    )
