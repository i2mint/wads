"""Tests for ``wads:<recipe>`` install commands and the CI job timeout (issue #160).

``apt-get install ffmpeg`` on a runner pulls ~99 packages from a mirror that sometimes
crawls for 20+ minutes; ``install.linux = "wads:static-ffmpeg"`` installs a pinned,
sha256-checked static build instead. And a stalled step should not hold a job for
GitHub's default 6 h: validation jobs carry ``timeout-minutes`` from
``[tool.wads.ci.testing].job_timeout_minutes``.
"""

import hashlib
import io
import os
import shutil
import subprocess
import tarfile
import textwrap
import warnings
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from wads.ci_config import DFLT_JOB_TIMEOUT_MINUTES, CIConfig
from wads.install_system_deps import (
    INSTALL_RECIPES,
    STATIC_FFMPEG_DEFAULTS,
    _expand_recipes,
    install_system_dependencies,
    static_ffmpeg_commands,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


ARCHIVE = '"${RUNNER_TEMP:-/tmp}/wads-static-ffmpeg.tar.xz"'


def test_static_ffmpeg_downloads_verifies_extracts_and_falls_back_to_apt():
    [cmd] = static_ffmpeg_commands({})
    static, fallback = cmd.split("; else ")
    assert static.startswith('if [ "$(uname -m)" = x86_64 ] && curl ')
    assert f"-o {ARCHIVE} {STATIC_FFMPEG_DEFAULTS['url']}" in static
    assert f"{STATIC_FFMPEG_DEFAULTS['sha256']} {ARCHIVE} | sha256sum -c -" in static
    assert "-C /usr/local/bin" in static
    assert "'*/bin/ffmpeg' '*/bin/ffprobe'" in static
    assert static.endswith(f"; then rm -f {ARCHIVE}")
    assert fallback.startswith(f"rm -f {ARCHIVE}; sudo rm -f /usr/local/bin/ffmpeg ")
    assert (
        "::warning::static ffmpeg install failed; installing from apt (slow)"
        in fallback
    )
    assert "apt-get install -y --no-install-recommends ffmpeg" in fallback


def test_static_ffmpeg_parameters_are_overridable_and_quoted():
    [cmd] = static_ffmpeg_commands(
        {
            "url": "https://example.com/my ffmpeg.tar.xz",
            "sha256": "abc",
            "binaries": ["ffmpeg"],
            "bin_dir": "/opt/bin",
            "download_timeout": 30,
            "apt_fallback": False,
        }
    )
    assert "'https://example.com/my ffmpeg.tar.xz'" in cmd
    assert "--max-time 30" in cmd and "-C /opt/bin" in cmd
    assert "'*/bin/ffprobe'" not in cmd and "apt-get" not in cmd


def test_expand_recipes_keeps_plain_commands_and_expands_named_ones():
    out = _expand_recipes(
        ["sudo true", "  wads:static-ffmpeg "],
        {"apt_fallback": False},
        platform="linux",
    )
    assert out[0] == "sudo true"
    assert out[1:] == static_ffmpeg_commands({"apt_fallback": False})
    assert set(INSTALL_RECIPES) == {"static-ffmpeg"}


@pytest.mark.parametrize(
    "install, recipe, error",
    [
        ('"wads:nope"', "", "unknown install recipe 'wads:nope'"),
        ('"wads:static-ffmpeg"', 'recipe = "x"', "recipe parameters must be a table"),
        (
            '"wads:static-ffmpeg"',
            'recipe.urll = "x"',
            "unknown recipe parameter(s) urll",
        ),
        ('"wads:static-ffmpeg"', 'recipe.url = "x"', "url override needs its sha256"),
        (
            '"wads:static-ffmpeg"',
            'recipe.apt_fallback = "no"',
            "apt_fallback must be a boolean, got 'no'",
        ),
        (
            '"wads:static-ffmpeg"',
            "recipe.download_timeout = 0",
            "download_timeout must be a positive integer",
        ),
        (
            '"wads:static-ffmpeg"',
            "recipe.binaries = []",
            "binaries must be a non-empty list of strings",
        ),
        (
            '"wads:static-ffmpeg"',
            "recipe.binaries = [1]",
            "binaries must be a non-empty list of strings",
        ),
        ('"wads:static-ffmpeg"', "recipe.bin_dir = 3", "bin_dir must be a non-empty"),
    ],
)
def test_bad_recipes_fail_the_dependency(tmp_path, capsys, install, recipe, error):
    (tmp_path / "pyproject.toml").write_text(
        textwrap.dedent(
            f"""
            [project]
            name = "demo"
            version = "0.0.1"

            [tool.wads.ops.ffmpeg]
            install.linux = {install}
            {recipe}
            """
        )
    )
    calls = []
    counts = install_system_dependencies(
        str(tmp_path),
        platform="linux",
        install=lambda *a, **k: calls.append(a) or (True, None),
        is_installed=lambda *a: False,
    )
    assert counts == (0, 0, 1) and calls == []
    assert error in capsys.readouterr().err


def test_the_recipe_is_refused_off_linux(tmp_path, capsys):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.0.1"\n\n'
        '[tool.wads.ops.ffmpeg]\ninstall.macos = "wads:static-ffmpeg"\n'
    )
    calls = []
    counts = install_system_dependencies(
        str(tmp_path),
        platform="macos",
        install=lambda *a, **k: calls.append(a) or (True, None),
        is_installed=lambda *a: False,
    )
    assert counts == (0, 0, 1) and calls == []
    assert "supports linux, not macos" in capsys.readouterr().err


def test_the_recipe_reaches_the_installer_expanded(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        textwrap.dedent(
            """
            [project]
            name = "demo"
            version = "0.0.1"

            [tool.wads.ops.ffmpeg]
            check.linux = "ffmpeg -version && ffprobe -version"
            install.linux = "wads:static-ffmpeg"

            [tool.wads.ops.ffmpeg.recipe]
            sha256 = "0123"
            """
        )
    )
    seen = []
    counts = install_system_dependencies(
        str(tmp_path),
        platform="linux",
        verbose=False,
        install=lambda dep, cmds, **k: seen.append(cmds) or (True, None),
        is_installed=lambda dep, checks: bool(seen),  # absent before, present after
    )
    assert counts == (1, 0, 0)
    assert seen == [static_ffmpeg_commands({"sha256": "0123"})]


# --------------------------------------------------------------------------------------
# The generated shell, executed against stub curl / sudo / uname / apt-get


_STUBS = {
    # Copies the test's archive to wherever `-o` says
    "curl": 'while [ $# -gt 0 ]; do [ "$1" = -o ] && out="$2"; shift; done\n'
    'cp "$FAKE_ARCHIVE" "$out"',
    "sudo": 'exec "$@"',
    "uname": 'echo "$FAKE_ARCH"',
    "apt-get": 'echo "$@" >> "$APT_LOG"',
}


def _has_gnu_tar_and_sha256sum() -> bool:
    if not (shutil.which("sha256sum") and shutil.which("tar")):
        return False
    version = subprocess.run(["tar", "--version"], capture_output=True, text=True)
    return "GNU tar" in version.stdout


def _fake_ffmpeg_archive() -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:xz") as tar:
        for name in ("x/bin/ffmpeg", "x/bin/ffprobe", "x/doc/README"):
            data = b"#!/bin/sh\necho fake\n"
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(data), 0o755
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


@pytest.fixture
def sandbox(tmp_path):
    """Run a recipe command with stubbed network/root/apt, real tar and sha256sum."""
    if not _has_gnu_tar_and_sha256sum():
        pytest.skip("needs sha256sum and GNU tar (--wildcards)")
    stubs, bin_dir, runner_temp = (tmp_path / d for d in ("stubs", "bin", "temp"))
    for d in (stubs, bin_dir, runner_temp):
        d.mkdir()
    for name, body in _STUBS.items():
        (stubs / name).write_text(f"#!/bin/sh\n{body}\n")
        (stubs / name).chmod(0o755)
    archive = _fake_ffmpeg_archive()
    (tmp_path / "fake.tar.xz").write_bytes(archive)
    env = {
        **os.environ,
        "PATH": f"{stubs}{os.pathsep}{os.environ['PATH']}",
        "RUNNER_TEMP": str(runner_temp),
        "FAKE_ARCHIVE": str(tmp_path / "fake.tar.xz"),
        "FAKE_ARCH": "x86_64",
        "APT_LOG": str(tmp_path / "apt.log"),
    }

    def run(params, **env_overrides):
        [cmd] = static_ffmpeg_commands({"bin_dir": str(bin_dir), **params})
        return subprocess.run(
            cmd,
            shell=True,
            env={**env, **env_overrides},
            capture_output=True,
            text=True,
        )

    return SimpleNamespace(
        run=run,
        sha256=hashlib.sha256(archive).hexdigest(),
        bin_dir=bin_dir,
        runner_temp=runner_temp,
        apt_log=tmp_path / "apt.log",
    )


def test_static_install_extracts_both_binaries_and_removes_the_archive(sandbox):
    result = sandbox.run({"sha256": sandbox.sha256, "apt_fallback": False})
    assert result.returncode == 0, result.stderr
    assert sorted(p.name for p in sandbox.bin_dir.iterdir()) == ["ffmpeg", "ffprobe"]
    assert list(sandbox.runner_temp.iterdir()) == []


def test_checksum_mismatch_without_fallback_fails_and_leaves_no_archive(sandbox):
    result = sandbox.run({"sha256": "0" * 64, "apt_fallback": False})
    assert result.returncode != 0
    assert list(sandbox.bin_dir.iterdir()) == []
    assert list(sandbox.runner_temp.iterdir()) == []
    assert not sandbox.apt_log.exists()


def test_checksum_mismatch_falls_back_to_apt_after_removing_stale_binaries(sandbox):
    (sandbox.bin_dir / "ffmpeg").write_text("partial")
    result = sandbox.run({"sha256": "0" * 64})
    assert result.returncode == 0, result.stderr
    assert list(sandbox.bin_dir.iterdir()) == []
    assert "static ffmpeg install failed; installing from apt (slow)" in result.stdout
    assert "install -y --no-install-recommends ffmpeg" in sandbox.apt_log.read_text()


def test_another_architecture_never_downloads_the_x86_64_build(sandbox):
    result = sandbox.run(
        {"sha256": sandbox.sha256, "apt_fallback": False}, FAKE_ARCH="aarch64"
    )
    assert result.returncode != 0
    assert list(sandbox.bin_dir.iterdir()) == []
    assert list(sandbox.runner_temp.iterdir()) == []


# --------------------------------------------------------------------------------------
# job_timeout_minutes


def _cfg(testing):
    return CIConfig({"tool": {"wads": {"ci": {"testing": testing}}}})


@pytest.mark.parametrize(
    "declared, expected",
    [({}, DFLT_JOB_TIMEOUT_MINUTES), ({"job_timeout_minutes": 15}, 15)],
)
def test_job_timeout_minutes(declared, expected):
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert _cfg(declared).job_timeout_minutes == expected


@pytest.mark.parametrize("invalid", [0, -5, "15", True, 1.5])
def test_invalid_job_timeout_minutes_warns_and_falls_back(invalid):
    with pytest.warns(UserWarning, match=f"job_timeout_minutes={invalid!r}"):
        assert (
            _cfg({"job_timeout_minutes": invalid}).job_timeout_minutes
            == DFLT_JOB_TIMEOUT_MINUTES
        )


def test_default_job_timeout_is_pinned_to_the_workflow_fallback():
    """The `|| '60'` in the workflows must equal the Python default."""
    assert DFLT_JOB_TIMEOUT_MINUTES == 60


@pytest.mark.parametrize(
    "workflow", [".github/workflows/uv-ci.yml", "wads/data/github_ci_uv.yml"]
)
def test_validation_jobs_carry_the_configured_timeout(workflow):
    jobs = yaml.safe_load((REPO_ROOT / workflow).read_text())["jobs"]
    expected = (
        "${{ fromJSON(needs.setup.outputs.job-timeout-minutes || "
        f"'{DFLT_JOB_TIMEOUT_MINUTES}') }}}}"
    )
    for job in ("validation", "windows-validation"):
        assert jobs[job]["timeout-minutes"] == expected, job
    setup_outputs = jobs["setup"]["outputs"]
    assert setup_outputs["job-timeout-minutes"] == (
        "${{ steps.config.outputs.job-timeout-minutes }}"
    )


def test_read_ci_config_exports_the_timeout(tmp_path, monkeypatch):
    from wads.scripts import read_ci_config as script

    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\n\n[tool.wads.ci.testing]\njob_timeout_minutes = 20\n'
    )
    out = tmp_path / "out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setenv("GITHUB_ENV", str(tmp_path / "env"))
    monkeypatch.setattr("sys.argv", ["x", str(tmp_path / "pyproject.toml")])
    try:
        script.main()
    except SystemExit as e:
        assert not e.code
    assert "job-timeout-minutes=20" in out.read_text()
