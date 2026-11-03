"""i2mint/wads#189: extra test runs with some dependencies pinned.

``[[tool.wads.ci.testing.pinned]]`` entries become one ``pinned-validation`` job each
in the reusable workflow (Linux, first Python): the normal install, the entry's
``requirements`` on top, then pytest with its ``pytest_args``. ``wads ci-local`` plans
the same runs. Plumbed CIConfig -> read_ci_config -> read-ci-config action -> setup
outputs -> the job's matrix.
"""

import json
from pathlib import Path

import pytest
import yaml

from wads.ci_config import CIConfig, PinnedTestRun
from wads.ci_local import plan_ci_local
from wads.scripts.read_ci_config import read_and_export_ci_config

REPO_ROOT = Path(__file__).resolve().parents[2]
UV_CI = REPO_ROOT / ".github" / "workflows" / "uv-ci.yml"
ACTION = REPO_ROOT / "actions" / "read-ci-config" / "action.yml"

OLDEST = {
    "name": "oldest-sdk",
    "requirements": ["elevenlabs==2.58.0"],
    "pytest_args": ["voxy/tests/test_elevenlabs_model.py"],
}


def _cfg(pinned, **testing):
    data = {"project": {"name": "voxy"}}
    data["tool"] = {"wads": {"ci": {"testing": {"pinned": pinned, **testing}}}}
    return CIConfig(data)


# --- config ------------------------------------------------------------------------


def test_nothing_declared_means_no_runs():
    assert CIConfig({}).pinned_test_runs == []


def test_a_declared_entry_is_read():
    (run,) = _cfg([OLDEST]).pinned_test_runs
    assert run == PinnedTestRun(
        name="oldest-sdk",
        requirements=("elevenlabs==2.58.0",),
        pytest_args=("voxy/tests/test_elevenlabs_model.py",),
    )


def test_a_single_table_and_string_fields_are_accepted():
    (run,) = _cfg(
        {"requirements": "attrs==22.1.0"}, pytest_args=["-x"]
    ).pinned_test_runs
    assert run.name == "pinned-1"
    assert run.requirements == ("attrs==22.1.0",)
    assert run.pytest_args == ("-x",), "defaults to the repo's pytest_args"


@pytest.mark.parametrize(
    "bad",
    [
        {"name": "x"},  # no requirements
        {"requirements": []},
        {"requirements": [3]},
        {"requirements": ["a==1"], "name": "has space"},
        {"requirements": ["a==1"], "name": "../escape"},
        {"requirements": ["a==1"], "pytest_args": [1]},
        "not a table",
    ],
)
def test_an_invalid_entry_is_skipped_with_a_warning(bad):
    with pytest.warns(UserWarning, match=r"pinned entry 1"):
        assert _cfg([bad]).pinned_test_runs == []


def test_a_repeated_name_is_skipped_with_a_warning():
    with pytest.warns(UserWarning, match="already used"):
        runs = _cfg([OLDEST, {**OLDEST, "requirements": ["x==1"]}]).pinned_test_runs
    assert [r.requirements for r in runs] == [("elevenlabs==2.58.0",)]


def test_the_output_joins_pytest_args_for_run_tests_uv():
    (run,) = _cfg([OLDEST]).pinned_test_runs
    assert run.as_output() == {
        "name": "oldest-sdk",
        "requirements": ["elevenlabs==2.58.0"],
        "pytest_args": "voxy/tests/test_elevenlabs_model.py",
    }


# --- setup job ---------------------------------------------------------------------


def _outputs(tmp_path, monkeypatch, pyproject):
    (tmp_path / "pyproject.toml").write_text(pyproject)
    out = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setenv("GITHUB_ENV", str(tmp_path / "gh_env"))
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    assert read_and_export_ci_config(str(tmp_path)) == 0
    lines = out.read_text().splitlines()
    return dict(line.split("=", 1) for line in lines if "=" in line)


def test_read_ci_config_emits_the_runs(tmp_path, monkeypatch):
    outputs = _outputs(
        tmp_path,
        monkeypatch,
        '[project]\nname = "voxy"\n\n[[tool.wads.ci.testing.pinned]]\n'
        'name = "oldest-sdk"\nrequirements = ["elevenlabs==2.58.0", "x>=1,<2"]\n',
    )
    (run,) = json.loads(outputs["pinned-runs"])
    assert run["requirements"] == ["elevenlabs==2.58.0", "x>=1,<2"]


def test_read_ci_config_emits_an_empty_list_when_none(tmp_path, monkeypatch):
    outputs = _outputs(tmp_path, monkeypatch, '[project]\nname = "voxy"\n')
    assert outputs["pinned-runs"] == "[]"


# --- workflow ----------------------------------------------------------------------


def _jobs():
    return yaml.safe_load(UV_CI.read_text(encoding="utf-8"))["jobs"]


def test_the_action_and_the_setup_job_expose_the_output():
    action = yaml.safe_load(ACTION.read_text(encoding="utf-8"))
    assert "pinned-runs" in action["outputs"]
    assert "pinned-runs" in _jobs()["setup"]["outputs"]


def test_the_job_is_skipped_unless_runs_are_declared():
    """Fail-closed: '[]' (nothing declared) and '' (an older read-ci-config) skip."""
    job = _jobs()["pinned-validation"]
    assert "needs.setup.outputs.pinned-runs != '[]'" in job["if"]
    assert "needs.setup.outputs.pinned-runs != ''" in job["if"]
    assert job["needs"] == "setup"
    assert "pinned-runs" in job["strategy"]["matrix"]["pinned"]


def test_the_job_does_not_gate_publish():
    """A skipped need would skip every release of every repo that declares nothing."""
    assert "pinned-validation" not in _jobs()["publish"]["needs"]


def test_requirements_reach_the_shell_only_through_the_environment():
    """A specifier's `<`, `>` or `;` must never be spliced into the script."""
    steps = _jobs()["pinned-validation"]["steps"]
    (pin,) = [s for s in steps if s.get("name") == "Install the pinned requirements"]
    assert "matrix.pinned.requirements" in pin["env"]["PINNED_REQUIREMENTS"]
    assert "${{" not in pin["run"]


def test_the_job_installs_like_validation_then_runs_the_entry_s_pytest_args():
    steps = _jobs()["pinned-validation"]["steps"]
    uses = [s.get("uses", s.get("name")) for s in steps]
    install = uses.index("i2mint/wads/actions/install-deps-uv@master")
    assert install < uses.index("Install the pinned requirements")
    tests = steps[uses.index("i2mint/wads/actions/run-tests-uv@master")]
    assert tests["with"]["pytest-args"] == "${{ matrix.pinned.pytest_args }}"
    validation_install = next(
        s
        for s in _jobs()["validation"]["steps"]
        if "install-deps-uv" in s.get("uses", "")
    )
    assert steps[install]["with"] == validation_install["with"]


# --- ci-local ----------------------------------------------------------------------


def test_ci_local_plans_each_run_after_the_normal_tests(tmp_path):
    config = _cfg([OLDEST], python_versions=["3.11", "3.12"])
    steps = plan_ci_local(tmp_path, config=config, platform="posix")
    names = [s.name for s in steps]
    assert names.index("python 3.12: tests") < names.index("pinned oldest-sdk: venv")
    by_name = {s.name: s for s in steps}
    assert by_name["pinned oldest-sdk: venv"].argv[-1] == "3.11", "first python"
    assert by_name["pinned oldest-sdk: pins"].argv[-1] == "elevenlabs==2.58.0"
    tests = by_name["pinned oldest-sdk: tests"].argv
    assert tests[-1] == "voxy/tests/test_elevenlabs_model.py"
    assert not any(a.startswith("--cov") for a in tests)


def test_ci_local_plans_nothing_extra_when_tests_are_off(tmp_path):
    config = _cfg([OLDEST], enabled=False)
    assert not any("pinned" in s.name for s in plan_ci_local(tmp_path, config=config))
