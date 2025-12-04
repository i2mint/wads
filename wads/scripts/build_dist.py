#!/usr/bin/env python3
"""
Build Python Distribution Packages

This script builds Python distribution packages (sdist and/or wheel) using
modern PEP 517 build tools.

Usage:
    python -m wads.scripts.build_dist [options]

Arguments:
    --output-dir PATH    Output directory for built distributions (default: dist)
    --sdist             Build source distribution (default: true)
    --wheel             Build wheel distribution (default: true)
    --no-sdist          Skip building source distribution
    --no-wheel          Skip building wheel distribution
"""

import argparse
import subprocess
import sys
from pathlib import Path


def _install_build_tools():
    """Install modern build tools."""
    print("Installing modern build tools")
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "pip", "build"],
            check=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install build tools: {e}", file=sys.stderr)
        return False
    return True


def _install_dependencies():
    """Install project dependencies."""
    print("Installing project dependencies")

    # Try different dependency files
    if Path("pyproject.toml").exists():
        print("Installing from pyproject.toml")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-e", "."],
            capture_output=True,
        )
        if result.returncode != 0:
            print("Could not install in editable mode, continuing...")
    elif Path("setup.cfg").exists():
        print("Installing from setup.cfg")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-e", "."],
            capture_output=True,
        )
        if result.returncode != 0:
            print("Could not install in editable mode, continuing...")
    elif Path("requirements.txt").exists():
        print("Installing from requirements.txt")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
            check=False,
        )


def build_distributions(
    output_dir: str = "dist",
    build_sdist: bool = True,
    build_wheel: bool = True,
) -> int:
    """
    Build distribution packages.

    Args:
        output_dir: Output directory for distributions
        build_sdist: Whether to build source distribution
        build_wheel: Whether to build wheel distribution

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    # Install build tools
    if not _install_build_tools():
        return 1

    # Install dependencies
    _install_dependencies()

    # Build distributions
    print("Building distributions")

    build_args = [sys.executable, "-m", "build"]

    # Determine what to build
    if build_sdist and not build_wheel:
        build_args.append("--sdist")
    elif build_wheel and not build_sdist:
        build_args.append("--wheel")
    # If both true, build creates both by default

    # Set output directory
    if output_dir:
        build_args.extend(["--outdir", output_dir])

    print(f"Running: {' '.join(build_args)}")

    try:
        subprocess.run(build_args, check=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ Build failed: {e}", file=sys.stderr)
        return 1

    # List built distributions
    output_path = Path(output_dir)
    if output_path.exists():
        print("\nBuilt distributions:")
        for item in sorted(output_path.iterdir()):
            size = item.stat().st_size / 1024  # KB
            print(f"  {item.name:40s} {size:8.1f} KB")

    return 0


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Build Python distribution packages",
    )
    parser.add_argument(
        "--output-dir",
        default="dist",
        help="Output directory for built distributions",
    )
    parser.add_argument(
        "--sdist",
        action="store_true",
        default=True,
        help="Build source distribution (default)",
    )
    parser.add_argument(
        "--wheel",
        action="store_true",
        default=True,
        help="Build wheel distribution (default)",
    )
    parser.add_argument(
        "--no-sdist",
        action="store_true",
        help="Skip building source distribution",
    )
    parser.add_argument(
        "--no-wheel",
        action="store_true",
        help="Skip building wheel distribution",
    )

    args = parser.parse_args()

    # Handle negations
    build_sdist = args.sdist and not args.no_sdist
    build_wheel = args.wheel and not args.no_wheel

    sys.exit(build_distributions(args.output_dir, build_sdist, build_wheel))


if __name__ == "__main__":
    main()
