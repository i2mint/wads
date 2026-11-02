"""Tests for ``wads.workdirs``: owned temp work directories and the stale sweep (#159)."""

import os
import subprocess
import sys

import pytest

from wads.workdirs import (
    HOUR,
    OWNER_FILE,
    make_workdir,
    pid_alive,
    sweep_stale_workdirs,
)


def _dir(root, name, *, age, owner=None):
    """A ``root/name`` directory last modified ``age`` seconds ago, owned by ``owner``."""
    d = root / name
    d.mkdir()
    if owner is not None:
        (d / OWNER_FILE).write_text(str(owner))
    mtime = d.stat().st_mtime - age
    os.utime(d, (mtime, mtime))
    return d


@pytest.mark.parametrize(
    "age, owner, alive, swept",
    [
        (7 * HOUR, 123, False, True),  # old, owner gone
        (7 * HOUR, 123, True, False),  # old, owner still running
        (7 * HOUR, 123, None, True),  # old, liveness unknown (Windows): age decides
        (7 * HOUR, None, True, True),  # old, no owner file (older wads): age decides
        (1 * HOUR, 123, False, False),  # young: never swept, e.g. a kept workdir
        (1 * HOUR, None, False, False),
    ],
)
def test_sweep_rule(tmp_path, age, owner, alive, swept):
    d = _dir(tmp_path, "wads-ci-local-x", age=age, owner=owner)
    removed = sweep_stale_workdirs(
        "wads-ci-local-", root=str(tmp_path), is_alive=lambda pid: alive
    )
    assert (removed == [str(d)]) is swept
    assert d.exists() is not swept


def test_sweep_leaves_other_prefixes_and_files_alone(tmp_path):
    other = _dir(tmp_path, "something-else", age=9 * HOUR)
    stray = tmp_path / "wads-ci-local-file"
    stray.write_text("")
    os.utime(stray, (0, 0))
    assert sweep_stale_workdirs("wads-ci-local-", root=str(tmp_path)) == []
    assert other.exists() and stray.exists()


def test_make_workdir_records_this_process_as_owner(tmp_path):
    d = make_workdir("wads-ci-local-", root=str(tmp_path))
    assert os.path.basename(d).startswith("wads-ci-local-")
    assert (tmp_path / os.path.basename(d) / OWNER_FILE).read_text() == str(os.getpid())


def test_sweep_never_follows_a_symlink(tmp_path):
    target = _dir(tmp_path, "elsewhere", age=9 * HOUR)
    link = tmp_path / "wads-ci-local-link"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks need privileges here")
    swept = sweep_stale_workdirs(
        "wads-ci-local-", root=str(tmp_path), is_alive=lambda pid: False
    )
    assert swept == [] and link.is_symlink() and target.exists()


@pytest.mark.skipif(os.name != "posix", reason="ownership is only checked on POSIX")
def test_sweep_leaves_another_users_workdir_alone(tmp_path, monkeypatch):
    d = _dir(tmp_path, "wads-ci-local-theirs", age=9 * HOUR)
    monkeypatch.setattr(os, "getuid", lambda: d.stat().st_uid + 1)
    assert sweep_stale_workdirs("wads-ci-local-", root=str(tmp_path)) == []
    assert d.exists()


@pytest.mark.skipif(os.name != "posix", reason="liveness is only probed on POSIX")
def test_a_running_owner_protects_its_workdir_however_old(tmp_path):
    d = make_workdir("wads-ci-local-", root=str(tmp_path))
    os.utime(d, (0, 0))
    assert sweep_stale_workdirs("wads-ci-local-", root=str(tmp_path)) == []


@pytest.mark.skipif(os.name != "posix", reason="liveness is only probed on POSIX")
def test_pid_alive_on_posix():
    assert pid_alive(os.getpid()) is True
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    assert pid_alive(proc.pid) is False


@pytest.mark.skipif(os.name == "posix", reason="non-POSIX behaviour")
def test_pid_alive_never_probes_off_posix():
    assert pid_alive(os.getpid()) is None


@pytest.mark.parametrize(
    "files, favail, expected",
    [
        (10**6, 5, "only 5 inodes free"),
        (10**6, 10**6, None),
        (0, 0, None),  # f_files == 0: the filesystem does not track inodes
    ],
)
def test_room_shortfall_counts_inodes(tmp_path, monkeypatch, files, favail, expected):
    from wads import workdirs

    stats = type("Stats", (), {"f_files": files, "f_favail": favail})()
    monkeypatch.setattr(workdirs.os, "statvfs", lambda path: stats, raising=False)
    monkeypatch.setattr(
        workdirs.shutil, "disk_usage", lambda p: type("U", (), {"free": 10**12})()
    )
    assert workdirs.room_shortfall(str(tmp_path), min_bytes=1, min_inodes=1000) == (
        expected
    )
