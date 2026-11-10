"""One version across PyPI and npm (i2mint/wads#210).

``[tool.wads.ci.version].sync`` lists manifests the publish job writes the bumped
version into; the setup job fails when they disagree with ``[project].version``;
and an npm publish that was asked for but released nothing fails instead of
staying green.
"""

import json
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest
import yaml

from wads.version_sync import (
    check_versions_agree,
    set_manifest_version,
    sync_files,
    sync_version,
    version_mismatches,
)

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "wads" / "scripts"
WORKFLOWS = ROOT / ".github" / "workflows"
_NO_SITE = ["-S"] if sys.version_info >= (3, 11) else []


def _pyproject(version="0.1.0", sync=None):
    data = {"project": {"name": "demo", "version": version}}
    if sync is not None:
        data["tool"] = {"wads": {"ci": {"version": {"sync": sync}}}}
    return data


def _package_json(path: Path, version="0.1.0", *, indent=2):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"name": "demo", "version": version, "files": ["dist"]}
    path.write_text(json.dumps(data, indent=indent) + "\n")
    return path


# --- config -------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        "ts/package.json",  # a string, not a list
        ["../other/package.json"],
        ["/abs/package.json"],
        ["ts\\package.json"],
        ["rust/core/Cargo.toml"],
        ["ts/package-lock.json"],
    ],
)
def test_sync_list_rejects_what_ci_could_not_write_safely(bad):
    with pytest.raises(ValueError, match=r"\[tool\.wads\.ci\.version\]\.sync"):
        sync_files(_pyproject(sync=bad))


def test_sync_list_defaults_to_nothing():
    assert sync_files(_pyproject()) == []


# --- writing ------------------------------------------------------------------


@pytest.mark.parametrize("indent", [2, 4, "\t"])
def test_write_keeps_the_manifest_format_and_other_fields(tmp_path, indent):
    manifest = _package_json(tmp_path / "package.json", indent=indent)
    set_manifest_version(manifest, "0.2.0")
    expected = {"name": "demo", "version": "0.2.0", "files": ["dist"]}
    assert manifest.read_text() == json.dumps(expected, indent=indent) + "\n"


def test_write_updates_the_npm_lockfile_beside_it(tmp_path):
    manifest = _package_json(tmp_path / "package.json")
    lock = tmp_path / "package-lock.json"
    lock.write_text(
        json.dumps(
            {
                "name": "demo",
                "version": "0.1.0",
                "lockfileVersion": 3,
                "packages": {
                    "": {"name": "demo", "version": "0.1.0"},
                    "node_modules/x": {"version": "0.1.0"},
                },
            },
            indent=2,
        )
        + "\n"
    )
    written = set_manifest_version(manifest, "0.2.0")
    assert written == [manifest, lock]
    data = json.loads(lock.read_text())
    assert data["version"] == "0.2.0"
    assert data["packages"][""]["version"] == "0.2.0"
    assert data["packages"]["node_modules/x"]["version"] == "0.1.0"  # a dependency


@pytest.mark.parametrize("version", ["1.0rc1", "0.1.0.post1", "1.0", "v1.0.0"])
def test_a_version_npm_would_reject_is_refused_before_writing(tmp_path, version):
    manifest = _package_json(tmp_path / "package.json")
    before = manifest.read_text()
    with pytest.raises(ValueError, match="not semver"):
        set_manifest_version(manifest, version)
    assert manifest.read_text() == before


def test_sync_version_names_a_missing_manifest(tmp_path):
    with pytest.raises(FileNotFoundError, match="ts/package.json"):
        sync_version(tmp_path, ["ts/package.json"], "0.2.0")


# --- agreement check ----------------------------------------------------------


def test_agreeing_versions_pass(tmp_path):
    _package_json(tmp_path / "ts" / "package.json", "0.3.0")
    data = _pyproject("0.3.0", ["ts/package.json"])
    assert version_mismatches(tmp_path, data) == []
    check_versions_agree(tmp_path, data)


def test_disagreeing_or_missing_manifests_are_named(tmp_path):
    _package_json(tmp_path / "ts" / "package.json", "0.2.0")
    data = _pyproject("0.3.0", ["ts/package.json", "js/package.json"])
    assert version_mismatches(tmp_path, data) == [
        ("ts/package.json", "0.2.0", "0.3.0"),
        ("js/package.json", None, "0.3.0"),
    ]
    with pytest.raises(ValueError, match="ts/package.json has '0.2.0'"):
        check_versions_agree(tmp_path, data)


# --- the CI scripts, run as the actions run them ------------------------------


def _run_script(script, *args, cwd, env=None):
    return subprocess.run(
        [sys.executable, "-I", *_NO_SITE, str(SCRIPTS / script), *args],
        cwd=cwd,
        env={**{k: os.environ[k] for k in ("SYSTEMROOT",) if k in os.environ}, **(env or {})},
        capture_output=True,
        text=True,
    )


def _write_pyproject(repo: Path, version: str, sync):
    lines = [f'[project]\nname = "demo"\nversion = "{version}"\n']
    if sync is not None:
        lines.append(f"[tool.wads.ci.version]\nsync = {json.dumps(sync)}\n")
    (repo / "pyproject.toml").write_text("".join(lines))


@pytest.mark.skipif(sys.version_info < (3, 11), reason="the action pins Python 3.11")
def test_setup_exports_the_sync_list(tmp_path):
    _write_pyproject(tmp_path, "0.3.0", ["ts/package.json"])
    _package_json(tmp_path / "ts" / "package.json", "0.3.0")
    result = _run_script(
        "read_ci_config.py", ".", cwd=tmp_path, env={"GITHUB_OUTPUT": "out.txt"}
    )
    assert result.returncode == 0, result.stderr
    outputs = (tmp_path / "out.txt").read_text().splitlines()
    assert 'version-sync=["ts/package.json"]' in outputs


@pytest.mark.skipif(sys.version_info < (3, 11), reason="the action pins Python 3.11")
def test_setup_fails_when_the_versions_disagree(tmp_path):
    _write_pyproject(tmp_path, "0.3.0", ["ts/package.json"])
    _package_json(tmp_path / "ts" / "package.json", "0.2.0")
    result = _run_script(
        "read_ci_config.py", ".", cwd=tmp_path, env={"GITHUB_OUTPUT": "out.txt"}
    )
    assert result.returncode == 1
    assert "versions disagree" in result.stderr


def test_sync_script_writes_the_release_version(tmp_path):
    manifest = _package_json(tmp_path / "ts" / "package.json", "0.3.0")
    result = _run_script(
        "sync_version.py", "0.3.1", '["ts/package.json"]', cwd=tmp_path
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(manifest.read_text())["version"] == "0.3.1"


def test_sync_script_fails_with_an_annotation(tmp_path):
    _package_json(tmp_path / "ts" / "package.json", "0.3.0")
    result = _run_script("sync_version.py", "1.0rc1", '["ts/package.json"]', cwd=tmp_path)
    assert result.returncode == 1
    assert result.stderr.startswith("::error::Version sync failed")


# --- uv-ci wiring -------------------------------------------------------------


@pytest.mark.parametrize("job", ["publish", "publish-native"])
def test_publish_jobs_sync_between_the_bump_and_the_bump_commit(job):
    steps = yaml.safe_load((WORKFLOWS / "uv-ci.yml").read_text())["jobs"][job]["steps"]
    names = [s.get("name", "") for s in steps]
    bump = names.index("Update Version Number")
    sync = names.index("Sync the version into other manifests")
    commit = names.index("Commit Changes")
    assert bump < sync < commit
    step = steps[sync]
    assert step["uses"] == "i2mint/wads/actions/sync-version@master"
    assert step["with"] == {
        "version": "${{ env.VERSION }}",
        "files": "${{ needs.setup.outputs.version-sync }}",
    }
    # nothing to do (and no action to resolve) for a repo that lists nothing
    assert "version-sync != '[]'" in step["if"]


def test_setup_job_exports_the_sync_list():
    wf = yaml.safe_load((WORKFLOWS / "uv-ci.yml").read_text())
    outputs = wf["jobs"]["setup"]["outputs"]
    assert outputs["version-sync"] == "${{ steps.config.outputs.version-sync }}"
    action = yaml.safe_load((ROOT / "actions" / "read-ci-config" / "action.yml").read_text())
    assert "version-sync" in action["outputs"]
    sync_action = yaml.safe_load((ROOT / "actions" / "sync-version" / "action.yml").read_text())
    assert set(sync_action["inputs"]) == {"version", "files"}


# --- npm publish: asked for a release, released nothing -> fail ---------------


def _publish_run(name):
    steps = yaml.safe_load((WORKFLOWS / name).read_text())["jobs"]["publish"]["steps"]
    return next(s for s in steps if s.get("name", "").startswith("Publish tarballs"))


def _fake_tool(bin_dir: Path, name: str, body: str):
    path = bin_dir / name
    path.write_text("#!/usr/bin/env bash\n" + body)
    path.chmod(0o755)


@pytest.mark.skipif(shutil.which("bash") is None or os.name == "nt", reason="bash step")
@pytest.mark.parametrize("name", ["npm-ci.yml", "npm-ci-monorepo.yml"])
@pytest.mark.parametrize(
    "on_npm, attempt, expect_rc, expect_text",
    [
        ("", "1", 0, "PUBLISH demo-0.1.0.tgz"),  # new version: published
        ("demo@0.1.0", "1", 1, "::error::nothing published: demo@0.1.0"),
        ("demo@0.1.0", "2", 0, "::warning::nothing published"),  # a re-run
    ],
)
def test_publish_fails_when_it_releases_nothing(
    tmp_path, name, on_npm, attempt, expect_rc, expect_text
):
    step = _publish_run(name)
    art = tmp_path / "npm-pack"
    art.mkdir()
    pkg_json = tmp_path / "package.json"
    pkg_json.write_text('{"name": "demo", "version": "0.1.0"}')
    with tarfile.open(art / "demo-0.1.0.tgz", "w:gz") as tar:
        tar.add(pkg_json, arcname="package/package.json")
    (art / "publish-order.txt").write_text("demo-0.1.0.tgz\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    # node: the manifest check prints "name version"; npm: view says whether
    # the version exists, publish records what it would upload.
    _fake_tool(bin_dir, "node", 'echo "demo 0.1.0"\n')
    _fake_tool(
        bin_dir,
        "npm",
        'if [ "$1" = view ]; then [ "$3" = "$ON_NPM" ]; exit; fi\n'
        'if [ "$1" = publish ]; then echo "PUBLISH $(basename "$2")"; exit 0; fi\n'
        "exit 0\n",
    )
    env = {
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "RUNNER_TEMP": str(tmp_path),
        "GITHUB_RUN_ATTEMPT": attempt,
        "ON_NPM": on_npm,
        "PROVENANCE": "false",
        "ACCESS": "public",
        "REGISTRY": "https://registry.npmjs.org",
        "MANIFEST_CHECK": "",
    }
    result = subprocess.run(
        ["bash", "-e", "-c", step["run"]], env=env, capture_output=True, text=True
    )
    assert result.returncode == expect_rc, result.stdout + result.stderr
    assert expect_text in result.stdout + result.stderr
