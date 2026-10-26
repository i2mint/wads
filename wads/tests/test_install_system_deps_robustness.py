"""Install robustness: process-group kill on timeout, apt lock wait, up-front validation."""

import subprocess
import sys
import textwrap
import time

import pytest

from wads.install_system_deps import (
    DFLT_INSTALL_TIMEOUT,
    SLOW_DEP_INSTALL_TIMEOUTS,
    _run_shell,
    install_dependency,
    install_system_dependencies,
    with_apt_lock_timeout,
)


@pytest.mark.skipif(sys.platform == "win32", reason="process groups are POSIX")
def test_timeout_kills_grandchildren(tmp_path):
    marker = tmp_path / "survivor"
    # the background grandchild would create the marker if it outlived the timeout
    cmd = f"(sleep 2; touch {marker}) & sleep 30"
    with pytest.raises(subprocess.TimeoutExpired):
        _run_shell(cmd, timeout=0.5)
    time.sleep(2.5)
    assert not marker.exists()


@pytest.mark.skipif(sys.platform == "win32", reason="process groups are POSIX")
def test_interrupt_kills_the_group(tmp_path, monkeypatch):
    marker = tmp_path / "survivor"

    def interrupted(self, timeout=None):
        raise KeyboardInterrupt

    monkeypatch.setattr(subprocess.Popen, "communicate", interrupted)
    with pytest.raises(KeyboardInterrupt):
        _run_shell(f"(sleep 2; touch {marker}) & sleep 30", timeout=5)
    time.sleep(2.5)
    assert not marker.exists()


def test_install_dependency_runs_the_apt_flagged_command(monkeypatch):
    seen = []

    def fake(cmd, *, timeout):
        seen.append(cmd)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr("wads.install_system_deps._run_shell", fake)
    install_dependency("x", "sudo apt-get install -y x", apt_lock_timeout=7)
    assert seen == ["sudo apt-get -o DPkg::Lock::Timeout=7 install -y x"]


@pytest.mark.parametrize(
    "cmd, expected",
    [
        ("apt-get update", "apt-get -o DPkg::Lock::Timeout=9 update"),
        (
            "sudo apt install -y apt-utils",
            "sudo apt -o DPkg::Lock::Timeout=9 install -y apt-utils",
        ),
        (
            "sudo DEBIAN_FRONTEND=noninteractive apt-get install -y x",
            "sudo DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=9 install -y x",
        ),
        (
            "apt-get update\nsudo -u root apt-get install x",
            "apt-get -o DPkg::Lock::Timeout=9 update\nsudo -u root apt-get -o DPkg::Lock::Timeout=9 install x",
        ),
        ("(env A=1 apt-get update)", "(env A=1 apt-get -o DPkg::Lock::Timeout=9 update)"),
        ("dpkg -s apt-get", "dpkg -s apt-get"),
        ("brew install apt", "brew install apt"),
        (
            "apt-get -o DPkg::Lock::Timeout=1 update",
            "apt-get -o DPkg::Lock::Timeout=1 update",
        ),
    ],
)
def test_with_apt_lock_timeout(cmd, expected):
    assert with_apt_lock_timeout(cmd, 9) == expected


def test_apt_lock_timeout_disabled():
    assert with_apt_lock_timeout("apt-get update", None) == "apt-get update"


@pytest.mark.parametrize(
    "kwargs",
    [{"default_install_retries": -1}, {"default_install_timeout": 0}, {"apt_lock_timeout": -1}],
)
def test_invalid_defaults_fail_before_any_work(tmp_path, capsys, kwargs):
    with pytest.raises(ValueError):
        install_system_dependencies(str(tmp_path), **kwargs)
    assert capsys.readouterr().out == ""


def test_cli_rejects_non_positive_timeout(monkeypatch, tmp_path):
    from wads.install_system_deps import main

    monkeypatch.setattr("sys.argv", ["x", str(tmp_path), "--install-timeout", "0"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2


def test_ffmpeg_gets_longer_default_timeout(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text(
        textwrap.dedent(
            """
            [project]
            name = "demo"
            version = "0.0.1"

            [tool.wads.ops.ffmpeg]
            install.linux = "echo hi"
            [tool.wads.ops.other]
            install.linux = "echo there"
            """
        )
    )
    seen = {}

    def fake(cmd, *, timeout):
        seen[cmd] = timeout
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr("wads.install_system_deps._run_shell", fake)
    install_system_dependencies(str(tmp_path), platform="linux", skip_check=True)
    assert seen == {
        "echo hi": SLOW_DEP_INSTALL_TIMEOUTS["ffmpeg"],
        "echo there": DFLT_INSTALL_TIMEOUT,
    }
