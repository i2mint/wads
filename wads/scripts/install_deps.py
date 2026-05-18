#!/usr/bin/env python3
"""
Install Dependencies

This script installs Python dependencies from various sources including
pyproject.toml, requirements.txt, and direct package names.

Usage:
    python -m wads.scripts.install_deps [options]

Arguments:
    --pypi-packages PKG1 PKG2...  Python packages to install
    --dependency-files FILE1,FILE2,...  Dependency files to install from
    --extras EXTRA1,EXTRA2,...  Extras to install from pyproject.toml
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def _pip_cmd() -> list[str]:
    """Return command prefix for pip install in the current interpreter.

    Falls back to ``uv pip`` when ``pip`` isn't installed in the running
    interpreter (e.g. minimal uv-managed venvs).
    """
    has_pip = (
        subprocess.run(
            [sys.executable, "-c", "import pip"], capture_output=True
        ).returncode
        == 0
    )
    if has_pip:
        return [sys.executable, "-m", "pip"]
    if shutil.which("uv"):
        return ["uv", "pip", "--python", sys.executable]
    return [sys.executable, "-m", "pip"]


def _upgrade_pip() -> bool:
    """Upgrade pip if pip is available; no-op when using uv fallback."""
    pip = _pip_cmd()
    if pip[:2] != [sys.executable, "-m"]:
        # Using uv — pip itself isn't installed in this env; skip upgrade.
        return True
    try:
        subprocess.run(pip + ["install", "--upgrade", "pip"], check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ pip install failed: {e}", file=sys.stderr)
        return False


def _run_pip_install(args: list[str]) -> bool:
    """Run pip install with the given arguments."""
    try:
        subprocess.run(
            _pip_cmd() + ["install"] + args,
            check=True,
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ pip install failed: {e}", file=sys.stderr)
        return False


def install_pypi_packages(packages: list[str]) -> bool:
    """Install packages from PyPI."""
    if not packages:
        return True

    print(f"Upgrading pip")
    if not _upgrade_pip():
        return False

    print(f"Installing packages: {' '.join(packages)}")
    if not _run_pip_install(packages):
        return False

    # Show installed versions
    print("\nInstalled package versions:")
    for pkg in packages:
        # Extract package name (remove version specifiers)
        pkg_name = pkg.split("[")[0].split("=")[0].split("<")[0].split(">")[0]
        result = subprocess.run(
            _pip_cmd() + ["show", pkg_name],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            for line in result.stdout.split("\n"):
                if line.startswith("Name:") or line.startswith("Version:"):
                    print(f"  {line}")

    return True


def install_from_dependency_files(
    files: list[str],
    extras: list[str] | None = None,
) -> bool:
    """Install from dependency files."""
    if not files:
        return True

    print("Upgrading pip")
    if not _upgrade_pip():
        return False

    success = True
    for path_str in files:
        path = Path(path_str.strip())

        if not path.exists():
            print(f"⚠️  Dependency file not found: {path}")
            continue

        if path.suffix == ".txt":
            print(f"Installing from requirements file: {path}")
            if not _run_pip_install(["-r", str(path)]):
                success = False

        elif path.suffix == ".toml":
            print(f"Installing from pyproject.toml: {path}")
            if extras:
                extras_str = ",".join(extras)
                install_spec = f".[{extras_str}]"
            else:
                install_spec = "."

            if not _run_pip_install(["-e", install_spec]):
                success = False

        elif path.suffix == ".cfg":
            print(f"Installing from setup.cfg: {path}")
            # For backward compatibility, use isee if available
            try:
                import isee

                subprocess.run(
                    [sys.executable, "-m", "isee", "install-requires"],
                    check=True,
                )
                subprocess.run(
                    [sys.executable, "-m", "isee", "tests-require"],
                    check=False,
                )
            except (ImportError, subprocess.CalledProcessError):
                if not _run_pip_install(["-e", "."]):
                    success = False

    # Show all installed packages
    print("\nInstalled Python packages:")
    subprocess.run(_pip_cmd() + ["list"])

    return success


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Install Python dependencies",
    )
    parser.add_argument(
        "--pypi-packages",
        nargs="+",
        help="Python packages to install (space-separated)",
    )
    parser.add_argument(
        "--dependency-files",
        help="Comma-separated paths to dependency files",
    )
    parser.add_argument(
        "--extras",
        help="Comma-separated extras to install from pyproject.toml",
    )

    args = parser.parse_args()

    success = True

    # Install PyPI packages
    if args.pypi_packages:
        if not install_pypi_packages(args.pypi_packages):
            success = False

    # Install from dependency files
    if args.dependency_files:
        files = [f.strip() for f in args.dependency_files.split(",")]
        extras = [e.strip() for e in args.extras.split(",")] if args.extras else None
        if not install_from_dependency_files(files, extras):
            success = False

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
