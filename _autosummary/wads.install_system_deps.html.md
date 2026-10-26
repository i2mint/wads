# wads.install_system_deps

Install system dependencies from [tool.wads.ops.\*] sections in pyproject.toml.

This script reads system dependency configurations and installs them on the appropriate platform.
It can be used as a standalone CLI tool or imported as a module.

Each `[tool.wads.ops.<dep>]` section may declare an `install_timeout` (seconds)
to raise the per-command ceiling for a dependency that is slow but healthy — a
cold-cache `apt-get install ffmpeg` on a GitHub runner is the motivating case.
Without a declaration the timeout stays at `DFLT_INSTALL_TIMEOUT`:

```default
[tool.wads.ops.ffmpeg]
install_timeout = 900
install.linux = ["sudo apt-get update", "sudo apt-get install -y ffmpeg"]
```

The CLI’s `--install-timeout` sets the fallback for dependencies that declare
none; a declaration always wins over it.

A failed or timed-out install command is retried with exponential backoff
(`DFLT_INSTALL_RETRIES` extra attempts, `DFLT_INSTALL_BACKOFF` seconds
before the first retry, doubling), because the usual cause on a hosted runner is a
transient apt mirror timeout that a raised ceiling does not cure. A dependency may
declare `install_retries` (`0` disables retrying); the CLI’s `--install-retries`
sets the fallback. Worst case for a command that always fails is
`(retries + 1) * install_timeout` plus the backoff waits. Commands are retried one at a time, so a successful
`apt-get update` is not repeated when only the following install flaked.

### Module Attributes

| [`SLOW_DEP_INSTALL_TIMEOUTS`](#wads.install_system_deps.SLOW_DEP_INSTALL_TIMEOUTS)   | Dependencies with a big dependency tree get a longer ceiling than the global default (a cold-cache `apt-get install ffmpeg` outlasts 300s).   |
|------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------|
| [`DFLT_APT_LOCK_TIMEOUT`](#wads.install_system_deps.DFLT_APT_LOCK_TIMEOUT)       | Seconds apt waits for the dpkg lock before giving up (`-o DPkg::Lock::Timeout`).                                                              |
| [`DFLT_KILL_GRACE`](#wads.install_system_deps.DFLT_KILL_GRACE)             | Seconds between SIGTERM and SIGKILL when a timed-out install is stopped.                                                                      |

### Functions

| [`check_if_installed`](#wads.install_system_deps.check_if_installed)(dep_name, check_cmds[, ...])   | Check if dependency is already installed using check commands.                  |
|----------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------|
| [`detect_platform`](#wads.install_system_deps.detect_platform)()                                 | Detect the current platform.                                                    |
| [`find_pyproject`](#wads.install_system_deps.find_pyproject)(path)                              | Find pyproject.toml file from path (file or directory).                         |
| [`install_dependency`](#wads.install_system_deps.install_dependency)(dep_name, install_cmds[, ...]) | Install a dependency using install commands.                                    |
| [`install_system_dependencies`](#wads.install_system_deps.install_system_dependencies)([...])                | Install system dependencies from pyproject.toml.                                |
| [`main`](#wads.install_system_deps.main)()                                            | CLI entry point.                                                                |
| [`read_system_deps`](#wads.install_system_deps.read_system_deps)(pyproject_path)                  | Read [tool.wads.ops.\*] sections from pyproject.toml.                           |
| [`with_apt_lock_timeout`](#wads.install_system_deps.with_apt_lock_timeout)(cmd, seconds)               | `cmd` with every `apt`/`apt-get` call told to wait `seconds` for the dpkg lock. |

### wads.install_system_deps.DFLT_APT_LOCK_TIMEOUT *= 120*

Seconds apt waits for the dpkg lock before giving up (`-o DPkg::Lock::Timeout`).

### wads.install_system_deps.DFLT_KILL_GRACE *= 5*

Seconds between SIGTERM and SIGKILL when a timed-out install is stopped.

### wads.install_system_deps.SLOW_DEP_INSTALL_TIMEOUTS *= {'ffmpeg': 900}*

Dependencies with a big dependency tree get a longer ceiling than the global default
(a cold-cache `apt-get install ffmpeg` outlasts 300s). A declaration or an explicit
`default_install_timeout` still wins.

### wads.install_system_deps.check_if_installed(dep_name, check_cmds, timeout=10)

Check if dependency is already installed using check commands.

* **Parameters:**
  * **dep_name** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Name of dependency
  * **check_cmds** (`any`) – Command(s) to check if installed (string, list, or empty)
  * **timeout** ([`float`](https://docs.python.org/3/builtins/functions.html#float)) – Timeout in seconds for check commands
* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)
* **Returns:**
  True if installed, False otherwise

### wads.install_system_deps.detect_platform()

Detect the current platform.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### wads.install_system_deps.find_pyproject(path)

Find pyproject.toml file from path (file or directory).

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

### wads.install_system_deps.install_dependency(dep_name, install_cmds, timeout=300, , retries=2, backoff=5, sleep=None, apt_lock_timeout=120)

Install a dependency using install commands.

* **Parameters:**
  * **dep_name** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Name of dependency
  * **install_cmds** (`any`) – Command(s) to install (string or list)
  * **timeout** ([`float`](https://docs.python.org/3/builtins/functions.html#float)) – Timeout in seconds for each command
  * **retries** ([`int`](https://docs.python.org/3/builtins/functions.html#int)) – Extra attempts for a command that fails or times out
  * **backoff** ([`float`](https://docs.python.org/3/builtins/functions.html#float)) – Seconds before the first retry; doubles for each further one
  * **sleep** – Wait function (default `time.sleep`; injectable for tests)
  * **apt_lock_timeout** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`float`](https://docs.python.org/3/builtins/functions.html#float)]) – Seconds each apt call waits for the dpkg lock (`None`: no flag)
* **Returns:**
  bool, error_message: Optional[str])
* **Return type:**
  [`Tuple`](https://docs.python.org/3/library/typing.html#typing.Tuple)[[`bool`](https://docs.python.org/3/builtins/functions.html#bool), [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]

### wads.install_system_deps.install_system_dependencies(pyproject_path='.', platform=None, skip_check=False, verbose=True, , default_install_timeout=None, default_install_retries=2, apt_lock_timeout=120)

Install system dependencies from pyproject.toml.

* **Parameters:**
  * **pyproject_path** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Path to pyproject.toml or directory containing it
  * **platform** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – Platform to install for (linux/macos/windows), auto-detect if None
  * **skip_check** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Skip checking if dependencies are already installed
  * **verbose** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Print detailed progress
  * **default_install_timeout** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`float`](https://docs.python.org/3/builtins/functions.html#float)]) – Per-command install timeout (seconds) for
    dependencies that declare no `install_timeout` of their own. `None`:
    [`SLOW_DEP_INSTALL_TIMEOUTS`](#wads.install_system_deps.SLOW_DEP_INSTALL_TIMEOUTS) for known-slow ones, else
    `DFLT_INSTALL_TIMEOUT`.
  * **apt_lock_timeout** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`float`](https://docs.python.org/3/builtins/functions.html#float)]) – Seconds each apt call waits for the dpkg lock (`None`: no flag).
  * **default_install_retries** ([`int`](https://docs.python.org/3/builtins/functions.html#int)) – Retries per failed install command for
    dependencies that declare no `install_retries` of their own.
* **Return type:**
  [`Tuple`](https://docs.python.org/3/library/typing.html#typing.Tuple)[[`int`](https://docs.python.org/3/builtins/functions.html#int), [`int`](https://docs.python.org/3/builtins/functions.html#int), [`int`](https://docs.python.org/3/builtins/functions.html#int)]
* **Returns:**
  (installed_count, skipped_count, failed_count)

### wads.install_system_deps.main()

CLI entry point.

### wads.install_system_deps.read_system_deps(pyproject_path)

Read [tool.wads.ops.\*] sections from pyproject.toml.

* **Return type:**
  [`Dict`](https://docs.python.org/3/library/typing.html#typing.Dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)]

### wads.install_system_deps.with_apt_lock_timeout(cmd, seconds)

`cmd` with every `apt`/`apt-get` call told to wait `seconds` for the dpkg lock.

```pycon
>>> with_apt_lock_timeout("sudo apt-get update && sudo apt-get install -y ffmpeg", 60)
'sudo apt-get -o DPkg::Lock::Timeout=60 update && sudo apt-get -o DPkg::Lock::Timeout=60 install -y ffmpeg'
>>> with_apt_lock_timeout("apt install -y apt-utils", None)
'apt install -y apt-utils'
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
