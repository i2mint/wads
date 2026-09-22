"""Tests for the per-dependency install timeout of ``wads.install_system_deps``.

The install timeout used to be a hardcoded 300s that no consumer layer could
reach: not ``pyproject.toml``, not the CLI, not the ``install-system-deps``
action. A slow-but-healthy install (ffmpeg on a cold GitHub runner) therefore
failed a CI run with no way to raise the ceiling short of editing wads itself.

These tests pin the new ``[tool.wads.ops.<dep>] install_timeout`` key, the
``default_install_timeout`` argument that backs it, and the fact that the
default stays at :data:`wads.install_system_deps.DFLT_INSTALL_TIMEOUT`.
"""

import subprocess
import textwrap
from pathlib import Path

import pytest

from wads.install_system_deps import (
    DFLT_INSTALL_TIMEOUT,
    install_dependency,
    install_system_dependencies,
)


class _RunRecorder:
    """Stand-in for ``subprocess.run`` that records ``(cmd, timeout)`` pairs."""

    def __init__(self):
        self.calls = []

    def __call__(self, cmd, **kwargs):
        self.calls.append((cmd, kwargs.get("timeout")))
        return subprocess.CompletedProcess(args=cmd, returncode=0)

    @property
    def timeouts(self):
        return {timeout for _cmd, timeout in self.calls}


def _write_pyproject(tmp_path: Path, *, extra_dep_lines: str = "") -> Path:
    """Write a pyproject.toml declaring one two-command linux system dep."""
    content = textwrap.dedent(
        f"""
        [project]
        name = "demo"
        version = "0.0.1"

        [tool.wads.ops.slowdep]
        description = "A dependency that takes its time"
        {extra_dep_lines}
        install.linux = ["echo one", "echo two"]
        """
    )
    (tmp_path / "pyproject.toml").write_text(content)
    return tmp_path


def test_declared_install_timeout_is_honoured(tmp_path, monkeypatch):
    """An ``install_timeout`` under [tool.wads.ops.<dep>] reaches subprocess.run."""
    _write_pyproject(tmp_path, extra_dep_lines="install_timeout = 600")
    recorder = _RunRecorder()
    monkeypatch.setattr("wads.install_system_deps.subprocess.run", recorder)

    installed, skipped, failed = install_system_dependencies(
        str(tmp_path), platform="linux", skip_check=True, verbose=False
    )

    assert (installed, skipped, failed) == (1, 0, 0)
    assert recorder.timeouts == {600}, (
        f"declared install_timeout=600 not honoured; saw {recorder.timeouts}"
    )


def test_undeclared_install_timeout_keeps_the_default(tmp_path, monkeypatch):
    """With no declaration, the timeout stays at today's default (300s)."""
    _write_pyproject(tmp_path)
    recorder = _RunRecorder()
    monkeypatch.setattr("wads.install_system_deps.subprocess.run", recorder)

    install_system_dependencies(
        str(tmp_path), platform="linux", skip_check=True, verbose=False
    )

    assert recorder.timeouts == {DFLT_INSTALL_TIMEOUT}
    assert DFLT_INSTALL_TIMEOUT == 300


def test_default_install_timeout_argument_overrides_the_constant(
    tmp_path, monkeypatch
):
    """``default_install_timeout`` applies to deps that declare no timeout."""
    _write_pyproject(tmp_path)
    recorder = _RunRecorder()
    monkeypatch.setattr("wads.install_system_deps.subprocess.run", recorder)

    install_system_dependencies(
        str(tmp_path),
        platform="linux",
        skip_check=True,
        verbose=False,
        default_install_timeout=900,
    )

    assert recorder.timeouts == {900}


def test_declared_timeout_wins_over_default_install_timeout(tmp_path, monkeypatch):
    """A per-dep declaration beats the caller-wide default."""
    _write_pyproject(tmp_path, extra_dep_lines="install_timeout = 42")
    recorder = _RunRecorder()
    monkeypatch.setattr("wads.install_system_deps.subprocess.run", recorder)

    install_system_dependencies(
        str(tmp_path),
        platform="linux",
        skip_check=True,
        verbose=False,
        default_install_timeout=900,
    )

    assert recorder.timeouts == {42}


def test_timeout_message_names_the_command_that_stalled():
    """A multi-command install must say WHICH command hit the wall."""
    success, error = install_dependency("demo", ["echo first", "sleep 5"], timeout=0.5)

    assert success is False
    assert "sleep 5" in error, f"timeout message does not name the command: {error!r}"
    assert "echo first" not in error


@pytest.mark.parametrize("declared", [600, 42])
def test_cli_install_timeout_flag(tmp_path, monkeypatch, declared):
    """``--install-timeout`` sets the default for deps that declare none."""
    from wads import install_system_deps as mod

    _write_pyproject(tmp_path)
    recorder = _RunRecorder()
    monkeypatch.setattr("wads.install_system_deps.subprocess.run", recorder)
    monkeypatch.setattr(
        "sys.argv",
        [
            "install_system_deps",
            str(tmp_path),
            "--platform",
            "linux",
            "--skip-check",
            "--quiet",
            "--install-timeout",
            str(declared),
        ],
    )

    with pytest.raises(SystemExit) as excinfo:
        mod.main()

    assert excinfo.value.code == 0
    assert recorder.timeouts == {declared}
