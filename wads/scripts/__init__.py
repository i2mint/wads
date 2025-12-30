"""
CI and automation scripts for wads.

These scripts extract complex logic from GitHub Actions workflow files,
making them easier to test, maintain, and reuse.

Available scripts:
    - build_dist: Build Python distribution packages
    - install_deps: Install Python dependencies
    - read_ci_config: Read CI configuration from pyproject.toml
    - set_env_vars: Set environment variables from GitHub Secrets
    - validate_ci_env: Validate CI environment variables
"""

__all__ = [
    "build_dist",
    "install_deps",
    "read_ci_config",
    "set_env_vars",
    "validate_ci_env",
]
