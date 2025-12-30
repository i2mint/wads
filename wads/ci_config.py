"""
Utilities for reading and applying CI configuration from pyproject.toml.

This module provides the infrastructure for using pyproject.toml as the single
source of truth for CI configuration, eliminating hardcoded project-specific
settings in CI workflow files.
"""

from typing import Any, Optional
from pathlib import Path
import sys
import warnings
import re

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        raise ImportError("tomli package required for Python < 3.11")


class CIConfig:
    """Represents CI configuration extracted from pyproject.toml."""

    def __init__(self, pyproject_data: dict, project_name: str = None):
        """
        Initialize CI configuration from pyproject.toml data.

        Args:
            pyproject_data: Parsed TOML data from pyproject.toml
            project_name: Project name (defaults to project.name from pyproject)
        """
        self.data = pyproject_data
        self.ci_config = pyproject_data.get("tool", {}).get("wads", {}).get("ci", {})
        self._project_name = (
            project_name
            or self.ci_config.get("project_name")
            or pyproject_data.get("project", {}).get("name", "")
        )

    @classmethod
    def from_file(cls, pyproject_path: str | Path) -> "CIConfig":
        """
        Load CI configuration from a pyproject.toml file.

        Args:
            pyproject_path: Path to pyproject.toml file or directory containing it

        Returns:
            CIConfig instance
        """
        pyproject_path = Path(pyproject_path)
        if pyproject_path.is_dir():
            pyproject_path = pyproject_path / "pyproject.toml"

        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)

        return cls(data)

    @property
    def project_name(self) -> str:
        """Get the project name for CI."""
        return self._project_name

    # ⚙️ EXECUTION FLOW AND COMMANDS
    @property
    def commands_pre_test(self) -> list[str]:
        """Get pre-test setup commands."""
        return self.ci_config.get("commands", {}).get("pre_test", [])

    @property
    def commands_test(self) -> list[str]:
        """Get test commands (defaults to ['pytest'])."""
        return self.ci_config.get("commands", {}).get("test", ["pytest"])

    @property
    def commands_post_test(self) -> list[str]:
        """Get post-test commands."""
        return self.ci_config.get("commands", {}).get("post_test", [])

    @property
    def commands_lint(self) -> list[str]:
        """Get lint commands."""
        return self.ci_config.get("commands", {}).get("lint", [])

    @property
    def commands_format(self) -> list[str]:
        """Get format commands."""
        return self.ci_config.get("commands", {}).get("format", [])

    # 🌍 ENVIRONMENT VARIABLES
    @property
    def env_vars_required(self) -> list[str]:
        """Get required environment variable names (CI fails if not in secrets)."""
        return self.ci_config.get("env", {}).get("required_envvars", [])

    @property
    def env_vars_test(self) -> list[str]:
        """Get test environment variable names (CI warns if not in secrets)."""
        return self.ci_config.get("env", {}).get("test_envvars", [])

    @property
    def env_vars_extra(self) -> list[str]:
        """Get extra/optional environment variable names (no warning if missing)."""
        return self.ci_config.get("env", {}).get("extra_envvars", [])

    @property
    def env_vars_all(self) -> list[str]:
        """Get all environment variable names (required + test + extra)."""
        return self.env_vars_required + self.env_vars_test + self.env_vars_extra

    @property
    def env_vars_defaults(self) -> dict[str, str]:
        """Get default environment variables."""
        return self.ci_config.get("env", {}).get("defaults", {})

    # ✅ CODE QUALITY AND FORMATTING
    @property
    def quality_config(self) -> dict:
        """Get code quality tool configuration."""
        return self.ci_config.get("quality", {})

    def is_ruff_enabled(self) -> bool:
        """Check if Ruff linter is enabled."""
        return self.quality_config.get("ruff", {}).get("enabled", True)

    def is_black_enabled(self) -> bool:
        """Check if Black formatter is enabled."""
        return self.quality_config.get("black", {}).get("enabled", False)

    def is_mypy_enabled(self) -> bool:
        """Check if Mypy type checker is enabled."""
        return self.quality_config.get("mypy", {}).get("enabled", False)

    # 🧪 TEST CONFIGURATION
    @property
    def testing_config(self) -> dict:
        """Get testing configuration."""
        return self.ci_config.get("testing", {})

    @property
    def python_versions(self) -> list[str]:
        """Get Python versions to test against."""
        return self.testing_config.get("python_versions", ["3.10", "3.12"])

    @property
    def pytest_args(self) -> list[str]:
        """Get pytest arguments."""
        return self.testing_config.get("pytest_args", ["-v", "--tb=short"])

    @property
    def coverage_enabled(self) -> bool:
        """Check if coverage is enabled."""
        return self.testing_config.get("coverage_enabled", True)

    @property
    def coverage_threshold(self) -> int:
        """Get minimum coverage threshold (0 = no enforcement)."""
        return self.testing_config.get("coverage_threshold", 0)

    @property
    def exclude_paths(self) -> list[str]:
        """Get test paths to exclude."""
        return self.testing_config.get("exclude_paths", ["examples", "scrap"])

    @property
    def test_on_windows(self) -> bool:
        """Check if Windows testing is enabled."""
        return self.testing_config.get("test_on_windows", True)

    @property
    def system_dependencies(self) -> dict | list:
        """Get system dependencies for CI environments (DEPRECATED).

        DEPRECATED: Use [tool.wads.ops.*] format with install-system-deps action instead.
        This property is maintained for backward compatibility with legacy format.

        Returns either:
        - A list of package names (Ubuntu only)
        - A dict with platform keys: ubuntu, macos, windows
        """
        return self.testing_config.get("system_dependencies", [])

    # 📦 BUILD AND PUBLISH SETTINGS
    @property
    def build_config(self) -> dict:
        """Get build configuration."""
        return self.ci_config.get("build", {})

    @property
    def build_sdist(self) -> bool:
        """Check if source distribution should be built."""
        return self.build_config.get("sdist", True)

    @property
    def build_wheel(self) -> bool:
        """Check if wheel should be built."""
        return self.build_config.get("wheel", True)

    @property
    def publish_config(self) -> dict:
        """Get publish configuration."""
        return self.ci_config.get("publish", {})

    @property
    def publish_enabled(self) -> bool:
        """Check if publishing is enabled."""
        return self.publish_config.get("enabled", True)

    # 📄 DOCUMENTATION SETTINGS
    @property
    def docs_config(self) -> dict:
        """Get documentation configuration."""
        return self.ci_config.get("docs", {})

    @property
    def docs_enabled(self) -> bool:
        """Check if documentation generation is enabled."""
        return self.docs_config.get("enabled", True)

    @property
    def docs_builder(self) -> str:
        """Get documentation builder name."""
        return self.docs_config.get("builder", "epythet")

    @property
    def docs_ignore_paths(self) -> list[str]:
        """Get paths to ignore during documentation generation."""
        return self.docs_config.get("ignore_paths", ["tests/", "scrap/", "examples/"])

    # 📊 CODE METRICS SETTINGS
    @property
    def metrics_config(self) -> dict:
        """Get code metrics configuration."""
        return self.ci_config.get("metrics", {})

    @property
    def metrics_enabled(self) -> bool:
        """Check if code metrics tracking is enabled."""
        return self.metrics_config.get("enabled", True)

    @property
    def metrics_config_path(self) -> str:
        """Get path to umpyre config file."""
        return self.metrics_config.get("config_path", ".github/umpyre-config.yml")

    @property
    def metrics_storage_branch(self) -> str:
        """Get git branch to store metrics data."""
        return self.metrics_config.get("storage_branch", "code-metrics")

    @property
    def metrics_python_version(self) -> str:
        """Get Python version for metrics collection."""
        return self.metrics_config.get("python_version", "3.10")

    @property
    def metrics_force_run(self) -> bool:
        """Check if metrics should run even on workflow failure."""
        return self.metrics_config.get("force_run", False)

    @property
    def ops(self) -> dict:
        """Get system dependencies configuration from [tool.wads.ops.*] sections.

        Returns:
            Dictionary mapping dependency names to their configuration
        """
        return self.data.get("tool", {}).get("wads", {}).get("ops", {})

    def to_ci_env_block(self) -> str:
        """
        Generate YAML env block for GitHub Actions.

        Returns:
            YAML string for env section
        """
        lines = ["env:"]
        lines.append(f"  PROJECT_NAME: {self.project_name}")

        # Add default environment variables
        for key, value in self.env_vars_defaults.items():
            lines.append(f"  {key}: {value}")

        return "\n".join(lines)

    def to_pre_test_step(self) -> Optional[str]:
        """
        Generate YAML step for pre-test commands.

        Returns:
            YAML string for pre-test step, or None if no commands
        """
        if not self.commands_pre_test:
            return None

        lines = ["      - name: Pre-test Setup"]
        lines.append("        run: |")
        for cmd in self.commands_pre_test:
            lines.append(f"          {cmd}")

        return "\n".join(lines)

    def has_ci_config(self) -> bool:
        """Check if any CI configuration is present."""
        return bool(self.ci_config)

    def _normalize_system_deps(self) -> dict[str, list[str]]:
        """Normalize system_dependencies to platform dict.

        Returns:
            Dict with keys: ubuntu, macos, windows
        """
        deps = self.system_dependencies
        if isinstance(deps, list):
            # Simple list means ubuntu-only
            return {"ubuntu": deps, "macos": [], "windows": []}
        elif isinstance(deps, dict):
            return {
                "ubuntu": deps.get("ubuntu", []),
                "macos": deps.get("macos", []),
                "windows": deps.get("windows", []),
            }
        return {"ubuntu": [], "macos": [], "windows": []}

    def generate_env_block(self) -> str:
        """
        Generate YAML env block for GitHub Actions.

        Creates env vars for:
        - PROJECT_NAME (from config)
        - Default env vars (from config.env.defaults)
        - Placeholders for secret-based env vars (set via set-env-vars action)

        Returns:
            YAML string for env section
        """
        lines = []

        # Always include PROJECT_NAME
        lines.append(f"  PROJECT_NAME: {self.project_name}")

        # Add default environment variables (literal values, not secrets)
        for key, value in self.env_vars_defaults.items():
            lines.append(f"  {key}: {value}")

        # Add env vars that come from secrets (using conditional syntax)
        # These are set conditionally only if the secret exists
        all_secret_vars = self.env_vars_all
        for var_name in all_secret_vars:
            # Use GitHub's conditional syntax to only set if secret exists
            lines.append(f"  {var_name}: ${{{{ secrets.{var_name} || '' }}}}")

        return "\n".join(lines) if lines else ""

    def generate_env_vars_yaml(self) -> str:
        """
        Generate YAML lines for all environment variables to be set from secrets.
        This is used in the #ENV_VARS# placeholder in CI templates.

        Returns:
            YAML string with conditional env var assignments
        """
        lines = []

        # Add env vars that come from secrets (using conditional syntax)
        # These are set conditionally only if the secret exists
        all_secret_vars = self.env_vars_all
        for var_name in all_secret_vars:
            # Use GitHub's conditional syntax to only set if secret exists
            lines.append(f"  {var_name}: ${{{{ secrets.{var_name} || '' }}}}")

        return "\n".join(lines) if lines else "  # No additional env vars configured"

    def generate_pre_test_steps(self, platform: str = "linux") -> str:
        """
        Generate YAML steps for pre-test commands and system dependencies.

        Supports legacy [tool.wads.ci.testing.system_dependencies] format.

        Args:
            platform: Platform identifier ('linux', 'macos', 'windows')

        Returns:
            YAML string for pre-test steps, or empty string if no commands/deps
        """
        steps = []
        install_commands = []

        # ---- LEGACY: Parse system_dependencies (DEPRECATED) ----
        legacy_deps = self._normalize_system_deps()
        platform_key = "ubuntu" if platform == "linux" else platform
        legacy_packages = legacy_deps.get(platform_key, [])

        if legacy_packages:
            warnings.warn(
                f"Using deprecated [tool.wads.ci.testing.system_dependencies]. "
                f"Please migrate to [tool.wads.ops.*] format with install-system-deps action",
                DeprecationWarning,
                stacklevel=2,
            )
            # For Ubuntu/Linux, use apt-get
            if platform == "linux":
                install_commands.append("sudo apt-get update")
                install_commands.append(
                    f"sudo apt-get install -y {' '.join(legacy_packages)}"
                )

        # ---- Build YAML steps ----
        if install_commands:
            steps.append("      - name: Install System Dependencies")
            steps.append("        run: |")
            for cmd in install_commands:
                steps.append(f"          {cmd}")

        # Add custom pre-test commands
        if self.commands_pre_test:
            if steps:
                steps.append("")  # Empty line between steps
            steps.append("      - name: Pre-test Setup")
            steps.append("        run: |")
            for cmd in self.commands_pre_test:
                steps.append(f"          {cmd}")

        return "\n".join(steps) if steps else ""

    def generate_windows_validation_job(self) -> str:
        """
        Generate YAML for Windows validation job.

        Supports legacy system_dependencies format.

        Returns:
            YAML string for Windows job, or empty string if disabled
        """
        if not self.test_on_windows:
            return ""

        install_commands = []

        # ---- LEGACY: Parse system_dependencies (DEPRECATED) ----
        legacy_deps = self._normalize_system_deps()
        windows_packages = legacy_deps.get("windows", [])

        if windows_packages:
            warnings.warn(
                f"Using deprecated [tool.wads.ci.testing.system_dependencies]. "
                f"Please migrate to [tool.wads.ops.*] format with install-system-deps action",
                DeprecationWarning,
                stacklevel=2,
            )
            # For Windows, use chocolatey
            install_commands.append(f"choco install -y {' '.join(windows_packages)}")

        # Build system dependencies step if needed
        system_deps_step = ""
        if install_commands:
            system_deps_step = "      - name: Install System Dependencies\n"
            system_deps_step += "        run: |\n"
            for cmd in install_commands:
                system_deps_step += f"          {cmd}\n"
            system_deps_step += "\n"

        template = """
  windows-validation:
    name: Windows Tests (Informational)
    if: "!contains(github.event.head_commit.message, '[skip ci]')"
    runs-on: windows-latest
    continue-on-error: true  # Don't fail the entire workflow if Windows tests fail

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python 3.10
        uses: actions/setup-python@v6
        with:
          python-version: "3.10"
{system_deps_step}
      - name: Install Dependencies
        uses: i2mint/wads/actions/install-deps@master
        with:
          dependency-files: pyproject.toml
          extras: dev,test

      - name: Run Windows Tests
        uses: i2mint/wads/actions/windows-tests@master
        with:
          root-dir: ${{{{ env.PROJECT_NAME }}}}
          exclude: {exclude}
          pytest-args: {pytest_args}
"""
        exclude = ",".join(self.exclude_paths)
        pytest_args = " ".join(self.pytest_args)
        return template.format(
            exclude=exclude, pytest_args=pytest_args, system_deps_step=system_deps_step
        )

    def generate_github_pages_job(self) -> str:
        """
        Generate YAML for GitHub Pages job.

        Returns:
            YAML string for GitHub Pages job, or empty string if disabled
        """
        if not self.docs_enabled:
            return ""

        ignore_paths = ",".join(self.docs_ignore_paths)
        template = f"""
  github-pages:
    name: Publish GitHub Pages

    permissions:
      contents: write
      pages: write
      id-token: write

    if: "!contains(github.event.head_commit.message, '[skip ci]') && github.ref == format('refs/heads/{{0}}', github.event.repository.default_branch)"
    needs: publish
    runs-on: ubuntu-latest

    steps:
      - uses: i2mint/epythet/actions/publish-github-pages@master
        with:
          github-token: ${{{{ secrets.GITHUB_TOKEN }}}}
          ignore: "{ignore_paths}"
"""
        return template

    def to_ci_template_substitutions(self) -> dict[str, str]:
        """
        Generate all template substitutions for CI workflow generation.

        Returns:
            Dictionary mapping placeholder names to their values
        """
        import json

        return {
            "#ENV_BLOCK#": self.generate_env_block(),
            "#ENV_VARS#": self.generate_env_vars_yaml(),
            "#PYTHON_VERSIONS#": json.dumps(self.python_versions),
            "#PRE_TEST_STEPS#": self.generate_pre_test_steps(),
            "#EXCLUDE_PATHS#": ",".join(self.exclude_paths),
            "#COVERAGE_ENABLED#": str(self.coverage_enabled).lower(),
            "#PYTEST_ARGS#": " ".join(self.pytest_args),
            "#WINDOWS_VALIDATION_JOB#": self.generate_windows_validation_job(),
            "#GITHUB_PAGES_JOB#": self.generate_github_pages_job(),
            "#BUILD_SDIST#": str(self.build_sdist).lower(),
            "#BUILD_WHEEL#": str(self.build_wheel).lower(),
            "#PROJECT_NAME#": self.project_name,
        }

    def __repr__(self) -> str:
        return f"CIConfig(project_name={self.project_name!r}, has_config={self.has_ci_config()})"


def read_ci_config(pyproject_path: str | Path) -> CIConfig:
    """
    Read CI configuration from pyproject.toml.

    Args:
        pyproject_path: Path to pyproject.toml file or directory containing it

    Returns:
        CIConfig instance with project configuration

    Usage::

        config = read_ci_config("path/to/project")
        print(config.project_name)        # Project name from pyproject.toml
        print(config.python_versions)     # Python versions to test
    """
    return CIConfig.from_file(pyproject_path)


def get_ci_config_or_defaults(
    pyproject_path: str | Path, project_name: str = None
) -> CIConfig:
    """
    Read CI configuration from pyproject.toml, using defaults if file doesn't exist.

    Args:
        pyproject_path: Path to pyproject.toml file or directory containing it
        project_name: Default project name if not found in config

    Returns:
        CIConfig instance with defaults if file doesn't exist
    """
    pyproject_path = Path(pyproject_path)
    if pyproject_path.is_dir():
        pyproject_path = pyproject_path / "pyproject.toml"

    if not pyproject_path.exists():
        # Return empty config with defaults
        return CIConfig({"project": {"name": project_name or ""}}, project_name)

    return read_ci_config(pyproject_path)
