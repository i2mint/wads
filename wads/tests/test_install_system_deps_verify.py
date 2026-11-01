"""Tests for post-install verification in ``wads.install_system_deps`` (issue #162).

Chocolatey printed ``installed 0/0 packages`` and exited 0 when its feed returned a
504, so the Windows job ran its tests without ffmpeg. An install is now confirmed by
re-running the dependency's declared ``check.<platform>``.
"""

import textwrap

import pytest

from wads import install_system_deps as mod
from wads.install_system_deps import (
    DFLT_INSTALL_BACKOFF,
    DFLT_VERIFY_RETRIES,
    install_and_verify,
    install_system_dependencies,
)


class _Recorder:
    """Stand-in for ``install_dependency`` / ``check_if_installed`` with scripted results.

    Pops one result per call, repeating the last; records each call's command spec.
    """

    def __init__(self, results):
        self.results = list(results)
        self.cmds = []

    @property
    def calls(self):
        return len(self.cmds)

    def __call__(self, dep_name, cmds, *args, **kwargs):
        self.cmds.append(cmds)
        return self.results.pop(0) if len(self.results) > 1 else self.results[0]


def _verify(install_results, check_results, check_cmds="where ffmpeg", **kw):
    install = _Recorder(install_results)
    is_installed = _Recorder(check_results)
    waits = []
    result = install_and_verify(
        "ffmpeg",
        "choco install ffmpeg -y",
        check_cmds,
        install=install,
        is_installed=is_installed,
        sleep=waits.append,
        **kw,
    )
    return result, install, is_installed, waits


def test_verified_install_succeeds_without_reinstalling():
    (ok, err), install, check, waits = _verify([(True, None)], [True])
    assert ok and err is None
    assert (install.calls, check.calls, waits) == (1, 1, [])


def test_silent_failure_is_reinstalled_after_backoff_then_reported():
    (ok, err), install, check, waits = _verify([(True, None)], [False])
    assert not ok
    assert "exited 0 but the check still fails" in err and "where ffmpeg" in err
    assert install.calls == check.calls == 1 + DFLT_VERIFY_RETRIES
    assert waits == [DFLT_INSTALL_BACKOFF]


def test_reinstall_backoff_doubles():
    *_, waits = _verify([(True, None)], [False], verify_retries=3, backoff=2)
    assert waits == [2, 4, 8]


def test_reinstall_that_takes_succeeds():
    (ok, _), install, _, _ = _verify([(True, None)], [False, True])
    assert ok and install.calls == 2


def test_verify_retries_zero_fails_at_once():
    (ok, _), install, _, waits = _verify([(True, None)], [False], verify_retries=0)
    assert not ok and install.calls == 1 and waits == []


def test_failed_install_is_not_checked_nor_repeated():
    # The install's own per-command retries already ran; no second round.
    (ok, err), install, check, _ = _verify([(False, "Exit code 1")], [True])
    assert (ok, err) == (False, "Exit code 1")
    assert (install.calls, check.calls) == (1, 0)


@pytest.mark.parametrize("check_cmds", [None, "", "   ", [], [""], [[]], ["  ", []]])
def test_blank_check_is_no_check(check_cmds):
    (ok, _), _, check, _ = _verify([(True, None)], [False], check_cmds=check_cmds)
    assert ok and check.calls == 0


def test_negative_verify_retries_is_rejected():
    with pytest.raises(ValueError):
        _verify([(True, None)], [True], verify_retries=-1)


@pytest.mark.parametrize(
    "os_name, expected",
    [("posix", "dpkg -s 'my pkg'"), ("nt", 'dpkg -s "my pkg"')],
)
def test_argv_form_is_quoted_for_the_platform_shell(monkeypatch, os_name, expected):
    monkeypatch.setattr(mod.os, "name", os_name)
    assert mod._as_commands([["dpkg", "-s", "my pkg"]]) == [expected]


# --- end to end through install_system_dependencies' install/is_installed seams ----


def _write_pyproject(tmp_path, body):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.0.1"\n\n' + textwrap.dedent(body)
    )


_FFMPEG = """
    [tool.wads.ops.ffmpeg]
    check.windows = "where ffmpeg"
    install.windows = "choco install ffmpeg -y"
"""


def _run(tmp_path, monkeypatch, *, checks, body=_FFMPEG, skip_check=True, **kw):
    """On 'windows', with the install exiting 0 and the check results scripted."""
    _write_pyproject(tmp_path, body)
    waits = []
    monkeypatch.setattr(mod.time, "sleep", waits.append)
    install = _Recorder([(True, None)])
    is_installed = _Recorder(checks)
    counts = install_system_dependencies(
        str(tmp_path),
        platform="windows",
        skip_check=skip_check,
        install=install,
        is_installed=is_installed,
        **{"verbose": False, **kw},
    )
    return counts, install, is_installed, waits


def test_choco_silent_failure_counts_as_failed(tmp_path, monkeypatch):
    (installed, _, failed), install, _, waits = _run(
        tmp_path, monkeypatch, checks=[False]
    )
    assert (installed, failed) == (0, 1)
    assert install.calls == 1 + DFLT_VERIFY_RETRIES
    assert waits == [DFLT_INSTALL_BACKOFF]


@pytest.mark.parametrize(
    "checks, counts, install_calls",
    [
        ([False, True], (1, 0, 0), 1),  # pre-check fails, verify passes
        ([False, False, False], (0, 0, 1), 2),  # verify fails: re-install, then fail
        ([True], (0, 1, 0), 0),  # already present
    ],
)
def test_default_ci_path_prechecks_then_verifies(
    tmp_path, monkeypatch, checks, counts, install_calls
):
    got, install, _, _ = _run(tmp_path, monkeypatch, checks=checks, skip_check=False)
    assert got == counts and install.calls == install_calls


def test_verify_install_false_opts_out(tmp_path, monkeypatch):
    body = _FFMPEG + "    verify_install = false\n"
    (installed, _, failed), install, check, _ = _run(
        tmp_path, monkeypatch, checks=[False], body=body
    )
    assert (installed, failed) == (1, 0)
    assert (install.calls, check.calls) == (1, 0)


def test_non_bool_verify_install_warns_and_verifies(tmp_path, monkeypatch, capsys):
    body = _FFMPEG + '    verify_install = "no"\n'
    (_, _, failed), _, check, _ = _run(
        tmp_path, monkeypatch, checks=[False], body=body, verbose=True
    )
    assert failed == 1 and check.calls == 1 + DFLT_VERIFY_RETRIES
    assert "invalid verify_install='no'" in capsys.readouterr().err


def test_argv_check_is_joined_for_precheck_and_verify(tmp_path, monkeypatch):
    # The i2mint/odbcdol form; it used to run `sh -c dpkg`, which always fails.
    body = """
        [tool.wads.ops.unixodbc]
        check.windows = [["dpkg", "-s", "unixodbc"], ["rpm", "-q", "unixODBC"]]
        install.windows = "choco install unixodbc -y"
    """
    _, _, check, _ = _run(
        tmp_path, monkeypatch, checks=[False, True], body=body, skip_check=False
    )
    joined = ["dpkg -s unixodbc", "rpm -q unixODBC"]
    assert check.cmds == [joined, joined]


def test_argv_install_runs_joined_commands(tmp_path, monkeypatch):
    # Through the real install_dependency: a list-of-lists install used to crash.
    _write_pyproject(
        tmp_path,
        """
        [tool.wads.ops.x]
        install.linux = [["echo", "a"], "echo b"]
        """,
    )
    ran = []
    monkeypatch.setattr(
        mod,
        "_run_shell",
        lambda cmd, **_: ran.append(cmd) or mod.subprocess.CompletedProcess(cmd, 0),
    )
    installed, _, failed = install_system_dependencies(
        str(tmp_path), platform="linux", skip_check=True, verbose=False
    )
    assert (installed, failed) == (1, 0) and ran == ["echo a", "echo b"]


def test_top_level_string_check_is_ignored_not_a_crash(tmp_path, monkeypatch):
    body = """
        [tool.wads.ops.ffmpeg]
        check = "where ffmpeg"
        install.windows = "choco install ffmpeg -y"
    """
    (installed, _, failed), _, check, _ = _run(
        tmp_path, monkeypatch, checks=[False], body=body, skip_check=False
    )
    assert (installed, failed, check.calls) == (1, 0, 0)


def test_unverified_deps_are_listed_once_in_the_summary(tmp_path, monkeypatch, capsys):
    body = """
        [tool.wads.ops.a]
        install.windows = "x"
        [tool.wads.ops.b]
        check.windows = "   "
        install.windows = "y"
    """
    _run(tmp_path, monkeypatch, checks=[False], body=body, verbose=True)
    out = capsys.readouterr().out
    assert out.count("Not verified (no check.windows): a, b") == 1
    assert "no check.windows declared" not in out


def test_cli_exits_nonzero_on_silent_failure(tmp_path, monkeypatch):
    _write_pyproject(tmp_path, _FFMPEG)
    monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    # main() passes no seams, so the module-level functions are looked up at call time
    monkeypatch.setattr(mod, "install_dependency", lambda *_, **__: (True, None))
    monkeypatch.setattr(mod, "check_if_installed", lambda *_, **__: False)
    monkeypatch.setattr(
        "sys.argv",
        ["x", str(tmp_path), "--platform", "windows", "--skip-check", "--quiet"],
    )
    with pytest.raises(SystemExit) as exc:
        mod.main()
    assert exc.value.code == 1


def test_non_table_install_fails_instead_of_passing_silently(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.0.1"\n\n'
        '[tool.wads.ops.ffmpeg]\ninstall = "sudo apt-get install -y ffmpeg"\n'
    )
    calls = []
    counts = install_system_dependencies(
        str(tmp_path),
        platform="linux",
        verbose=False,
        install=lambda *a, **k: calls.append(a) or (True, None),
        is_installed=lambda *a: False,
    )
    assert counts == (0, 0, 1) and calls == []
