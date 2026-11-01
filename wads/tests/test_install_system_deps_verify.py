"""Tests for post-install verification in ``wads.install_system_deps`` (issue #162).

Chocolatey printed ``installed 0/0 packages`` and exited 0 when its feed returned a
504, so the Windows job ran its tests without ffmpeg. An install is now confirmed by
re-running the dependency's declared ``check.<platform>``.
"""

import textwrap

import pytest

from wads import install_system_deps as mod
from wads.install_system_deps import (
    DFLT_VERIFY_RETRIES,
    install_and_verify,
    install_system_dependencies,
)


class _Recorder:
    """Stand-in for ``install_dependency`` / ``check_if_installed`` with scripted results."""

    def __init__(self, results):
        self.results = list(results)
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        return self.results.pop(0) if len(self.results) > 1 else self.results[0]


def _verify(install_results, check_results, check_cmds="where ffmpeg", **kw):
    install = _Recorder(install_results)
    is_installed = _Recorder(check_results)
    result = install_and_verify(
        "ffmpeg",
        "choco install ffmpeg -y",
        check_cmds,
        install=install,
        is_installed=is_installed,
        **kw,
    )
    return result, install, is_installed


def test_default_is_pinned():
    assert DFLT_VERIFY_RETRIES == 1


def test_verified_install_succeeds_without_reinstalling():
    (ok, err), install, check = _verify([(True, None)], [True])
    assert ok and err is None
    assert (install.calls, check.calls) == (1, 1)


def test_silent_failure_is_reinstalled_then_reported():
    (ok, err), install, check = _verify([(True, None)], [False])
    assert not ok
    assert "exited 0 but the check still fails" in err and "where ffmpeg" in err
    assert install.calls == check.calls == 1 + DFLT_VERIFY_RETRIES


def test_reinstall_that_takes_succeeds():
    (ok, _), install, _ = _verify([(True, None)], [False, True])
    assert ok and install.calls == 2


def test_verify_retries_zero_fails_at_once():
    (ok, _), install, _ = _verify([(True, None)], [False], verify_retries=0)
    assert not ok and install.calls == 1


def test_failed_install_is_not_checked_nor_repeated():
    # The install's own per-command retries already ran; no second round.
    (ok, err), install, check = _verify([(False, "Exit code 1")], [True])
    assert (ok, err) == (False, "Exit code 1")
    assert (install.calls, check.calls) == (1, 0)


@pytest.mark.parametrize("check_cmds", [None, "", []])
def test_no_check_declared_trusts_the_exit_status(check_cmds):
    (ok, _), _, check = _verify([(True, None)], [False], check_cmds=check_cmds)
    assert ok and check.calls == 0


def test_negative_verify_retries_is_rejected():
    with pytest.raises(ValueError):
        _verify([(True, None)], [True], verify_retries=-1)


def _write_pyproject(tmp_path, extra=""):
    (tmp_path / "pyproject.toml").write_text(
        textwrap.dedent(
            f"""
            [project]
            name = "demo"
            version = "0.0.1"

            [tool.wads.ops.ffmpeg]
            check.windows = "where ffmpeg"
            install.windows = "choco install ffmpeg -y"
            {extra}
            """
        )
    )


def _run(tmp_path, monkeypatch, *, check_passes, extra=""):
    """End to end on 'windows', with the install exiting 0 and the check scripted."""
    _write_pyproject(tmp_path, extra)
    installs = _Recorder([(True, None)])
    # Inject the install and the check through install_and_verify's own seams.
    monkeypatch.setattr(
        mod,
        "install_and_verify",
        lambda *a, **k: install_and_verify(
            *a, install=installs, is_installed=lambda *_: check_passes, **k
        ),
    )
    counts = install_system_dependencies(
        str(tmp_path), platform="windows", skip_check=True, verbose=False
    )
    return counts, installs


def test_choco_silent_failure_counts_as_failed(tmp_path, monkeypatch):
    (installed, _, failed), installs = _run(tmp_path, monkeypatch, check_passes=False)
    assert (installed, failed) == (0, 1)
    assert installs.calls == 1 + DFLT_VERIFY_RETRIES


def test_verified_install_counts_as_installed(tmp_path, monkeypatch):
    (installed, _, failed), _ = _run(tmp_path, monkeypatch, check_passes=True)
    assert (installed, failed) == (1, 0)


def test_verify_install_false_opts_out(tmp_path, monkeypatch):
    (installed, _, failed), installs = _run(
        tmp_path, monkeypatch, check_passes=False, extra="verify_install = false"
    )
    assert (installed, failed) == (1, 0)
    assert installs.calls == 1


def test_cli_exits_nonzero_on_silent_failure(tmp_path, monkeypatch):
    _write_pyproject(tmp_path)
    monkeypatch.setattr(
        mod,
        "install_and_verify",
        lambda *a, **k: install_and_verify(
            *a,
            install=lambda *_, **__: (True, None),
            is_installed=lambda *_: False,
            **k,
        ),
    )
    monkeypatch.setattr(
        "sys.argv",
        ["x", str(tmp_path), "--platform", "windows", "--skip-check", "--quiet"],
    )
    with pytest.raises(SystemExit) as exc:
        mod.main()
    assert exc.value.code == 1
