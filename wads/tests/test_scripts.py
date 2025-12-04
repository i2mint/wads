"""Unit tests for CI scripts."""

import json
import os
from pathlib import Path
from unittest.mock import patch
import pytest


class TestReadCiConfig:
    """Test read_ci_config.py script."""

    def test_reads_config_successfully(self, tmp_path):
        """Test that config is read correctly."""
        from wads.scripts.read_ci_config import read_and_export_ci_config

        # Create test pyproject.toml
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            """
[project]
name = "test-project"
version = "0.1.0"

[tool.wads.ci.testing]
python_versions = ["3.10", "3.12"]
coverage_enabled = true
"""
        )

        # Mock GitHub Actions environment
        output_file = tmp_path / 'output.txt'
        env_file = tmp_path / 'env.txt'
        summary_file = tmp_path / 'summary.txt'

        with patch.dict(
            'os.environ',
            {
                'GITHUB_OUTPUT': str(output_file),
                'GITHUB_ENV': str(env_file),
                'GITHUB_STEP_SUMMARY': str(summary_file),
            },
        ):
            result = read_and_export_ci_config(tmp_path)

            assert result == 0

            # Check outputs
            output_content = output_file.read_text()
            assert 'project-name=test-project' in output_content
            assert '3.10' in output_content

            # Check env vars
            env_content = env_file.read_text()
            assert 'PROJECT_NAME=test-project' in env_content

    def test_handles_missing_pyproject(self, tmp_path):
        """Test error handling for missing pyproject.toml."""
        from wads.scripts.read_ci_config import read_and_export_ci_config

        result = read_and_export_ci_config(tmp_path / "nonexistent")
        assert result == 1

    def test_works_without_github_env(self, tmp_path):
        """Test graceful degradation without GitHub environment."""
        from wads.scripts.read_ci_config import read_and_export_ci_config

        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            """
[project]
name = "test-project"
"""
        )

        # Should not crash without GITHUB_OUTPUT
        with patch.dict('os.environ', {}, clear=True):
            result = read_and_export_ci_config(tmp_path)
            # Should succeed but outputs won't be written
            assert result == 0


class TestValidateCiEnv:
    """Test validate_ci_env.py script."""

    def test_validates_required_vars_present(self, tmp_path):
        """Test validation passes when required vars are present."""
        from wads.scripts.validate_ci_env import validate_ci_environment

        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            """
[project]
name = "test-project"

[tool.wads.ci.env]
required_envvars = ["API_KEY"]
"""
        )

        with patch.dict('os.environ', {'API_KEY': 'secret'}):
            success, missing = validate_ci_environment(tmp_path)
            assert success
            assert len(missing) == 0

    def test_detects_missing_required_vars(self, tmp_path):
        """Test validation fails when required vars are missing."""
        from wads.scripts.validate_ci_env import validate_ci_environment

        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            """
[project]
name = "test-project"

[tool.wads.ci.env]
required_envvars = ["MISSING_VAR", "ANOTHER_MISSING"]
"""
        )

        with patch.dict('os.environ', {}, clear=True):
            success, missing = validate_ci_environment(tmp_path)
            assert not success
            assert "MISSING_VAR" in missing
            assert "ANOTHER_MISSING" in missing

    def test_handles_no_required_vars(self, tmp_path):
        """Test validation passes when no vars are required."""
        from wads.scripts.validate_ci_env import validate_ci_environment

        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            """
[project]
name = "test-project"
"""
        )

        success, missing = validate_ci_environment(tmp_path)
        assert success
        assert len(missing) == 0


class TestSetEnvVars:
    """Test set_env_vars.py script."""

    def test_sets_vars_from_secrets_context(self, tmp_path):
        """Test setting environment variables from secrets context."""
        from wads.scripts.set_env_vars import set_environment_variables

        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            """
[project]
name = "test-project"

[tool.wads.ci.env]
required_envvars = ["DATABASE_URL"]
test_envvars = ["TEST_SECRET"]
extra_envvars = ["OPTIONAL_VAR"]
"""
        )

        env_file = tmp_path / 'env.txt'
        summary_file = tmp_path / 'summary.txt'

        secrets = {
            "DATABASE_URL": "postgres://localhost/db",
            "TEST_SECRET": "test123",
            "OPTIONAL_VAR": "optional_value",
        }

        with patch.dict(
            'os.environ',
            {
                'GITHUB_ENV': str(env_file),
                'GITHUB_STEP_SUMMARY': str(summary_file),
                'SECRETS_CONTEXT': json.dumps(secrets),
            },
        ):
            result = set_environment_variables(tmp_path)

            assert result == 0
            env_content = env_file.read_text()
            assert 'DATABASE_URL' in env_content
            assert 'postgres://localhost/db' in env_content

    def test_fails_on_missing_required_var(self, tmp_path):
        """Test failure when required var is missing."""
        from wads.scripts.set_env_vars import set_environment_variables

        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            """
[project]
name = "test-project"

[tool.wads.ci.env]
required_envvars = ["CRITICAL_VAR"]
"""
        )

        env_file = tmp_path / 'env.txt'

        with patch.dict(
            'os.environ', {'GITHUB_ENV': str(env_file), 'SECRETS_CONTEXT': '{}'}
        ):
            result = set_environment_variables(tmp_path)
            assert result == 1

    def test_skips_reserved_vars(self, tmp_path):
        """Test that reserved variables are not set."""
        from wads.scripts.set_env_vars import set_environment_variables

        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            """
[project]
name = "test-project"

[tool.wads.ci.env]
required_envvars = ["GITHUB_TOKEN", "MY_VAR"]
"""
        )

        env_file = tmp_path / 'env.txt'

        secrets = {"GITHUB_TOKEN": "should_not_be_set", "MY_VAR": "should_be_set"}

        with patch.dict(
            'os.environ',
            {'GITHUB_ENV': str(env_file), 'SECRETS_CONTEXT': json.dumps(secrets)},
        ):
            result = set_environment_variables(tmp_path)

            # Should fail because GITHUB_TOKEN is skipped but required
            assert result == 1


class TestBuildDist:
    """Test build_dist.py script."""

    def test_build_minimal_package(self, tmp_path, monkeypatch):
        """Test building a minimal package."""
        from wads.scripts.build_dist import build_distributions

        # Create minimal pyproject.toml
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            """
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "test-pkg"
version = "0.1.0"
"""
        )

        # Create package directory
        pkg_dir = tmp_path / "test_pkg"
        pkg_dir.mkdir()
        (pkg_dir / "__init__.py").write_text('__version__ = "0.1.0"')

        monkeypatch.chdir(tmp_path)

        result = build_distributions(
            output_dir=str(tmp_path / "dist"), build_sdist=True, build_wheel=True
        )

        assert result == 0
        dist_dir = tmp_path / "dist"
        assert dist_dir.exists()

        # Check that at least one distribution was created
        files = list(dist_dir.iterdir())
        assert len(files) > 0

    def test_build_wheel_only(self, tmp_path, monkeypatch):
        """Test building only wheel."""
        from wads.scripts.build_dist import build_distributions

        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            """
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "test-pkg"
version = "0.1.0"
"""
        )

        pkg_dir = tmp_path / "test_pkg"
        pkg_dir.mkdir()
        (pkg_dir / "__init__.py").write_text("")

        monkeypatch.chdir(tmp_path)

        result = build_distributions(
            output_dir=str(tmp_path / "dist"), build_sdist=False, build_wheel=True
        )

        assert result == 0
        dist_dir = tmp_path / "dist"
        files = list(dist_dir.iterdir())

        # Should have wheel
        assert any(f.suffix == '.whl' for f in files)


class TestInstallDeps:
    """Test install_deps.py script."""

    def test_installs_pypi_packages(self):
        """Test installing packages from PyPI."""
        from wads.scripts.install_deps import install_pypi_packages

        # Test with a simple package
        result = install_pypi_packages(['pip'])
        assert result is True

    def test_handles_empty_package_list(self):
        """Test handling empty package list."""
        from wads.scripts.install_deps import install_pypi_packages

        result = install_pypi_packages([])
        assert result is True

    def test_install_from_requirements_file(self, tmp_path):
        """Test installing from requirements.txt."""
        from wads.scripts.install_deps import install_from_dependency_files

        # Create requirements file
        req_file = tmp_path / "requirements.txt"
        req_file.write_text("pip>=20.0\n")

        result = install_from_dependency_files([str(req_file)])
        assert result is True

    def test_handles_missing_file_gracefully(self, tmp_path):
        """Test handling missing dependency file."""
        from wads.scripts.install_deps import install_from_dependency_files

        # Should handle missing file gracefully
        result = install_from_dependency_files([str(tmp_path / "nonexistent.txt")])
        # Should still succeed (just skip the missing file)
        assert result is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
