"""i2mint/wads#189: extra test legs with some dependencies pinned.

``[[tool.wads.ci.testing.pinned]]`` entries become extra legs of the reusable workflow's
``validation`` matrix, added by ``include``: the normal install, then the project and
the entry's ``requirements`` in one resolve, ``uv pip check``, then pytest with its
``pytest_args`` on its ``python_version``. They gate publish like every validation leg.
A repo that declares nothing keeps exactly its legs and check names. ``wads ci-local``
plans the same legs. Plumbed CIConfig -> read_ci_config -> read-ci-config action ->
setup outputs -> the matrix's ``include``.
"""

import itertools
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from wads.ci_config import CIConfig, PinnedTestRun
from wads.ci_local import plan_ci_local
from wads.scripts.read_ci_config import (
    pinned_runs_matrix_include,
    read_and_export_ci_config,
)
from wads.tests.test_ci_trigger import _Evaluator, _tokenize, evaluate

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
    (run,) = _cfg([OLDEST], python_versions=["3.11", "3.12"]).pinned_test_runs
    assert run == PinnedTestRun(
        name="oldest-sdk",
        requirements=("elevenlabs==2.58.0",),
        pytest_args=("voxy/tests/test_elevenlabs_model.py",),
        python_version="3.11",
    )


def test_defaults_name_pytest_args_and_python_version():
    (run,) = _cfg(
        [{"requirements": "attrs==22.1.0", "pytest_args": []}],
        pytest_args=["-x"],
        python_versions=["3.12"],
    ).pinned_test_runs
    assert run.name == "pinned-1"
    assert run.requirements == ("attrs==22.1.0",)
    assert run.pytest_args == ("-x",), "empty or absent: the repo's pytest_args"
    assert run.python_version == "3.12", "the first python_versions entry"


def test_python_version_is_per_entry():
    (run,) = _cfg([{**OLDEST, "python_version": "3.13"}]).pinned_test_runs
    assert run.python_version == "3.13"


@pytest.mark.parametrize(
    "bad, match",
    [
        ({"name": "x"}, "requirements"),  # no requirements
        ({"requirements": []}, "requirements is empty"),
        ({"requirements": [3]}, "requirements"),
        ({"requirements": ["--index-url=https://evil"]}, "PEP 508"),
        ({"requirements": ["-e ."]}, "PEP 508"),
        ({"requirements": ["a==1"], "name": "has space"}, "name"),
        ({"requirements": ["a==1"], "name": "../escape"}, "name"),
        ({"requirements": ["a==1"], "pytest_args": [1]}, "pytest_args"),
        ({"requirements": ["a==1"], "python_version": 3.11}, "quote it"),
        ({"requirements": ["a==1"], "python_version": "3.11; rm"}, "python_version"),
        ("not a table", "table"),
    ],
)
def test_an_invalid_entry_fails_closed(bad, match):
    with pytest.raises(ValueError, match=r"pinned\]\] entry 1: .*" + match):
        _cfg([bad]).pinned_test_runs


def test_a_repeated_name_fails_closed():
    with pytest.raises(ValueError, match="entry 2: the name 'oldest-sdk' is already"):
        _cfg([OLDEST, {**OLDEST, "requirements": ["x==1"]}]).pinned_test_runs


def test_a_single_table_is_refused():
    """Only the array-of-tables shape: ``[tool.wads.ci.testing.pinned]`` is an error."""
    with pytest.raises(ValueError, match="array of tables"):
        _cfg(OLDEST).pinned_test_runs


# --- setup job ---------------------------------------------------------------------


def test_the_include_entries_are_self_contained():
    include = pinned_runs_matrix_include(_cfg([OLDEST], python_versions=["3.11"]))
    assert include == [
        {
            "python-version": "3.11",
            "pinned": {
                "name": "oldest-sdk",
                "requirements": ["elevenlabs==2.58.0"],
                "pytest_args": "voxy/tests/test_elevenlabs_model.py",
            },
        }
    ]


def test_no_include_entries_when_tests_are_off():
    assert pinned_runs_matrix_include(_cfg([OLDEST], enabled=False)) == []


def test_an_invalid_entry_fails_even_when_tests_are_off():
    with pytest.raises(ValueError):
        pinned_runs_matrix_include(_cfg([{"name": "x"}], enabled=False))


def _setup(tmp_path, monkeypatch, pyproject):
    (tmp_path / "pyproject.toml").write_text(pyproject)
    out = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setenv("GITHUB_ENV", str(tmp_path / "gh_env"))
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    code = read_and_export_ci_config(str(tmp_path))
    lines = out.read_text().splitlines() if out.exists() else []
    return code, dict(line.split("=", 1) for line in lines if "=" in line)


def test_read_ci_config_emits_the_runs(tmp_path, monkeypatch):
    code, outputs = _setup(
        tmp_path,
        monkeypatch,
        '[project]\nname = "voxy"\n\n[[tool.wads.ci.testing.pinned]]\n'
        'name = "oldest-sdk"\nrequirements = ["elevenlabs==2.58.0", "x>=1,<2"]\n',
    )
    assert code == 0
    (entry,) = json.loads(outputs["pinned-runs"])
    assert entry["python-version"] == "3.10"
    assert entry["pinned"]["requirements"] == ["elevenlabs==2.58.0", "x>=1,<2"]


def test_read_ci_config_emits_an_empty_list_when_none(tmp_path, monkeypatch):
    code, outputs = _setup(tmp_path, monkeypatch, '[project]\nname = "voxy"\n')
    assert code == 0
    assert outputs["pinned-runs"] == "[]"


def test_an_invalid_entry_turns_the_setup_job_red(tmp_path, monkeypatch, capsys):
    code, _ = _setup(
        tmp_path,
        monkeypatch,
        '[project]\nname = "voxy"\n\n[[tool.wads.ci.testing.pinned]]\nname = "x"\n',
    )
    assert code == 1
    assert "pinned]] entry 1" in capsys.readouterr().err


# --- workflow ----------------------------------------------------------------------


def _jobs():
    return yaml.safe_load(UV_CI.read_text(encoding="utf-8"))["jobs"]


def _validation():
    return _jobs()["validation"]


def _step(name):
    (step,) = [s for s in _validation()["steps"] if s.get("name") == name]
    return step


def _value(expr, context):
    """The VALUE of a GitHub expression (``||`` and ``&&`` return operands)."""
    return _Evaluator(_tokenize(expr), context).parse()


def _expand(matrix, include):
    """GitHub's matrix expansion, include semantics included: an include object is
    merged into every combination none of whose ORIGINAL values it overwrites, and
    becomes a new combination when there is none."""
    keys = list(matrix)
    combos = [dict(zip(keys, values)) for values in itertools.product(*matrix.values())]
    originals = [dict(c) for c in combos]
    extra = []
    for obj in include:
        fits = [
            i
            for i, orig in enumerate(originals)
            if all(orig[k] == v for k, v in obj.items() if k in orig)
        ]
        for i in fits:
            combos[i].update(obj)
        if not fits:
            extra.append(dict(obj))
    return combos + extra


def _legs(include, versions=("3.10", "3.12")):
    matrix = _validation()["strategy"]["matrix"]
    assert (
        matrix["include"] == "${{ fromJson(needs.setup.outputs.pinned-runs || '[]') }}"
    )
    base = {k: v for k, v in matrix.items() if k != "include"}
    assert base["python-version"].startswith("${{ fromJson(needs.setup.outputs.python")
    base["python-version"] = list(versions)
    return _expand(base, include)


def _leg_context(leg):
    pinned = leg.get("pinned")
    context = {
        "matrix.python-version": leg["python-version"],
        "matrix.pinned": pinned,
        "needs.setup.outputs.pytest-args": "-v --tb=short",
        "needs.setup.outputs.ruff-enabled": "true",
        "needs.setup.outputs.black-enabled": "true",
        "needs.setup.outputs.mypy-enabled": "true",
        "needs.setup.outputs.metrics-enabled": "true",
    }
    for key in ("name", "pytest_args"):
        context[f"matrix.pinned.{key}"] = pinned[key] if pinned else None
    return context


def _names(include):
    name = _validation()["name"]
    return [_value(name, _leg_context(leg)) for leg in _legs(include)]


def test_the_action_and_the_setup_job_expose_the_output():
    action = yaml.safe_load(ACTION.read_text(encoding="utf-8"))
    assert "pinned-runs" in action["outputs"]
    assert "pinned-runs" in _jobs()["setup"]["outputs"]


def test_there_is_no_separate_pinned_job():
    assert "pinned-validation" not in _jobs()


def test_without_pins_the_legs_and_check_names_are_today_s():
    """A repo that declares nothing (``[]``, or ``''`` from an older read-ci-config,
    which the ``|| '[]'`` covers) keeps exactly ``Validation (<version>)``."""
    assert [leg["python-version"] for leg in _legs([])] == ["3.10", "3.12"]
    assert _names([]) == ["Validation (3.10)", "Validation (3.12)"]


def test_each_pinned_run_is_a_new_leg_not_merged_into_one():
    include = pinned_runs_matrix_include(
        _cfg([OLDEST, {**OLDEST, "name": "other"}], python_versions=["3.10", "3.12"])
    )
    legs = _legs(include)
    assert len(legs) == 4
    assert [leg["pinned"] for leg in legs[:2]] == [False, False], "normal legs intact"
    assert _names(include) == [
        "Validation (3.10)",
        "Validation (3.12)",
        "Validation (pinned oldest-sdk)",
        "Validation (pinned other)",
    ]


def test_pinned_legs_gate_publish():
    """They are legs of `validation`, which publish needs: a release must pass on the
    oldest dependency it claims to support."""
    assert "validation" in _jobs()["publish"]["needs"]


def test_the_pin_step_runs_only_on_pinned_legs_after_the_normal_install():
    steps = _validation()["steps"]
    names = [s.get("name") for s in steps]
    pin = _step("Install Pinned Requirements")
    assert names.index("Install Dependencies") < names.index(pin["name"])
    assert names.index(pin["name"]) < names.index("Run Tests")
    assert pin["if"] == "matrix.pinned"


def test_pins_resolve_with_the_project_then_pip_check():
    """One resolve: a pin outside the package's ranges fails instead of overriding."""
    run = _step("Install Pinned Requirements")["run"]
    install = run.index('uv pip install -e "$target" "${reqs[@]}"')
    assert install < run.index("uv pip check")
    assert 'target=".[$INSTALL_EXTRAS]"' in run


def test_requirements_reach_the_shell_only_through_the_environment():
    """A specifier's `<`, `>` or `;` must never be spliced into the script."""
    pin = _step("Install Pinned Requirements")
    assert "matrix.pinned.requirements" in pin["env"]["PINNED_REQUIREMENTS"]
    assert pin["env"]["INSTALL_EXTRAS"] == "${{ needs.setup.outputs.install-extras }}"
    assert "${{" not in pin["run"]


@pytest.mark.skipif(
    os.name != "posix" or shutil.which("bash") is None,
    reason="needs a POSIX bash (Windows may resolve WSL's bash.exe); the step runs on Linux",
)
@pytest.mark.parametrize("extras, target", [("", "."), ("test,dev", ".[test,dev]")])
def test_the_pin_step_script_passes_each_requirement_as_one_argument(
    tmp_path, extras, target
):
    """Run the step's real script against a fake ``uv`` that records its argv."""
    bin_dir = tmp_path / ".venv" / "bin"
    bin_dir.mkdir(parents=True)
    log = tmp_path / "uv.log"
    uv = bin_dir / "uv"
    uv.write_text(f'#!/bin/sh\nprintf "%s|" "$@" >> "{log}"\necho >> "{log}"\n')
    uv.chmod(0o755)
    (bin_dir / "activate").write_text(f'PATH="{bin_dir}:$PATH"\n')
    # The step quotes each value whole, whatever shell characters it holds.
    requirements = ["x>=1,<2", 'y[a,b]==1 ; "z"']
    env = dict(
        os.environ,
        PINNED_REQUIREMENTS=json.dumps(requirements),
        INSTALL_EXTRAS=extras,
        COVERAGE="true",
    )
    script = _step("Install Pinned Requirements")["run"]
    result = subprocess.run(
        ["bash", "-e", "-c", script],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    calls = [line.rstrip("|").split("|") for line in log.read_text().splitlines()]
    # pytest joins the resolve, so a later pytest install cannot undo a pin
    assert calls[0] == [
        "pip",
        "install",
        "-e",
        target,
        *requirements,
        "pytest",
        "pytest-cov",
    ]
    assert calls[1] == ["pip", "check"]


@pytest.mark.skipif(
    os.name != "posix" or shutil.which("bash") is None,
    reason="needs a POSIX bash (Windows may resolve WSL's bash.exe); the step runs on Linux",
)
@pytest.mark.parametrize("payload", ["[]", "not json"])
def test_the_pin_step_fails_when_no_requirement_arrives(tmp_path, payload):
    """Never a silent unpinned leg: an empty or broken payload turns the step red."""
    (tmp_path / ".venv" / "bin").mkdir(parents=True)
    (tmp_path / ".venv" / "bin" / "activate").write_text("")
    env = dict(os.environ, PINNED_REQUIREMENTS=payload, INSTALL_EXTRAS="")
    script = _step("Install Pinned Requirements")["run"]
    result = subprocess.run(
        ["bash", "-e", "-c", script], cwd=tmp_path, env=env, capture_output=True
    )
    assert result.returncode != 0


def test_the_tests_use_the_entry_s_pytest_args_and_the_normal_coverage():
    tests = _step("Run Tests")["with"]
    assert tests["coverage"] == "${{ needs.setup.outputs.coverage-enabled }}"
    (normal, pinned) = _legs([{"python-version": "3.10", "pinned": OLDEST}])[1:]
    pinned = {**pinned, "pinned": {**OLDEST, "pytest_args": "t.py"}}
    assert _value(tests["pytest-args"], _leg_context(normal)) == "-v --tb=short"
    assert _value(tests["pytest-args"], _leg_context(pinned)) == "t.py"


@pytest.mark.parametrize(
    "name",
    [
        "Format Source Code",
        "Format Source Code (black)",
        "Lint Validation",
        "Type Check (mypy)",
        "Track Code Metrics",
    ],
)
def test_quality_and_metrics_steps_run_on_normal_legs_only(name):
    condition = _step(name)["if"]
    (normal, pinned) = _legs([{"python-version": "3.12", "pinned": OLDEST}])[1:]
    assert evaluate(condition, _leg_context(normal))
    assert not evaluate(condition, _leg_context(pinned))


def test_the_licence_perimeter_runs_once_not_on_a_pinned_leg():
    assert _step("Licence Perimeter")["if"].endswith("&& !matrix.pinned")


# --- ci-local ----------------------------------------------------------------------


def test_ci_local_plans_each_run_after_the_normal_tests(tmp_path):
    config = _cfg([OLDEST], python_versions=["3.11", "3.12"])
    steps = plan_ci_local(tmp_path, config=config, platform="posix")
    names = [s.name for s in steps]
    assert names.index("python 3.12: tests") < names.index("pinned oldest-sdk: venv")
    by_name = {s.name: s for s in steps}
    assert by_name["pinned oldest-sdk: venv"].argv[-1] == "3.11", "first python"
    install = by_name["pinned oldest-sdk: install"].argv
    assert install[-5:] == ("-e", ".", "elevenlabs==2.58.0", "pytest", "pytest-cov"), (
        "one resolve, pytest included"
    )
    assert by_name["pinned oldest-sdk: pip check"].argv[:3] == ("uv", "pip", "check")
    assert names.index("pinned oldest-sdk: pip check") < names.index(
        "pinned oldest-sdk: tests"
    )
    tests = by_name["pinned oldest-sdk: tests"].argv
    assert tests[-1] == "voxy/tests/test_elevenlabs_model.py"
    assert "--cov=voxy" in tests, "coverage as on the normal legs"


def test_ci_local_uses_the_entry_s_python_version(tmp_path):
    config = _cfg([{**OLDEST, "python_version": "3.13"}])
    by_name = {s.name: s for s in plan_ci_local(tmp_path, config=config)}
    assert by_name["pinned oldest-sdk: venv"].argv[-1] == "3.13"


def test_ci_local_normal_legs_have_no_pip_check(tmp_path):
    names = [s.name for s in plan_ci_local(tmp_path, config=_cfg([OLDEST]))]
    assert not any(n.startswith("python ") and "pip check" in n for n in names)


def test_ci_local_plans_nothing_extra_when_tests_are_off(tmp_path):
    config = _cfg([OLDEST], enabled=False)
    assert not any("pinned" in s.name for s in plan_ci_local(tmp_path, config=config))


def test_ci_local_fails_closed_on_an_invalid_entry(tmp_path):
    with pytest.raises(ValueError, match="pinned"):
        plan_ci_local(tmp_path, config=_cfg([{"name": "x"}]))


def test_a_pin_with_an_environment_marker_is_refused():
    """uv skips a requirement whose marker is false: the leg would run unpinned."""
    with pytest.raises(ValueError, match="environment marker"):
        CIConfig(
            {
                "tool": {
                    "wads": {
                        "ci": {
                            "testing": {
                                "pinned": [
                                    {
                                        "name": "m",
                                        "requirements": [
                                            "x==1; python_version < '3.10'"
                                        ],
                                    }
                                ]
                            }
                        }
                    }
                }
            }
        ).pinned_test_runs
