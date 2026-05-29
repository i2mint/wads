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
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Union

#: Defaults applied when a field is absent from ``wads.ci``.
NPM_CI_DEFAULTS = {
    "subdir": "js",
    "nodeVersions": ["20", "22", "24"],
    "publishNode": "24",
    "lintCommand": "npm run lint --if-present",
    "testCommand": "npm test --if-present",
    "buildCommand": "npm run build --if-present",
}

#: Defaults for the nested ``wads.ci.publish`` block.
NPM_PUBLISH_DEFAULTS = {
    "enabled": False,
    "marker": "[publish-npm]",
    "registry": "https://registry.npmjs.org",
    "provenance": True,
    "trustedPublishing": True,
    "access": "public",
}


class NpmCIConfig:
    """Typed accessors over a ``package.json`` ``wads.ci`` configuration block."""

    def __init__(self, package_json_data: dict):
        self._data = package_json_data or {}
        self._ci = (self._data.get("wads") or {}).get("ci") or {}
        self._publish = self._ci.get("publish") or {}

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
