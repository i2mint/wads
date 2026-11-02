"""
Install system dependencies from [tool.wads.ops.*] sections in pyproject.toml.

This script reads system dependency configurations and installs them on the appropriate platform.
It can be used as a standalone CLI tool or imported as a module.

Each ``[tool.wads.ops.<dep>]`` section may declare an ``install_timeout`` (seconds)
to raise the per-command ceiling for a dependency that is slow but healthy — a
cold-cache ``apt-get install ffmpeg`` on a GitHub runner is the motivating case.
Without a declaration the timeout stays at :data:`DFLT_INSTALL_TIMEOUT`::

    [tool.wads.ops.ffmpeg]
    install_timeout = 900
    install.linux = ["sudo apt-get update", "sudo apt-get install -y ffmpeg"]

The CLI's ``--install-timeout`` sets the fallback for dependencies that declare
none; a declaration always wins over it.

A failed or timed-out install command is retried with exponential backoff
(:data:`DFLT_INSTALL_RETRIES` extra attempts, :data:`DFLT_INSTALL_BACKOFF` seconds
before the first retry, doubling), because the usual cause on a hosted runner is a
transient apt mirror timeout that a raised ceiling does not cure. A dependency may
declare ``install_retries`` (``0`` disables retrying); the CLI's ``--install-retries``
sets the fallback. Worst case for a command that always fails is
``(retries + 1) * install_timeout`` plus the backoff waits. Commands are retried one at a time, so a successful
``apt-get update`` is not repeated when only the following install flaked.

An install command may name a wads recipe instead of spelling it out (issue #160)::

    [tool.wads.ops.ffmpeg]
    check.linux = "ffmpeg -version && ffprobe -version"
    install.linux = "wads:static-ffmpeg"

expands to :func:`static_ffmpeg_commands`: a pinned, sha256-checked static build in
seconds instead of a crawling apt mirror, with apt as the fallback (Linux x86_64 only;
another architecture goes straight to apt). Override its parameters (``url``,
``sha256``, ...) under ``[tool.wads.ops.ffmpeg.recipe]``; an unknown or mistyped
parameter fails the dependency. Running the binaries in the check (rather than
``which``) also catches a wrong-architecture or corrupt download.

An install whose commands all exit 0 is not trusted on that alone: when the dependency
declares a ``check.<platform>``, that check is re-run afterwards, and a dependency whose
check still fails is re-installed (:data:`DFLT_VERIFY_RETRIES` more rounds, each after a
backoff wait that starts at :data:`DFLT_INSTALL_BACKOFF` seconds and doubles) and then
reported as failed. Package managers do report success for installs that did nothing —
Chocolatey prints ``installed 0/0 packages`` and exits 0 when its feed returns a 5xx —
and a CI job would then run its tests without the dependency, red for the wrong reason
or green with the coverage silently skipped (issue #162). A dependency whose check
cannot pass in the installing process (one that only works in a new shell, say) opts
out with ``verify_install = false``. A blank check counts as no check: not verified.

So the worst case for one dependency is ``(verify_retries + 1)`` full install rounds —
each up to ``n_commands * (retries + 1) * install_timeout`` plus its command backoffs,
followed by its checks (``n_checks * DFLT_CHECK_TIMEOUT``) — plus the backoff waits
between rounds: with the defaults, a failing verify roughly doubles the install time.

``check`` and ``install`` take a string or a list. A list item is either a command line
or a command in argv form (a list of strings, e.g.
``check.linux = [["dpkg", "-s", "unixodbc"], ["rpm", "-q", "unixODBC"]]``), which is
quoted into one command line for the platform's shell. Checks are OR-ed (any passing
one means installed); install commands are AND-ed (run in order, all must succeed).
"""

import sys
import math
import os
import re
import shlex
import signal
import subprocess
import time
import platform as platform_module
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple
import argparse

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        print("ERROR: tomli package required for Python < 3.11", file=sys.stderr)
        print("Install with: pip install tomli", file=sys.stderr)
        sys.exit(1)


# Seconds allowed for a single command. Install commands get a generous ceiling
# (package managers fetch over the network); check commands are local and fast.
# Both are overridable — see `install_system_dependencies` and the CLI.
DFLT_INSTALL_TIMEOUT = 300
#: Dependencies with a big dependency tree get a longer ceiling than the global default
#: (a cold-cache ``apt-get install ffmpeg`` outlasts 300s). A declaration or an explicit
#: ``default_install_timeout`` still wins.
SLOW_DEP_INSTALL_TIMEOUTS = {"ffmpeg": 900}

#: An install command of the form ``wads:<name>`` names a recipe here, expanded into
#: the commands the recipe builds from its defaults overridden by the dependency's
#: ``[tool.wads.ops.<dep>.recipe]`` table (issue #160).
RECIPE_PREFIX = "wads:"
#: Static ffmpeg + ffprobe for linux64 (x86_64), checked against its sha256.
#: BtbN/FFmpeg-Builds keeps the last autobuild of each month for two years, so this
#: 2026-09-30 pin expires around 2028-09: re-pin (url + sha256) before then.
STATIC_FFMPEG_DEFAULTS = {
    "url": (
        "https://github.com/BtbN/FFmpeg-Builds/releases/download/"
        "autobuild-2026-09-30-13-08/ffmpeg-n8.1.3-9-g29e619e767-linux64-gpl-8.1.tar.xz"
    ),
    "sha256": "97ce978979194b5cf7e06a5e68020dbdaa7a4f3294c5452b6a1bc347100dbb79",
    "binaries": ["ffmpeg", "ffprobe"],
    "bin_dir": "/usr/local/bin",
    "download_timeout": 120,
    "apt_fallback": True,
}
#: Where the static ffmpeg archive is downloaded: a double-quoted shell word, so the
#: runner's shell expands ``RUNNER_TEMP`` (``/tmp`` outside GitHub Actions).
_STATIC_FFMPEG_ARCHIVE = '"${RUNNER_TEMP:-/tmp}/wads-static-ffmpeg.tar.xz"'
#: ``uname -m`` of the only architecture the static ffmpeg build runs on.
_STATIC_FFMPEG_ARCH = "x86_64"
#: Seconds apt waits for the dpkg lock before giving up (``-o DPkg::Lock::Timeout``).
DFLT_APT_LOCK_TIMEOUT = 120
#: Seconds between SIGTERM and SIGKILL when a timed-out install is stopped.
DFLT_KILL_GRACE = 5
DFLT_CHECK_TIMEOUT = 10
# Extra attempts per failed install command, and the wait before the first retry
# (doubled for each further one). Transient mirror failures are the common cause.
DFLT_INSTALL_RETRIES = 2
DFLT_INSTALL_BACKOFF = 5
#: Extra install rounds for a dependency whose commands succeeded but whose declared
#: ``check`` still fails afterwards (a package manager that reported success for
#: nothing — e.g. Chocolatey on a feed 5xx).
DFLT_VERIFY_RETRIES = 1


def find_pyproject(path: str) -> Path:
    """Find pyproject.toml file from path (file or directory)."""
    p = Path(path)
    if p.is_dir():
        return p / "pyproject.toml"
    return p


def detect_platform() -> str:
    """Detect the current platform."""
    system = platform_module.system().lower()
    if system == "linux":
        return "linux"
    elif system == "darwin":
        return "macos"
    elif system == "windows":
        return "windows"
    else:
        raise ValueError(f"Unknown platform: {system}")


def read_system_deps(pyproject_path: Path) -> Dict[str, dict]:
    """Read [tool.wads.ops.*] sections from pyproject.toml."""
    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)

    return data.get("tool", {}).get("wads", {}).get("ops", {})


def _as_commands(cmds) -> List[str]:
    """The command lines declared by ``cmds``; blank or malformed entries are dropped.

    A string is one command line; a list holds command lines and argv-form commands
    (lists of strings, quoted for the platform's shell); anything else declares none.

    >>> _as_commands("which ffmpeg")
    ['which ffmpeg']
    >>> _as_commands(["which ffmpeg", "  ", ["dpkg", "-s", "unixodbc"], [], 3])
    ['which ffmpeg', 'dpkg -s unixodbc']
    >>> _as_commands("   "), _as_commands([[]]), _as_commands(None)
    ([], [], [])
    """

    def command_line(item) -> Optional[str]:
        if isinstance(item, str):
            return item if item.strip() else None
        if isinstance(item, list) and item and all(isinstance(a, str) for a in item):
            join = subprocess.list2cmdline if os.name == "nt" else shlex.join
            return join(item)
        return None

    if isinstance(cmds, str):
        return [cmds] if cmds.strip() else []
    if not isinstance(cmds, list):
        return []
    return [line for line in map(command_line, cmds) if line]


def _platform_value(dep_config: dict, key: str, platform: str):
    """``dep_config[key][platform]``, or ``None`` when ``key`` is not a per-platform table.

    >>> _platform_value({"check": {"linux": "which x"}}, "check", "linux")
    'which x'
    >>> _platform_value({"check": "which x"}, "check", "linux") is None
    True
    """
    table = dep_config.get(key)
    return table.get(platform) if isinstance(table, dict) else None


def static_ffmpeg_commands(params: dict) -> List[str]:
    """Commands installing a static ffmpeg build: download, verify, extract, else apt.

    A static build takes seconds; ``apt-get install ffmpeg`` pulls ~99 packages from
    a runner mirror that sometimes crawls for 20+ minutes, which no timeout or retry
    cures (issue #160). ``params`` overrides :data:`STATIC_FFMPEG_DEFAULTS`: ``url``
    and ``sha256`` of a ``.tar.xz`` whose ``*/bin/`` holds ``binaries``, extracted
    into ``bin_dir``. The archive goes to ``$RUNNER_TEMP`` (else ``/tmp``) and is
    removed afterwards, whatever happened. On a machine that is not x86_64, or when
    the download, the checksum or the extraction fails, the command fails, or, when
    ``apt_fallback`` is true, removes any partly extracted ``binaries`` and installs
    ffmpeg from apt (``--no-install-recommends``) with a warning.

    >>> [cmd] = static_ffmpeg_commands({"apt_fallback": False})
    >>> "sha256sum -c -" in cmd and "'*/bin/ffprobe'" in cmd and "apt-get" not in cmd
    True
    """
    p = {**STATIC_FFMPEG_DEFAULTS, **params}
    q = shlex.quote
    archive = _STATIC_FFMPEG_ARCHIVE
    members = " ".join(q(f"*/bin/{name}") for name in p["binaries"])
    static = (
        f'[ "$(uname -m)" = {_STATIC_FFMPEG_ARCH} ]'
        f" && curl -fsSL --retry 2 --retry-all-errors --retry-delay 5 --connect-timeout 20"
        f" --max-time {p['download_timeout']} -o {archive} {q(p['url'])}"
        f" && printf '%s  %s\\n' {q(p['sha256'])} {archive} | sha256sum -c -"
        f" && sudo tar -xJf {archive} -C {q(p['bin_dir'])} --no-same-owner"
        f" --strip-components=2 --wildcards {members}"
    )
    if p["apt_fallback"]:
        installed = " ".join(q(f"{p['bin_dir']}/{name}") for name in p["binaries"])
        otherwise = (
            f"sudo rm -f {installed}"
            ' && echo "::warning::static ffmpeg not installed (not x86_64, or the'
            ' download, checksum or extraction failed); installing from apt (slow)"'
            " && sudo apt-get update"
            # --reinstall: if bin_dir is apt's own (/usr/bin), the rm above removed
            # files of an installed package, which a plain install would not restore.
            " && sudo apt-get install -y --reinstall --no-install-recommends ffmpeg"
        )
    else:
        otherwise = "false"
    return [f"if {static}; then rm -f {archive}; else rm -f {archive}; {otherwise}; fi"]


@dataclass(frozen=True)
class InstallRecipe:
    """A named install: builds commands from ``defaults`` overridden by parameters.

    ``platforms`` are the ``install.<platform>`` keys the recipe may be named under.
    ``min_timeout`` (seconds) floors the per-command install timeout of a dependency
    using the recipe unless it declares ``install_timeout`` itself, so the recipe's
    own worst case fits whatever the dependency is called (issue #181).
    """

    commands: Callable[[dict], List[str]]
    defaults: dict
    platforms: Tuple[str, ...]
    min_timeout: Optional[float] = None


#: Recipes ``install.<platform> = "wads:<name>"`` may name; extend by adding to it.
INSTALL_RECIPES = {
    # The apt fallback runs inside the same command, so the floor is apt's ffmpeg one.
    "static-ffmpeg": InstallRecipe(
        static_ffmpeg_commands,
        STATIC_FFMPEG_DEFAULTS,
        platforms=("linux",),
        min_timeout=SLOW_DEP_INSTALL_TIMEOUTS["ffmpeg"],
    ),
}

#: What a recipe parameter must be, keyed by the type of its default.
_RECIPE_PARAM_KINDS = {
    bool: ("a boolean", lambda v: isinstance(v, bool)),
    int: (
        "a positive integer",
        lambda v: isinstance(v, int) and not isinstance(v, bool) and v > 0,
    ),
    str: ("a non-empty string", lambda v: isinstance(v, str) and bool(v)),
    list: (
        "a non-empty list of strings",
        lambda v: (
            isinstance(v, list) and bool(v) and all(isinstance(x, str) for x in v)
        ),
    ),
}


def _validate_recipe_params(params, *, defaults: dict) -> None:
    """Raise ``ValueError`` unless ``params`` can override ``defaults``.

    Every key must be one of ``defaults``' and of the same kind as its default; a
    ``url`` override must come with its ``sha256`` when the recipe checks one.

    >>> _validate_recipe_params({"retries": 2}, defaults={"url": "u"})
    Traceback (most recent call last):
    ...
    ValueError: unknown recipe parameter(s) retries (known: url)
    >>> _validate_recipe_params({"n": "2"}, defaults={"n": 1})
    Traceback (most recent call last):
    ...
    ValueError: recipe parameter n must be a positive integer, got '2'
    """
    if not isinstance(params, dict):
        raise ValueError(f"recipe parameters must be a table, got {params!r}")
    unknown = sorted(set(params) - set(defaults))
    if unknown:
        raise ValueError(
            f"unknown recipe parameter(s) {', '.join(unknown)} "
            f"(known: {', '.join(sorted(defaults))})"
        )
    if "url" in params and "sha256" in defaults and "sha256" not in params:
        raise ValueError("a recipe url override needs its sha256 too")
    for key, value in params.items():
        kind, is_valid = _RECIPE_PARAM_KINDS[type(defaults[key])]
        if not is_valid(value):
            raise ValueError(f"recipe parameter {key} must be {kind}, got {value!r}")


def _recipe_timeout_floor(commands: List[str]) -> float:
    """The largest ``min_timeout`` of the recipes ``commands`` name (0 when none).

    >>> _recipe_timeout_floor(["echo hi"]), _recipe_timeout_floor(["wads:static-ffmpeg"])
    (0, 900)
    """
    floors = [
        recipe.min_timeout or 0
        for cmd in commands
        if cmd.strip().startswith(RECIPE_PREFIX)
        and (recipe := INSTALL_RECIPES.get(cmd.strip()[len(RECIPE_PREFIX) :]))
    ]
    return max(floors, default=0)


def _expand_recipes(commands: List[str], params, *, platform: str) -> List[str]:
    """``commands`` with each ``wads:<name>`` replaced by that recipe's commands.

    Raises ``ValueError`` for an unknown recipe, one that does not support
    ``platform``, or ``params`` it does not accept (see
    :func:`_validate_recipe_params`).

    >>> _expand_recipes(["echo hi"], {}, platform="linux")
    ['echo hi']
    >>> _expand_recipes(["wads:nope"], {}, platform="linux")
    Traceback (most recent call last):
    ...
    ValueError: unknown install recipe 'wads:nope' (known: static-ffmpeg)
    >>> _expand_recipes(["wads:static-ffmpeg"], {}, platform="macos")
    Traceback (most recent call last):
    ...
    ValueError: install recipe 'wads:static-ffmpeg' supports linux, not macos
    """
    expanded = []
    for cmd in commands:
        name = cmd.strip()
        if not name.startswith(RECIPE_PREFIX):
            expanded.append(cmd)
            continue
        recipe = INSTALL_RECIPES.get(name[len(RECIPE_PREFIX) :])
        if recipe is None:
            known = ", ".join(sorted(INSTALL_RECIPES))
            raise ValueError(f"unknown install recipe {name!r} (known: {known})")
        if platform not in recipe.platforms:
            raise ValueError(
                f"install recipe {name!r} supports "
                f"{', '.join(recipe.platforms)}, not {platform}"
            )
        _validate_recipe_params(params, defaults=recipe.defaults)
        expanded += recipe.commands(params)
    return expanded


def check_if_installed(
    dep_name: str, check_cmds: any, timeout: float = DFLT_CHECK_TIMEOUT
) -> bool:
    """
    Check if dependency is already installed using check commands.

    Args:
        dep_name: Name of dependency
        check_cmds: Command(s) to check if installed (see :func:`_as_commands`)
        timeout: Timeout in seconds for check commands

    Returns:
        True if installed, False otherwise
    """
    # Try each check command (OR logic)
    for check_cmd in _as_commands(check_cmds):
        try:
            result = subprocess.run(
                check_cmd, shell=True, capture_output=True, timeout=timeout
            )
            if result.returncode == 0:
                return True
        except Exception:
            # Check failed, continue to next
            pass

    return False


_APT_CALL_RE = re.compile(
    r"(?P<head>(?:^|&&|\|\||[;|(])\s*"
    r"(?:(?:sudo|env|time|nice)\s+(?:(?:-[uUgG]|--user|--group)\s+\S+\s+|-\S+\s+)*|\w+=\S*\s+)*)"
    r"(?P<apt>apt-get|apt)(?=\s)",
    re.MULTILINE,
)


def with_apt_lock_timeout(cmd: str, seconds: Optional[float]) -> str:
    """``cmd`` with every ``apt``/``apt-get`` call told to wait ``seconds`` for the dpkg lock.

    >>> with_apt_lock_timeout("sudo apt-get update && sudo apt-get install -y ffmpeg", 60)
    'sudo apt-get -o DPkg::Lock::Timeout=60 update && sudo apt-get -o DPkg::Lock::Timeout=60 install -y ffmpeg'
    >>> with_apt_lock_timeout("apt install -y apt-utils", None)
    'apt install -y apt-utils'
    """
    if not seconds or "dpkg::lock::timeout" in cmd.lower():
        return cmd
    return _APT_CALL_RE.sub(
        lambda m: f"{m['head']}{m['apt']} -o DPkg::Lock::Timeout={math.ceil(seconds)}",
        cmd,
    )


def _group_alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except (ProcessLookupError, PermissionError):
        # macOS reports EPERM for a group that holds only zombies; for root-owned
        # members we could not signal them anyway
        return False
    return True


def _kill_group(proc: subprocess.Popen, *, grace: float) -> None:
    """Stop ``proc`` and, on POSIX, everything in its session.

    SIGTERM first (``sudo`` relays it to a root-owned child that cannot be SIGKILLed
    through), then SIGKILL for whatever is still in the group after ``grace`` seconds.
    The shell exiting early proves nothing about its descendants, so the wait is on the
    group, not on ``proc``.
    """
    if os.name != "posix":
        proc.kill()
    else:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
        deadline = time.monotonic() + grace
        while _group_alive(proc.pid) and time.monotonic() < deadline:
            proc.poll()  # reap the shell so it does not linger as a zombie in the group
            time.sleep(0.05)
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    proc.wait()


def _run_shell(
    cmd: str, *, timeout: float, kill_grace: float = DFLT_KILL_GRACE
) -> subprocess.CompletedProcess:
    """Run a shell command with output streaming; on timeout or interrupt kill its process tree.

    ``subprocess.run(shell=True, timeout=...)`` kills only the shell, leaving e.g. a
    ``sudo apt-get`` child holding the dpkg lock, which would make every retry fail.
    On POSIX the command gets its own session so the whole group can be signalled
    (on Windows only the shell is killed).
    """
    with subprocess.Popen(
        cmd, shell=True, start_new_session=os.name == "posix"
    ) as proc:
        try:
            proc.communicate(timeout=timeout)
        except (
            BaseException
        ):  # TimeoutExpired, or Ctrl-C: the child no longer shares our tty group
            _kill_group(proc, grace=kill_grace)
            raise
        return subprocess.CompletedProcess(cmd, proc.returncode)


def _run_with_retries(
    cmd: str,
    *,
    timeout: float,
    retries: int,
    backoff: float,
    sleep=None,
) -> Optional[str]:
    """Run one shell command, retrying failures; return an error message or None."""
    if retries < 0:
        raise ValueError(f"retries must be >= 0, got {retries}")
    error = None
    for attempt in range(retries + 1):
        if attempt:
            wait = backoff * 2 ** (attempt - 1)
            print(
                f"  Retry {attempt}/{retries} in {wait:g}s (previous attempt: {error})"
            )
            (sleep or time.sleep)(wait)  # looked up late so tests can patch it
        try:
            result = _run_shell(cmd, timeout=timeout)
            if result.returncode == 0:
                return None
            error = f"Exit code {result.returncode}"
        except subprocess.TimeoutExpired:
            # Name the command: a multi-command install (e.g. an apt update
            # followed by an apt install) is otherwise indistinguishable in the log.
            error = f"Timeout after {timeout}s running: {cmd}"
        except Exception as e:
            error = str(e)
    return error


def install_dependency(
    dep_name: str,
    install_cmds: any,
    timeout: float = DFLT_INSTALL_TIMEOUT,
    *,
    retries: int = DFLT_INSTALL_RETRIES,
    backoff: float = DFLT_INSTALL_BACKOFF,
    sleep=None,
    apt_lock_timeout: Optional[float] = DFLT_APT_LOCK_TIMEOUT,
) -> Tuple[bool, Optional[str]]:
    """
    Install a dependency using install commands.

    Args:
        dep_name: Name of dependency
        install_cmds: Command(s) to install (see :func:`_as_commands`)
        timeout: Timeout in seconds for each command
        retries: Extra attempts for a command that fails or times out
        backoff: Seconds before the first retry; doubles for each further one
        sleep: Wait function (default ``time.sleep``; injectable for tests)
        apt_lock_timeout: Seconds each apt call waits for the dpkg lock (``None``: no flag)

    Returns:
        (success: bool, error_message: Optional[str])
    """
    commands = _as_commands(install_cmds)
    if not commands:
        if isinstance(install_cmds, str):
            return False, "Empty install command"
        if isinstance(install_cmds, list):
            return False, "Empty install command list"
        return False, "Invalid install command format"

    # Execute install commands (AND logic - all must succeed)
    for i, cmd in enumerate(commands, 1):
        cmd = with_apt_lock_timeout(cmd, apt_lock_timeout)
        if len(commands) > 1:
            print(f"  Step {i}/{len(commands)}: {cmd}")
        else:
            print(f"  Command: {cmd}")

        error = _run_with_retries(
            cmd, timeout=timeout, retries=retries, backoff=backoff, sleep=sleep
        )
        if error:
            return False, error

    return True, None


def install_and_verify(
    dep_name: str,
    install_cmds: any,
    check_cmds: any,
    *,
    verify_retries: int = DFLT_VERIFY_RETRIES,
    backoff: float = DFLT_INSTALL_BACKOFF,
    sleep=None,
    is_installed=check_if_installed,
    install=install_dependency,
    **install_kwargs,
) -> Tuple[bool, Optional[str]]:
    """Install a dependency, then confirm it with its check commands.

    ``install`` runs ``install_cmds`` (with its own per-command retries); when it
    reports success and ``check_cmds`` declares a command, ``is_installed`` must
    agree, or the install is repeated up to ``verify_retries`` more times, after
    ``backoff`` seconds (doubling), before failing. With no check declared the
    install's own exit status is all there is to go on. ``backoff`` and ``sleep``
    are also passed on to ``install`` for its per-command retries.

    Returns ``(success, error_message)`` like :func:`install_dependency`.
    """
    if verify_retries < 0:
        raise ValueError(f"verify_retries must be >= 0, got {verify_retries}")
    checks = _as_commands(check_cmds)
    for attempt in range(verify_retries + 1):
        if attempt:
            wait = backoff * 2 ** (attempt - 1)
            print(
                f"  Re-installing {dep_name} ({attempt}/{verify_retries}) in {wait:g}s"
            )
            (sleep or time.sleep)(wait)  # looked up late so tests can patch it
        success, error = install(
            dep_name, install_cmds, backoff=backoff, sleep=sleep, **install_kwargs
        )
        if not success or not checks or is_installed(dep_name, checks):
            return success, error
        error = "install commands exited 0 but the check still fails: " + " || ".join(
            checks
        )
        print(f"  {error}")
    return False, error


def install_system_dependencies(
    pyproject_path: str = ".",
    platform: Optional[str] = None,
    skip_check: bool = False,
    verbose: bool = True,
    *,
    default_install_timeout: Optional[float] = None,
    default_install_retries: int = DFLT_INSTALL_RETRIES,
    apt_lock_timeout: Optional[float] = DFLT_APT_LOCK_TIMEOUT,
    install=None,
    is_installed=None,
) -> Tuple[int, int, int]:
    """
    Install system dependencies from pyproject.toml.

    Args:
        pyproject_path: Path to pyproject.toml or directory containing it
        platform: Platform to install for (linux/macos/windows), auto-detect if None
        skip_check: Skip checking if dependencies are already installed
        verbose: Print detailed progress
        default_install_timeout: Per-command install timeout (seconds) for
            dependencies that declare no ``install_timeout`` of their own. ``None``:
            :data:`SLOW_DEP_INSTALL_TIMEOUTS` for known-slow ones, else
            :data:`DFLT_INSTALL_TIMEOUT`.
        apt_lock_timeout: Seconds each apt call waits for the dpkg lock (``None``: no flag).
        default_install_retries: Retries per failed install command for
            dependencies that declare no ``install_retries`` of their own.
        install: Runs one dependency's install commands (``None``:
            :func:`install_dependency`).
        is_installed: Runs one dependency's check commands, before installing and to
            verify the install (``None``: :func:`check_if_installed`).

    Returns:
        (installed_count, skipped_count, failed_count)
    """
    if apt_lock_timeout is not None and apt_lock_timeout < 0:
        raise ValueError(f"apt_lock_timeout must be >= 0, got {apt_lock_timeout}")
    # Fail before any output rather than at the first dependency
    if default_install_retries < 0:
        raise ValueError(
            f"default_install_retries must be >= 0, got {default_install_retries}"
        )
    if default_install_timeout is not None and default_install_timeout <= 0:
        raise ValueError(
            f"default_install_timeout must be > 0, got {default_install_timeout}"
        )
    # Resolved now, not at definition time, so patching the module still takes effect
    install = install or install_dependency
    is_installed = is_installed or check_if_installed

    # Find pyproject.toml
    try:
        pyproject = find_pyproject(pyproject_path)
    except Exception as e:
        if verbose:
            print(f"Error finding pyproject.toml: {e}", file=sys.stderr)
        return 0, 0, 1

    if not pyproject.exists():
        if verbose:
            print(f"Warning: pyproject.toml not found at {pyproject}", file=sys.stderr)
        return 0, 0, 0

    # Detect platform
    if platform is None:
        try:
            platform = detect_platform()
        except ValueError as e:
            if verbose:
                print(f"Warning: {e}", file=sys.stderr)
            return 0, 0, 0

    if verbose:
        print(f"Installing system dependencies for {platform}")
        print(f"Reading from: {pyproject}")

    # Read dependencies
    try:
        ops = read_system_deps(pyproject)
    except Exception as e:
        if verbose:
            print(f"Error reading pyproject.toml: {e}", file=sys.stderr)
        return 0, 0, 1

    if not ops:
        if verbose:
            print("No [tool.wads.ops.*] sections found in pyproject.toml")
        return 0, 0, 0

    if verbose:
        print(f"Found {len(ops)} system dependencies\n")

    def setting_for(dep_name: str, dep_config: dict, key: str, default, is_valid):
        """A dep's own ``key`` if valid, else ``default``.

        An invalid value is reported and ignored rather than raised: a typo in
        pyproject.toml should not take down the whole install step, it should
        degrade to the default.
        """
        declared = dep_config.get(key)
        if declared is None:
            return default
        if isinstance(declared, bool) or not is_valid(declared):
            if verbose:
                print(
                    f"Warning: ignoring invalid {key}={declared!r} for "
                    f"{dep_name}; using {default}",
                    file=sys.stderr,
                )
            return default
        return declared

    def fallback_timeout_for(dep_name):
        if default_install_timeout is not None:
            return default_install_timeout
        return SLOW_DEP_INSTALL_TIMEOUTS.get(dep_name, DFLT_INSTALL_TIMEOUT)

    def timeout_for(dep_name, dep_config, *, floor=0):
        return setting_for(
            dep_name,
            dep_config,
            "install_timeout",
            max(fallback_timeout_for(dep_name), floor),
            lambda v: isinstance(v, (int, float)) and v > 0,
        )

    def retries_for(dep_name, dep_config):
        return setting_for(
            dep_name,
            dep_config,
            "install_retries",
            default_install_retries,
            lambda v: isinstance(v, int) and v >= 0,
        )

    def verify_for(dep_name, dep_config):
        declared = dep_config.get("verify_install", True)
        if isinstance(declared, bool):
            return declared
        if verbose:
            print(
                f"Warning: ignoring invalid verify_install={declared!r} for "
                f"{dep_name}; using True",
                file=sys.stderr,
            )
        return True

    # Process each dependency
    installed_count = 0
    skipped_count = 0
    failed_count = 0
    unverified = []  # installed with no check to confirm it

    for dep_name, dep_config in ops.items():
        if verbose:
            print(f"{'=' * 70}")
            print(f"Dependency: {dep_name}")

            description = dep_config.get("description", "")
            if description:
                print(f"Description: {description}")

            url = dep_config.get("url", "")
            if url:
                print(f"URL: {url}")

        check_cmds = _as_commands(_platform_value(dep_config, "check", platform))

        # Configuration errors fail the dependency before the pre-check, so one is
        # reported even on a machine that already has the dependency (issue #181).
        # A non-table `install` is a config error, not "nothing to install here":
        # failing it keeps a typo from going green silently.
        if not isinstance(dep_config.get("install", {}), dict):
            if verbose:
                print(
                    f"✗ {dep_name}: install must be a per-platform table "
                    f"(install.{platform} = ...), got "
                    f"{type(dep_config['install']).__name__}",
                    file=sys.stderr,
                )
            failed_count += 1
            continue
        declared_cmds = _as_commands(_platform_value(dep_config, "install", platform))
        try:
            install_cmds = _expand_recipes(
                declared_cmds, dep_config.get("recipe", {}), platform=platform
            )
        except ValueError as e:
            if verbose:
                print(f"✗ {dep_name}: {e}", file=sys.stderr)
            failed_count += 1
            continue

        # Check if already installed
        if not skip_check and check_cmds and is_installed(dep_name, check_cmds):
            if verbose:
                print(f"✓ {dep_name} is already installed")
            skipped_count += 1
            continue

        if not install_cmds:
            if verbose:
                print(f"Warning: No install command for {dep_name} on {platform}")
            continue

        # Install
        install_timeout = timeout_for(
            dep_name, dep_config, floor=_recipe_timeout_floor(declared_cmds)
        )
        if verbose:
            print(
                f"\nInstalling {dep_name}... (timeout: {install_timeout}s per command)"
            )

        verify = verify_for(dep_name, dep_config)
        success, error = install_and_verify(
            dep_name,
            install_cmds,
            check_cmds if verify else [],
            timeout=install_timeout,
            retries=retries_for(dep_name, dep_config),
            apt_lock_timeout=apt_lock_timeout,
            install=install,
            is_installed=is_installed,
        )

        if success:
            if verbose:
                print(f"✓ {dep_name} installed successfully")
            installed_count += 1
            if verify and not check_cmds:
                unverified.append(dep_name)
        else:
            if verbose:
                print(f"✗ Installation failed for {dep_name}: {error}", file=sys.stderr)
            failed_count += 1

        # Show note if present
        note = dep_config.get("note")
        if note and verbose:
            print(f"Note: {note}")

        if verbose:
            print()  # Blank line between deps

    # Summary
    if verbose:
        print(f"{'=' * 70}")
        print("SUMMARY")
        print(f"{'=' * 70}")
        print(f"✓ Installed: {installed_count}")
        print(f"⊘ Already present: {skipped_count}")
        if failed_count > 0:
            print(f"✗ Failed: {failed_count}")
        if unverified:
            print(f"Not verified (no check.{platform}): {', '.join(unverified)}")

    return installed_count, skipped_count, failed_count


def _positive_float(text: str) -> float:
    """argparse type: a float > 0."""
    value = float(text)
    if value <= 0:
        raise argparse.ArgumentTypeError(f"must be > 0, got {value}")
    return value


def _non_negative_int(text: str) -> int:
    """argparse type: an int >= 0."""
    value = int(text)
    if value < 0:
        raise argparse.ArgumentTypeError(f"must be >= 0, got {value}")
    return value


def main():
    """CLI entry point."""
    # The progress output uses non-ASCII markers (✓, ✗, ⊘). On Windows CI
    # runners the console defaults to cp1252, which can't encode them and raises
    # UnicodeEncodeError mid-run. Force UTF-8 so the output is portable.
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass  # non-reconfigurable stream (e.g. already-wrapped) — leave as-is

    parser = argparse.ArgumentParser(
        description="Install system dependencies from [tool.wads.ops.*] in pyproject.toml"
    )
    parser.add_argument(
        "pyproject_path",
        nargs="?",
        default=".",
        help="Path to pyproject.toml file or directory containing it (default: current directory)",
    )
    parser.add_argument(
        "--platform",
        choices=["linux", "macos", "windows"],
        help="Platform to install for (default: auto-detect)",
    )
    parser.add_argument(
        "--skip-check",
        action="store_true",
        help="Skip checking if dependencies are already installed",
    )
    parser.add_argument(
        "--quiet", action="store_true", help="Suppress output except errors"
    )
    parser.add_argument(
        "--install-timeout",
        type=_positive_float,
        default=None,
        metavar="SECONDS",
        help=(
            "Per-command install timeout for dependencies that declare no "
            f"install_timeout of their own (default: {DFLT_INSTALL_TIMEOUT}; "
            f"{', '.join(SLOW_DEP_INSTALL_TIMEOUTS)} get longer)"
        ),
    )

    parser.add_argument(
        "--install-retries",
        type=_non_negative_int,
        default=DFLT_INSTALL_RETRIES,
        metavar="N",
        help=(
            "Retries (with exponential backoff) of a failed install command, for "
            "dependencies that declare no install_retries of their own "
            f"(default: {DFLT_INSTALL_RETRIES})"
        ),
    )

    args = parser.parse_args()

    installed, skipped, failed = install_system_dependencies(
        pyproject_path=args.pyproject_path,
        platform=args.platform,
        skip_check=args.skip_check,
        verbose=not args.quiet,
        default_install_timeout=args.install_timeout,
        default_install_retries=args.install_retries,
    )

    # Exit with error if any failed
    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()
