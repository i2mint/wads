#!/usr/bin/env python3
"""
CI Environment Validation Script

This script validates that all required environment variables are set
based on configuration in pyproject.toml [tool.wads.ci.env].

Usage:
    python -m wads.scripts.validate_ci_env

Exit codes:
    0 - All required environment variables are set
    1 - One or more required environment variables are missing
"""

import os
import sys
from pathlib import Path


def validate_ci_environment(pyproject_path: str | Path = ".") -> tuple[bool, list[str]]:
    """
    Validate that all required CI environment variables are set.

    Args:
        pyproject_path: Path to directory containing pyproject.toml

    Returns:
        Tuple of (success, missing_vars)
    """
    try:
        from wads.ci_config import CIConfig

        config = CIConfig.from_file(pyproject_path)
        required_vars = config.env_vars_required

        if not required_vars:
            return True, []

        missing_vars = [var for var in required_vars if var not in os.environ]

        return len(missing_vars) == 0, missing_vars

    except FileNotFoundError:
        print("❌ pyproject.toml not found", file=sys.stderr)
        return False, []
    except Exception as e:
        print(f"❌ Error reading CI config: {e}", file=sys.stderr)
        return False, []


def main():
    """Main entry point for CI environment validation."""
    print("🔍 Validating CI environment variables...")

    success, missing_vars = validate_ci_environment()

    if success:
        print("✅ All required environment variables are set")
        return 0
    else:
        print("\n❌ Missing required environment variables:", file=sys.stderr)
        for var in missing_vars:
            print(f"  - {var}", file=sys.stderr)
        print(
            "\nPlease configure these in your CI secrets or environment.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
