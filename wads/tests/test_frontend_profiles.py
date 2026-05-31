"""Tests for the frontend profile registry (issue #39).

Covers:
- the ``js`` profile stays byte-compatible with the pre-#39 overlay (golden
  files under ``wads/tests/data/golden/frontend_js/``);
- the ``ts`` single-package profile;
- the ``ts-monorepo`` profile (pnpm workspaces + turbo);
- multiple components (``js`` + ``ts``) coexisting without workflow collision;
- the registry surface and the ``populate --frontend`` CLI integration.

The ``js`` golden anchors the back-compat acceptance; if you *intentionally*
change ``js`` output, regenerate the goldens and review the diff in the PR.
"""

import json
import subprocess
from pathlib import Path

import pytest

from wads.npm_config import NpmCIConfig
from wads.profiles import (
    FRONTEND_PROFILES,
    FrontendProfile,
    apply_frontend,
    get_frontend_profile,
    register_frontend_profile,
    _workflow_basename,
)
from wads.populate import populate_pkg_dir

GOLDEN_DIR = Path(__file__).parent / "data" / "golden" / "frontend_js"


def _git_init(pkg_dir, url):
    subprocess.run(["git", "init", "-q"], cwd=pkg_dir, check=True)
    subprocess.run(["git", "config", "user.email", "t@e.com"], cwd=pkg_dir, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=pkg_dir, check=True)
    subprocess.run(["git", "remote", "add", "origin", url], cwd=pkg_dir, check=True)


# --- registry ------------------------------------------------------------------


def test_registry_has_builtin_profiles():
    assert set(FRONTEND_PROFILES) >= {"js", "ts", "ts-monorepo"}
    assert get_frontend_profile("js").default_subdir == "js"
    assert get_frontend_profile("ts").default_subdir == "ts"
    assert get_frontend_profile("ts-monorepo").default_package_manager == "pnpm"


def test_unknown_profile_is_informative():
    with pytest.raises(ValueError, match="Unknown frontend profile 'nope'"):
        get_frontend_profile("nope")


def test_workflow_basename_scheme():
    # js is the back-compat anchor; everything else is per-subdir.
    assert _workflow_basename("js") == "npm-ci.yml"
    assert _workflow_basename("ts") == "npm-ci-ts.yml"
    assert _workflow_basename("frontend") == "npm-ci-frontend.yml"


def test_register_custom_profile_roundtrip():
    sentinel = FrontendProfile(
        name="_test_custom",
        default_subdir="x",
        default_package_manager="npm",
        artifacts=lambda ctx: [],
    )
    try:
        register_frontend_profile(sentinel)
        assert get_frontend_profile("_test_custom") is sentinel
    finally:
        FRONTEND_PROFILES.pop("_test_custom", None)


# --- js profile: byte-compatible back-compat anchor ----------------------------


def test_js_profile_matches_golden(tmp_path):
    apply_frontend(
        str(tmp_path),
        profile="js",
        project_name="mypkg",
        description="A widget",
        license="apache-2.0",
    )
    for golden in GOLDEN_DIR.rglob("*"):
        if not golden.is_file():
            continue
        rel = golden.relative_to(GOLDEN_DIR)
        produced = (tmp_path / rel).read_text()
        assert produced == golden.read_text(), f"js output drifted for {rel}"


def test_js_via_apply_frontend_default_profile(tmp_path):
    # profile defaults to "js"
    result = apply_frontend(str(tmp_path), project_name="mypkg")
    assert "js/package.json" in result.added
    assert ".github/workflows/npm-ci.yml" in result.added


# --- ts single-package profile -------------------------------------------------


def test_ts_profile_writes_expected_files(tmp_path):
    result = apply_frontend(str(tmp_path), profile="ts", project_name="widget")
    assert set(result.added) == {
        "ts/package.json",
        "ts/tsconfig.json",
        "ts/src/index.ts",
        ".github/workflows/npm-ci-ts.yml",
    }

    pkg_json = json.loads((tmp_path / "ts" / "package.json").read_text())
    assert pkg_json["type"] == "module"
    assert pkg_json["scripts"]["test"] == "vitest run"
    assert "tsup" in pkg_json["scripts"]["build"]
    # Same wads.ci SSOT + publish model as js: validate-always, publish-opt-in.
    cfg = NpmCIConfig(pkg_json)
    assert cfg.subdir == "ts"
    assert cfg.publish_enabled is False
    assert cfg.publish_marker == "[publish-npm]"
    assert cfg.provenance is True

    tsconfig = json.loads((tmp_path / "ts" / "tsconfig.json").read_text())
    assert tsconfig["compilerOptions"]["strict"] is True

    workflow = (tmp_path / ".github" / "workflows" / "npm-ci-ts.yml").read_text()
    assert "name: NPM CI (ts)" in workflow
    assert "package-dir: ts" in workflow
    assert "i2mint/wads/.github/workflows/npm-ci.yml@master" in workflow
    assert "<<" not in workflow and ">>" not in workflow


def test_ts_profile_pnpm_package_manager(tmp_path):
    apply_frontend(
        str(tmp_path), profile="ts", project_name="widget", package_manager="pnpm"
    )
    pkg_json = json.loads((tmp_path / "ts" / "package.json").read_text())
    assert NpmCIConfig(pkg_json).package_manager == "pnpm"


# --- ts-monorepo profile -------------------------------------------------------


def test_ts_monorepo_profile_structure(tmp_path):
    result = apply_frontend(str(tmp_path), profile="ts-monorepo", project_name="widget")
    assert set(result.added) == {
        "ts/package.json",
        "ts/pnpm-workspace.yaml",
        "ts/turbo.json",
        "ts/tsconfig.base.json",
        "ts/packages/core/package.json",
        "ts/packages/core/tsconfig.json",
        "ts/packages/core/src/index.ts",
        ".github/workflows/npm-ci-ts.yml",
    }

    root = json.loads((tmp_path / "ts" / "package.json").read_text())
    assert root["private"] is True
    assert root["packageManager"].startswith("pnpm@")
    assert NpmCIConfig(root).package_manager == "pnpm"
    assert NpmCIConfig(root).publish_enabled is False  # opt-in, same model

    workspace = (tmp_path / "ts" / "pnpm-workspace.yaml").read_text()
    assert "packages/*" in workspace

    pkg = json.loads(
        (tmp_path / "ts" / "packages" / "core" / "package.json").read_text()
    )
    assert pkg["name"] == "widget"

    # The monorepo stub calls the *monorepo* reusable workflow.
    workflow = (tmp_path / ".github" / "workflows" / "npm-ci-ts.yml").read_text()
    assert "i2mint/wads/.github/workflows/npm-ci-monorepo.yml@master" in workflow
    assert "<<" not in workflow and ">>" not in workflow


# --- multiple components coexist without collision -----------------------------


def test_js_and_ts_components_no_collision(tmp_path):
    apply_frontend(str(tmp_path), profile="js", project_name="widget")
    apply_frontend(str(tmp_path), profile="ts", project_name="widget")

    assert (tmp_path / "js" / "package.json").exists()
    assert (tmp_path / "ts" / "package.json").exists()
    workflows = sorted(p.name for p in (tmp_path / ".github" / "workflows").iterdir())
    assert workflows == ["npm-ci-ts.yml", "npm-ci.yml"]

    js_wf = (tmp_path / ".github" / "workflows" / "npm-ci.yml").read_text()
    ts_wf = (tmp_path / ".github" / "workflows" / "npm-ci-ts.yml").read_text()
    assert 'paths:\n      - "js/**"' in js_wf
    assert 'paths:\n      - "ts/**"' in ts_wf


# --- populate --frontend CLI integration --------------------------------------


def test_populate_frontend_ts(tmp_path):
    pkg_dir = tmp_path / "widget"
    pkg_dir.mkdir()
    _git_init(pkg_dir, "https://github.com/myorg/widget")

    populate_pkg_dir(
        str(pkg_dir),
        description="Has a TS lib",
        root_url="https://github.com/myorg",
        version="0.1.0",
        verbose=False,
        frontend="ts",
    )
    assert (pkg_dir / "pyproject.toml").exists()  # Python side untouched
    assert (pkg_dir / "ts" / "tsconfig.json").exists()
    assert (pkg_dir / ".github" / "workflows" / "npm-ci-ts.yml").exists()
    assert not (pkg_dir / "js").exists()


def test_populate_frontend_multi(tmp_path):
    pkg_dir = tmp_path / "widget"
    pkg_dir.mkdir()
    _git_init(pkg_dir, "https://github.com/myorg/widget")

    populate_pkg_dir(
        str(pkg_dir),
        description="JS and TS",
        root_url="https://github.com/myorg",
        version="0.1.0",
        verbose=False,
        frontend="js,ts",
    )
    assert (pkg_dir / "js" / "package.json").exists()
    assert (pkg_dir / "ts" / "package.json").exists()
    assert (pkg_dir / ".github" / "workflows" / "npm-ci.yml").exists()
    assert (pkg_dir / ".github" / "workflows" / "npm-ci-ts.yml").exists()


def test_populate_with_npm_is_js_alias(tmp_path):
    pkg_dir = tmp_path / "widget"
    pkg_dir.mkdir()
    _git_init(pkg_dir, "https://github.com/myorg/widget")

    populate_pkg_dir(
        str(pkg_dir),
        description="Legacy flag",
        root_url="https://github.com/myorg",
        version="0.1.0",
        verbose=False,
        with_npm=True,
    )
    assert (pkg_dir / "js" / "package.json").exists()
    assert (pkg_dir / ".github" / "workflows" / "npm-ci.yml").exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
