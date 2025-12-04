"""Test CLI interfaces of scripts."""

import subprocess
import sys
from pathlib import Path
import pytest


class TestScriptCLI:
    """Test command-line interfaces of scripts."""

    def test_read_ci_config_module_exists(self):
        """Test that read_ci_config module can be imported."""
        result = subprocess.run(
            [sys.executable, "-m", "wads.scripts.read_ci_config", "--help"],
            capture_output=True,
            text=True,
        )
        # Should either show help or fail gracefully
        assert result.returncode in [0, 1, 2]

    def test_build_dist_module_exists(self):
        """Test that build_dist module can be imported."""
        result = subprocess.run(
            [sys.executable, "-m", "wads.scripts.build_dist", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode in [0, 2]  # 0 for success, 2 for argparse help

    def test_validate_ci_env_module_exists(self):
        """Test that validate_ci_env module can be imported."""
        result = subprocess.run(
            [sys.executable, "-m", "wads.scripts.validate_ci_env", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode in [0, 1, 2]

    def test_install_deps_module_exists(self):
        """Test that install_deps module can be imported."""
        result = subprocess.run(
            [sys.executable, "-m", "wads.scripts.install_deps", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode in [0, 2]

    def test_set_env_vars_module_exists(self):
        """Test that set_env_vars module can be imported."""
        result = subprocess.run(
            [sys.executable, "-m", "wads.scripts.set_env_vars", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode in [0, 1, 2]

    @pytest.mark.integration
    def test_validate_ci_env_on_real_project(self, tmp_path):
        """Test validate_ci_env on a real project structure."""
        # Create minimal pyproject.toml
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            """
[project]
name = "test-cli-project"

[tool.wads.ci.env]
required_envvars = []
"""
        )

        result = subprocess.run(
            [sys.executable, "-m", "wads.scripts.validate_ci_env"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )

        # Should succeed with no required env vars
        assert result.returncode == 0
        assert "✅" in result.stdout or "All required" in result.stdout

    @pytest.mark.integration
    def test_build_dist_with_real_package(self, tmp_path):
        """Test build_dist with a real package."""
        # Create minimal project
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            """
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "cli-test-pkg"
version = "0.1.0"
"""
        )

        pkg_dir = tmp_path / "cli_test_pkg"
        pkg_dir.mkdir()
        (pkg_dir / "__init__.py").write_text('__version__ = "0.1.0"')

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "wads.scripts.build_dist",
                "--output-dir",
                str(tmp_path / "dist"),
                "--wheel",
                "--no-sdist",
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=120,  # Build can take time
        )

        # Should succeed
        assert result.returncode == 0

        # Check that dist directory was created
        dist_dir = tmp_path / "dist"
        assert dist_dir.exists()

    def test_scripts_fail_gracefully_on_missing_pyproject(self, tmp_path):
        """Test that scripts fail gracefully when pyproject.toml is missing."""
        # read_ci_config
        result = subprocess.run(
            [sys.executable, "-m", "wads.scripts.read_ci_config"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
        assert "not found" in result.stderr.lower() or "error" in result.stderr.lower()

    def test_scripts_can_be_imported(self):
        """Test that all scripts can be imported as modules."""
        scripts = [
            'wads.scripts.read_ci_config',
            'wads.scripts.build_dist',
            'wads.scripts.install_deps',
            'wads.scripts.set_env_vars',
            'wads.scripts.validate_ci_env',
        ]

        for script in scripts:
            result = subprocess.run(
                [sys.executable, "-c", f"import {script}"],
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, f"Failed to import {script}: {result.stderr}"


class TestScriptDocumentation:
    """Test that scripts have proper documentation."""

    def test_scripts_have_docstrings(self):
        """Test that scripts have module-level docstrings."""
        from wads.scripts import (
            read_ci_config,
            build_dist,
            install_deps,
            set_env_vars,
            validate_ci_env,
        )

        modules = [
            read_ci_config,
            build_dist,
            install_deps,
            set_env_vars,
            validate_ci_env,
        ]

        for module in modules:
            assert module.__doc__ is not None, f"{module.__name__} missing docstring"
            assert len(module.__doc__.strip()) > 0

    def test_scripts_have_usage_examples_in_docstrings(self):
        """Test that script docstrings include usage examples."""
        from wads.scripts import (
            read_ci_config,
            build_dist,
            install_deps,
            set_env_vars,
            validate_ci_env,
        )

        modules = [
            read_ci_config,
            build_dist,
            install_deps,
            set_env_vars,
            validate_ci_env,
        ]

        for module in modules:
            docstring = module.__doc__ or ""
            # Should have Usage section or python -m example
            assert (
                'Usage:' in docstring
                or 'python -m' in docstring
                or 'python3 -m' in docstring
            ), f"{module.__name__} docstring missing usage example"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
