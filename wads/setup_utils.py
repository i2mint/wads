"""
Utilities for setting up packages based on pyproject.toml configuration.

This module provides tools for users to:
- Install Python dependencies with various options
- Install system dependencies based on OS and toml specs
- Validate environment variables
- Diagnose missing dependencies and provide instructions
"""

from typing import Optional, List, Dict, Set, Tuple
from pathlib import Path
import subprocess
import sys
import platform
import importlib
import warnings
from dataclasses import dataclass

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        raise ImportError("tomli package required for Python < 3.11")

from wads.ci_config import CIConfig


@dataclass
class InstallResult:
    """Result of an installation attempt."""

    success: bool
    package_name: str
    message: str
    command_executed: Optional[str] = None


@dataclass
class DiagnosticResult:
    """Result of dependency diagnostics."""

    missing_python_deps: List[str]
    missing_system_deps: List[Dict[str, str]]
    missing_env_vars: List[str]
    warnings: List[str]
    recommendations: List[str]


def get_current_platform() -> str:
    """
    Get current platform identifier (linux, macos, windows).

    Returns:
        Platform string compatible with wads configuration
    """
    system = platform.system().lower()
    if system == "darwin":
        return "macos"
    elif system in ("linux", "windows"):
        return system
    else:
        warnings.warn(f"Unknown platform: {system}, defaulting to 'linux'")
        return "linux"


def is_package_importable(package_name: str) -> bool:
    """
    Check if a Python package can be imported.

    Args:
        package_name: Name of the package to check

    Returns:
        True if the package is importable
    """
    # Handle common package name variations
    # e.g., "scikit-learn" -> "sklearn", "pillow" -> "PIL"
    import_name_map = {
        "scikit-learn": "sklearn",
        "pillow": "PIL",
        "pyyaml": "yaml",
        "python-dateutil": "dateutil",
    }

    import_name = import_name_map.get(package_name.lower(), package_name)

    # Try the mapped name first, then the package name as-is
    for name in [import_name, package_name]:
        try:
            importlib.import_module(name.replace("-", "_"))
            return True
        except (ImportError, ModuleNotFoundError):
            pass

    return False


def get_installed_pip_packages() -> Set[str]:
    """
    Get set of installed pip package names.

    Returns:
        Set of installed package names (lowercase)
    """
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "list", "--format=freeze"],
            capture_output=True,
            text=True,
            check=True,
        )
        packages = set()
        for line in result.stdout.splitlines():
            if "==" in line:
                package_name = line.split("==")[0].lower()
                packages.add(package_name)
        return packages
    except subprocess.CalledProcessError:
        return set()


def install_python_dependencies(
    pyproject_path: str | Path,
    exclude: Optional[List[str]] = None,
    check_importable: bool = True,
    upgrade: bool = False,
    allow_downgrade: bool = False,
    extras: Optional[List[str]] = None,
    dry_run: bool = False,
    verbose: bool = True,
) -> List[InstallResult]:
    """
    Install Python dependencies from pyproject.toml.

    Args:
        pyproject_path: Path to pyproject.toml or directory containing it
        exclude: List of package names to exclude from installation
        check_importable: Only install if package is not already importable
        upgrade: Pass --upgrade flag to pip
        allow_downgrade: Allow pip to downgrade packages (adds --force-reinstall)
        extras: List of extras to install (e.g., ['dev', 'test'])
        dry_run: If True, only show what would be installed
        verbose: Print detailed progress information

    Returns:
        List of InstallResult objects
    """
    pyproject_path = Path(pyproject_path)
    if pyproject_path.is_dir():
        pyproject_path = pyproject_path / "pyproject.toml"

    if not pyproject_path.exists():
        raise FileNotFoundError(f"pyproject.toml not found at {pyproject_path}")

    # Parse pyproject.toml
    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)

    # Get dependencies
    project = data.get("project", {})
    dependencies = project.get("dependencies", [])
    optional_deps = project.get("optional-dependencies", {})

    # Add extras if specified
    if extras:
        for extra in extras:
            if extra in optional_deps:
                dependencies.extend(optional_deps[extra])

    # Filter out excluded packages
    exclude_set = set((exclude or []))
    to_install = [
        dep
        for dep in dependencies
        if dep.split("[")[0].split(">=")[0].split("==")[0].strip() not in exclude_set
    ]

    results = []
    installed_packages = get_installed_pip_packages() if check_importable else set()

    for dep_spec in to_install:
        # Extract package name from dependency spec
        package_name = (
            dep_spec.split("[")[0]
            .split(">=")[0]
            .split("==")[0]
            .split(">")[0]
            .split("<")[0]
            .split("!")[0]
            .strip()
        )

        # Check if already available
        if check_importable:
            if is_package_importable(package_name):
                if verbose:
                    print(f"✓ {package_name} already available (importable)")
                results.append(
                    InstallResult(
                        success=True,
                        package_name=package_name,
                        message="Already importable",
                    )
                )
                continue

            # Also check pip list
            if package_name.lower() in installed_packages:
                if not upgrade:
                    if verbose:
                        print(f"✓ {package_name} already installed")
                    results.append(
                        InstallResult(
                            success=True,
                            package_name=package_name,
                            message="Already installed",
                        )
                    )
                    continue

        # Build install command
        cmd = [sys.executable, "-m", "pip", "install"]

        if upgrade:
            cmd.append("--upgrade")

        if allow_downgrade:
            cmd.append("--force-reinstall")

        cmd.append(dep_spec)

        if dry_run:
            if verbose:
                print(f"Would install: {dep_spec}")
                print(f"  Command: {' '.join(cmd)}")
            results.append(
                InstallResult(
                    success=True,
                    package_name=package_name,
                    message="Dry run - would install",
                    command_executed=" ".join(cmd),
                )
            )
            continue

        # Execute installation
        if verbose:
            print(f"Installing {dep_spec}...")

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            if verbose:
                print(f"✓ {package_name} installed successfully")
            results.append(
                InstallResult(
                    success=True,
                    package_name=package_name,
                    message="Installed successfully",
                    command_executed=" ".join(cmd),
                )
            )
        except subprocess.CalledProcessError as e:
            if verbose:
                print(f"✗ Failed to install {package_name}")
                print(f"  Error: {e.stderr}")
            results.append(
                InstallResult(
                    success=False,
                    package_name=package_name,
                    message=f"Installation failed: {e.stderr}",
                    command_executed=" ".join(cmd),
                )
            )

    return results


def check_system_dependency(
    dep_name: str, dep_ops: Dict, platform: str, verbose: bool = True
) -> bool:
    """
    Check if a system dependency is installed using check commands.

    Args:
        dep_name: Simplified dependency name
        dep_ops: Operational metadata for the dependency
        platform: Platform identifier (linux, macos, windows)
        verbose: Print check attempts

    Returns:
        True if dependency is installed (or no check command available)
    """
    check_section = dep_ops.get("check", {})
    check_cmds = check_section.get(platform)

    if not check_cmds:
        # No check command available
        return None  # Unknown status

    # Normalize to list of lists
    if isinstance(check_cmds, str):
        check_cmds = [[check_cmds]]
    elif isinstance(check_cmds, list) and check_cmds and isinstance(check_cmds[0], str):
        # Single command as list of strings: ["dpkg", "-s", "pkg"]
        check_cmds = [check_cmds]

    # Try each check command (any success means installed)
    for cmd in check_cmds:
        try:
            if verbose:
                print(f"  Checking with: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, check=False)
            if result.returncode == 0:
                return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue

    return False


def install_system_dependencies(
    pyproject_path: str | Path,
    platform: Optional[str] = None,
    check_first: bool = True,
    dry_run: bool = False,
    verbose: bool = True,
    interactive: bool = True,
) -> List[InstallResult]:
    """
    Install system dependencies based on pyproject.toml configuration.

    This is a wrapper around wads.install_system_deps module.

    Args:
        pyproject_path: Path to pyproject.toml or directory containing it
        platform: Platform identifier (auto-detected if None)
        check_first: Use check commands to verify if already installed (ignored in dry_run)
        dry_run: If True, only show what would be installed
        verbose: Print detailed progress information
        interactive: Ask for confirmation before installing (not yet implemented)

    Returns:
        List of InstallResult objects
    """
    from wads.install_system_deps import (
        install_system_dependencies as _install_system_deps,
        read_system_deps,
        find_pyproject,
    )

    pyproject_path = Path(pyproject_path)

    if dry_run:
        # For dry run, just read and display what would be installed
        try:
            pyproject = find_pyproject(str(pyproject_path))
            ops = read_system_deps(pyproject)

            results = []
            for dep_name, dep_config in ops.items():
                description = dep_config.get("description", "No description")
                results.append(
                    InstallResult(
                        success=True,
                        package_name=dep_name,
                        message=f"Would install: {description}",
                    )
                )
                if verbose:
                    print(f"Would install {dep_name}: {description}")

            return results
        except Exception as e:
            return [InstallResult(success=False, package_name="N/A", message=str(e))]

    # Call the new standalone installer
    installed, skipped, failed = _install_system_deps(
        pyproject_path=str(pyproject_path),
        platform=platform,
        skip_check=not check_first,
        verbose=verbose,
    )

    # Convert to InstallResult objects for compatibility
    results = []

    # We don't have detailed per-package results from the new installer,
    # so we create summary results
    if installed > 0:
        results.append(
            InstallResult(
                success=True,
                package_name=f"{installed} packages",
                message="Successfully installed",
            )
        )

    if skipped > 0:
        results.append(
            InstallResult(
                success=True,
                package_name=f"{skipped} packages",
                message="Already installed",
            )
        )

    if failed > 0:
        results.append(
            InstallResult(
                success=False,
                package_name=f"{failed} packages",
                message="Installation failed",
            )
        )

    return results


def check_environment_variables(
    pyproject_path: str | Path, verbose: bool = True
) -> Dict[str, Optional[str]]:
    """
    Check required environment variables from pyproject.toml.

    Args:
        pyproject_path: Path to pyproject.toml or directory containing it
        verbose: Print warnings for missing variables

    Returns:
        Dict mapping variable names to their values (None if missing)
    """
    import os

    pyproject_path = Path(pyproject_path)
    if pyproject_path.is_dir():
        pyproject_path = pyproject_path / "pyproject.toml"

    if not pyproject_path.exists():
        raise FileNotFoundError(f"pyproject.toml not found at {pyproject_path}")

    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)

    config = CIConfig(data)

    required_vars = config.env_vars_required
    default_vars = config.env_vars_defaults

    results = {}

    if verbose and required_vars:
        print("\nChecking required environment variables:")

    for var_name in required_vars:
        value = os.environ.get(var_name)
        results[var_name] = value

        if verbose:
            if value:
                print(f"  ✓ {var_name} is set")
            else:
                print(f"  ✗ {var_name} is NOT set")
                if var_name in default_vars:
                    print(f"    Default value available: {default_vars[var_name]}")

    return results


def diagnose_setup(
    pyproject_path: str | Path,
    check_python: bool = True,
    check_system: bool = True,
    check_env: bool = True,
    platform: Optional[str] = None,
) -> DiagnosticResult:
    """
    Diagnose missing dependencies and configuration issues.

    Args:
        pyproject_path: Path to pyproject.toml or directory containing it
        check_python: Check Python dependencies
        check_system: Check system dependencies
        check_env: Check environment variables
        platform: Platform identifier (auto-detected if None)

    Returns:
        DiagnosticResult with comprehensive analysis
    """
    import os

    pyproject_path = Path(pyproject_path)
    if pyproject_path.is_dir():
        pyproject_path = pyproject_path / "pyproject.toml"

    if not pyproject_path.exists():
        raise FileNotFoundError(f"pyproject.toml not found at {pyproject_path}")

    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)

    config = CIConfig(data)

    if platform is None:
        platform = get_current_platform()

    missing_python = []
    missing_system = []
    missing_env = []
    warnings_list = []
    recommendations = []

    # Check Python dependencies
    if check_python:
        project = data.get("project", {})
        dependencies = project.get("dependencies", [])

        for dep_spec in dependencies:
            package_name = dep_spec.split("[")[0].split(">=")[0].split("==")[0].strip()
            if not is_package_importable(package_name):
                missing_python.append(package_name)

    # Check system dependencies
    if check_system:
        ops = config.ops

        for dep_name, dep_config in ops.items():
            # Check if installed
            installed = check_system_dependency(
                dep_name, dep_config, platform, verbose=False
            )

            if installed is False:
                # Definitely not installed
                install_cmd = dep_config.get("install", {}).get(platform)
                missing_system.append(
                    {
                        "name": dep_name,
                        "description": dep_config.get("description", "No description"),
                        "url": dep_config.get("url", ""),
                        "install_command": install_cmd,
                        "alternatives": dep_config.get("alternatives", []),
                        "note": dep_config.get("note", ""),
                    }
                )
            elif installed is None:
                # Cannot verify
                warnings_list.append(
                    f"Cannot verify if {dep_name} is installed (no check command for {platform})"
                )

    # Check environment variables
    if check_env:
        required_vars = config.env_vars_required

        for var_name in required_vars:
            if var_name not in os.environ:
                missing_env.append(var_name)

    # Generate recommendations
    if missing_python:
        recommendations.append(
            f"Install Python dependencies:\n"
            f"  python -m wads.setup_utils install-python {pyproject_path.parent}"
        )

    if missing_system:
        recommendations.append(
            f"Install system dependencies:\n"
            f"  python -m wads.setup_utils install-system {pyproject_path.parent}"
        )

        for dep in missing_system:
            if dep["install_command"]:
                recommendations.append(
                    f"  Or manually for {dep['name']}:\n"
                    f"    {dep['install_command'] if isinstance(dep['install_command'], str) else '; '.join(dep['install_command'])}"
                )

    if missing_env:
        recommendations.append(
            f"Set required environment variables:\n"
            + "\n".join(f"  export {var}=<value>" for var in missing_env)
        )

    return DiagnosticResult(
        missing_python_deps=missing_python,
        missing_system_deps=missing_system,
        missing_env_vars=missing_env,
        warnings=warnings_list,
        recommendations=recommendations,
    )


def print_diagnostic_report(result: DiagnosticResult):
    """
    Print a formatted diagnostic report.

    Args:
        result: DiagnosticResult to display
    """
    print("\n" + "=" * 70)
    print("DEPENDENCY DIAGNOSTIC REPORT")
    print("=" * 70)

    # Python dependencies
    if result.missing_python_deps:
        print("\n❌ Missing Python Dependencies:")
        for dep in result.missing_python_deps:
            print(f"  • {dep}")
    else:
        print("\n✓ All Python dependencies satisfied")

    # System dependencies
    if result.missing_system_deps:
        print("\n❌ Missing System Dependencies:")
        for dep in result.missing_system_deps:
            print(f"\n  • {dep['name']}")
            print(f"    DepURL: {dep['depurl']}")
            print(f"    Purpose: {dep['rationale']}")
            if dep["url"]:
                print(f"    Info: {dep['url']}")
            if dep["install_command"]:
                cmd = dep["install_command"]
                if isinstance(cmd, list):
                    print(f"    Install:")
                    for c in cmd:
                        print(f"      {c}")
                else:
                    print(f"    Install: {cmd}")
            if dep["alternatives"]:
                print(f"    Alternatives: {', '.join(dep['alternatives'])}")
            if dep["note"]:
                print(f"    Note: {dep['note']}")
    else:
        print("\n✓ All system dependencies satisfied (or cannot be verified)")

    # Environment variables
    if result.missing_env_vars:
        print("\n❌ Missing Environment Variables:")
        for var in result.missing_env_vars:
            print(f"  • {var}")
    else:
        print("\n✓ All required environment variables set")

    # Warnings
    if result.warnings:
        print("\n⚠️  Warnings:")
        for warning in result.warnings:
            print(f"  • {warning}")

    # Recommendations
    if result.recommendations:
        print("\n📋 Recommendations:")
        for i, rec in enumerate(result.recommendations, 1):
            print(f"\n{i}. {rec}")

    print("\n" + "=" * 70)


# CLI interface
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Setup utilities for wads packages")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # install-python command
    install_py = subparsers.add_parser(
        "install-python", help="Install Python dependencies"
    )
    install_py.add_argument("path", help="Path to pyproject.toml or directory")
    install_py.add_argument("--exclude", nargs="+", help="Packages to exclude")
    install_py.add_argument(
        "--no-check", action="store_true", help="Skip importability check"
    )
    install_py.add_argument("--upgrade", action="store_true", help="Upgrade packages")
    install_py.add_argument(
        "--allow-downgrade", action="store_true", help="Allow downgrades"
    )
    install_py.add_argument("--extras", nargs="+", help="Extras to install")
    install_py.add_argument(
        "--dry-run", action="store_true", help="Show what would be installed"
    )

    # install-system command
    install_sys = subparsers.add_parser(
        "install-system", help="Install system dependencies"
    )
    install_sys.add_argument("path", help="Path to pyproject.toml or directory")
    install_sys.add_argument("--platform", help="Platform (linux, macos, windows)")
    install_sys.add_argument(
        "--no-check", action="store_true", help="Skip existing installation check"
    )
    install_sys.add_argument(
        "--dry-run", action="store_true", help="Show what would be installed"
    )
    install_sys.add_argument(
        "--non-interactive", action="store_true", help="No confirmation prompts"
    )

    # check-env command
    check_env_parser = subparsers.add_parser(
        "check-env", help="Check environment variables"
    )
    check_env_parser.add_argument("path", help="Path to pyproject.toml or directory")

    # diagnose command
    diagnose = subparsers.add_parser("diagnose", help="Diagnose setup issues")
    diagnose.add_argument("path", help="Path to pyproject.toml or directory")
    diagnose.add_argument("--platform", help="Platform (linux, macos, windows)")

    args = parser.parse_args()

    if args.command == "install-python":
        results = install_python_dependencies(
            args.path,
            exclude=args.exclude,
            check_importable=not args.no_check,
            upgrade=args.upgrade,
            allow_downgrade=args.allow_downgrade,
            extras=args.extras,
            dry_run=args.dry_run,
        )

        success_count = sum(1 for r in results if r.success)
        print(f"\n{'=' * 70}")
        print(f"Installed {success_count}/{len(results)} packages successfully")

    elif args.command == "install-system":
        results = install_system_dependencies(
            args.path,
            platform=args.platform,
            check_first=not args.no_check,
            dry_run=args.dry_run,
            interactive=not args.non_interactive,
        )

        success_count = sum(1 for r in results if r.success)
        print(f"\n{'=' * 70}")
        print(f"Installed {success_count}/{len(results)} dependencies successfully")

    elif args.command == "check-env":
        results = check_environment_variables(args.path)
        missing = [k for k, v in results.items() if v is None]

        if missing:
            print(f"\n❌ {len(missing)} environment variable(s) missing")
            sys.exit(1)
        else:
            print("\n✓ All required environment variables set")

    elif args.command == "diagnose":
        result = diagnose_setup(args.path, platform=args.platform)
        print_diagnostic_report(result)

        # Exit with error if issues found
        if (
            result.missing_python_deps
            or result.missing_system_deps
            or result.missing_env_vars
        ):
            sys.exit(1)

    else:
        parser.print_help()
