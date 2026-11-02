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
import shutil
import subprocess
import sys
from pathlib import Path


def _using_uv() -> bool:
    """True when we should drive installs via ``uv pip`` (pip is missing)."""
    has_pip = (
        subprocess.run(
            [sys.executable, "-c", "import pip"], capture_output=True
        ).returncode
        == 0
    )
    return not has_pip and shutil.which("uv") is not None


def _pip_install_cmd() -> list[str]:
    """Build the command prefix for a pip install in the current interpreter.

    Uses ``uv pip install --python <interpreter>`` when pip isn't present in
    the running interpreter (e.g. minimal uv-managed venvs); ``--python`` must
    follow the subcommand for uv.
    """
    if _using_uv():
        return ["uv", "pip", "install", "--python", sys.executable]
    return [sys.executable, "-m", "pip", "install"]


def _has_build_tool() -> bool:
    """True when ``python -m build`` is importable in this interpreter."""
    probe = [sys.executable, "-c", "import build"]
    return subprocess.run(probe, capture_output=True).returncode == 0


def _ensure_build_tool() -> bool:
    """Install ``build`` into this interpreter only when it is missing.

    Nothing else is installed or upgraded: the project itself is never installed,
    because ``python -m build`` builds in an isolated environment, so installing it
    into this interpreter never affected the build and only left it behind (an
    editable install pointing at the build directory, issue #119).
    """
    if _has_build_tool():
        return True
    print("Installing the build tool")
    try:
        subprocess.run(_pip_install_cmd() + ["build"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Failed to install build tools: {e}", file=sys.stderr)
        return False
    return True


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
    if not _ensure_build_tool():
        return 1

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
        print(f"[ERROR] Build failed: {e}", file=sys.stderr)
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
