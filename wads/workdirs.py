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
Windows ``os.kill`` with signal 0 terminates the process instead of probing it.

>>> import tempfile
>>> root = tempfile.mkdtemp()
>>> d = make_workdir("demo-", root=root)
>>> sweep_stale_workdirs("demo-", root=root, min_age=0)  # its owner (us) is alive
[]
>>> sweep_stale_workdirs("demo-", root=root, min_age=0, is_alive=lambda pid: False) == [d]
True
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
#: A work directory younger than this (seconds) is never swept, whoever owns it.
DFLT_STALE_AGE = 6 * 3600


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
    except OSError:
        return None
    return True


def _owner_pid(workdir: Path) -> Optional[int]:
    try:
        return int((workdir / OWNER_FILE).read_text().strip())
    except (OSError, ValueError):
        return None


def _is_stale(workdir: Path, *, min_age: float, now: float, is_alive: Callable) -> bool:
    try:
        age = now - workdir.stat().st_mtime
    except OSError:
        return False
    if age < min_age:
        return False
    pid = _owner_pid(workdir)
    return pid is None or is_alive(pid) is not True


def sweep_stale_workdirs(
    prefix: str,
    *,
    root: Optional[str] = None,
    min_age: float = DFLT_STALE_AGE,
    now: Optional[float] = None,
    is_alive: Callable[[int], Optional[bool]] = pid_alive,
) -> list[str]:
    """Remove ``<root>/<prefix>*`` directories that are stale; return the removed paths.

    Stale: last modified at least ``min_age`` seconds ago, and either no owner file or an
    owner that ``is_alive`` does not confirm running (``False`` or ``None``). ``root``
    defaults to the system temp directory. Removal errors are ignored: a directory that
    cannot be removed is not reported.
    """
    root_path = Path(root or tempfile.gettempdir())
    now = time.time() if now is None else now
    removed = []
    for workdir in sorted(root_path.glob(f"{prefix}*")):
        if not workdir.is_dir() or workdir.is_symlink():
            continue
        if _is_stale(workdir, min_age=min_age, now=now, is_alive=is_alive):
            shutil.rmtree(workdir, ignore_errors=True)
            if not workdir.exists():
                removed.append(str(workdir))
    return removed
