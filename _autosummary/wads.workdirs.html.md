# wads.workdirs

Temporary work directories that record their owner, and a sweep for the ones left behind.

A tool that makes a big temporary directory (a venv, an install, a build) and removes it
in its own cleanup leaks the directory whenever it is killed before the cleanup runs: a
stopped background task, a session that ends mid-run. On a machine whose temp filesystem
is a small tmpfs those leftovers add up until a later run fails partway with
`No space left on device` (issue #159, `wads ci-local`).

[`make_workdir()`](#wads.workdirs.make_workdir) creates the directory with an owner file holding the creating
process’s PID. [`sweep_stale_workdirs()`](#wads.workdirs.sweep_stale_workdirs) removes directories with the same prefix that
are older than `min_age` seconds and whose owner is not running. A directory with no
owner file (made by an older version) is judged by age alone. Owner liveness is checked
with `os.kill(pid, 0)` on POSIX only; elsewhere age is the only test, because on
Windows `os.kill` with signal 0 terminates the process instead of probing it. On POSIX
the sweep also leaves alone directories another user owns: it could not remove them from
a shared `/tmp` anyway, and root should not age-sweep other users’ work.

[`room_shortfall()`](#wads.workdirs.room_shortfall) says what a filesystem lacks (free bytes, and free inodes where
[`free_inodes()`](#wads.workdirs.free_inodes) can report them) before a job needing that much room starts: a tmpfs
can run out of inodes with bytes to spare.

```pycon
>>> import tempfile
>>> root = tempfile.mkdtemp()
>>> d = make_workdir("demo-", root=root)
>>> import os; os.utime(d, (0, 0))  # make it old (a fresh mtime can lead the clock)
>>> sweep_stale_workdirs("demo-", root=root, min_age=60, is_alive=lambda pid: True)
[]
>>> sweep_stale_workdirs("demo-", root=root, min_age=60, is_alive=lambda pid: False) == [d]
True
>>> import shutil; shutil.rmtree(root)
```

### Module Attributes

| [`OWNER_FILE`](#wads.workdirs.OWNER_FILE)     | Name of the file inside a work directory that holds its owner's PID.                                     |
|-----------------------------------------------------------------|----------------------------------------------------------------------------------------------------------|
| [`HOUR`](#wads.workdirs.HOUR)           | Seconds in an hour.                                                                                      |
| [`DFLT_STALE_AGE`](#wads.workdirs.DFLT_STALE_AGE) | A work directory younger than this (seconds) is never swept, whoever owns it.                            |
| [`BYTES_PER_GB`](#wads.workdirs.BYTES_PER_GB)   | Bytes per GB, for the messages [`room_shortfall()`](#wads.workdirs.room_shortfall) writes. |

### Functions

| [`free_inodes`](#wads.workdirs.free_inodes)(path)                               | Inodes free to us on `path`'s filesystem; `None` where that is not reported.    |
|--------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------|
| [`make_workdir`](#wads.workdirs.make_workdir)(prefix, \*[, root])                | `tempfile.mkdtemp(prefix=prefix, dir=root)`, plus an owner file with our PID.   |
| [`pid_alive`](#wads.workdirs.pid_alive)(pid)                                  | Whether process `pid` exists; `None` where that cannot be checked safely.       |
| [`room_shortfall`](#wads.workdirs.room_shortfall)(path, \*, min_bytes, min_inodes) | What `path`'s filesystem lacks for a job needing that much room, or `None`.     |
| [`sweep_stale_workdirs`](#wads.workdirs.sweep_stale_workdirs)(prefix, \*[, root, ...])   | Remove `<root>/<prefix>*` directories that are stale; return the removed paths. |

### wads.workdirs.BYTES_PER_GB *= 1000000000.0*

Bytes per GB, for the messages [`room_shortfall()`](#wads.workdirs.room_shortfall) writes.

### wads.workdirs.DFLT_STALE_AGE *= 21600*

A work directory younger than this (seconds) is never swept, whoever owns it.

### wads.workdirs.HOUR *= 3600*

Seconds in an hour.

### wads.workdirs.OWNER_FILE *= '.owner-pid'*

Name of the file inside a work directory that holds its owner’s PID.

### wads.workdirs.free_inodes(path)

Inodes free to us on `path`’s filesystem; `None` where that is not reported.

`None` off POSIX (no `os.statvfs`) and on filesystems that do not track inodes
(`f_files == 0`: btrfs, an unlimited tmpfs).

* **Return type:**
  [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`int`](https://docs.python.org/3/builtins/functions.html#int)]

### wads.workdirs.make_workdir(prefix, , root=None)

`tempfile.mkdtemp(prefix=prefix, dir=root)`, plus an owner file with our PID.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### wads.workdirs.pid_alive(pid)

Whether process `pid` exists; `None` where that cannot be checked safely.

* **Return type:**
  [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`bool`](https://docs.python.org/3/builtins/functions.html#bool)]

### wads.workdirs.room_shortfall(path, , min_bytes, min_inodes)

What `path`’s filesystem lacks for a job needing that much room, or `None`.

Both bytes and inodes count: a tmpfs can run out of inodes with bytes to spare
(issue #159). Inodes are skipped where [`free_inodes()`](#wads.workdirs.free_inodes) cannot report them.

```pycon
>>> import tempfile
>>> room_shortfall(tempfile.gettempdir(), min_bytes=0, min_inodes=0) is None
True
>>> room_shortfall(tempfile.gettempdir(), min_bytes=10**30, min_inodes=0)[:5]
'only '
```

* **Return type:**
  [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### wads.workdirs.sweep_stale_workdirs(prefix, \*, root=None, min_age=21600, is_alive=<function pid_alive>)

Remove `<root>/<prefix>*` directories that are stale; return the removed paths.

Stale: owned by this user (POSIX), last modified at least `min_age` seconds ago, and
either no owner file or an owner that `is_alive` does not confirm running (`False`
or `None`). Symbolic links are never followed or removed. `root`
defaults to the system temp directory. Removal errors are ignored: a directory that
cannot be removed is not reported.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]
