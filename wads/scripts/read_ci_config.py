#!/usr/bin/env python3
"""
Read CI Configuration and Export to GitHub Actions

This script reads CI configuration from pyproject.toml and exports it as
GitHub Actions outputs and environment variables.

Usage:
    python -m wads.scripts.read_ci_config [path_to_pyproject]

Environment:
    GITHUB_OUTPUT - Path to GitHub Actions output file
    GITHUB_ENV - Path to GitHub Actions environment file
    GITHUB_STEP_SUMMARY - Path to GitHub Actions step summary file
"""

import json
import os
import sys
from pathlib import Path


def _set_output(name: str, value):
    """Set GitHub Actions output."""
    output_file = os.environ.get("GITHUB_OUTPUT")
    if not output_file:
        print(
            f"Warning: GITHUB_OUTPUT not set, skipping output: {name}", file=sys.stderr
        )
        return

    with open(output_file, "a") as f:
        # Handle multiline values
        if isinstance(value, (list, dict)):
            value = json.dumps(value)
        elif isinstance(value, bool):
            value = str(value).lower()
        f.write(f"{name}={value}\n")


def _set_env(name: str, value):
    """Set GitHub Actions environment variable."""
    env_file = os.environ.get("GITHUB_ENV")
    if not env_file:
        print(f"Warning: GITHUB_ENV not set, skipping env var: {name}", file=sys.stderr)
        return

    with open(env_file, "a") as f:
        if isinstance(value, (list, dict)):
            value = json.dumps(value)
        elif isinstance(value, bool):
            value = str(value).lower()
        f.write(f"{name}={value}\n")


def read_and_export_ci_config(pyproject_path: str | Path = ".") -> int:
    """
    Read CI configuration and export to GitHub Actions.

    Args:
        pyproject_path: Path to pyproject.toml file or directory containing it

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    try:
        from wads.ci_config import read_ci_config

        # Read configuration
        config = read_ci_config(pyproject_path)

        # Export as outputs and environment variables

        # Project metadata
        _set_output("project-name", config.project_name)
        _set_env("PROJECT_NAME", config.project_name)

        # Testing configuration
        _set_output("python-versions", config.python_versions)
        _set_output("pytest-args", " ".join(config.pytest_args))
        _set_output("coverage-enabled", config.coverage_enabled)
        _set_output("exclude-paths", ",".join(config.exclude_paths))
        _set_output("test-on-windows", config.test_on_windows)

        # Build configuration
        _set_output("build-sdist", config.build_sdist)
        _set_output("build-wheel", config.build_wheel)

        # Metrics configuration
        _set_output("metrics-enabled", config.metrics_enabled)
        _set_output("metrics-config-path", config.metrics_config_path)
        _set_output("metrics-storage-branch", config.metrics_storage_branch)
        _set_output("metrics-python-version", config.metrics_python_version)
        _set_output("metrics-force-run", config.metrics_force_run)

        # Print summary
        print("✅ CI configuration loaded successfully")
        print(f"   Project: {config.project_name}")
        print(f"   Python versions: {config.python_versions}")
        print(f"   Coverage: {config.coverage_enabled}")
        print(f"   Test on Windows: {config.test_on_windows}")

        # Add to GitHub Actions step summary if available
        summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary_file:
            with open(summary_file, "a") as f:
                f.write("## 🔧 CI Configuration\n\n")
                f.write(f"- **Project:** {config.project_name}\n")
                f.write(f"- **Python Versions:** {config.python_versions}\n")
                f.write(f"- **Coverage Enabled:** {config.coverage_enabled}\n")
                f.write(f"- **Test on Windows:** {config.test_on_windows}\n")
                f.write("\n")

        return 0

    except FileNotFoundError:
        print("❌ pyproject.toml not found", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"❌ Error reading CI config: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1


def main():
    """Main entry point."""
    pyproject_path = sys.argv[1] if len(sys.argv) > 1 else "."
    sys.exit(read_and_export_ci_config(pyproject_path))


if __name__ == "__main__":
    main()
