"""One version across PyPI and npm (i2mint/wads#210).

``[tool.wads.ci.version].sync`` lists manifests the publish job writes the bumped
version into; the setup job fails when they disagree with ``[project].version``;
and an npm publish that was asked for but released nothing fails instead of
staying green, or would reuse the previous PyPI release's number.
"""

import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest
import yaml

from wads.ci_config import CIConfig
from wads.version_sync import (
    caller_workflow_path,
    check_versions_agree,
    npm_publish_refusal,
    pypi_release_expected,
    set_json_version,
    set_manifest_version,
    static_project_version,
    sync_files,
    sync_version,
    version_mismatches,
)

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "wads" / "scripts"
WORKFLOWS = ROOT / ".github" / "workflows"
UV_WORKFLOWS = [WORKFLOWS / "uv-ci.yml", ROOT / "wads" / "data" / "github_ci_uv.yml"]
NPM_WORKFLOWS = ["npm-ci.yml", "npm-ci-monorepo.yml"]
_NO_SITE = ["-S"] if sys.version_info >= (3, 11) else []
_NEEDS_TOMLLIB = pytest.mark.skipif(
    sys.version_info < (3, 11), reason="the guard reads pyproject.toml with tomllib"
)
_NEEDS_BASH = pytest.mark.skipif(
    shutil.which("bash") is None or os.name == "nt", reason="bash step"
)


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


# What `npm version 0.2.0 --no-git-tag-version --ignore-scripts` writes (npm 10),
# checked against a real npm below when one is installed.
LAYOUTS = {
    "crlf": (
        b'{\r\n  "name": "demo",\r\n  "version": "0.1.0",\r\n  "files": [\r\n    "dist"\r\n  ]\r\n}\r\n',
        b'{\r\n  "name": "demo",\r\n  "version": "0.2.0",\r\n  "files": [\r\n    "dist"\r\n  ]\r\n}\r\n',
    ),
    "minified": (
        b'{"name":"demo","version":"0.1.0","files":["dist"]}',
        b'{"name":"demo","version":"0.2.0","files":["dist"]}',
    ),
    "minified, final newline": (  # npm drops it: a minified file stays one line
        b'{"name":"demo","version":"0.1.0","files":["dist"]}\n',
        b'{"name":"demo","version":"0.2.0","files":["dist"]}',
    ),
    "indented, no final newline": (  # npm adds one
        b'{\n  "name": "demo",\n  "version": "0.1.0"\n}',
        b'{\n  "name": "demo",\n  "version": "0.2.0"\n}\n',
    ),
    "tab, non-ascii": (
        '{\n\t"name": "demo",\n\t"version": "0.1.0",\n\t"description": "caf\u00e9"\n}\n'.encode(),
        '{\n\t"name": "demo",\n\t"version": "0.2.0",\n\t"description": "caf\u00e9"\n}\n'.encode(),
    ),
}


@pytest.mark.parametrize("layout", list(LAYOUTS))
def test_write_matches_npm_version_byte_for_byte(tmp_path, layout):
    before, expected = LAYOUTS[layout]
    manifest = tmp_path / "package.json"
    manifest.write_bytes(before)
    set_manifest_version(manifest, "0.2.0")
    assert manifest.read_bytes() == expected


@pytest.mark.skipif(shutil.which("npm") is None, reason="needs a real npm")
@pytest.mark.parametrize("layout", list(LAYOUTS))
def test_the_expected_bytes_are_what_npm_writes(tmp_path, layout):
    before, expected = LAYOUTS[layout]
    (tmp_path / "package.json").write_bytes(before)
    subprocess.run(
        ["npm", "version", "0.2.0", "--no-git-tag-version", "--ignore-scripts"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        shell=os.name == "nt",
    )
    assert (tmp_path / "package.json").read_bytes() == expected


def test_a_crlf_lockfile_keeps_its_line_endings(tmp_path):
    manifest = tmp_path / "package.json"
    manifest.write_bytes(b'{\r\n  "name": "demo",\r\n  "version": "0.1.0"\r\n}\r\n')
    lock = tmp_path / "package-lock.json"
    lock.write_bytes(
        b'{\r\n  "name": "demo",\r\n  "version": "0.1.0",\r\n  "lockfileVersion": 3,\r\n'
        b'  "packages": {\r\n    "": {\r\n      "version": "0.1.0"\r\n    }\r\n  }\r\n}\r\n'
    )
    set_manifest_version(manifest, "0.2.0")
    assert lock.read_bytes() == (
        b'{\r\n  "name": "demo",\r\n  "version": "0.2.0",\r\n  "lockfileVersion": 3,\r\n'
        b'  "packages": {\r\n    "": {\r\n      "version": "0.2.0"\r\n    }\r\n  }\r\n}\r\n'
    )


def test_one_json_file_can_be_written_alone(tmp_path):
    """The push-back resolver writes the manifest and the lockfile one at a time."""
    lock = tmp_path / "package-lock.json"
    lock.write_text('{"version": "0.1.0", "packages": {"": {"version": "0.1.0"}}}')
    set_json_version(lock, "0.3.0")
    assert json.loads(lock.read_text()) == {
        "version": "0.3.0",
        "packages": {"": {"version": "0.3.0"}},
    }
    assert not (tmp_path / "package.json").exists()


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


@pytest.mark.parametrize(
    "project, says",
    [
        ({"name": "demo", "dynamic": ["version"]}, "dynamic"),
        ({}, "setup.cfg"),  # no [project] table: setup.cfg / setup.py metadata
        ({"name": "demo"}, "missing"),
    ],
)
def test_sync_needs_a_static_project_version(tmp_path, project, says):
    _package_json(tmp_path / "ts" / "package.json", "0.3.0")
    data = {"tool": {"wads": {"ci": {"version": {"sync": ["ts/package.json"]}}}}}
    if project:
        data["project"] = project
    with pytest.raises(ValueError, match="static \\[project\\]\\.version") as info:
        check_versions_agree(tmp_path, data)
    assert says in str(info.value)
    assert "remove the sync key" in str(info.value)


def test_a_non_static_version_is_fine_without_sync(tmp_path):
    check_versions_agree(tmp_path, {"project": {"dynamic": ["version"]}})
    assert static_project_version({"project": {"version": "1.0.0"}}) == "1.0.0"


# --- npm publish guard: npm must not get the previous release's number --------


def _guard_data(sync=("ts/package.json",), version="1.2.3", **ci):
    data = _pyproject(version, list(sync))
    data["tool"]["wads"]["ci"].update(ci)
    return data


NPM = "Release the TS side [publish-npm]"


@pytest.mark.parametrize(
    "changed",
    [
        ["ts/src/index.ts"],
        ["ts/package.json", "ts/src/index.ts"],
        [],  # an empty commit
    ],
)
def test_a_push_inside_the_npm_package_may_publish(changed):
    assert npm_publish_refusal(_guard_data(), "ts", changed, NPM) is None


@pytest.mark.parametrize(
    "changed",
    [
        ["pkg/core.py"],
        ["ts/src/index.ts", "pkg/core.py"],
        ["README.md"],  # anything outside counts: the Python release ships it
        ["ts-old/index.ts"],  # a sibling with the same prefix is outside
        ["ts"],  # a file named like the directory is not inside it
    ],
)
def test_a_push_that_also_releases_python_is_refused(changed):
    msg = npm_publish_refusal(_guard_data(), "ts", changed, NPM)
    assert msg.startswith("This push also releases the Python package")
    assert "previous release's number (1.2.3)" in msg
    assert "changes only ts/" in msg
    assert "'[skip publish]'" in msg
    outside = [f for f in changed if not f.startswith("ts/")]
    assert f"Changed outside ts/: {', '.join(outside)}" in msg


def test_the_refusal_names_a_few_files_and_counts_the_rest():
    changed = [f"pkg/m{i}.py" for i in range(8)]
    msg = npm_publish_refusal(_guard_data(), "ts", changed, NPM)
    assert msg.endswith(
        "pkg/m0.py, pkg/m1.py, pkg/m2.py, pkg/m3.py, pkg/m4.py and 3 more"
    )


@pytest.mark.parametrize(
    "data",
    [
        _pyproject("1.2.3"),  # no sync
        _guard_data(sync=["js/package.json"]),  # another npm package is synced
        _guard_data(sync=[]),
    ],
)
def test_no_synced_manifest_in_the_package_means_no_guard(data):
    assert npm_publish_refusal(data, "ts", ["pkg/core.py"], NPM) is None


@pytest.mark.parametrize("package_dir", ["ts", "ts/", "./ts", "./ts/"])
def test_the_package_dir_is_normalized(package_dir):
    assert npm_publish_refusal(_guard_data(), package_dir, ["ts/a.ts"], NPM) is None
    assert npm_publish_refusal(_guard_data(), package_dir, ["pkg/a.py"], NPM)


def test_a_monorepo_workspace_package_under_the_root_is_guarded():
    data = _guard_data(sync=["ts/packages/core/package.json"])
    assert npm_publish_refusal(data, "ts", ["ts/packages/core/src/a.ts"], NPM) is None
    msg = npm_publish_refusal(data, "ts", ["pkg/a.py"], NPM)
    assert "ts/packages/core/package.json" in msg


@pytest.mark.parametrize("package_dir", [".", "", "./"])
def test_an_npm_package_at_the_repo_root_needs_the_skip_publish_marker(package_dir):
    data = _guard_data(sync=["package.json"])
    msg = npm_publish_refusal(data, package_dir, ["src/index.ts"], NPM)
    assert "npm package is the repo root" in msg
    assert msg.endswith("Changed: src/index.ts")
    assert (
        npm_publish_refusal(
            data, package_dir, ["src/index.ts"], NPM + " [skip publish]"
        )
        is None
    )


@pytest.mark.parametrize(
    "ci, subject, refused",
    [
        ({}, NPM, True),
        ({}, NPM + " [skip publish]", False),
        ({}, NPM + " [SKIP PUBLISH]", False),  # case-insensitive, like contains()
        ({}, NPM + " [skip ci]", False),
        # configured markers replace the defaults
        ({"publish": {"skip_publish_marker": "[no pypi]"}}, NPM + " [no pypi]", False),
        (
            {"publish": {"skip_publish_marker": "[no pypi]"}},
            NPM + " [skip publish]",
            True,
        ),
        ({"publish": {"skip_ci_marker": "[ci skip]"}}, NPM + " [ci skip]", False),
        # PyPI publishing off: only the publish marker releases
        ({"publish": {"enabled": False}}, NPM, False),
        ({"publish": {"enabled": False}}, NPM + " [publish]", True),
        (
            {"publish": {"enabled": False, "publish_marker": "[pypi]"}},
            NPM + " [pypi]",
            True,
        ),
        # on-demand trigger: uv-ci runs (and releases) only when asked
        ({"trigger": {"mode": "on-demand"}}, NPM, False),
        ({"trigger": {"mode": "on-demand"}}, NPM + " [run ci]", True),
        ({"trigger": {"mode": "on-demand"}}, NPM + " [run deploy]", True),
        (
            {"trigger": {"mode": "on-demand", "run_ci_publishes": False}},
            NPM + " [run ci]",
            False,
        ),
    ],
)
def test_the_guard_follows_uv_ci_publish_gates(ci, subject, refused):
    data = _guard_data(**ci)
    assert pypi_release_expected(data, subject) is refused
    msg = npm_publish_refusal(data, "ts", ["pkg/core.py"], subject)
    assert (msg is not None) is refused


def test_the_npm_stub_workflow_counts_as_inside_the_package():
    """The Python stub's paths filter ignores the npm stub, so no PyPI release follows."""
    stub = caller_workflow_path("o/r/.github/workflows/npm-ci.yml@refs/heads/main")
    changed = ["ts/a.ts", ".github/workflows/npm-ci.yml"]
    assert (
        npm_publish_refusal(_guard_data(), "ts", changed, NPM, also_inside=[stub])
        is None
    )
    assert npm_publish_refusal(_guard_data(), "ts", changed, NPM)  # without it
    other = ["ts/a.ts", ".github/workflows/ci.yml"]  # the Python stub is not inside
    assert npm_publish_refusal(_guard_data(), "ts", other, NPM, also_inside=[stub])


@pytest.mark.parametrize(
    "ref, path",
    [
        (
            "o/r/.github/workflows/npm-ci.yml@refs/heads/main",
            ".github/workflows/npm-ci.yml",
        ),
        (
            "o/r/.github/workflows/npm-ci-ts.yml@refs/pull/3/merge",
            ".github/workflows/npm-ci-ts.yml",
        ),
        ("", None),
        ("something-else", None),
    ],
)
def test_caller_workflow_path(ref, path):
    assert caller_workflow_path(ref) == path


@pytest.mark.parametrize(
    "publish, match",
    [
        ({"enabled": "false"}, "enabled must be true or false"),
        ({"enabled": 0}, "enabled must be true or false"),
        ({"publish_marker": ""}, "publish_marker must be a non-empty"),
        ({"skip_ci_marker": False}, "skip_ci_marker must be a non-empty"),
        ({"skip_publish_marker": "  "}, "skip_publish_marker must be a non-empty"),
    ],
)
def test_malformed_publish_config_is_an_error_for_the_guard_and_uv_ci(publish, match):
    """uv-ci compares the text of these settings; the guard must not read them differently."""
    with pytest.raises(ValueError, match=match):
        pypi_release_expected(_guard_data(publish=publish), NPM)


def test_the_refusal_names_the_configured_skip_publish_marker():
    data = _guard_data(publish={"skip_publish_marker": "[no pypi]"})
    assert "'[no pypi]'" in npm_publish_refusal(data, "ts", ["pkg/a.py"], NPM)


def test_a_bad_sync_list_is_an_error_not_a_pass():
    with pytest.raises(ValueError, match="sync"):
        npm_publish_refusal(_guard_data(sync=["../x/package.json"]), "ts", [], NPM)


# --- parity: the guard's PyPI decision is uv-ci's own -------------------------
#
# Runs uv-ci.yml's "Decide skip markers" and "Decide trigger level" bash, fed by
# read_ci_config.py's real outputs, and evaluates the publish job's `if:` over
# them, next to pypi_release_expected, over a grid of configs and subjects.

PARITY_CONFIGS = {
    "defaults": {},
    "publish off": {"publish": {"enabled": False}},
    "custom markers": {
        "publish": {
            "enabled": False,
            "publish_marker": "[pypi]",
            "skip_ci_marker": "[ci skip]",
            "skip_publish_marker": "[no pypi]",
        }
    },
    "custom skips, publish on": {
        "publish": {"skip_ci_marker": "[ci skip]", "skip_publish_marker": "[no pypi]"}
    },
    "on-demand": {"trigger": {"mode": "on-demand"}},
    "on-demand, run-ci validates only": {
        "trigger": {"mode": "on-demand", "run_ci_publishes": False}
    },
    "on-demand, publish off": {
        "trigger": {"mode": "on-demand"},
        "publish": {"enabled": False},
    },
    "on-demand, custom trigger markers": {
        "trigger": {
            "mode": "on-demand",
            "run_ci_marker": "[ci]",
            "deploy_marker": "[ship]",
        }
    },
}
PARITY_SUBJECTS = [
    "Fix",
    "Fix [skip publish]",
    "Fix [SKIP CI]",
    "Fix [publish]",
    "Fix [pypi]",
    "Fix [no pypi]",
    "Fix [ci skip]",
    "Fix [run ci]",
    "Fix [Run Deploy]",
    "Fix [run ci] [publish]",
    "Fix [ci]",
    "Fix [ship] [no pypi]",
]


def _toml_value(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    return json.dumps(value)


def _uv_ci_gate_steps():
    wf = yaml.safe_load((WORKFLOWS / "uv-ci.yml").read_text())
    steps = {s.get("name"): s for s in wf["jobs"]["setup"]["steps"]}
    publish_if = wf["jobs"]["publish"]["if"]
    return [steps["Decide skip markers"], steps["Decide trigger level"]], publish_if


def _step_env(step, outputs, subject):
    """A step's env with its ${{ }} expressions resolved as on a push."""
    env = {}
    for key, expr in step["env"].items():
        inner = expr.strip().removeprefix("${{").removesuffix("}}").strip()
        if inner == "steps.commit.outputs.subject":
            env[key] = subject
        elif inner.startswith("steps.config.outputs."):
            env[key] = outputs.get(inner.removeprefix("steps.config.outputs."), "")
        elif inner == "github.event_name":
            env[key] = "push"
        elif inner == "github.event.inputs.level":
            env[key] = ""
        else:
            raise AssertionError(f"unknown expression in the gate step: {expr}")
    return env


@_NEEDS_TOMLLIB
@_NEEDS_BASH
@pytest.mark.parametrize("config", list(PARITY_CONFIGS))
def test_the_guard_decides_pypi_releases_exactly_as_uv_ci(tmp_path, config):
    gate_steps, publish_if = _uv_ci_gate_steps()
    # The publish job's `if:` evaluated below, clause by clause.
    for clause in (
        "needs.setup.outputs.skip-publish == 'false'",
        "(needs.setup.outputs.publish-enabled == 'true' || contains(needs.setup.outputs.commit-subject, needs.setup.outputs.publish-marker))",
        "needs.setup.outputs.deploy == 'true'",
    ):
        assert clause in publish_if

    ci = PARITY_CONFIGS[config]
    lines = ['[project]\nname = "demo"\nversion = "1.2.3"\n']
    for table, values in ci.items():
        lines.append(f"[tool.wads.ci.{table}]\n")
        lines += [f"{k} = {_toml_value(v)}\n" for k, v in values.items()]
    (tmp_path / "pyproject.toml").write_text("".join(lines))
    read = _run_script(
        "read_ci_config.py", ".", cwd=tmp_path, env={"GITHUB_OUTPUT": "config.txt"}
    )
    assert read.returncode == 0, read.stderr
    outputs = dict(
        line.split("=", 1)
        for line in (tmp_path / "config.txt").read_text().splitlines()
        if "=" in line
    )
    data = {
        "project": {"name": "demo", "version": "1.2.3"},
        "tool": {"wads": {"ci": ci}},
    }

    for subject in PARITY_SUBJECTS:
        gates = tmp_path / "gates.txt"
        gates.write_text("")
        verdicts = {}
        for step in gate_steps:
            env = {
                "PATH": os.environ["PATH"],
                "GITHUB_OUTPUT": str(gates),
                **_step_env(step, outputs, subject),
            }
            result = subprocess.run(
                ["bash", "-eo", "pipefail", "-c", step["run"]],
                env=env,
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, result.stderr
        verdicts = dict(line.split("=", 1) for line in gates.read_text().splitlines())
        uv_ci_publishes = (
            verdicts["skip-publish"] == "false"
            and (
                outputs["publish-enabled"] == "true"
                or outputs["publish-marker"].lower() in subject.lower()
            )
            and verdicts["deploy"] == "true"
        )
        assert pypi_release_expected(data, subject) is uv_ci_publishes, (
            config,
            subject,
        )


# --- the CI scripts, run as the actions run them ------------------------------


def _run_script(script, *args, cwd, env=None):
    return subprocess.run(
        [sys.executable, "-I", *_NO_SITE, str(SCRIPTS / script), *args],
        cwd=cwd,
        env={
            **{k: os.environ[k] for k in ("SYSTEMROOT",) if k in os.environ},
            **(env or {}),
        },
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


def test_sync_script_writes_one_file(tmp_path):
    lock = tmp_path / "package-lock.json"
    lock.write_bytes(b'{\r\n  "version": "0.1.0"\r\n}\r\n')
    result = _run_script("sync_version.py", "--file", str(lock), "0.2.0", cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert lock.read_bytes() == b'{\r\n  "version": "0.2.0"\r\n}\r\n'
    bad = _run_script("sync_version.py", "--file", str(lock), "1.0rc1", cwd=tmp_path)
    assert bad.returncode == 1 and "::error::" in bad.stderr


def test_sync_script_fails_with_an_annotation(tmp_path):
    _package_json(tmp_path / "ts" / "package.json", "0.3.0")
    result = _run_script(
        "sync_version.py", "1.0rc1", '["ts/package.json"]', cwd=tmp_path
    )
    assert result.returncode == 1
    assert result.stderr.startswith("::error::Version sync failed")


def _changed(tmp_path, *paths):
    listing = tmp_path / "changed"
    listing.write_text("".join(p + "\0" for p in paths))
    return str(listing)


def test_guard_script_is_a_no_op_without_pyproject(tmp_path):
    result = _run_script(
        "npm_publish_guard.py",
        "ts",
        _changed(tmp_path, "pkg/a.py"),
        cwd=tmp_path,
        env={"SUBJECT": NPM},
    )
    assert result.returncode == 0, result.stderr
    assert "nothing to check" in result.stdout


@_NEEDS_TOMLLIB
@pytest.mark.parametrize(
    "changed, subject, rc",
    [
        (["ts/src/a.ts"], NPM, 0),
        (["ts/src/a.ts", "pkg/a.py"], NPM, 1),
        (["ts/src/a.ts", "pkg/a.py"], NPM + " [skip publish]", 0),
    ],
)
def test_guard_script_decides_from_the_repo_pyproject(tmp_path, changed, subject, rc):
    _write_pyproject(tmp_path, "1.2.3", ["ts/package.json"])
    result = _run_script(
        "npm_publish_guard.py",
        "ts",
        _changed(tmp_path, *changed),
        cwd=tmp_path,
        env={"SUBJECT": subject},
    )
    assert result.returncode == rc, result.stdout + result.stderr
    if rc:
        assert result.stderr.startswith(
            "::error::This push also releases the Python package"
        )


@_NEEDS_TOMLLIB
def test_guard_script_fails_on_a_bad_config(tmp_path):
    _write_pyproject(tmp_path, "1.2.3", ["../x/package.json"])
    result = _run_script(
        "npm_publish_guard.py",
        "ts",
        _changed(tmp_path),
        cwd=tmp_path,
        env={"SUBJECT": NPM},
    )
    assert result.returncode == 1
    assert result.stderr.startswith("::error::npm publish guard failed")


# --- the guard action's bash, against a real git history -----------------------


def _git(repo, *args):
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def _guard_action():
    return yaml.safe_load(
        (ROOT / "actions" / "npm-publish-guard" / "action.yml").read_text()
    )


@pytest.fixture
def guarded_repo(tmp_path, monkeypatch):
    """A repo syncing ts/package.json: a first commit, then a push of two commits.

    Returns ``(repo, run)``, where ``run(before)`` runs the action's step there.
    """
    if shutil.which("git") is None:
        pytest.skip("needs git")
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(home / "gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", os.devnull)
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "ci@example.invalid")
    _git(repo, "config", "user.name", "CI")
    _write_pyproject(repo, "1.2.3", ["ts/package.json"])
    _package_json(repo / "ts" / "package.json", "1.2.3")
    (repo / "pkg").mkdir()
    (repo / "pkg" / "core.py").write_text("x = 1\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "first")
    # `python3 -I` in the action: this interpreter, whatever python3 is on PATH
    shim = tmp_path / "bin"
    shim.mkdir()
    (shim / "python3").write_text(
        f'#!/usr/bin/env bash\nexec "{sys.executable}" "$@"\n'
    )
    (shim / "python3").chmod(0o755)
    run_script = _guard_action()["runs"]["steps"][0]["run"]

    def run(before, subject=NPM, workflow_ref=""):
        env = {
            **os.environ,
            "PATH": f"{shim}{os.pathsep}{os.environ['PATH']}",
            "GITHUB_ACTION_PATH": str(ROOT / "actions" / "npm-publish-guard"),
            "RUNNER_TEMP": str(tmp_path),
            "PACKAGE_DIR": "ts",
            "SUBJECT": subject,
            "BEFORE": before,
            "WORKFLOW_REF": workflow_ref,
        }
        return subprocess.run(
            ["bash", "-c", run_script],
            cwd=repo,
            env=env,
            capture_output=True,
            text=True,
        )

    return repo, run


def _commit_file(repo, rel, text, message):
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    _git(repo, "add", rel)
    _git(repo, "commit", "-q", "-m", message)


@_NEEDS_BASH
@_NEEDS_TOMLLIB
def test_guard_action_looks_at_every_commit_of_the_push(guarded_repo):
    repo, run = guarded_repo
    before = _git(repo, "rev-parse", "HEAD")
    _commit_file(repo, "pkg/core.py", "x = 2\n", "python change")
    _commit_file(repo, "ts/src/a.ts", "export {}\n", "ts change")
    result = run(before)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "Changed outside ts/: pkg/core.py" in result.stderr
    # the skip-publish marker lets it through
    assert run(before, NPM + " [skip publish]").returncode == 0


@_NEEDS_BASH
@_NEEDS_TOMLLIB
def test_guard_action_passes_a_push_that_changes_only_the_npm_package(guarded_repo):
    repo, run = guarded_repo
    _commit_file(repo, "pkg/core.py", "x = 2\n", "earlier python change")
    before = _git(repo, "rev-parse", "HEAD")
    _commit_file(repo, "ts/src/a.ts", "export {}\n", "ts change")
    result = run(before)
    assert result.returncode == 0, result.stdout + result.stderr


@_NEEDS_BASH
@_NEEDS_TOMLLIB
@pytest.mark.parametrize(
    "before", ["", "0" * 40, "1234567890abcdef1234567890abcdef12345678"]
)
def test_guard_action_falls_back_to_the_last_commit(guarded_repo, before):
    """A new branch (zeros), no `before`, or one this checkout lacks: HEAD^..HEAD."""
    repo, run = guarded_repo
    _commit_file(repo, "pkg/core.py", "x = 2\n", "python change")
    _commit_file(repo, "ts/src/a.ts", "export {}\n", "ts change")
    result = run(before)
    assert result.returncode == 0, result.stdout + result.stderr
    if before.strip("0"):
        assert "::warning::" in result.stdout
    _commit_file(repo, "pkg/core.py", "x = 3\n", "python change on top")
    assert run(before).returncode == 1


@_NEEDS_BASH
@_NEEDS_TOMLLIB
def test_guard_action_sees_a_move_into_the_package_as_a_change_outside(guarded_repo):
    """A rename from pkg/ to ts/ also removes pkg/core.py: that ships with PyPI too."""
    repo, run = guarded_repo
    before = _git(repo, "rev-parse", "HEAD")
    (repo / "ts" / "src").mkdir(parents=True)
    _git(repo, "mv", "pkg/core.py", "ts/src/core.py")
    _git(repo, "commit", "-q", "-m", "move")
    result = run(before)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "Changed outside ts/: pkg/core.py" in result.stderr


@_NEEDS_BASH
@_NEEDS_TOMLLIB
def test_guard_action_counts_the_calling_npm_stub_as_inside(guarded_repo):
    repo, run = guarded_repo
    before = _git(repo, "rev-parse", "HEAD")
    _commit_file(repo, ".github/workflows/npm-ci.yml", "name: npm\n", "stub")
    _commit_file(repo, "ts/src/a.ts", "export {}\n", "ts change")
    assert run(before).returncode == 1
    ref = "o/r/.github/workflows/npm-ci.yml@refs/heads/main"
    result = run(before, workflow_ref=ref)
    assert result.returncode == 0, result.stdout + result.stderr


@_NEEDS_BASH
def test_guard_action_is_a_no_op_without_pyproject(guarded_repo):
    repo, run = guarded_repo
    (repo / "pyproject.toml").unlink()
    result = run("")
    assert result.returncode == 0, result.stderr
    assert "nothing to check" in result.stdout


# --- uv-ci wiring -------------------------------------------------------------


@pytest.mark.parametrize(
    "workflow, job",
    [
        (UV_WORKFLOWS[0], "publish"),
        (UV_WORKFLOWS[0], "publish-native"),
        (UV_WORKFLOWS[1], "publish"),
    ],
    ids=["uv-ci:publish", "uv-ci:publish-native", "inline-template:publish"],
)
def test_publish_jobs_sync_between_the_bump_and_the_bump_commit(workflow, job):
    steps = yaml.safe_load(workflow.read_text())["jobs"][job]["steps"]
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


@pytest.mark.parametrize("workflow", UV_WORKFLOWS, ids=["uv-ci", "inline-template"])
def test_setup_job_exports_the_sync_list(workflow):
    wf = yaml.safe_load(workflow.read_text())
    outputs = wf["jobs"]["setup"]["outputs"]
    assert outputs["version-sync"] == "${{ steps.config.outputs.version-sync }}"


def test_the_actions_take_the_documented_inputs():
    action = yaml.safe_load(
        (ROOT / "actions" / "read-ci-config" / "action.yml").read_text()
    )
    assert "version-sync" in action["outputs"]
    sync_action = yaml.safe_load(
        (ROOT / "actions" / "sync-version" / "action.yml").read_text()
    )
    assert set(sync_action["inputs"]) == {"version", "files"}


@pytest.mark.parametrize("name", NPM_WORKFLOWS)
def test_npm_pack_job_runs_the_guard_before_any_repo_code(name):
    steps = yaml.safe_load((WORKFLOWS / name).read_text())["jobs"]["pack"]["steps"]
    checkout = steps[0]
    assert checkout["uses"].startswith("actions/checkout@")
    assert checkout["with"]["fetch-depth"] == 0
    assert checkout["with"]["persist-credentials"] is False
    guard = steps[1]
    assert guard["uses"] == "i2mint/wads/actions/npm-publish-guard@master"
    assert guard["with"] == {
        "package-dir": "${{ inputs.package-dir }}",
        "subject": "${{ needs.setup.outputs.commit_subject }}",
        "before": "${{ github.event.before }}",
        "workflow-ref": "${{ github.workflow_ref }}",
    }
    assert set(_guard_action()["inputs"]) == set(guard["with"])


# --- npm publish: asked for a release, released nothing -> fail ---------------


def _publish_run(name):
    steps = yaml.safe_load((WORKFLOWS / name).read_text())["jobs"]["publish"]["steps"]
    return next(s for s in steps if s.get("name", "").startswith("Publish tarballs"))


def _fake_tool(bin_dir: Path, name: str, body: str):
    path = bin_dir / name
    path.write_text("#!/usr/bin/env bash\n" + body)
    path.chmod(0o755)


@_NEEDS_BASH
@pytest.mark.skipif(
    shutil.which("openssl") is None, reason="the step hashes with openssl"
)
@pytest.mark.parametrize("name", NPM_WORKFLOWS)
@pytest.mark.parametrize(
    "on_npm, attempt, registry_bytes, expect_rc, expect_text",
    [
        ("", "1", "", 0, "PUBLISH demo-0.1.0.tgz"),  # new version: published
        ("demo@0.1.0", "1", "same", 1, "::error::nothing published: demo@0.1.0"),
        # a re-run of the attempt that published these very bytes
        ("demo@0.1.0", "2", "same", 0, "::warning::nothing published"),
        # a re-run, but npm holds other bytes: someone else's release
        ("demo@0.1.0", "2", "other", 1, "::error::nothing published: demo@0.1.0"),
    ],
)
def test_publish_fails_when_it_releases_nothing(
    tmp_path, name, on_npm, attempt, registry_bytes, expect_rc, expect_text
):
    step = _publish_run(name)
    art = tmp_path / "npm-pack"
    art.mkdir()
    pkg_json = tmp_path / "package.json"
    pkg_json.write_text('{"name": "demo", "version": "0.1.0"}')
    with tarfile.open(art / "demo-0.1.0.tgz", "w:gz") as tar:
        tar.add(pkg_json, arcname="package/package.json")
    (art / "publish-order.txt").write_text("demo-0.1.0.tgz\n")
    tgz = (art / "demo-0.1.0.tgz").read_bytes()
    if registry_bytes == "other":
        tgz += b"something else"
    integrity = "sha512-" + base64.b64encode(hashlib.sha512(tgz).digest()).decode()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    # node: the manifest check prints "name version"; npm: `view -- NAME@VER
    # version` says whether the version exists, `view ... dist.integrity` prints
    # the registry's hash, publish records what it would upload.
    _fake_tool(bin_dir, "node", 'echo "demo 0.1.0"\n')
    _fake_tool(
        bin_dir,
        "npm",
        'if [ "$1" = view ]; then\n'
        '  [ "$3" = "$ON_NPM" ] || exit 1\n'
        '  if [ "$4" = dist.integrity ]; then echo "$INTEGRITY"; fi\n'
        "  exit 0\n"
        "fi\n"
        'if [ "$1" = publish ]; then echo "PUBLISH $(basename "$2")"; exit 0; fi\n'
        "exit 0\n",
    )
    env = {
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "RUNNER_TEMP": str(tmp_path),
        "GITHUB_RUN_ATTEMPT": attempt,
        "ON_NPM": on_npm,
        "INTEGRITY": integrity,
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
    if registry_bytes == "other" and attempt == "2":
        assert "on npm is not this run's tarball" in result.stdout


@pytest.mark.parametrize("name", NPM_WORKFLOWS)
def test_the_npm_hint_mentions_pypi_sync_only_as_a_condition(name):
    run = _publish_run(name)["run"]
    assert "if this repo also publishes to PyPI, [tool.wads.ci.version].sync" in run
