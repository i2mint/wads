"""Tests for ``wads:<recipe>`` install commands and the CI job timeout (issue #160).

``apt-get install ffmpeg`` on a runner pulls ~99 packages from a mirror that sometimes
crawls for 20+ minutes; ``install.linux = "wads:static-ffmpeg"`` installs a pinned,
sha256-checked static build instead. And a stalled step should not hold a job for
GitHub's default 6 h: validation jobs carry ``timeout-minutes`` from
``[tool.wads.ci.testing].job_timeout_minutes``.
"""

import textwrap
from pathlib import Path

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


def test_static_ffmpeg_downloads_verifies_extracts_and_falls_back_to_apt():
    [cmd] = static_ffmpeg_commands({})
    static, fallback = cmd.split(") || (")
    assert STATIC_FFMPEG_DEFAULTS["url"] in static
    assert (
        f"{STATIC_FFMPEG_DEFAULTS['sha256']}  /tmp/wads-static-ffmpeg.tar.xz" in static
    )
    assert "sha256sum -c -" in static
    assert "-C /usr/local/bin" in static
    assert "'*/bin/ffmpeg' '*/bin/ffprobe'" in static
    assert "::warning::" in fallback
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
        ["sudo true", "  wads:static-ffmpeg "], {"apt_fallback": False}
    )
    assert out[0] == "sudo true"
    assert out[1:] == static_ffmpeg_commands({"apt_fallback": False})
    assert set(INSTALL_RECIPES) == {"static-ffmpeg"}


@pytest.mark.parametrize(
    "install, recipe, error",
    [
        ('"wads:nope"', "", "unknown install recipe 'wads:nope'"),
        ('"wads:static-ffmpeg"', 'recipe = "x"', "recipe parameters must be a table"),
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


def test_the_recipe_reaches_the_installer_expanded(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        textwrap.dedent(
            """
            [project]
            name = "demo"
            version = "0.0.1"

            [tool.wads.ops.ffmpeg]
            check.linux = "which ffmpeg && which ffprobe"
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
# job_timeout_minutes


def _cfg(testing):
    return CIConfig({"tool": {"wads": {"ci": {"testing": testing}}}})


@pytest.mark.parametrize(
    "declared, expected",
    [
        ({}, DFLT_JOB_TIMEOUT_MINUTES),
        ({"job_timeout_minutes": 15}, 15),
        ({"job_timeout_minutes": 0}, DFLT_JOB_TIMEOUT_MINUTES),
        ({"job_timeout_minutes": "15"}, DFLT_JOB_TIMEOUT_MINUTES),
        ({"job_timeout_minutes": True}, DFLT_JOB_TIMEOUT_MINUTES),
    ],
)
def test_job_timeout_minutes(declared, expected):
    assert _cfg(declared).job_timeout_minutes == expected


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
