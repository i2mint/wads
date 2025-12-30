"""
Install system dependencies from [tool.wads.ops.*] sections in pyproject.toml.

This script reads system dependency configurations and installs them on the appropriate platform.
It can be used as a standalone CLI tool or imported as a module.
"""

import sys
import os
import subprocess
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


def check_if_installed(dep_name: str, check_cmds: any, timeout: int = 10) -> bool:
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


def install_dependency(
    dep_name: str, install_cmds: any, timeout: int = 300
) -> Tuple[bool, Optional[str]]:
    """
    Install a dependency using install commands.

    Args:
        dep_name: Name of dependency
        install_cmds: Command(s) to install (string or list)
        timeout: Timeout in seconds for each command

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

        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=False,  # Show output in real-time
                timeout=timeout,
            )

            if result.returncode != 0:
                return False, f"Exit code {result.returncode}"

        except subprocess.TimeoutExpired:
            return False, f"Timeout after {timeout}s"
        except Exception as e:
            return False, str(e)

    return True, None


def install_system_dependencies(
    pyproject_path: str = ".",
    platform: Optional[str] = None,
    skip_check: bool = False,
    verbose: bool = True,
) -> Tuple[int, int, int]:
    """
    Install system dependencies from pyproject.toml.

    Args:
        pyproject_path: Path to pyproject.toml or directory containing it
        platform: Platform to install for (linux/macos/windows), auto-detect if None
        skip_check: Skip checking if dependencies are already installed
        verbose: Print detailed progress

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
        if verbose:
            print(f"\nInstalling {dep_name}...")

        success, error = install_dependency(dep_name, install_cmds)

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


def main():
    """CLI entry point."""
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

    args = parser.parse_args()

    installed, skipped, failed = install_system_dependencies(
        pyproject_path=args.pyproject_path,
        platform=args.platform,
        skip_check=args.skip_check,
        verbose=not args.quiet,
    )

    # Exit with error if any failed
    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()
