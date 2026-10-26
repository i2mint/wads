"""Tests for retry-with-backoff of failed install commands in ``wads.install_system_deps``.

``apt-get install ffmpeg`` on a hosted runner flakes on mirror timeouts; raising the
timeout does not cure that, so a failed command is retried before the dependency is
declared failed (issue #146).
"""

import subprocess
import textwrap

import pytest

from wads.install_system_deps import (
    DFLT_INSTALL_BACKOFF,
    DFLT_INSTALL_RETRIES,
    install_dependency,
    install_system_dependencies,
)


class _Flaky:
    """``subprocess.run`` stand-in: per-command queue of outcomes (int rc or 'timeout')."""

    def __init__(self, outcomes):
        self.outcomes = {cmd: list(seq) for cmd, seq in outcomes.items()}
        self.calls = []

    def __call__(self, cmd, **kwargs):
        self.calls.append(cmd)
        seq = self.outcomes.get(cmd, [0])
        outcome = seq.pop(0) if len(seq) > 1 else seq[0]
        if outcome == "timeout":
            raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout"))
        return subprocess.CompletedProcess(cmd, outcome)


@pytest.fixture
def waits():
    return []


def _install(monkeypatch, waits, outcomes, cmds, **kw):
    flaky = _Flaky(outcomes)
    monkeypatch.setattr("wads.install_system_deps.subprocess.run", flaky)
    result = install_dependency("d", cmds, sleep=waits.append, **kw)
    return result, flaky


def test_defaults_are_pinned():
    assert (DFLT_INSTALL_RETRIES, DFLT_INSTALL_BACKOFF) == (2, 5)


def test_flaky_command_succeeds_after_retries_with_doubling_backoff(
    monkeypatch, waits
):
    (ok, err), flaky = _install(
        monkeypatch, waits, {"apt": ["timeout", 100, 0]}, ["apt"]
    )
    assert ok and err is None
    assert flaky.calls == ["apt"] * 3
    assert waits == [5, 10]


def test_persistent_failure_reports_last_error_after_all_attempts(monkeypatch, waits):
    (ok, err), flaky = _install(monkeypatch, waits, {"apt": [7]}, ["apt"], retries=1)
    assert not ok and err == "Exit code 7"
    assert len(flaky.calls) == 2


def test_retries_zero_disables_retrying(monkeypatch, waits):
    (ok, _), flaky = _install(monkeypatch, waits, {"apt": [1]}, ["apt"], retries=0)
    assert not ok and flaky.calls == ["apt"] and waits == []


def test_only_the_failed_command_is_retried(monkeypatch, waits):
    (ok, _), flaky = _install(
        monkeypatch, waits, {"install": [1, 0]}, ["update", "install"]
    )
    assert ok
    assert flaky.calls == ["update", "install", "install"]


def test_timeout_error_still_names_the_command(monkeypatch, waits):
    (ok, err), _ = _install(
        monkeypatch, waits, {"slow": ["timeout"]}, ["slow"], retries=1, timeout=3
    )
    assert not ok and "Timeout after 3s running: slow" in err


def _write_pyproject(tmp_path, extra=""):
    (tmp_path / "pyproject.toml").write_text(
        textwrap.dedent(
            f"""
            [project]
            name = "demo"
            version = "0.0.1"

            [tool.wads.ops.dep]
            {extra}
            install.linux = ["flaky"]
            """
        )
    )


@pytest.mark.parametrize(
    "extra, kwargs, expected_calls",
    [
        ("", {}, 3),
        ("install_retries = 0", {}, 1),
        ("install_retries = 4", {"default_install_retries": 0}, 5),
        ("", {"default_install_retries": 1}, 2),
        ("install_retries = -1", {}, 3),  # invalid: ignored, default used
        ("install_retries = true", {}, 3),
    ],
)
def test_retries_resolution(tmp_path, monkeypatch, extra, kwargs, expected_calls):
    _write_pyproject(tmp_path, extra)
    flaky = _Flaky({"flaky": [1]})
    monkeypatch.setattr("wads.install_system_deps.subprocess.run", flaky)
    monkeypatch.setattr("wads.install_system_deps.time.sleep", lambda s: None)
    _, _, failed = install_system_dependencies(
        str(tmp_path), platform="linux", skip_check=True, verbose=False, **kwargs
    )
    assert failed == 1
    assert len(flaky.calls) == expected_calls


def test_cli_install_retries_flag(tmp_path, monkeypatch):
    from wads import install_system_deps as mod

    _write_pyproject(tmp_path)
    flaky = _Flaky({"flaky": [1]})
    monkeypatch.setattr("wads.install_system_deps.subprocess.run", flaky)
    monkeypatch.setattr("wads.install_system_deps.time.sleep", lambda s: None)
    monkeypatch.setattr(
        "sys.argv",
        ["x", str(tmp_path), "--platform", "linux", "--skip-check", "--quiet",
         "--install-retries", "0"],
    )
    with pytest.raises(SystemExit) as e:
        mod.main()
    assert e.value.code == 1 and len(flaky.calls) == 1
