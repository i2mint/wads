"""Temporary work directories that record their owner, and a sweep for the ones left behind.

A tool that makes a big temporary directory (a venv, an install, a build) and removes it
in its own cleanup leaks the directory whenever it is killed before the cleanup runs: a
stopped background task, a session that ends mid-run. On a machine whose temp filesystem
is a small tmpfs those leftovers add up until a later run fails partway with
``No space left on device`` (issue #159, ``wads ci-local``).

:func:`make_workdir` creates the directory with an owner file holding the creating
process's PID. :func:`sweep_stale_workdirs` removes directories with the same prefix that
are older than ``min_age`` seconds and whose owner is not running. A directory with no
owner file (made by an older version) is judged by age alone. Owner liveness is checked
with ``os.kill(pid, 0)`` on POSIX only; elsewhere age is the only test, because on
Windows ``os.kill`` with signal 0 terminates the process instead of probing it. On POSIX
the sweep also leaves alone directories another user owns: it could not remove them from
a shared ``/tmp`` anyway, and root should not age-sweep other users' work.

:func:`room_shortfall` says what a filesystem lacks (free bytes, and free inodes where
:func:`free_inodes` can report them) before a job needing that much room starts: a tmpfs
can run out of inodes with bytes to spare.

>>> import tempfile
>>> root = tempfile.mkdtemp()
>>> d = make_workdir("demo-", root=root)
>>> import os; os.utime(d, (0, 0))  # make it old (a fresh mtime can lead the clock)
>>> sweep_stale_workdirs("demo-", root=root, min_age=60, is_alive=lambda pid: True)
[]
>>> sweep_stale_workdirs("demo-", root=root, min_age=60, is_alive=lambda pid: False) == [d]
True
>>> import shutil; shutil.rmtree(root)
"""

from __future__ import annotations

import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Callable, Optional

#: Name of the file inside a work directory that holds its owner's PID.
OWNER_FILE = ".owner-pid"
#: Seconds in an hour.
HOUR = 3600
#: A work directory younger than this (seconds) is never swept, whoever owns it.
DFLT_STALE_AGE = 6 * HOUR


def make_workdir(prefix: str, *, root: Optional[str] = None) -> str:
    """``tempfile.mkdtemp(prefix=prefix, dir=root)``, plus an owner file with our PID."""
    workdir = tempfile.mkdtemp(prefix=prefix, dir=root)
    Path(workdir, OWNER_FILE).write_text(str(os.getpid()))
    return workdir


def pid_alive(pid: int) -> Optional[bool]:
    """Whether process ``pid`` exists; ``None`` where that cannot be checked safely."""
    if os.name != "posix":
        return None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:  # exists, owned by someone else
        return True
    except (OSError, OverflowError):  # OverflowError: a corrupt, out-of-range pid
        return None
    return True


def _owner_pid(workdir: Path) -> Optional[int]:
    try:
        pid = int((workdir / OWNER_FILE).read_text().strip())
    except (OSError, ValueError):
        return None
    return pid if pid > 0 else None  # 0 and negatives address process groups


def _is_stale(workdir: Path, *, min_age: float, now: float, is_alive: Callable) -> bool:
    try:
        st = workdir.stat()
    except OSError:
        return False
    getuid = getattr(os, "getuid", None)  # POSIX only
    if getuid is not None and st.st_uid != getuid():
        return False
    if now - st.st_mtime < min_age:
        return False
    pid = _owner_pid(workdir)
    return pid is None or is_alive(pid) is not True


def sweep_stale_workdirs(
    prefix: str,
    *,
    root: Optional[str] = None,
    min_age: float = DFLT_STALE_AGE,
    is_alive: Callable[[int], Optional[bool]] = pid_alive,
) -> list[str]:
    """Remove ``<root>/<prefix>*`` directories that are stale; return the removed paths.

    Stale: owned by this user (POSIX), last modified at least ``min_age`` seconds ago, and
    either no owner file or an owner that ``is_alive`` does not confirm running (``False``
    or ``None``). Symbolic links are never followed or removed. ``root``
    defaults to the system temp directory. Removal errors are ignored: a directory that
    cannot be removed is not reported.
    """
    root_path = Path(root or tempfile.gettempdir())
    now = time.time()
    removed = []
    for workdir in sorted(root_path.glob(f"{prefix}*")):
        if not workdir.is_dir() or workdir.is_symlink():
            continue
        if _is_stale(workdir, min_age=min_age, now=now, is_alive=is_alive):
            shutil.rmtree(workdir, ignore_errors=True)
            if not workdir.exists():
                removed.append(str(workdir))
    return removed


#: Bytes per GB, for the messages :func:`room_shortfall` writes.
BYTES_PER_GB = 1e9


def free_inodes(path: str) -> Optional[int]:
    """Inodes free to us on ``path``'s filesystem; ``None`` where that is not reported.

    ``None`` off POSIX (no ``os.statvfs``) and on filesystems that do not track inodes
    (``f_files == 0``: btrfs, an unlimited tmpfs).
    """
    statvfs = getattr(os, "statvfs", None)
    if statvfs is None:
        return None
    stats = statvfs(path)
    return stats.f_favail if stats.f_files else None


def room_shortfall(path: str, *, min_bytes: int, min_inodes: int) -> Optional[str]:
    """What ``path``'s filesystem lacks for a job needing that much room, or ``None``.

    Both bytes and inodes count: a tmpfs can run out of inodes with bytes to spare
    (issue #159). Inodes are skipped where :func:`free_inodes` cannot report them.

    >>> import tempfile
    >>> room_shortfall(tempfile.gettempdir(), min_bytes=0, min_inodes=0) is None
    True
    >>> room_shortfall(tempfile.gettempdir(), min_bytes=10**30, min_inodes=0)[:5]
    'only '
    """
    shortfalls = []
    free = shutil.disk_usage(path).free
    if free < min_bytes:
        shortfalls.append(f"only {free / BYTES_PER_GB:.1f} GB free")
    inodes = free_inodes(path)
    if inodes is not None and inodes < min_inodes:
        shortfalls.append(f"only {inodes:,} inodes free")
    return " and ".join(shortfalls) or None
