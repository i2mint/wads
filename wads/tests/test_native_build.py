"""i2mint/wads#166: the reusable workflow's native (maturin) wheel path.

Config (``wads.native_build``) -> setup outputs (``read_ci_config``) -> the gated jobs in
``uv-ci.yml``. A pure-Python repo must run exactly the jobs it ran before; the gate
evaluations live in ``test_ci_trigger.py``, the permission rules in
``test_workflow_permissions.py``. The actions themselves run for real in the
``native-selftest`` workflow, on the ``ci-fixtures/native_pkg`` fixture.
"""

import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from wads.native_build import (
    DFLT_NATIVE_TARGETS,
    NATIVE_TARGETS,
    cargo_test_args,
    native_build_config,
)
from wads.scripts.read_ci_config import read_and_export_ci_config

ROOT = Path(__file__).resolve().parents[2]
UV_CI = ROOT / ".github" / "workflows" / "uv-ci.yml"
SELFTEST = ROOT / ".github" / "workflows" / "native-selftest.yml"
FIXTURE = ROOT / "ci-fixtures" / "native_pkg"
MATURIN = {"build-system": {"build-backend": "maturin"}}


def _with_native(native, **extra):
    return {**MATURIN, "tool": {"wads": {"ci": {"build": {"native": native}}}}, **extra}


# --- config ------------------------------------------------------------------------


def test_a_maturin_backend_turns_the_path_on_with_the_five_default_targets():
    nb = native_build_config({**MATURIN, "project": {"name": "my-pkg"}, "tool": {}})
    assert [t["name"] for t in nb.matrix()] == list(DFLT_NATIVE_TARGETS)
    assert len(DFLT_NATIVE_TARGETS) == 5
    assert nb.smoke_import == "my_pkg", "no module-name: the import name"
    assert nb.options()["maturin_args"] == "--release --locked"
    assert nb.options()["cargo_test_args"] is None, "derived from cargo metadata"


@pytest.mark.parametrize("backend", ["hatchling.build", "setuptools.build_meta", ""])
def test_other_backends_have_no_native_path(backend):
    assert native_build_config({"build-system": {"build-backend": backend}}) is None


def test_native_false_turns_it_off_and_a_name_turns_it_on():
    assert native_build_config(_with_native(False)) is None
    on = native_build_config(
        {
            "project": {"name": "p"},
            "tool": {"wads": {"ci": {"build": {"native": "maturin"}}}},
        }
    )
    assert on is not None and on.backend == "maturin"


def test_the_table_form_sets_targets_args_and_imports():
    nb = native_build_config(
        _with_native(
            {
                "targets": [
                    "linux-x86_64",
                    {
                        "name": "linux-musl",
                        "runner": "ubuntu-latest",
                        "target": "x86_64-unknown-linux-musl",
                        "manylinux": "musllinux_1_2",
                    },
                ],
                "maturin_args": ["--release"],
                "smoke_import": "pkg._core",
                "cargo_test_args": ["-p", "pkg-core"],
            }
        )
    )
    assert [t["name"] for t in nb.matrix()] == ["linux-x86_64", "linux-musl"]
    assert nb.matrix()[1]["manylinux"] == "musllinux_1_2"
    assert nb.options() == {
        "maturin_args": "--release",
        "smoke_import": "pkg._core",
        "manifest_path": "Cargo.toml",
        "cargo_test_args": ["-p", "pkg-core"],
    }


def test_the_extension_module_is_the_default_smoke_import():
    nb = native_build_config(
        {**MATURIN, "tool": {"maturin": {"module-name": "pkg._core"}}}
    )
    assert nb.smoke_import == "pkg._core"


@pytest.mark.parametrize(
    "native, message",
    [
        ("cython", "native must be one of"),
        ({"targets": ["linux-sparc"]}, "unknown target"),
        ({"targets": []}, "non-empty"),
        ({"targets": ["linux-x86_64", "linux-x86_64"]}, "unique"),
        ({"targets": [{"name": "x", "runner": "r"}]}, "bad target table"),
        ({"maturin_args": "--release"}, "list of strings"),
        ({"smoke_import": " "}, "non-blank"),
        ({"targetz": ["linux-x86_64"]}, "unknown key"),
    ],
)
def test_a_bad_setting_fails_closed(native, message):
    """A red setup job beats a release that silently builds something else."""
    with pytest.raises(ValueError, match=message):
        native_build_config(_with_native(native))


def test_native_true_needs_a_known_backend():
    with pytest.raises(ValueError, match="no native path"):
        native_build_config({"tool": {"wads": {"ci": {"build": {"native": True}}}}})


def test_the_registry_marks_the_cross_compiled_leg_unsmokable():
    assert NATIVE_TARGETS["macos-x86_64"].smoke is False
    assert all(t.smoke for n, t in NATIVE_TARGETS.items() if n != "macos-x86_64")


# --- cargo test arguments ----------------------------------------------------------


def _metadata(root):
    return {
        "packages": [
            {"name": "pkg-core", "manifest_path": str(root / "rust/core/Cargo.toml")},
            {"name": "pkg-py", "manifest_path": str(root / "rust/py/Cargo.toml")},
        ]
    }


def test_the_binding_crate_is_excluded(tmp_path):
    args = cargo_test_args(
        _metadata(tmp_path), binding_manifest=str(tmp_path / "rust/py/Cargo.toml")
    )
    assert args == ["--workspace", "--exclude", "pkg-py"]


def test_the_script_reads_the_binding_from_tool_maturin(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[tool.maturin]\nmanifest-path = "rust/py/Cargo.toml"\n'
    )
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            str(ROOT / "wads/scripts/cargo_test_args.py"),
            str(tmp_path),
        ],
        input=json.dumps(_metadata(tmp_path)),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "--workspace --exclude pkg-py"


def test_a_single_crate_package_has_nothing_to_cargo_test(tmp_path):
    meta = {
        "packages": [{"name": "pkg", "manifest_path": str(tmp_path / "Cargo.toml")}]
    }
    assert cargo_test_args(meta, binding_manifest=str(tmp_path / "Cargo.toml")) == []


# --- setup outputs -----------------------------------------------------------------


def _outputs(tmp_path, monkeypatch, pyproject):
    (tmp_path / "pyproject.toml").write_text(pyproject)
    out = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setenv("GITHUB_ENV", str(tmp_path / "gh_env"))
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    code = read_and_export_ci_config(str(tmp_path))
    lines = out.read_text().splitlines() if out.exists() else []
    return code, dict(line.split("=", 1) for line in lines if "=" in line)


def test_a_pure_python_repo_emits_native_false(tmp_path, monkeypatch):
    code, outputs = _outputs(tmp_path, monkeypatch, '[project]\nname = "p"\n')
    assert code == 0
    assert (outputs["native"], outputs["native-targets"]) == ("false", "[]")


def test_the_fixture_emits_its_matrix(tmp_path, monkeypatch):
    code, outputs = _outputs(
        tmp_path, monkeypatch, (FIXTURE / "pyproject.toml").read_text()
    )
    assert code == 0 and outputs["native"] == "true"
    assert len(json.loads(outputs["native-targets"])) == 5
    assert json.loads(outputs["native-options"])["smoke_import"] == (
        "wads_native_fixture._core"
    )


def test_a_bad_native_setting_turns_the_setup_job_red(tmp_path, monkeypatch):
    code, _ = _outputs(
        tmp_path,
        monkeypatch,
        '[project]\nname = "p"\n[tool.wads.ci.build]\nnative = "cython"\n',
    )
    assert code == 1


# --- workflow ----------------------------------------------------------------------


def _jobs(path=UV_CI):
    return yaml.safe_load(path.read_text(encoding="utf-8"))["jobs"]


def test_the_validation_rust_steps_are_gated_on_native():
    steps = _jobs()["validation"]["steps"]
    by_name = {s.get("name"): s for s in steps}
    names = [s.get("name") for s in steps]
    for name in ("Set up Rust", "Rust Checks"):
        assert "needs.setup.outputs.native == 'true'" in by_name[name]["if"]
    assert names.index("Set up Rust") < names.index("Install Dependencies")
    assert names.index("Install Dependencies") < names.index("Rust Checks")


def test_publish_native_reuses_the_publish_steps_and_swaps_only_the_build():
    jobs = _jobs()
    publish = jobs["publish"]["steps"]
    native = jobs["publish-native"]["steps"]
    built = [s for s in publish if s.get("name") == "Build Distribution"]
    assert len(built) == 1
    shared = [s for s in publish if s not in built]
    assert [s for s in native if s in shared] == shared, "same steps, same order"
    extra = [s.get("name") for s in native if s not in shared]
    assert extra == [
        "Check the wheels carry this release's version",
        "Build the sdist",
        "Collect the wheels",
        "List the distributions",
    ]


def test_the_wheels_gate_the_native_release():
    jobs = _jobs()
    assert jobs["publish-native"]["needs"] == [
        "setup",
        "validation",
        "native-version",
        "native-wheels",
    ]
    assert jobs["native-wheels"]["needs"] == ["setup", "native-version"]
    assert "native-wheels" not in jobs["publish"]["needs"]


def test_the_selftest_builds_the_fixture_with_this_commit_s_actions():
    steps = [s for job in _jobs(SELFTEST).values() for s in job["steps"]]
    used = {s["uses"] for s in steps if str(s.get("uses", "")).startswith("./actions/")}
    assert used == {
        "./actions/setup-rust",
        "./actions/rust-checks",
        "./actions/build-native-wheel",
    }
    called = {
        s["uses"].split("@")[0].replace("i2mint/wads/", "./")
        for job in ("validation", "native-wheels")
        for s in _jobs()[job]["steps"]
        if "rust" in str(s.get("uses", "")) or "native" in str(s.get("uses", ""))
    }
    assert called == used, "the self-test covers every native action uv-ci.yml calls"


# --- ci-local ----------------------------------------------------------------------


def test_ci_local_runs_the_rust_checks_for_a_native_repo(tmp_path):
    from wads.ci_local import plan_ci_local, run_ci_local
    from wads.tests.test_ci_local import FakeRunner, RunResult

    (tmp_path / "pyproject.toml").write_text((FIXTURE / "pyproject.toml").read_text())
    names = [s.name for s in plan_ci_local(tmp_path)]
    assert (
        names.index("lint (ruff)")
        < names.index("rust: fmt")
        < names.index("rust: test")
    )
    meta = json.dumps(
        {
            "packages": [
                {"name": "c", "manifest_path": str(tmp_path / "rust/core/Cargo.toml")},
                {"name": "b", "manifest_path": str(tmp_path / "rust/py/Cargo.toml")},
            ]
        }
    )
    runner = FakeRunner((["cargo", "metadata"], RunResult(0, meta)))
    report = run_ci_local(tmp_path, runner=runner, environ={}, out=io.StringIO())
    assert report.ok
    manifest = ["--manifest-path", "rust/py/Cargo.toml"]
    assert [
        "cargo",
        "test",
        *manifest,
        "--workspace",
        "--exclude",
        "b",
    ] in runner.argvs()
    assert ["cargo", "fmt", "--all", "--check", *manifest] in runner.argvs()


def test_ci_local_has_no_rust_steps_for_a_pure_python_repo(tmp_path):
    from wads.ci_local import plan_ci_local

    (tmp_path / "pyproject.toml").write_text('[project]\nname = "p"\n')
    assert not any(s.name.startswith("rust:") for s in plan_ci_local(tmp_path))


@pytest.mark.skipif(
    os.name != "posix", reason="POSIX bash (Windows may resolve WSL's bash.exe)"
)
def test_the_wheel_check_refuses_a_non_abi3_wheel():
    """One wheel per platform covers every CPython only when it is abi3 (#166 review)."""
    action = yaml.safe_load(
        (ROOT / "actions/build-native-wheel/action.yml").read_text()
    )
    (check,) = [
        s for s in action["runs"]["steps"] if s.get("name") == "Check the wheel"
    ]

    def run(wheel_name, version=""):
        with __import__("tempfile").TemporaryDirectory() as d:
            (Path(d) / "dist").mkdir()
            (Path(d) / "dist" / wheel_name).write_text("")
            env = {"PATH": "/usr/bin:/bin", "VERSION": version}
            return subprocess.run(
                ["bash", "-c", check["run"]],
                cwd=d,
                env=env,
                capture_output=True,
                text=True,
            )

    assert run("p-0.1.0-cp310-abi3-manylinux_2_17_x86_64.whl", "0.1.0").returncode == 0
    bad = run("p-0.1.0-cp312-cp312-manylinux_2_17_x86_64.whl", "0.1.0")
    assert bad.returncode == 1 and "not an abi3 wheel" in bad.stdout
    assert run("p-0.0.9-cp310-abi3-win_amd64.whl", "0.1.0").returncode == 1


def test_the_release_artifacts_overwrite_on_a_full_rerun():
    """A full re-run re-uploads the same artifact names; without overwrite it 409s."""
    action = yaml.safe_load(
        (ROOT / "actions/build-native-wheel/action.yml").read_text()
    )
    (upload,) = [
        s for s in action["runs"]["steps"] if "upload-artifact" in str(s.get("uses"))
    ]
    assert upload["with"]["overwrite"] is True
    steps = _jobs()["native-version"]["steps"]
    (upload,) = [s for s in steps if "upload-artifact" in str(s.get("uses"))]
    assert upload["with"]["overwrite"] is True


def test_the_fixture_commits_its_lockfile_so_the_locked_default_is_exercised():
    assert (FIXTURE / "Cargo.lock").is_file()
    assert "generate-lockfile" not in SELFTEST.read_text()
