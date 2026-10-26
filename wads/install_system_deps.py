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
"""

import sys
import os
import subprocess
import time
import platform as platform_module
from pathlib import Path
from typing import Dict, List, Optional, Tuple
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
DFLT_CHECK_TIMEOUT = 10
# Extra attempts per failed install command, and the wait before the first retry
# (doubled for each further one). Transient mirror failures are the common cause.
DFLT_INSTALL_RETRIES = 2
DFLT_INSTALL_BACKOFF = 5


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


def check_if_installed(
    dep_name: str, check_cmds: any, timeout: float = DFLT_CHECK_TIMEOUT
) -> bool:
    """
    Check if dependency is already installed using check commands.

    Args:
        dep_name: Name of dependency
        check_cmds: Command(s) to check if installed (string, list, or empty)
        timeout: Timeout in seconds for check commands

    Returns:
        True if installed, False otherwise
    """
    # Normalize to list of commands
    if isinstance(check_cmds, str):
        commands = [check_cmds] if check_cmds.strip() else []
    elif isinstance(check_cmds, list):
        commands = [cmd for cmd in check_cmds if cmd]
    else:
        return False

    # Try each check command (OR logic)
    for check_cmd in commands:
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
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=False,  # Show output in real-time
                timeout=timeout,
            )
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
) -> Tuple[bool, Optional[str]]:
    """
    Install a dependency using install commands.

    Args:
        dep_name: Name of dependency
        install_cmds: Command(s) to install (string or list)
        timeout: Timeout in seconds for each command
        retries: Extra attempts for a command that fails or times out
        backoff: Seconds before the first retry; doubles for each further one
        sleep: Wait function (default ``time.sleep``; injectable for tests)

    Returns:
        (success: bool, error_message: Optional[str])
    """
    # Normalize to list of commands
    if isinstance(install_cmds, str):
        if not install_cmds.strip():
            return False, "Empty install command"
        commands = [install_cmds]
    elif isinstance(install_cmds, list):
        commands = [cmd for cmd in install_cmds if cmd]
        if not commands:
            return False, "Empty install command list"
    else:
        return False, "Invalid install command format"

    # Execute install commands (AND logic - all must succeed)
    for i, cmd in enumerate(commands, 1):
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


def install_system_dependencies(
    pyproject_path: str = ".",
    platform: Optional[str] = None,
    skip_check: bool = False,
    verbose: bool = True,
    *,
    default_install_timeout: float = DFLT_INSTALL_TIMEOUT,
    default_install_retries: int = DFLT_INSTALL_RETRIES,
) -> Tuple[int, int, int]:
    """
    Install system dependencies from pyproject.toml.

    Args:
        pyproject_path: Path to pyproject.toml or directory containing it
        platform: Platform to install for (linux/macos/windows), auto-detect if None
        skip_check: Skip checking if dependencies are already installed
        verbose: Print detailed progress
        default_install_timeout: Per-command install timeout (seconds) for
            dependencies that declare no ``install_timeout`` of their own.
        default_install_retries: Retries per failed install command for
            dependencies that declare no ``install_retries`` of their own.

    Returns:
        (installed_count, skipped_count, failed_count)
    """
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

    def timeout_for(dep_name, dep_config):
        return setting_for(
            dep_name,
            dep_config,
            "install_timeout",
            default_install_timeout,
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

    # Process each dependency
    installed_count = 0
    skipped_count = 0
    failed_count = 0

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

        # Check if already installed
        if not skip_check:
            check_cmds = dep_config.get("check", {}).get(platform)
            if check_cmds:
                if check_if_installed(dep_name, check_cmds):
                    if verbose:
                        print(f"✓ {dep_name} is already installed")
                    skipped_count += 1
                    continue

        # Get install commands
        install_cmds = dep_config.get("install", {}).get(platform)

        if not install_cmds:
            if verbose:
                print(f"Warning: No install command for {dep_name} on {platform}")
            continue

        # Install
        install_timeout = timeout_for(dep_name, dep_config)
        if verbose:
            print(
                f"\nInstalling {dep_name}... (timeout: {install_timeout}s per command)"
            )

        success, error = install_dependency(
            dep_name,
            install_cmds,
            install_timeout,
            retries=retries_for(dep_name, dep_config),
        )

        if success:
            if verbose:
                print(f"✓ {dep_name} installed successfully")
            installed_count += 1
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

    return installed_count, skipped_count, failed_count


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
        type=float,
        default=DFLT_INSTALL_TIMEOUT,
        metavar="SECONDS",
        help=(
            "Per-command install timeout for dependencies that declare no "
            f"install_timeout of their own (default: {DFLT_INSTALL_TIMEOUT})"
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
