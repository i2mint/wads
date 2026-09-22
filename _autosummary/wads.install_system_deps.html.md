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

### Functions

| [`check_if_installed`](#wads.install_system_deps.check_if_installed)(dep_name, check_cmds[, ...])   | Check if dependency is already installed using check commands.   |
|----------------------------------------------------------------------------------------------------|------------------------------------------------------------------|
| [`detect_platform`](#wads.install_system_deps.detect_platform)()                                 | Detect the current platform.                                     |
| [`find_pyproject`](#wads.install_system_deps.find_pyproject)(path)                              | Find pyproject.toml file from path (file or directory).          |
| [`install_dependency`](#wads.install_system_deps.install_dependency)(dep_name, install_cmds[, ...]) | Install a dependency using install commands.                     |
| [`install_system_dependencies`](#wads.install_system_deps.install_system_dependencies)([...])                | Install system dependencies from pyproject.toml.                 |
| [`main`](#wads.install_system_deps.main)()                                            | CLI entry point.                                                 |
| [`read_system_deps`](#wads.install_system_deps.read_system_deps)(pyproject_path)                  | Read [tool.wads.ops.\*] sections from pyproject.toml.            |

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

### wads.install_system_deps.install_dependency(dep_name, install_cmds, timeout=300)

Install a dependency using install commands.

* **Parameters:**
  * **dep_name** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Name of dependency
  * **install_cmds** (`any`) – Command(s) to install (string or list)
  * **timeout** ([`float`](https://docs.python.org/3/builtins/functions.html#float)) – Timeout in seconds for each command
* **Returns:**
  bool, error_message: Optional[str])
* **Return type:**
  [`Tuple`](https://docs.python.org/3/library/typing.html#typing.Tuple)[[`bool`](https://docs.python.org/3/builtins/functions.html#bool), [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]

### wads.install_system_deps.install_system_dependencies(pyproject_path='.', platform=None, skip_check=False, verbose=True, , default_install_timeout=300)

Install system dependencies from pyproject.toml.

* **Parameters:**
  * **pyproject_path** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Path to pyproject.toml or directory containing it
  * **platform** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – Platform to install for (linux/macos/windows), auto-detect if None
  * **skip_check** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Skip checking if dependencies are already installed
  * **verbose** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Print detailed progress
  * **default_install_timeout** ([`float`](https://docs.python.org/3/builtins/functions.html#float)) – Per-command install timeout (seconds) for
    dependencies that declare no `install_timeout` of their own.
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
