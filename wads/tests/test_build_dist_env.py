"""``build_dist`` must not change the interpreter it runs in (issue #119).

It used to ``pip install -e .`` the project being built (and ``--upgrade pip build``)
into ``sys.executable``: the wads test suite left ``test-pkg`` editable-installed in the
developer's interpreter, pointing at a deleted pytest temp dir. ``python -m build``
builds in an isolated environment, so that install never affected the build.
"""

import subprocess

import pytest

from wads.scripts import build_dist


@pytest.fixture
def commands(monkeypatch):
    """Record every subprocess command build_dist runs; pretend each succeeds."""
    seen = []

    def fake_run(cmd, **kwargs):
        seen.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    monkeypatch.setattr(build_dist.subprocess, "run", fake_run)
    return seen


def _installs(commands):
    return [cmd for cmd in commands if "install" in cmd]


def test_nothing_is_installed_when_build_is_present(commands, tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n')
    monkeypatch.chdir(tmp_path)
    assert build_dist.build_distributions(output_dir=str(tmp_path / "dist")) == 0
    assert _installs(commands) == []
    assert any(cmd[1:3] == ["-m", "build"] for cmd in commands)


def test_only_build_is_installed_when_missing(commands, tmp_path, monkeypatch):
    monkeypatch.setattr(build_dist, "_has_build_tool", lambda: False)
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n')
    monkeypatch.chdir(tmp_path)
    assert build_dist.build_distributions(output_dir=str(tmp_path / "dist")) == 0
    [install] = _installs(commands)
    assert install[-1] == "build" and "-e" not in install and "--upgrade" not in install


def test_a_stray_build_directory_does_not_pass_the_probe(tmp_path, monkeypatch):
    """``import build`` succeeds on an empty ``build/`` dir; ``python -m build`` fails.

    The probe is captured, then re-run with ``-S`` (no site-packages, so no real
    ``build``) next to a stray ``build/`` directory: it must report absence.
    """
    probes = []
    monkeypatch.setattr(
        build_dist.subprocess,
        "run",
        lambda cmd, **kw: probes.append(cmd) or subprocess.CompletedProcess(cmd, 0),
    )
    build_dist._has_build_tool()
    [probe] = probes
    monkeypatch.undo()
    (tmp_path / "build").mkdir()
    isolated = [probe[0], "-S", *probe[1:]]
    assert subprocess.run(isolated, cwd=tmp_path, capture_output=True).returncode != 0
    # ...whereas the naive probe would have been fooled:
    naive = [probe[0], "-S", "-c", "import build"]
    assert subprocess.run(naive, cwd=tmp_path, capture_output=True).returncode == 0
