#!/usr/bin/env python3
"""
Set Environment Variables from GitHub Secrets

This script reads the CI configuration from pyproject.toml and sets environment
variables from GitHub Secrets, validating required variables.

Usage:
    python -m wads.scripts.set_env_vars [path_to_pyproject]

Environment:
    SECRETS_CONTEXT - JSON string of all GitHub Secrets
    GITHUB_ENV - Path to GitHub Actions environment file
    GITHUB_STEP_SUMMARY - Path to GitHub Actions step summary file
"""

import json
import os
import sys
from pathlib import Path

# Reserved env vars that should not be set from secrets
RESERVED_VARS = {
    "GITHUB_TOKEN",
    "GITHUB_ACTOR",
    "GITHUB_REPOSITORY",
    "GITHUB_REF",
    "GITHUB_SHA",
    "GITHUB_WORKSPACE",
    "GITHUB_EVENT_NAME",
    "GITHUB_EVENT_PATH",
    "GITHUB_RUN_ID",
    "GITHUB_RUN_NUMBER",
    "GITHUB_ACTION",
    "GITHUB_ACTIONS",
    "CI",
    "HOME",
    "PATH",
    "SHELL",
    "USER",
}


def _set_env_var(name: str, value: str):
    """Set environment variable for subsequent GitHub Actions steps."""
    env_file = os.environ.get("GITHUB_ENV")
    if not env_file:
        print(f"Warning: GITHUB_ENV not set, skipping: {name}", file=sys.stderr)
        return

    with open(env_file, "a") as f:
        # Escape multiline values
        delimiter = f"EOF_{name}"
        f.write(f"{name}<<{delimiter}\n{value}\n{delimiter}\n")


def set_environment_variables(pyproject_path: str | Path = ".") -> int:
    """
    Set environment variables from GitHub Secrets based on CI config.

    Args:
        pyproject_path: Path to pyproject.toml file or directory containing it

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    try:
        from wads.ci_config import CIConfig

        # Read CI configuration
        config = CIConfig.from_file(pyproject_path)

        # Get secrets (GitHub Actions provides this as JSON)
        secrets_json = os.environ.get("SECRETS_CONTEXT", "{}")
        secrets = json.loads(secrets_json)

        # Track what we're setting
        set_vars = []
        missing_required = []
        missing_test = []
        skipped_reserved = []

        # Get all env var lists
        required_vars = config.env_vars_required
        test_vars = config.env_vars_test
        extra_vars = config.env_vars_extra

        # Process required env vars
        for var_name in required_vars:
            if var_name in RESERVED_VARS:
                skipped_reserved.append(var_name)
                missing_required.append(var_name)  # Treat as missing
                print(f"❌ Cannot set reserved env var: {var_name}", file=sys.stderr)
                continue

            if var_name in secrets:
                _set_env_var(var_name, secrets[var_name])
                set_vars.append(var_name)
                print(f"✅ Set required env var: {var_name}")
            else:
                missing_required.append(var_name)
                print(f"❌ Missing required env var: {var_name}", file=sys.stderr)

        # Process test env vars
        for var_name in test_vars:
            if var_name in RESERVED_VARS:
                skipped_reserved.append(var_name)
                continue

            if var_name in secrets:
                _set_env_var(var_name, secrets[var_name])
                set_vars.append(var_name)
                print(f"✅ Set test env var: {var_name}")
            else:
                missing_test.append(var_name)
                print(
                    f"⚠️  Missing test env var: {var_name} (tests may fail or be skipped)"
                )

        # Process extra env vars (no warnings)
        for var_name in extra_vars:
            if var_name in RESERVED_VARS:
                skipped_reserved.append(var_name)
                continue

            if var_name in secrets:
                _set_env_var(var_name, secrets[var_name])
                set_vars.append(var_name)
                print(f"✅ Set extra env var: {var_name}")

        # Set default env vars
        for var_name, value in config.env_vars_defaults.items():
            if var_name not in os.environ:  # Don't override existing
                _set_env_var(var_name, value)
                print(f"✅ Set default env var: {var_name}")

        # Print summary
        print("\n" + "=" * 70)
        print(f"Environment Variables Summary:")
        print(f"  Set: {len(set_vars)} variables")
        if missing_test:
            print(f"  ⚠️  Missing test vars: {len(missing_test)}")
        if skipped_reserved:
            print(f"  Skipped reserved vars: {', '.join(skipped_reserved)}")
        print("=" * 70)

        # Create GitHub Actions step summary
        summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary_file:
            with open(summary_file, "a") as f:
                f.write("## 🔐 Environment Variables\n\n")
                if set_vars:
                    f.write(f"✅ **Set {len(set_vars)} variables** from secrets\n\n")
                if missing_test:
                    f.write(
                        f"⚠️  **Missing test variables:** {', '.join(missing_test)}\n\n"
                    )
                    f.write("_Tests requiring these may fail or be skipped_\n\n")
                if skipped_reserved:
                    f.write(
                        f"ℹ️  Skipped reserved variables: {', '.join(skipped_reserved)}\n\n"
                    )

        # Fail if required vars are missing
        if missing_required:
            print(
                f"\n❌ ERROR: Missing required environment variables!", file=sys.stderr
            )
            print(
                f"   Add these to GitHub Secrets: {', '.join(missing_required)}",
                file=sys.stderr,
            )
            return 1

        print("\n✅ Environment variables configured successfully")
        return 0

    except FileNotFoundError:
        print("❌ pyproject.toml not found", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"❌ Error setting environment variables: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1


def main():
    """Main entry point."""
    pyproject_path = sys.argv[1] if len(sys.argv) > 1 else "."
    sys.exit(set_environment_variables(pyproject_path))


if __name__ == "__main__":
    main()
