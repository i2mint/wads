"""`wads ci-local`: the plan it derives from `[tool.wads.ci]`, and runs with a fake runner.

No test here runs a real command: every run goes through `FakeRunner`, and
`subprocess.run` is booby-trapped for the whole module so a slip would fail loudly
rather than lint, install, build, upload or push. The default runner is also checked
to refuse upload and push steps under pytest on its own.
"""

import io
import json
import os
from pathlib import Path

import pytest

import wads.ci_local as ci_local_module
from wads.ci_config import CIConfig
from wads.npm_config import (
    NPM_CI_DEFAULTS,
    NPM_MONOREPO_COMMAND_DEFAULTS,
    NpmComponent,
    npm_components,
    npm_validate_commands,
)
from wads.profiles import apply_frontend
from wads.scripts.pytest_doctest_flags import DOCTEST_OPTIONFLAGS
from wads.ci_local import (
    GIT_LS_FILES,
    HOST_INSTALL_PIN_VARS,
    HOST_ONLY_VARS,
    NPM_COMMAND_SHELL,
    PUSHES,
    RELEASE_COMMIT_MESSAGE,
    RELEASE_TAG_MESSAGE,
    UPLOADS,
    VERSION_TOOL,
    WRITES,
    RunResult,
    ci_local,
    plan_ci_local,
    pytest_argv,
    render_plan,
    resolve_pypi_token,
    run_ci_local,
    subprocess_runner,
    tool_problems,
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
            {
                "argv": list(argv),
                "env": dict(env),
                "side_effect": side_effect,
                "cwd": Path(cwd),
            }
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


def test_default_plan_mirrors_the_ci_validation_job(tmp_path):
    steps = plan_ci_local(tmp_path, config=_config(), platform="posix")
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
    assert by_name["format check (ruff)"].argv == (
        "uvx",
        "ruff",
        "format",
        "--check",
        ".",
    )
    assert not by_name["format check (ruff)"].blocking, (
        "CI reformats; it never fails on it"
    )
    assert by_name["lint (ruff)"].argv == ("uvx", "ruff", "check", "pkg")
    assert by_name["python 3.12: venv"].argv == (
        "uv",
        "venv",
        "<<workdir>>/py3.12",
        "--python",
        "3.12",
    )
    assert by_name["python 3.12: install"].argv[-2:] == ("-e", ".")
    assert by_name["python 3.12: install pytest"].argv[-2:] == ("pytest", "pytest-cov")
    tests = by_name["python 3.12: tests"].argv
    assert tests[:3] == ("<<workdir>>/py3.12/bin/python", "-m", "pytest")
    # ci-local's private basetemp (issue #159; first, so a `--` in the user's
    # pytest_args cannot make it a test path), then CI's pytest arguments
    assert list(tests[3:]) == [
        "--basetemp",
        "<<workdir>>/pytest",
        *pytest_argv(_config(), repo=tmp_path),
    ]
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
    assert [s.name for s in steps if s.name.endswith(": tests")] == [
        "python 3.12: tests"
    ]


def test_config_toggles_add_and_remove_steps():
    config = _config(
        quality={
            "ruff": {"enabled": False},
            "black": {"enabled": True},
            "mypy": {"enabled": True},
        },
        testing={"enabled": False, "python_versions": ["3.11", "3.12"]},
        build={"sdist": False},
        env={"required_envvars": ["API_KEY"]},
    )
    names = _names(plan_ci_local(".", config=config))
    assert names == [
        "required env vars",
        "format check (black)",
        "type check (mypy)",
        "build",
    ]
    build = plan_ci_local(".", config=config)[-1]
    assert build.argv[-1] == "--wheel"


def test_the_licence_gate_runs_once_on_the_first_python():
    data = {
        "project": {"name": "pkg"},
        "tool": {"wads": {"licence": {"enabled": True}}},
    }
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
    assert {by_name["push branch"].side_effect, by_name["push tag"].side_effect} == {
        PUSHES
    }
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


def test_run_tests_action_takes_its_doctest_flags_from_the_shared_script():
    action = (REPO_ROOT / "actions" / "run-tests-uv" / "action.yml").read_text()
    assert "wads/scripts/pytest_doctest_flags.py" in action
    assert "ELLIPSIS IGNORE_EXCEPTION_DETAIL" not in action


@pytest.mark.parametrize(
    "name, text",
    [
        (
            "pyproject.toml",
            '[tool.pytest.ini_options]\ndoctest_optionflags = ["ELLIPSIS"]\n',
        ),
        ("pytest.ini", "[pytest]\ndoctest_optionflags = ELLIPSIS\n"),
        ("tox.ini", "[pytest]\ndoctest_optionflags=ELLIPSIS\n"),
        ("setup.cfg", "[tool:pytest]\ndoctest_optionflags = ELLIPSIS\n"),
    ],
)
def test_repo_doctest_flags_win_over_the_ci_default(tmp_path, name, text):
    (tmp_path / name).write_text(text)
    argv = pytest_argv(_config(), repo=tmp_path)
    assert "--doctest-modules" in argv
    assert not any("doctest_optionflags" in a for a in argv)


def test_ci_default_doctest_flags_apply_when_the_repo_sets_none(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\ntestpaths = []\n"
    )
    argv = pytest_argv(_config(), repo=tmp_path)
    assert f"doctest_optionflags={DOCTEST_OPTIONFLAGS}" in argv


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

    report = run_ci_local(
        repo, runner=runner, environ={"API_KEY": "k"}, out=io.StringIO()
    )
    assert report.ok
    assert all(call["env"]["LOG_LEVEL"] == "INFO" for call in runner.calls)


def test_host_install_pins_are_kept_out_of_every_step(repo):
    """Issue #191: the dev machine's UV_CONSTRAINT (which pins fleet packages to their
    main checkouts) must not reach ci-local's installs; hosted CI has no such file."""
    runner, out = FakeRunner(), io.StringIO()
    environ = {name: f"/x/{name}.txt" for name in HOST_INSTALL_PIN_VARS}
    report = run_ci_local(repo, runner=runner, environ=environ, out=out)
    assert report.ok and runner.calls
    for call in runner.calls:
        assert not set(HOST_INSTALL_PIN_VARS) & call["env"].keys()
    assert f"ran without {', '.join(sorted(HOST_INSTALL_PIN_VARS))}" in out.getvalue()

    # The seam keeps them for a caller who wants the dev machine's pins.
    runner = FakeRunner()
    run_ci_local(
        repo, runner=runner, environ=environ, out=io.StringIO(), host_only_vars=()
    )
    assert all(
        call["env"]["UV_CONSTRAINT"] == "/x/UV_CONSTRAINT.txt" for call in runner.calls
    )


def test_a_committed_default_wins_over_a_dropped_pin_and_is_not_reported(repo):
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "pkg"\n\n[tool.wads.ci.env]\n'
        'defaults = {UV_CONSTRAINT = "repo-constraints.txt"}\n'
    )
    runner, out = FakeRunner(), io.StringIO()
    run_ci_local(repo, runner=runner, environ={"UV_CONSTRAINT": "/x/c.txt"}, out=out)
    assert all(
        c["env"]["UV_CONSTRAINT"] == "repo-constraints.txt" for c in runner.calls
    )
    assert "ran without" not in out.getvalue()


def test_no_pin_note_when_no_pin_was_set(repo):
    out = io.StringIO()
    run_ci_local(repo, runner=FakeRunner(), environ={"HOME": "/h"}, out=out)
    assert "ran without" not in out.getvalue()


# --- publish -----------------------------------------------------------------------------


def _git_state(*, status="", origin_head="origin/master", branch="master", behind="0"):
    return [
        (["git", "status", "--porcelain"], RunResult(0, status)),
        (["git", "symbolic-ref"], RunResult(0, origin_head)),
        (["git", "branch", "--show-current"], RunResult(0, branch)),
        (["git", "rev-list", "--count"], RunResult(0, behind)),
    ]


def _assert_nothing_changed(runner):
    assert not [
        c for c in runner.calls if c["side_effect"] in (WRITES, UPLOADS, PUSHES)
    ]
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
    report = run_ci_local(
        repo, publish=True, runner=runner, environ={"PYPI_PASSWORD": TOKEN}, out=out
    )
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
        ([*VERSION_TOOL, "gen-semver"], RunResult(0, "Installed 3\n0.2.1\n")),
    )
    out = io.StringIO()
    report = run_ci_local(
        repo, publish=True, runner=runner, environ={"PYPI_PASSWORD": TOKEN}, out=out
    )
    assert report.ok, out.getvalue()
    upload = next(c for c in runner.calls if c["side_effect"] == UPLOADS)
    assert upload["argv"][:2] == ["uv", "publish"] and upload["argv"][2].endswith(
        "/dist/*"
    )
    assert upload["env"]["UV_PUBLISH_TOKEN"] == TOKEN
    others = [c for c in runner.calls if c is not upload]
    assert not any(TOKEN in c["env"].values() for c in others), (
        "only the upload step may see the PyPI token"
    )
    assert "PYPI_PASSWORD" not in upload["env"]
    argvs = runner.argvs()
    assert [*VERSION_TOOL, "update-pyproject-toml", "--version=0.2.1"] in argvs
    assert [
        "git",
        "commit",
        "--all",
        "-m",
        "**CI** Formatted code + Updated version to 0.2.1 [skip ci]",
    ] in argvs
    assert ["git", "tag", "-a", "0.2.1", "-m", "Release version 0.2.1"] in argvs
    assert argvs[-2:] == [
        ["git", "push", "origin", "master"],
        ["git", "push", "origin", "0.2.1"],
    ]
    rendered = out.getvalue()
    assert "Released 0.2.1" in rendered and "PyPI token from $PYPI_PASSWORD" in rendered
    assert TOKEN not in rendered, "the token is never printed"


def test_a_bad_version_stops_before_any_write(repo):
    runner = FakeRunner(*_git_state(), (list(VERSION_TOOL), RunResult(0, "oops\n")))
    report = run_ci_local(
        repo,
        publish=True,
        runner=runner,
        environ={"PYPI_PASSWORD": TOKEN},
        out=io.StringIO(),
    )
    assert report.failure.name == "bump version"
    assert not [c for c in runner.calls if c["side_effect"] in (UPLOADS, PUSHES)]


def test_a_failure_after_the_upload_says_how_to_finish(repo):
    runner = FakeRunner(
        *_git_state(),
        ([*VERSION_TOOL, "gen-semver"], RunResult(0, "0.2.1\n")),
        (["git", "push", "origin", "master"], RunResult(1)),
    )
    out = io.StringIO()
    run_ci_local(
        repo, publish=True, runner=runner, environ={"PYPI_PASSWORD": TOKEN}, out=out
    )
    assert "AFTER the upload: PyPI has 0.2.1" in out.getvalue()
    advice = out.getvalue().split("Finish by hand, in order:")[1]
    assert "  git push origin master\n  git push origin 0.2.1" in advice
    assert "git commit" not in advice, "the commit already happened"


def test_the_version_tool_brings_pip():
    """isee imports pip at load; a bare uvx environment has none (found on a real run)."""
    assert VERSION_TOOL[-1] == "isee" and "pip" in VERSION_TOOL


# --- credentials and the never-upload guard ----------------------------------------------


def test_token_precedence(isolated_home):
    pypirc = isolated_home / ".pypirc"
    pypirc.write_text("[pypi]\nusername = __token__\npassword = pypi-from-file\n")
    assert resolve_pypi_token(
        environ={"PYPI_PASSWORD": "a", "UV_PUBLISH_TOKEN": "b"}
    ) == ("a", "$PYPI_PASSWORD")
    assert resolve_pypi_token(environ={"UV_PUBLISH_TOKEN": "b"}) == (
        "b",
        "$UV_PUBLISH_TOKEN",
    )
    assert resolve_pypi_token(environ={}) == ("pypi-from-file", f"{pypirc} [pypi]")


def test_a_pypirc_password_that_is_not_a_token_is_not_used(isolated_home):
    (isolated_home / ".pypirc").write_text(
        "[pypi]\nusername = bob\npassword = hunter2\n"
    )
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

    code = cw.dispatch(
        _dispatch_funcs, ["ci-local", "--dry-run", "--repo", str(repo)], prog="wads"
    )
    assert code == 0
    assert "wads ci-local plan" in capsys.readouterr().out


def test_a_commit_failure_after_the_upload_lists_every_remaining_step(repo):
    runner = FakeRunner(
        *_git_state(),
        ([*VERSION_TOOL, "gen-semver"], RunResult(0, "0.2.1\n")),
        (["git", "commit"], RunResult(1)),
    )
    out = io.StringIO()
    run_ci_local(
        repo, publish=True, runner=runner, environ={"PYPI_PASSWORD": TOKEN}, out=out
    )
    advice = out.getvalue().split("Finish by hand, in order:")[1].splitlines()[1:5]
    assert advice == [
        "  git commit --all -m '**CI** Formatted code + Updated version to 0.2.1 [skip ci]'",
        "  git tag -a 0.2.1 -m 'Release version 0.2.1'",
        "  git push origin master",
        "  git push origin 0.2.1",
    ]


def test_an_upload_failure_warns_of_a_partial_upload_and_a_dirty_tree(repo):
    runner = FakeRunner(
        *_git_state(),
        ([*VERSION_TOOL, "gen-semver"], RunResult(0, "0.2.1\n")),
        (["uv", "publish"], RunResult(1)),
    )
    out = io.StringIO()
    run_ci_local(
        repo, publish=True, runner=runner, environ={"PYPI_PASSWORD": TOKEN}, out=out
    )
    text = out.getvalue()
    assert "may be PARTIAL" in text and "https://pypi.org/project/pkg/0.2.1/" in text
    assert "changed by: format (ruff), write version (pyproject.toml)" in text
    assert "git checkout -- ." in text
    assert "Nothing was uploaded" not in text


def test_a_failure_before_the_upload_says_nothing_went_up(repo):
    runner = FakeRunner(
        *_git_state(),
        ([*VERSION_TOOL, "gen-semver"], RunResult(0, "0.2.1\n")),
        (["uv", "build"], RunResult(1)),
    )
    out = io.StringIO()
    run_ci_local(
        repo, publish=True, runner=runner, environ={"PYPI_PASSWORD": TOKEN}, out=out
    )
    assert "Nothing was uploaded." in out.getvalue()
    assert "git checkout -- ." in out.getvalue()


def test_level_validate_contradicts_publish_and_deploy_is_publish(capsys):
    from wads.ci_local import ci_local

    with pytest.raises(SystemExit, match="contradicts"):
        ci_local(".", publish=True, level="validate", dry_run=True)
    with pytest.raises(SystemExit, match="--level must be"):
        ci_local(".", level="bogus", dry_run=True)
    ci_local(".", level="deploy", dry_run=True)
    assert "upload to PyPI" in capsys.readouterr().out


# --------------------------------------------------------------------------------------
# The work directory (issue #159)


def test_a_run_sweeps_workdirs_that_killed_runs_left(repo, tmp_path):
    root = tmp_path / "tmp"
    root.mkdir()
    stale = root / "wads-ci-local-killed"
    stale.mkdir()
    os.utime(stale, (0, 0))  # ancient, and no owner file: a pre-#159 leftover
    out = io.StringIO()
    report = run_ci_local(
        repo, runner=FakeRunner(), environ={}, out=out, workdir_root=str(root)
    )
    assert report.ok and not stale.exists()
    assert "Removed 1 stale wads-ci-local-* workdir(s)" in out.getvalue()
    assert list(root.iterdir()) == [], "this run's own workdir is cleaned up too"


def test_a_full_temp_filesystem_fails_before_any_command(repo, tmp_path, monkeypatch):
    monkeypatch.setattr(
        ci_local_module.shutil,
        "disk_usage",
        lambda path: type("Usage", (), {"free": 10**8})(),
    )
    runner = FakeRunner()
    report = run_ci_local(
        repo, runner=runner, environ={}, out=io.StringIO(), workdir_root=str(tmp_path)
    )
    assert not report.ok and report.failure.name == "temp space"
    assert "0.1 GB free" in report.outcomes[0][2]
    assert runner.calls == []


def _statvfs_reporting(monkeypatch, *, favail):
    """Make ``os.statvfs`` report ``favail`` free inodes (bytes stay real)."""
    real = os.statvfs

    class Stats:
        def __init__(self, path):
            self._real, self.f_files, self.f_favail = real(path), 10**6, favail

        def __getattr__(self, name):
            return getattr(self._real, name)

    monkeypatch.setattr(ci_local_module.os, "statvfs", Stats)


@pytest.mark.skipif(not hasattr(os, "statvfs"), reason="inodes are POSIX only")
def test_an_inode_shortfall_fails_before_any_command(repo, tmp_path, monkeypatch):
    _statvfs_reporting(monkeypatch, favail=5)
    runner = FakeRunner()
    report = run_ci_local(
        repo, runner=runner, environ={}, out=io.StringIO(), workdir_root=str(tmp_path)
    )
    assert not report.ok and report.failure.name == "temp space"
    assert "only 5 inodes free" in report.outcomes[0][2]
    assert runner.calls == []


def test_a_run_without_venvs_skips_the_temp_space_check(repo, monkeypatch):
    monkeypatch.setattr(ci_local_module, "_temp_space_step", None)  # never built
    config = _config(testing={"enabled": False})
    report = run_ci_local(
        repo, config=config, runner=FakeRunner(), environ={}, out=io.StringIO()
    )
    assert report.ok and "temp space" not in _names(s for s, *_ in report.outcomes)


def test_a_failing_sweep_does_not_stop_the_run(repo, monkeypatch):
    def broken_sweep(*args, **kwargs):
        raise PermissionError("denied")

    monkeypatch.setattr(ci_local_module, "sweep_stale_workdirs", broken_sweep)
    out = io.StringIO()
    report = run_ci_local(repo, runner=FakeRunner(), environ={}, out=out)
    assert report.ok
    assert "Note: skipped the stale workdir sweep (denied)" in out.getvalue()


def test_dry_run_header_names_the_sweep_and_the_space_needed():
    text = render_plan(plan_ci_local(".", config=_config()))
    assert (
        "A real run first removes stale wads-ci-local-* workdirs older than 6 h "
        "whose owner is gone, and requires about 2.0 GB / 200,000 inodes free."
    ) in text
    no_venvs = render_plan(
        plan_ci_local(".", config=_config(testing={"enabled": False}))
    )
    assert "whose owner is gone." in no_venvs and "requires" not in no_venvs


def test_a_corrupt_owner_file_is_judged_by_age(tmp_path):
    from wads.workdirs import OWNER_FILE, sweep_stale_workdirs

    for i, junk in enumerate(["99999999999999999999", "0", "-1", "x"]):
        d = tmp_path / f"wads-ci-local-{i}"
        d.mkdir()
        (d / OWNER_FILE).write_text(junk)
        os.utime(d, (0, 0))
    assert len(sweep_stale_workdirs("wads-ci-local-", root=str(tmp_path))) == 4


def test_the_dev_shell_s_python_path_settings_are_kept_out(repo):
    """Issue #194: PYTHONSAFEPATH=1 keeps the cwd off sys.path, which CI's
    `python -m pytest` puts on it; PYTHONPATH adds what CI does not have."""
    runner = FakeRunner()
    environ = {name: "1" for name in HOST_ONLY_VARS} | {"HOME": "/h"}
    run_ci_local(repo, runner=runner, environ=environ, out=io.StringIO())
    assert all(not set(HOST_ONLY_VARS) & c["env"].keys() for c in runner.calls)


def test_each_leg_s_tests_run_with_its_venv_activated(repo):
    """As run-tests-uv activates .venv: VIRTUAL_ENV and the venv's bin first on PATH."""
    runner = FakeRunner()
    run_ci_local(repo, runner=runner, environ={"PATH": "/usr/bin"}, out=io.StringIO())
    legs = [c for c in runner.calls if c["argv"][1:3] == ["-m", "pytest"]]
    assert len(legs) == 2  # 3.10 and 3.12, each in its own venv
    for tests in legs:
        venv = tests["env"]["VIRTUAL_ENV"]
        assert tests["argv"][0].startswith(venv)
        bin_dir = f"{venv}/Scripts" if os.name == "nt" else f"{venv}/bin"
        assert tests["env"]["PATH"].split(os.pathsep)[0] == bin_dir
        assert tests["env"]["PATH"].endswith("/usr/bin")
    # ...and only the test steps: installs keep the plain environment
    others = [c for c in runner.calls if c not in legs]
    assert all("VIRTUAL_ENV" not in c["env"] for c in others)


def test_an_empty_path_does_not_put_the_cwd_on_the_tests_path(repo):
    """On POSIX an empty PATH entry is the cwd: no trailing separator without a PATH."""
    runner = FakeRunner()
    run_ci_local(repo, runner=runner, environ={}, out=io.StringIO())
    legs = [c for c in runner.calls if c["argv"][1:3] == ["-m", "pytest"]]
    assert legs and all(not c["env"]["PATH"].endswith(os.pathsep) for c in legs)


# --------------------------------------------------------------------------------------
# npm components of a polyglot repo (issue #213)

NPM_NAMES = ["install", "lint", "test", "build"]
SINGLE = "i2mint/wads/.github/workflows/npm-ci.yml@master"
MONOREPO = "i2mint/wads/.github/workflows/npm-ci-monorepo.yml@master"


def _scaffold(root, profile, subdir=None, **ci):
    """A component as ``populate --frontend`` writes it: package.json + the CI stub.

    ``ci`` entries are merged into the scaffolded ``wads.ci`` block.
    """
    apply_frontend(str(root), profile=profile, project_name="pkg", subdir=subdir)
    directory = root / (subdir or {"js": "js", "ts": "ts"}.get(profile, "ts"))
    if ci:
        data = json.loads((directory / "package.json").read_text())
        data["wads"]["ci"].update(ci)
        (directory / "package.json").write_text(json.dumps(data))
    return directory


def _stub(root, name, uses, package_dir=None):
    """A hand-written caller stub, for the cases ``populate`` does not write."""
    workflows = root / ".github" / "workflows"
    workflows.mkdir(parents=True, exist_ok=True)
    with_ = f"    with:\n      package-dir: {package_dir}\n" if package_dir else ""
    (workflows / name).write_text(f"jobs:\n  npm-ci:\n    uses: {uses}\n{with_}")


def _package_json(directory, ci=None):
    directory.mkdir(parents=True, exist_ok=True)
    data = {"name": "x"} | ({"wads": {"ci": ci}} if ci is not None else {})
    (directory / "package.json").write_text(json.dumps(data))
    return directory


def _stub_package_dirs(root):
    """The ``package-dir`` of every wads caller, read straight from the stubs' YAML."""
    import yaml

    dirs = set()
    for path in (root / ".github" / "workflows").glob("*.yml"):
        for job in (yaml.safe_load(path.read_text()).get("jobs") or {}).values():
            if "i2mint/wads/.github/workflows/npm-ci" in str(job.get("uses", "")):
                dirs.add((job.get("with") or {}).get("package-dir"))
    return dirs


def _fake_tools(tmp_path, *names):
    """A PATH holding a stub per name that ``shutil.which`` resolves on any OS.

    Nothing runs them: the runner is fake.
    """
    bin_dir = tmp_path / "fake-bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    for name in names:
        tool = bin_dir / name
        tool.write_text("#!/bin/sh\n")
        tool.chmod(0o755)
        # On Windows `which` only finds a name with a PATHEXT extension.
        (bin_dir / f"{name}.cmd").write_text("@exit /b 0\r\n")
    return str(bin_dir)


def _npm_steps_of(steps):
    return [step for step in steps if step.name.startswith("npm")]


def _tree(root):
    return sorted(
        (str(p.relative_to(root)), p.read_bytes())
        for p in root.rglob("*")
        if p.is_file()
    )


def test_npm_components_are_the_stubs_ci_runs(tmp_path):
    _scaffold(tmp_path, "js")
    _scaffold(tmp_path, "ts")
    _scaffold(tmp_path, "ts-monorepo", subdir="web")
    _package_json(tmp_path / "other", {"subdir": "other"})  # wads.ci, but no stub
    (tmp_path / ".github/workflows/ci.yml").write_text(
        "jobs:\n  ci:\n    uses: i2mint/wads/.github/workflows/uv-ci.yml@master\n"
    )
    assert npm_components(tmp_path) == [
        NpmComponent("js", "npm-ci.yml", monorepo=False),
        NpmComponent("ts", "npm-ci-ts.yml", monorepo=False),
        NpmComponent("web", "npm-ci-web.yml", monorepo=True),
    ]
    assert {c.dir for c in npm_components(tmp_path)} == _stub_package_dirs(tmp_path)


def test_a_stub_without_package_dir_uses_the_reusable_workflow_s_default(tmp_path):
    _stub(tmp_path, "npm-ci.yml", SINGLE)
    _stub(tmp_path, "mono.yaml", MONOREPO)
    assert npm_components(tmp_path) == [
        NpmComponent(".", "mono.yaml", monorepo=True),
        NpmComponent("js", "npm-ci.yml", monorepo=False),
    ]


def _git_listing(repo, *, ignored=()):
    """What ``git ls-files --cached --others --exclude-standard -z`` would print for
    ``repo`` if ``.gitignore`` held ``ignored`` (repo-relative paths)."""
    names = sorted(
        p.relative_to(repo).as_posix()  # git prints POSIX paths on every OS
        for p in repo.rglob("*")
        if p.is_file() or p.is_symlink()
    )
    kept = [n for n in names if n not in ignored]
    return RunResult(0, "".join(f"{n}\0" for n in kept))


def _run_npm(
    repo, tmp_path, *, tools=("bash", "node", "npm"), ignored=(), responses=()
):
    """Run ci-local with fake tools and a git listing of ``repo``; keep the workdir.

    Returns ``(report, runner, output, copy)``, ``copy`` being the npm source dir.
    """
    runner = FakeRunner(
        *responses, (list(GIT_LS_FILES), _git_listing(repo, ignored=ignored))
    )
    out = io.StringIO()
    workdirs = tmp_path / "workdirs"
    workdirs.mkdir(parents=True, exist_ok=True)
    report = run_ci_local(
        repo,
        runner=runner,
        environ={"PATH": _fake_tools(tmp_path, *tools)},
        out=out,
        keep_workdir=True,
        workdir_root=str(workdirs),
    )
    [workdir] = workdirs.iterdir()
    return report, runner, out.getvalue(), workdir / "src"


def _npm_calls(runner):
    return [c for c in runner.calls if c["argv"][0] == "bash"]


def test_a_component_adds_the_npm_validate_job_before_the_build(tmp_path):
    _scaffold(tmp_path, "ts")
    steps = plan_ci_local(tmp_path, config=_config(), platform="posix")
    assert _names(steps)[-7:] == [
        "npm: copy the repo",
        "npm ts: config",
        *(f"npm ts: {kind}" for kind in NPM_NAMES),
        "build",
    ]
    by_name = {step.name: step for step in steps}
    for kind in NPM_NAMES:
        step = by_name[f"npm ts: {kind}"]
        # the command is read from the copy at run time, as CI reads its checkout
        assert step.argv == (*NPM_COMMAND_SHELL, f"<<npm0_{kind}>>")
        assert step.cwd == "<<workdir>>/src/ts", "never in the developer's tree"
        assert step.requires == ("bash", "node", "<<npm0_manager>>") and step.blocking
        assert not step.side_effect
    assert by_name["npm ts: lint"].display() == (
        "cd '<<workdir>>/src/ts' && bash -e -c '<<npm0_lint>>'"
    )


def test_npm_steps_run_in_a_copy_and_leave_the_tree_alone(repo, tmp_path):
    component = _scaffold(repo, "ts", lintCommand="npm run lint", testCommand="vitest")
    (component / "node_modules" / "dep").mkdir(parents=True)
    (component / "node_modules" / "dep" / "index.js").write_text("")
    (repo / "notes.txt").write_text("ignored")
    before = _tree(repo)
    # node_modules is not gitignored here: the copy still leaves it out
    report, runner, _, copy = _run_npm(repo, tmp_path, ignored=("notes.txt",))
    assert report.ok
    assert _tree(repo) == before, "the developer's tree is untouched"
    copied = sorted(
        p.relative_to(copy).as_posix() for p in copy.rglob("*") if p.is_file()
    )
    assert "ts/package.json" in copied and "pyproject.toml" in copied
    assert not [n for n in copied if "node_modules" in n or n == "notes.txt"]
    calls = _npm_calls(runner)
    assert [c["argv"][-1] for c in calls] == [
        "npm install",
        "npm run lint",
        "vitest",  # wads.ci wins over the default
        "npm run build --if-present",
    ]
    assert all(c["cwd"] == copy / "ts" for c in calls)


def test_a_gitignored_lockfile_is_not_in_the_copy_so_npm_installs(repo, tmp_path):
    """As in CI's checkout: a lockfile git ignores does not exist there (no EUSAGE)."""
    component = _scaffold(repo, "ts")
    (component / "package-lock.json").write_text("{}")
    _, tracked_runner, _, _ = _run_npm(repo, tmp_path / "tracked")
    assert _npm_calls(tracked_runner)[0]["argv"][-1] == "npm ci"
    _, ignored_runner, _, _ = _run_npm(
        repo, tmp_path / "ignored", ignored=("ts/package-lock.json",)
    )
    assert _npm_calls(ignored_runner)[0]["argv"][-1] == "npm install"


def test_a_gitignored_pnpm_lockfile_does_not_pick_pnpm(repo, tmp_path):
    component = _scaffold(repo, "ts", packageManager="")  # unset: auto-detect
    (component / "pnpm-lock.yaml").write_text("")
    report, runner, _, _ = _run_npm(
        repo, tmp_path, ignored=("ts/pnpm-lock.yaml",)
    )  # no pnpm on PATH, and none needed
    assert report.ok and _npm_calls(runner)[0]["argv"][-1] == "npm install"


@pytest.mark.skipif(
    os.name == "nt", reason="chmod cannot make a file unreadable on Windows"
)
@pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0, reason="root reads anything"
)
def test_a_file_that_cannot_be_copied_fails_the_step_not_the_run(repo, tmp_path):
    _scaffold(repo, "ts")
    secret = repo / "unreadable.txt"
    secret.write_text("x")
    secret.chmod(0)
    try:
        report, _, out, _ = _run_npm(repo, tmp_path)
    finally:
        secret.chmod(0o644)
    assert not report.ok and report.failure.name == "npm: copy the repo"
    assert "could not copy the repo for the npm components" in out


def test_outside_git_the_copy_is_the_tree_minus_node_modules(repo, tmp_path):
    component = _scaffold(repo, "ts")
    (component / "node_modules").mkdir()
    (component / "node_modules" / "x.js").write_text("")
    report, _, _, copy = _run_npm(
        repo, tmp_path, responses=[(list(GIT_LS_FILES), RunResult(128))]
    )
    assert report.ok and any("not a git checkout" in n for n in report.notes)
    assert (copy / "ts" / "package.json").is_file()
    assert not (copy / "ts" / "node_modules").exists()


def test_two_stubs_on_one_dir_validate_it_once(tmp_path):
    _scaffold(tmp_path, "ts")
    _stub(tmp_path, "npm-ci-ts-again.yml", SINGLE, package_dir="./ts/")
    assert len([c for c in npm_components(tmp_path) if c.dir == "ts"]) == 2
    steps = _npm_steps_of(plan_ci_local(tmp_path, config=_config()))
    assert _names(steps) == ["npm: copy the repo", "npm ts: config"] + [
        f"npm ts: {k}" for k in NPM_NAMES
    ]


def test_one_dir_called_as_single_and_as_monorepo_runs_both(tmp_path):
    _scaffold(tmp_path, "ts")
    _stub(tmp_path, "npm-ci-ts-mono.yml", MONOREPO, package_dir="ts")
    names = _names(_npm_steps_of(plan_ci_local(tmp_path, config=_config())))
    assert "npm ts (single): lint" in names and "npm ts (monorepo): lint" in names


def test_a_package_dir_expression_is_not_a_component(tmp_path):
    _stub(tmp_path, "npm-ci-x.yml", SINGLE, package_dir="${{ inputs.dir }}")
    assert npm_components(tmp_path) == []


def test_no_stub_or_npm_false_means_no_npm_step(tmp_path):
    _package_json(tmp_path / "ts", {"subdir": "ts"})  # wads.ci, but CI never runs it
    plain = plan_ci_local(tmp_path, config=_config(), platform="posix")
    assert not _npm_steps_of(plain)
    _scaffold(tmp_path, "ts")
    opted_out = plan_ci_local(tmp_path, config=_config(), platform="posix", npm=False)
    assert _names(opted_out) == _names(plain)


def test_publish_does_not_wait_on_the_npm_component(tmp_path):
    """As in CI: the PyPI publish job needs only the Python validation."""
    _scaffold(tmp_path, "ts")
    steps = plan_ci_local(tmp_path, publish=True, config=_config(), platform="posix")
    assert not _npm_steps_of(steps)


@pytest.mark.parametrize(
    "ci, files, manager, install",
    [
        ({}, (), "npm", "npm install"),
        ({}, ("package-lock.json",), "npm", "npm ci"),
        ({"packageManager": "npm"}, ("pnpm-lock.yaml",), "npm", "npm install"),
        ({}, ("pnpm-lock.yaml",), "pnpm", "pnpm install --frozen-lockfile"),
        ({"packageManager": "pnpm"}, (), "pnpm", "pnpm install --no-frozen-lockfile"),
        ({"packageManager": "yarn"}, (), "npm", "npm install"),
    ],
)
def test_the_package_manager_and_install_mirror_npm_ci(
    tmp_path, ci, files, manager, install
):
    directory = _package_json(tmp_path / "ts", ci)
    for name in files:
        (directory / name).write_text("")
    commands = npm_validate_commands(directory)
    assert (commands.package_manager, commands.install) == (manager, install)


def test_the_stub_s_workflow_decides_monorepo_not_the_files(repo, tmp_path):
    single = _package_json(repo / "a", {"buildCommand": ""})
    (single / "pnpm-workspace.yaml").write_text("")  # but called by npm-ci.yml
    _stub(repo, "npm-ci-a.yml", SINGLE, package_dir="a")
    _package_json(repo / "b", {})  # no pnpm-workspace.yaml, monorepo workflow
    _stub(repo, "npm-ci-b.yml", MONOREPO, package_dir="b")
    report, runner, _, copy = _run_npm(
        repo, tmp_path, tools=("bash", "node", "npm", "pnpm")
    )
    assert report.ok
    by_dir = {}
    for call in _npm_calls(runner):
        by_dir.setdefault(call["cwd"].name, []).append(call["argv"][-1])
    assert by_dir["a"] == [
        "npm install",
        "npm run lint --if-present",
        "npm test --if-present",
        "npm run build --if-present",  # "" means unset, as in CI
    ]
    assert by_dir["b"] == [
        "pnpm install --no-frozen-lockfile",
        "pnpm turbo run lint",
        "pnpm turbo run test",
        "pnpm turbo run build",
    ]


def test_an_invalid_wads_ci_block_fails_as_ci_s_setup_job_does(repo, tmp_path):
    _scaffold(repo, "ts", trigger={"mode": "sometimes"})
    report, _, out, _ = _run_npm(repo, tmp_path)
    assert not report.ok and report.failure.name == "npm ts: config"
    assert "npm-ci-ts.yml: wads.ci.trigger.mode must be one of" in out


def test_a_failing_npm_step_reads_as_red_ci(repo, tmp_path):
    _scaffold(repo, "ts", testCommand="vitest run")
    report, runner, _, _ = _run_npm(
        repo, tmp_path, responses=[([*NPM_COMMAND_SHELL, "vitest run"], RunResult(1))]
    )
    assert not report.ok and report.failure.name == "npm ts: test"
    assert not runner.ran("uv", "build")


def test_a_missing_package_manager_fails_the_gate_with_a_hint(repo, tmp_path):
    _scaffold(repo, "ts", packageManager="pnpm")
    report, runner, out, _ = _run_npm(repo, tmp_path)  # bash, node, npm: no pnpm
    assert not report.ok and report.failure.name == "npm ts: install"
    assert not _npm_calls(runner), "nothing ran"
    assert not runner.ran("uv", "build")
    assert "pnpm not on PATH: install pnpm: https://pnpm.io/installation" in out


def test_the_steps_path_decides_not_the_developer_s(repo, tmp_path):
    """An empty PATH for the steps finds no tools, even if the host has them."""
    _scaffold(repo, "ts")
    report, _, _, _ = _run_npm(repo, tmp_path, tools=())
    assert not report.ok and report.failure.name == "npm ts: install"


def test_npm_false_runs_no_npm_step(repo):
    _scaffold(repo, "ts")
    runner = FakeRunner()
    report = run_ci_local(repo, runner=runner, environ={}, out=io.StringIO(), npm=False)
    assert report.ok and not _npm_steps_of(s for s, _, _ in report.outcomes)
    assert not runner.ran(*GIT_LS_FILES)


def test_the_npm_semantics_match_the_reusable_workflows():
    """npm-ci.yml / npm-ci-monorepo.yml are the SSOT: pin the mirrored strings."""
    workflows = REPO_ROOT / ".github" / "workflows"
    single = (workflows / "npm-ci.yml").read_text()
    monorepo = (workflows / "npm-ci-monorepo.yml").read_text()
    for text in (
        "npm ci || npm install",  # ci-local takes the branch up front, by lockfile
        "pnpm install --frozen-lockfile",
        "pnpm install --no-frozen-lockfile",
        "fs.existsSync('pnpm-lock.yaml') ? 'pnpm' : 'npm'",
    ):
        assert text in single
    assert "pnpm install --frozen-lockfile" in monorepo
    assert "pnpm install --no-frozen-lockfile" in monorepo
    for key, default in NPM_CI_DEFAULTS.items():
        if key.endswith("Command"):
            assert f"ci.{key} || '{default}'" in single
    for key, default in NPM_MONOREPO_COMMAND_DEFAULTS.items():
        if key.endswith("Command"):
            assert f"ci.{key} || '{default}'" in monorepo
    # No `shell:` anywhere, so every `run:` step is Actions' default `bash -e {0}`.
    assert NPM_COMMAND_SHELL == ("bash", "-e", "-c")
    assert "shell:" not in single and "shell:" not in monorepo


def test_windows_bash_must_not_be_the_wsl_launcher():
    def which(tool, path):
        return {"bash": r"C:\Windows\System32\bash.exe"}.get(
            tool, rf"C:\bin\{tool}.exe"
        )

    [problem] = tool_problems(
        ["bash", "node"], {"PATH": "x"}, platform="nt", which=which
    )
    assert "WSL launcher" in problem and "gitforwindows.org" in problem
    assert tool_problems(["bash"], {"PATH": "x"}, platform="posix", which=which) == []

    def git_bash(tool, path):
        return r"C:\Program Files\Git\bin\bash.exe"

    assert tool_problems(["bash"], {"PATH": "x"}, platform="nt", which=git_bash) == []


def test_the_cli_takes_no_npm(repo, capsys):
    _scaffold(repo, "ts")
    ci_local(str(repo), dry_run=True)
    assert "npm ts: lint" in capsys.readouterr().out
    ci_local(str(repo), dry_run=True, no_npm=True)
    assert "npm" not in capsys.readouterr().out.replace("npm-", "")
    cw = pytest.importorskip("cw")
    from wads.__main__ import _dispatch_funcs

    args = ["ci-local", "--dry-run", "--no-npm", "--repo", str(repo)]
    assert cw.dispatch(_dispatch_funcs, args, prog="wads") == 0
    assert "npm ts:" not in capsys.readouterr().out
