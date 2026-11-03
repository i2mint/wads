"""i2mint/wads#192: warn when ``check.windows`` calls ``which``, which cmd.exe lacks.

Checks run with ``shell=True``; on Windows that is cmd.exe, where ``which`` resolves
only if Git's ``usr\\bin`` is on PATH, so a good install reads as failed. wads reports
such commands (setup job, install step on Windows, repo audit) and never rewrites them.
"""

import textwrap

import pytest

from wads.install_system_deps import (
    install_system_dependencies,
    unix_only_check_warnings,
)
from wads.repo_audit import audit_repo
from wads.scripts.read_ci_config import read_and_export_ci_config


@pytest.mark.parametrize(
    "check",
    [
        "which ffmpeg",
        "  which ffmpeg",
        "where ffmpeg || which ffmpeg",
        "ffmpeg -version && which ffprobe",
        "(which ffmpeg)",
        ["where ffmpeg", "which ffmpeg"],
        [["which", "ffmpeg"]],
    ],
)
def test_which_as_a_command_is_reported(check):
    (warning,) = unix_only_check_warnings({"ffmpeg": {"check": {"windows": check}}})
    assert "check.windows for ffmpeg uses `which`" in warning
    assert "where <name>" in warning


@pytest.mark.parametrize(
    "check",
    [
        "where ffmpeg",
        "ffmpeg -version",
        "echo which-one",  # not in command position
        "findstr which notes.txt",  # an argument, not the command
        "",
        [],
    ],
)
def test_other_windows_checks_are_not_reported(check):
    assert unix_only_check_warnings({"ffmpeg": {"check": {"windows": check}}}) == []


def test_only_the_windows_check_is_inspected():
    ops = {
        "ffmpeg": {"check": {"linux": "which ffmpeg", "macos": "which ffmpeg"}},
        "odd": "not a table",
        "flat": {"check": "which x"},  # not per-platform: not a Windows check
    }
    assert unix_only_check_warnings(ops) == []


def test_the_command_table_is_a_seam():
    ops = {"x": {"check": {"windows": "command -v x"}}}
    assert unix_only_check_warnings(ops) == []
    (warning,) = unix_only_check_warnings(ops, unix_only={"command": "`where x`"})
    assert "uses `command`" in warning and "`where x`" in warning


_PYPROJECT = textwrap.dedent(
    """\
    [project]
    name = "mypkg"
    version = "0.1.0"

    [tool.wads.ops.ffmpeg]
    check.linux = "which ffmpeg"
    check.windows = "which ffmpeg"
    install.windows = "choco install ffmpeg -y"
    """
)


def test_the_setup_job_prints_a_github_warning(tmp_path, monkeypatch, capsys):
    for var in ("GITHUB_OUTPUT", "GITHUB_ENV", "GITHUB_STEP_SUMMARY"):
        monkeypatch.delenv(var, raising=False)
    (tmp_path / "pyproject.toml").write_text(_PYPROJECT)
    assert read_and_export_ci_config(str(tmp_path)) == 0
    out = capsys.readouterr().out
    assert "::warning title=Unix-only Windows check::check.windows for ffmpeg" in out


def test_the_repo_audit_flags_it(tmp_path):
    (tmp_path / "pyproject.toml").write_text(_PYPROJECT)
    findings = audit_repo(tmp_path, network=False)["findings"]
    assert any("uses `which`" in f["summary"] for f in findings)


def test_the_install_step_warns_on_windows(tmp_path, capsys):
    (tmp_path / "pyproject.toml").write_text(_PYPROJECT)
    install_system_dependencies(
        str(tmp_path),
        platform="windows",
        install=lambda *a, **k: (True, ""),
        is_installed=lambda *a, **k: True,
    )
    assert "Warning: check.windows for ffmpeg uses `which`" in capsys.readouterr().err
