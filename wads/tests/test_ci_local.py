"""`wads ci-local`: the plan it derives from `[tool.wads.ci]`, and runs with a fake runner.

No test here runs a real command: every run goes through `FakeRunner`, and
`subprocess.run` is booby-trapped for the whole module so a slip would fail loudly
rather than lint, install, build, upload or push. The default runner is also checked
to refuse upload and push steps under pytest on its own.
"""

import io
from pathlib import Path

import pytest

import wads.ci_local as ci_local_module
from wads.ci_config import CIConfig
from wads.ci_local import (
    DOCTEST_OPTIONFLAGS,
    PUSHES,
    RELEASE_COMMIT_MESSAGE,
    RELEASE_TAG_MESSAGE,
    UPLOADS,
    WRITES,
    RunResult,
    ci_local,
    plan_ci_local,
    pytest_argv,
    render_plan,
    resolve_pypi_token,
    run_ci_local,
    subprocess_runner,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
TOKEN = "pypi-FAKE-TOKEN-never-real"


@pytest.fixture(autouse=True)
def no_real_subprocess(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError(f"a test reached subprocess.run: {args}")

    monkeypatch.setattr(ci_local_module.subprocess, "run", refuse)


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """No developer ~/.pypirc or token env var may leak into a test."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    for name in ("PYPI_PASSWORD", "UV_PUBLISH_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    return home


def _config(**ci):
    return CIConfig({"project": {"name": "pkg"}, "tool": {"wads": {"ci": ci}}})


def _names(steps):
    return [step.name for step in steps]


class FakeRunner:
    """Records every command and answers from ``responses``: (argv prefix, RunResult)."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, argv, *, cwd, env, capture=False, side_effect=""):
        self.calls.append(
            {"argv": list(argv), "env": dict(env), "side_effect": side_effect}
        )
        for prefix, result in self.responses:
            if list(argv[: len(prefix)]) == list(prefix):
                return result
        return RunResult(0)

    def argvs(self):
        return [call["argv"] for call in self.calls]

    def ran(self, *prefix):
        return any(argv[: len(prefix)] == list(prefix) for argv in self.argvs())


# --------------------------------------------------------------------------------------
# The plan


def test_default_plan_mirrors_the_ci_validation_job():
    steps = plan_ci_local(".", config=_config(), platform="posix")
    assert _names(steps) == [
        "format check (ruff)",
        "lint (ruff)",
        "python 3.10: venv",
        "python 3.10: install",
        "python 3.10: install pytest",
        "python 3.10: tests",
        "python 3.12: venv",
        "python 3.12: install",
        "python 3.12: install pytest",
        "python 3.12: tests",
        "build",
    ]
    by_name = {step.name: step for step in steps}
    assert by_name["format check (ruff)"].argv == ("uvx", "ruff", "format", "--check", ".")
    assert not by_name["format check (ruff)"].blocking, "CI reformats; it never fails on it"
    assert by_name["lint (ruff)"].argv == ("uvx", "ruff", "check", "pkg")
    assert by_name["python 3.12: venv"].argv == ("uv", "venv", "<<workdir>>/py3.12", "--python", "3.12")
    assert by_name["python 3.12: install"].argv[-2:] == ("-e", ".")
    assert by_name["python 3.12: install pytest"].argv[-2:] == ("pytest", "pytest-cov")
    tests = by_name["python 3.12: tests"].argv
    assert tests[:3] == ("<<workdir>>/py3.12/bin/python", "-m", "pytest")
    assert list(tests[3:]) == pytest_argv(_config())
    assert by_name["build"].argv == ("uv", "build", "--out-dir", "<<workdir>>/dist")
    assert not any(step.side_effect for step in steps), "validation has no side effects"


def test_pytest_arguments_follow_the_config():
    config = _config(
        testing={
            "coverage_enabled": False,
            "exclude_paths": ["scrap", " docs "],
            "pytest_args": ["-x", "-k 'not slow'"],
        }
    )
    assert pytest_argv(config) == [
        "--doctest-modules",
        "-o",
        f"doctest_optionflags={DOCTEST_OPTIONFLAGS}",
        "--ignore=scrap",
        "--ignore=docs",
        "-x",
        "-k",
        "not slow",
    ]


def test_extras_are_installed_editable_like_ci():
    steps = plan_ci_local(".", config=_config(install={"extras": ["create", "docs"]}))
    install = next(step for step in steps if step.name.endswith(": install"))
    assert install.argv[-2:] == ("-e", ".[create,docs]")


def test_the_on_demand_matrix_plans_a_single_python():
    steps = plan_ci_local(".", config=_config(testing={"python_versions": ["3.12"]}))
    assert [s.name for s in steps if s.name.endswith(": tests")] == ["python 3.12: tests"]


def test_config_toggles_add_and_remove_steps():
    config = _config(
        quality={"ruff": {"enabled": False}, "black": {"enabled": True}, "mypy": {"enabled": True}},
        testing={"enabled": False, "python_versions": ["3.11", "3.12"]},
        build={"sdist": False},
        env={"required_envvars": ["API_KEY"]},
    )
    names = _names(plan_ci_local(".", config=config))
    assert names == ["required env vars", "format check (black)", "type check (mypy)", "build"]
    build = plan_ci_local(".", config=config)[-1]
    assert build.argv[-1] == "--wheel"


def test_the_licence_gate_runs_once_on_the_first_python():
    data = {"project": {"name": "pkg"}, "tool": {"wads": {"licence": {"enabled": True}}}}
    names = _names(plan_ci_local(".", config=CIConfig(data)))
    assert [n for n in names if "licence" in n] == ["python 3.10: licence perimeter"]


def test_publish_plan_refuses_first_then_releases_like_the_publish_job():
    steps = plan_ci_local(".", publish=True, config=_config())
    names = _names(steps)
    assert names[:4] == [
        "clean working tree",
        "on the default branch",
        "up to date with origin",
        "PyPI credentials",
    ]
    release = names[names.index("python 3.12: tests") + 1 :]
    assert release == [
        "format (ruff)",
        "bump version",
        "write version (pyproject.toml)",
        "build",
        "upload to PyPI",
        "commit release",
        "tag release",
        "push branch",
        "push tag",
    ]
    by_name = {step.name: step for step in steps}
    assert by_name["upload to PyPI"].side_effect == UPLOADS
    assert by_name["upload to PyPI"].env == (("UV_PUBLISH_TOKEN", "<<pypi_token>>"),)
    assert {by_name["push branch"].side_effect, by_name["push tag"].side_effect} == {PUSHES}
    assert names.count("build") == 1


def test_publish_plan_updates_setup_cfg_when_the_repo_has_one(tmp_path):
    (tmp_path / "setup.cfg").write_text("[metadata]\nversion = 0.1.0\n")
    names = _names(plan_ci_local(tmp_path, publish=True, config=_config()))
    assert "write version (setup.cfg)" in names


def test_render_plan_flags_non_blocking_and_side_effecting_steps():
    text = render_plan(plan_ci_local(".", publish=True, config=_config()))
    assert "format check (ruff): uvx ruff format --check .  [non-blocking]" in text
    assert "upload to PyPI: uv publish '<<workdir>>/dist/*'  [uploads]" in text


# --- drift guards: ci-local's mirrors of values the CI files hardcode -------------------


def test_doctest_flags_match_the_run_tests_action():
    action = (REPO_ROOT / "actions" / "run-tests-uv" / "action.yml").read_text()
    assert f"-o doctest_optionflags='{DOCTEST_OPTIONFLAGS}'" in action


def test_release_commit_and_tag_messages_match_the_reusable_workflow():
    workflow = (REPO_ROOT / ".github" / "workflows" / "uv-ci.yml").read_text()
    as_ci = lambda message: message.replace("<<version>>", "${{ env.VERSION }}")
    assert f'commit-message: "{as_ci(RELEASE_COMMIT_MESSAGE)}"' in workflow
    assert f'message: "{as_ci(RELEASE_TAG_MESSAGE)}"' in workflow


def test_the_build_action_uses_flags_uv_build_accepts():
    action = (REPO_ROOT / "actions" / "build-dist-uv" / "action.yml").read_text()
    assert "--no-sdist" not in action and "--no-wheel" not in action
    assert 'BUILD_ARGS="--wheel"' in action and 'BUILD_ARGS="--sdist"' in action


# --------------------------------------------------------------------------------------
# Running with a fake runner


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "pyproject.toml").write_text('[project]\nname = "pkg"\nversion = "0.1.0"\n')
    return root


def test_a_green_run_executes_the_plan_in_order(repo):
    runner, out = FakeRunner(), io.StringIO()
    report = run_ci_local(repo, runner=runner, environ={}, out=out)
    assert report.ok
    assert len(runner.calls) == len(plan_ci_local(repo))
    assert not any("<<" in item for argv in runner.argvs() for item in argv)
    workdir = Path(runner.argvs()[2][2]).parent  # uv venv <workdir>/py3.10
    assert not workdir.exists(), "the temporary workdir is cleaned up"
    assert "Result: PASSED. CI would have reported this run green." in out.getvalue()


def test_a_failing_test_stops_the_run_and_reads_as_a_red_ci(repo):
    runner = FakeRunner()

    def pytest_fails(argv, **kwargs):
        # The interpreter path is per-run, so match on `-m pytest` rather than a prefix.
        result = runner(argv, **kwargs)
        return RunResult(1) if argv[1:3] == ["-m", "pytest"] else result

    out = io.StringIO()
    report = run_ci_local(repo, runner=pytest_fails, environ={}, out=out)
    assert not report.ok and report.failure.name == "python 3.10: tests"
    assert not runner.ran("uv", "build"), "nothing after the failure runs"
    rendered = out.getvalue()
    assert "skip  build" in rendered
    assert "CI would have reported this run red" in rendered


def test_a_non_blocking_failure_is_a_warning_not_a_stop(repo):
    runner = FakeRunner((["uvx", "ruff", "format", "--check"], RunResult(1)))
    out = io.StringIO()
    report = run_ci_local(repo, runner=runner, environ={}, out=out)
    assert report.ok and runner.ran("uvx", "ruff", "check")
    assert "warn  format check (ruff)" in out.getvalue()


def test_required_env_is_checked_and_defaults_are_exported(repo):
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "pkg"\n\n[tool.wads.ci.env]\nrequired_envvars = ["API_KEY"]\n'
        'defaults = {LOG_LEVEL = "INFO"}\n'
    )
    runner = FakeRunner()
    report = run_ci_local(repo, runner=runner, environ={}, out=io.StringIO())
    assert report.failure.name == "required env vars" and runner.calls == []

    report = run_ci_local(repo, runner=runner, environ={"API_KEY": "k"}, out=io.StringIO())
    assert report.ok
    assert all(call["env"]["LOG_LEVEL"] == "INFO" for call in runner.calls)


# --- publish -----------------------------------------------------------------------------


def _git_state(*, status="", origin_head="origin/master", branch="master", behind="0"):
    return [
        (["git", "status", "--porcelain"], RunResult(0, status)),
        (["git", "symbolic-ref"], RunResult(0, origin_head)),
        (["git", "branch", "--show-current"], RunResult(0, branch)),
        (["git", "rev-list", "--count"], RunResult(0, behind)),
    ]


def _assert_nothing_changed(runner):
    assert not [c for c in runner.calls if c["side_effect"] in (WRITES, UPLOADS, PUSHES)]
    assert not runner.ran("uvx"), "refusal happens before lint, tests or the bump"


@pytest.mark.parametrize(
    "state, reason",
    [
        ({"status": " M pkg/core.py"}, "dirty"),
        ({"branch": "feature"}, "not the default branch 'master'"),
        ({"behind": "2"}, "2 commit(s) behind origin/master"),
    ],
)
def test_publish_refuses_before_changing_anything(repo, state, reason):
    runner = FakeRunner(*_git_state(**state))
    out = io.StringIO()
    report = run_ci_local(repo, publish=True, runner=runner, environ={"PYPI_PASSWORD": TOKEN}, out=out)
    assert not report.ok
    assert reason in out.getvalue()
    assert "REFUSED to publish" in out.getvalue()
    _assert_nothing_changed(runner)


def test_publish_refuses_without_credentials(repo):
    runner = FakeRunner(*_git_state())
    out = io.StringIO()
    report = run_ci_local(repo, publish=True, runner=runner, environ={}, out=out)
    assert report.failure.name == "PyPI credentials"
    assert "no PyPI API token" in out.getvalue()
    _assert_nothing_changed(runner)


def test_publish_releases_like_the_publish_job(repo):
    runner = FakeRunner(
        *_git_state(),
        (["uvx", "--from", "isee", "isee", "gen-semver"], RunResult(0, "Installed 3\n0.2.1\n")),
    )
    out = io.StringIO()
    report = run_ci_local(repo, publish=True, runner=runner, environ={"PYPI_PASSWORD": TOKEN}, out=out)
    assert report.ok, out.getvalue()
    upload = next(c for c in runner.calls if c["side_effect"] == UPLOADS)
    assert upload["argv"][:2] == ["uv", "publish"] and upload["argv"][2].endswith("/dist/*")
    assert upload["env"]["UV_PUBLISH_TOKEN"] == TOKEN
    others = [c for c in runner.calls if c is not upload]
    assert all(c["env"].get("UV_PUBLISH_TOKEN") != TOKEN for c in others if "PYPI" not in str(c))
    argvs = runner.argvs()
    assert ["uvx", "--from", "isee", "isee", "update-pyproject-toml", "--version=0.2.1"] in argvs
    assert ["git", "commit", "--all", "-m", "**CI** Formatted code + Updated version to 0.2.1 [skip ci]"] in argvs
    assert ["git", "tag", "-a", "0.2.1", "-m", "Release version 0.2.1"] in argvs
    assert argvs[-2:] == [["git", "push", "origin", "master"], ["git", "push", "origin", "0.2.1"]]
    rendered = out.getvalue()
    assert "Released 0.2.1" in rendered and "PyPI token from $PYPI_PASSWORD" in rendered
    assert TOKEN not in rendered, "the token is never printed"


def test_a_bad_version_stops_before_any_write(repo):
    runner = FakeRunner(*_git_state(), (["uvx", "--from", "isee"], RunResult(0, "oops\n")))
    report = run_ci_local(repo, publish=True, runner=runner, environ={"PYPI_PASSWORD": TOKEN}, out=io.StringIO())
    assert report.failure.name == "bump version"
    assert not [c for c in runner.calls if c["side_effect"] in (UPLOADS, PUSHES)]


def test_a_failure_after_the_upload_says_how_to_finish(repo):
    runner = FakeRunner(
        *_git_state(),
        (["uvx", "--from", "isee", "isee", "gen-semver"], RunResult(0, "0.2.1\n")),
        (["git", "push", "origin", "master"], RunResult(1)),
    )
    out = io.StringIO()
    run_ci_local(repo, publish=True, runner=runner, environ={"PYPI_PASSWORD": TOKEN}, out=out)
    assert "AFTER the upload: PyPI has 0.2.1" in out.getvalue()
    assert "git push origin master && git push origin 0.2.1" in out.getvalue()


# --- credentials and the never-upload guard ----------------------------------------------


def test_token_precedence(isolated_home):
    pypirc = isolated_home / ".pypirc"
    pypirc.write_text("[pypi]\nusername = __token__\npassword = pypi-from-file\n")
    assert resolve_pypi_token(environ={"PYPI_PASSWORD": "a", "UV_PUBLISH_TOKEN": "b"}) == ("a", "$PYPI_PASSWORD")
    assert resolve_pypi_token(environ={"UV_PUBLISH_TOKEN": "b"}) == ("b", "$UV_PUBLISH_TOKEN")
    assert resolve_pypi_token(environ={}) == ("pypi-from-file", f"{pypirc} [pypi]")


def test_a_pypirc_password_that_is_not_a_token_is_not_used(isolated_home):
    (isolated_home / ".pypirc").write_text("[pypi]\nusername = bob\npassword = hunter2\n")
    assert resolve_pypi_token(environ={}) == (None, "")


@pytest.mark.parametrize("side_effect", [UPLOADS, PUSHES])
def test_the_default_runner_refuses_to_upload_or_push_under_pytest(side_effect):
    with pytest.raises(RuntimeError, match="under pytest"):
        subprocess_runner(["true"], cwd=".", env={}, side_effect=side_effect)


# --- the console script ------------------------------------------------------------------


def test_dry_run_prints_the_plan_and_runs_nothing(repo, capsys):
    ci_local(str(repo), dry_run=True)
    out = capsys.readouterr().out
    assert out.startswith("wads ci-local plan")
    assert "lint (ruff): uvx ruff check pkg" in out


def test_a_failed_run_exits_non_zero(repo, monkeypatch):
    class Failed:
        ok = False

    monkeypatch.setattr(ci_local_module, "run_ci_local", lambda *a, **k: Failed())
    with pytest.raises(SystemExit) as exit_info:
        ci_local(str(repo))
    assert exit_info.value.code == 1


def test_the_wads_console_script_dispatches_ci_local(repo, capsys):
    cw = pytest.importorskip("cw")
    from wads.__main__ import _dispatch_funcs

    code = cw.dispatch(_dispatch_funcs, ["ci-local", "--dry-run", "--repo", str(repo)], prog="wads")
    assert code == 0
    assert "wads ci-local plan" in capsys.readouterr().out
