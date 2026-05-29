"""Tests for the opt-in NPM setup overlay and its config reader."""

import json
import subprocess

import pytest

from wads.npm_config import NpmCIConfig
from wads.profiles import apply_npm_overlay, _to_spdx
from wads.populate import populate_pkg_dir


def _git_init(pkg_dir, url):
    subprocess.run(["git", "init", "-q"], cwd=pkg_dir, check=True)
    subprocess.run(["git", "config", "user.email", "t@e.com"], cwd=pkg_dir, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=pkg_dir, check=True)
    subprocess.run(["git", "remote", "add", "origin", url], cwd=pkg_dir, check=True)


# --- NpmCIConfig ---------------------------------------------------------------


def test_npm_config_defaults_when_empty():
    cfg = NpmCIConfig({"name": "x"})
    assert cfg.has_ci_config() is False
    assert cfg.subdir == "js"
    assert cfg.package_manager == "npm"
    assert cfg.node_versions == ["20", "22", "24"]
    assert cfg.publish_enabled is False
    assert cfg.publish_marker == "[publish-npm]"
    assert cfg.provenance is True


def test_npm_config_reads_values():
    data = {
        "name": "@scope/widget",
        "version": "1.0.0",
        "wads": {
            "ci": {
                "subdir": "frontend",
                "packageManager": "pnpm",
                "nodeVersions": ["22"],
                "publish": {"enabled": True, "marker": "[ship-it]", "access": "restricted"},
            }
        },
    }
    cfg = NpmCIConfig(data)
    assert cfg.has_ci_config() is True
    assert cfg.package_name == "@scope/widget"
    assert cfg.version == "1.0.0"
    assert cfg.subdir == "frontend"
    assert cfg.package_manager == "pnpm"
    assert cfg.node_versions == ["22"]
    assert cfg.publish_enabled is True
    assert cfg.publish_marker == "[ship-it]"
    assert cfg.access == "restricted"


def test_spdx_mapping():
    assert _to_spdx("mit") == "MIT"
    assert _to_spdx("apache-2.0") == "Apache-2.0"
    assert _to_spdx(None) == "MIT"
    assert _to_spdx("MIT") == "MIT"


# --- overlay -------------------------------------------------------------------


def test_apply_npm_overlay_writes_files(tmp_path):
    result = apply_npm_overlay(
        str(tmp_path),
        project_name="mypkg",
        description="A widget",
        license="apache-2.0",
        npm_subdir="js",
    )
    assert "js/package.json" in result.added
    assert ".github/workflows/npm-ci.yml" in result.added

    pkg_json = json.loads((tmp_path / "js" / "package.json").read_text())
    assert pkg_json["name"] == "mypkg"
    assert pkg_json["license"] == "Apache-2.0"
    assert pkg_json["description"] == "A widget"
    # Config block round-trips through NpmCIConfig
    cfg = NpmCIConfig(pkg_json)
    assert cfg.has_ci_config()
    assert cfg.subdir == "js"
    assert cfg.package_manager == "npm"  # default
    assert cfg.publish_enabled is False  # default OFF

    workflow = (tmp_path / ".github" / "workflows" / "npm-ci.yml").read_text()
    assert "i2mint/wads/.github/workflows/npm-ci.yml@master" in workflow
    assert "package-dir: js" in workflow
    # No leftover Jinja markers
    assert "<<" not in workflow and ">>" not in workflow


def test_overlay_custom_subdir_and_name(tmp_path):
    apply_npm_overlay(
        str(tmp_path),
        project_name="proj",
        npm_subdir="frontend",
        npm_package_name="@acme/proj-ui",
    )
    pkg_json = json.loads((tmp_path / "frontend" / "package.json").read_text())
    assert pkg_json["name"] == "@acme/proj-ui"
    assert NpmCIConfig(pkg_json).subdir == "frontend"
    workflow = (tmp_path / ".github" / "workflows" / "npm-ci.yml").read_text()
    assert "frontend/**" in workflow
    assert "package-dir: frontend" in workflow


def test_overlay_pnpm_package_manager(tmp_path):
    apply_npm_overlay(
        str(tmp_path),
        project_name="proj",
        npm_subdir="ts",
        npm_package_manager="pnpm",
    )
    pkg_json = json.loads((tmp_path / "ts" / "package.json").read_text())
    assert NpmCIConfig(pkg_json).package_manager == "pnpm"
    # No leftover Jinja marker for the new placeholder.
    raw = (tmp_path / "ts" / "package.json").read_text()
    assert "<<" not in raw and ">>" not in raw


# --- populate --with-npm integration ------------------------------------------


def test_populate_with_npm_flag(tmp_path):
    pkg_dir = tmp_path / "mypkg"
    pkg_dir.mkdir()
    _git_init(pkg_dir, "https://github.com/myorg/mypkg")

    populate_pkg_dir(
        str(pkg_dir),
        description="Has a widget",
        root_url="https://github.com/myorg",
        author="Dev",
        version="0.1.0",
        verbose=False,
        with_npm=True,
    )

    # Python side still present
    assert (pkg_dir / "pyproject.toml").exists()
    assert (pkg_dir / ".github" / "workflows" / "ci.yml").exists()
    # NPM side added
    assert (pkg_dir / "js" / "package.json").exists()
    assert (pkg_dir / ".github" / "workflows" / "npm-ci.yml").exists()


def test_populate_without_npm_flag_adds_nothing(tmp_path):
    pkg_dir = tmp_path / "plain"
    pkg_dir.mkdir()
    _git_init(pkg_dir, "https://github.com/myorg/plain")

    populate_pkg_dir(
        str(pkg_dir),
        description="No JS",
        root_url="https://github.com/myorg",
        version="0.1.0",
        verbose=False,
    )
    assert not (pkg_dir / "js").exists()
    assert not (pkg_dir / ".github" / "workflows" / "npm-ci.yml").exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
