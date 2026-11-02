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

An install command may name a wads recipe instead of spelling it out (issue #160):

```default
[tool.wads.ops.ffmpeg]
check.linux = "ffmpeg -version && ffprobe -version"
install.linux = "wads:static-ffmpeg"
```

expands to [`static_ffmpeg_commands()`](#wads.install_system_deps.static_ffmpeg_commands): a pinned, sha256-checked static build in
seconds instead of a crawling apt mirror, with apt as the fallback (Linux x86_64 only;
another architecture goes straight to apt). Override its parameters (`url`,
`sha256`, …) under `[tool.wads.ops.ffmpeg.recipe]`; an unknown or mistyped
parameter fails the dependency. Running the binaries in the check (rather than
`which`) also catches a wrong-architecture or corrupt download.

An install whose commands all exit 0 is not trusted on that alone: when the dependency
declares a `check.<platform>`, that check is re-run afterwards, and a dependency whose
check still fails is re-installed ([`DFLT_VERIFY_RETRIES`](#wads.install_system_deps.DFLT_VERIFY_RETRIES) more rounds, each after a
backoff wait that starts at `DFLT_INSTALL_BACKOFF` seconds and doubles) and then
reported as failed. Package managers do report success for installs that did nothing —
Chocolatey prints `installed 0/0 packages` and exits 0 when its feed returns a 5xx —
and a CI job would then run its tests without the dependency, red for the wrong reason
or green with the coverage silently skipped (issue #162). A dependency whose check
cannot pass in the installing process (one that only works in a new shell, say) opts
out with `verify_install = false`. A blank check counts as no check: not verified.

So the worst case for one dependency is `(verify_retries + 1)` full install rounds —
each up to `n_commands * (retries + 1) * install_timeout` plus its command backoffs,
followed by its checks (`n_checks * DFLT_CHECK_TIMEOUT`) — plus the backoff waits
between rounds: with the defaults, a failing verify roughly doubles the install time.

`check` and `install` take a string or a list. A list item is either a command line
or a command in argv form (a list of strings, e.g.
`check.linux = [["dpkg", "-s", "unixodbc"], ["rpm", "-q", "unixODBC"]]`), which is
quoted into one command line for the platform’s shell. Checks are OR-ed (any passing
one means installed); install commands are AND-ed (run in order, all must succeed).

### Module Attributes

| [`SLOW_DEP_INSTALL_TIMEOUTS`](#wads.install_system_deps.SLOW_DEP_INSTALL_TIMEOUTS)   | Dependencies with a big dependency tree get a longer ceiling than the global default (a cold-cache `apt-get install ffmpeg` outlasts 300s).                                                                        |
|------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`RECIPE_PREFIX`](#wads.install_system_deps.RECIPE_PREFIX)               | An install command of the form `wads:<name>` names a recipe here, expanded into the commands the recipe builds from its defaults overridden by the dependency's `[tool.wads.ops.<dep>.recipe]` table (issue #160). |
| [`STATIC_FFMPEG_DEFAULTS`](#wads.install_system_deps.STATIC_FFMPEG_DEFAULTS)      | Static ffmpeg + ffprobe for linux64 (x86_64), checked against its sha256.                                                                                                                                          |
| [`DFLT_APT_LOCK_TIMEOUT`](#wads.install_system_deps.DFLT_APT_LOCK_TIMEOUT)       | Seconds apt waits for the dpkg lock before giving up (`-o DPkg::Lock::Timeout`).                                                                                                                                   |
| [`DFLT_KILL_GRACE`](#wads.install_system_deps.DFLT_KILL_GRACE)             | Seconds between SIGTERM and SIGKILL when a timed-out install is stopped.                                                                                                                                           |
| [`DFLT_VERIFY_RETRIES`](#wads.install_system_deps.DFLT_VERIFY_RETRIES)         | Extra install rounds for a dependency whose commands succeeded but whose declared `check` still fails afterwards (a package manager that reported success for nothing — e.g. Chocolatey on a feed 5xx).            |
| [`INSTALL_RECIPES`](#wads.install_system_deps.INSTALL_RECIPES)             | Recipes `install.<platform> = "wads:<name>"` may name; extend by adding to it.                                                                                                                                     |

### Functions

| [`check_if_installed`](#wads.install_system_deps.check_if_installed)(dep_name, check_cmds[, ...])   | Check if dependency is already installed using check commands.                  |
|----------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------|
| [`detect_platform`](#wads.install_system_deps.detect_platform)()                                 | Detect the current platform.                                                    |
| [`find_pyproject`](#wads.install_system_deps.find_pyproject)(path)                              | Find pyproject.toml file from path (file or directory).                         |
| [`install_and_verify`](#wads.install_system_deps.install_and_verify)(dep_name, install_cmds, ...)   | Install a dependency, then confirm it with its check commands.                  |
| [`install_dependency`](#wads.install_system_deps.install_dependency)(dep_name, install_cmds[, ...]) | Install a dependency using install commands.                                    |
| [`install_system_dependencies`](#wads.install_system_deps.install_system_dependencies)([...])                | Install system dependencies from pyproject.toml.                                |
| [`main`](#wads.install_system_deps.main)()                                            | CLI entry point.                                                                |
| [`read_system_deps`](#wads.install_system_deps.read_system_deps)(pyproject_path)                  | Read [tool.wads.ops.\*] sections from pyproject.toml.                           |
| [`static_ffmpeg_commands`](#wads.install_system_deps.static_ffmpeg_commands)(params)                    | Commands installing a static ffmpeg build: download, verify, extract, else apt. |
| [`with_apt_lock_timeout`](#wads.install_system_deps.with_apt_lock_timeout)(cmd, seconds)               | `cmd` with every `apt`/`apt-get` call told to wait `seconds` for the dpkg lock. |

### Classes

| [`InstallRecipe`](#wads.install_system_deps.InstallRecipe)(commands, defaults, platforms)   | A named install: builds commands from `defaults` overridden by parameters.   |
|-------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------|

### wads.install_system_deps.DFLT_APT_LOCK_TIMEOUT *= 120*

Seconds apt waits for the dpkg lock before giving up (`-o DPkg::Lock::Timeout`).

### wads.install_system_deps.DFLT_KILL_GRACE *= 5*

Seconds between SIGTERM and SIGKILL when a timed-out install is stopped.

### wads.install_system_deps.DFLT_VERIFY_RETRIES *= 1*

Extra install rounds for a dependency whose commands succeeded but whose declared
`check` still fails afterwards (a package manager that reported success for
nothing — e.g. Chocolatey on a feed 5xx).

### wads.install_system_deps.INSTALL_RECIPES *= {'static-ffmpeg': InstallRecipe(commands=<function static_ffmpeg_commands>, defaults={'url': 'https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-2026-09-30-13-08/ffmpeg-n8.1.3-9-g29e619e767-linux64-gpl-8.1.tar.xz', 'sha256': '97ce978979194b5cf7e06a5e68020dbdaa7a4f3294c5452b6a1bc347100dbb79', 'binaries': ['ffmpeg', 'ffprobe'], 'bin_dir': '/usr/local/bin', 'download_timeout': 120, 'apt_fallback': True}, platforms=('linux',))}*

Recipes `install.<platform> = "wads:<name>"` may name; extend by adding to it.

### *class* wads.install_system_deps.InstallRecipe(commands, defaults, platforms)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A named install: builds commands from `defaults` overridden by parameters.

`platforms` are the `install.<platform>` keys the recipe may be named under.

### wads.install_system_deps.RECIPE_PREFIX *= 'wads:'*

An install command of the form `wads:<name>` names a recipe here, expanded into
the commands the recipe builds from its defaults overridden by the dependency’s
`[tool.wads.ops.<dep>.recipe]` table (issue #160).

### wads.install_system_deps.SLOW_DEP_INSTALL_TIMEOUTS *= {'ffmpeg': 900}*

Dependencies with a big dependency tree get a longer ceiling than the global default
(a cold-cache `apt-get install ffmpeg` outlasts 300s). A declaration or an explicit
`default_install_timeout` still wins.

### wads.install_system_deps.STATIC_FFMPEG_DEFAULTS *= {'apt_fallback': True, 'bin_dir': '/usr/local/bin', 'binaries': ['ffmpeg', 'ffprobe'], 'download_timeout': 120, 'sha256': '97ce978979194b5cf7e06a5e68020dbdaa7a4f3294c5452b6a1bc347100dbb79', 'url': 'https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-2026-09-30-13-08/ffmpeg-n8.1.3-9-g29e619e767-linux64-gpl-8.1.tar.xz'}*

Static ffmpeg + ffprobe for linux64 (x86_64), checked against its sha256.
BtbN/FFmpeg-Builds keeps the last autobuild of each month for two years, so this
2026-09-30 pin expires around 2028-09: re-pin (url + sha256) before then.

### wads.install_system_deps.check_if_installed(dep_name, check_cmds, timeout=10)

Check if dependency is already installed using check commands.

* **Parameters:**
  * **dep_name** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Name of dependency
  * **check_cmds** (`any`) – Command(s) to check if installed (see `_as_commands()`)
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

### wads.install_system_deps.install_and_verify(dep_name, install_cmds, check_cmds, \*, verify_retries=1, backoff=5, sleep=None, is_installed=<function check_if_installed>, install=<function install_dependency>, \*\*install_kwargs)

Install a dependency, then confirm it with its check commands.

`install` runs `install_cmds` (with its own per-command retries); when it
reports success and `check_cmds` declares a command, `is_installed` must
agree, or the install is repeated up to `verify_retries` more times, after
`backoff` seconds (doubling), before failing. With no check declared the
install’s own exit status is all there is to go on. `backoff` and `sleep`
are also passed on to `install` for its per-command retries.

Returns `(success, error_message)` like [`install_dependency()`](#wads.install_system_deps.install_dependency).

* **Return type:**
  [`Tuple`](https://docs.python.org/3/library/typing.html#typing.Tuple)[[`bool`](https://docs.python.org/3/builtins/functions.html#bool), [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]

### wads.install_system_deps.install_dependency(dep_name, install_cmds, timeout=300, , retries=2, backoff=5, sleep=None, apt_lock_timeout=120)

Install a dependency using install commands.

* **Parameters:**
  * **dep_name** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Name of dependency
  * **install_cmds** (`any`) – Command(s) to install (see `_as_commands()`)
  * **timeout** ([`float`](https://docs.python.org/3/builtins/functions.html#float)) – Timeout in seconds for each command
  * **retries** ([`int`](https://docs.python.org/3/builtins/functions.html#int)) – Extra attempts for a command that fails or times out
  * **backoff** ([`float`](https://docs.python.org/3/builtins/functions.html#float)) – Seconds before the first retry; doubles for each further one
  * **sleep** – Wait function (default `time.sleep`; injectable for tests)
  * **apt_lock_timeout** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`float`](https://docs.python.org/3/builtins/functions.html#float)]) – Seconds each apt call waits for the dpkg lock (`None`: no flag)
* **Returns:**
  bool, error_message: Optional[str])
* **Return type:**
  [`Tuple`](https://docs.python.org/3/library/typing.html#typing.Tuple)[[`bool`](https://docs.python.org/3/builtins/functions.html#bool), [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]

### wads.install_system_deps.install_system_dependencies(pyproject_path='.', platform=None, skip_check=False, verbose=True, , default_install_timeout=None, default_install_retries=2, apt_lock_timeout=120, install=None, is_installed=None)

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
  * **install** – Runs one dependency’s install commands (`None`:
    [`install_dependency()`](#wads.install_system_deps.install_dependency)).
  * **is_installed** – Runs one dependency’s check commands, before installing and to
    verify the install (`None`: [`check_if_installed()`](#wads.install_system_deps.check_if_installed)).
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

### wads.install_system_deps.static_ffmpeg_commands(params)

Commands installing a static ffmpeg build: download, verify, extract, else apt.

A static build takes seconds; `apt-get install ffmpeg` pulls ~99 packages from
a runner mirror that sometimes crawls for 20+ minutes, which no timeout or retry
cures (issue #160). `params` overrides [`STATIC_FFMPEG_DEFAULTS`](#wads.install_system_deps.STATIC_FFMPEG_DEFAULTS): `url`
and `sha256` of a `.tar.xz` whose `*/bin/` holds `binaries`, extracted
into `bin_dir`. The archive goes to `$RUNNER_TEMP` (else `/tmp`) and is
removed afterwards, whatever happened. On a machine that is not x86_64, or when
the download, the checksum or the extraction fails, the command fails, or, when
`apt_fallback` is true, removes any partly extracted `binaries` and installs
ffmpeg from apt (`--no-install-recommends`) with a warning.

```pycon
>>> [cmd] = static_ffmpeg_commands({"apt_fallback": False})
>>> "sha256sum -c -" in cmd and "'*/bin/ffprobe'" in cmd and "apt-get" not in cmd
True
```

* **Return type:**
  [`List`](https://docs.python.org/3/library/typing.html#typing.List)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

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
