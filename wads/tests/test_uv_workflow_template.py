"""Test the github_ci_uv.yml workflow template."""

import yaml
from pathlib import Path
import pytest


class TestUvWorkflowTemplate:
    """Test the uv-based CI workflow template structure and validity."""

    @pytest.fixture
    def template_path(self):
        """Get path to the uv workflow template."""
        from wads import data_dir

        return Path(data_dir) / "github_ci_uv.yml"

    @pytest.fixture
    def template_content(self, template_path):
        """Load the template file content."""
        return template_path.read_text()

    @pytest.fixture
    def template_data(self, template_content):
        """Parse the template as YAML."""
        return yaml.safe_load(template_content)

    def test_template_file_exists(self, template_path):
        """Test that the template file exists."""
        assert template_path.exists()
        assert template_path.is_file()

    def test_template_is_valid_yaml(self, template_content):
        """Test that template is valid YAML."""
        data = yaml.safe_load(template_content)
        assert data is not None
        assert isinstance(data, dict)

    def test_template_has_required_structure(self, template_data):
        """Test that template has required top-level structure."""
        assert "name" in template_data
        assert True in template_data or "on" in template_data
        assert "jobs" in template_data
        assert isinstance(template_data["jobs"], dict)

    def test_template_has_required_jobs(self, template_data):
        """Test that template has all required jobs."""
        jobs = template_data["jobs"]
        for job_name in ["setup", "validation", "publish"]:
            assert job_name in jobs, f"Missing required job: {job_name}"

    def test_template_has_optional_jobs(self, template_data):
        """Test that template includes optional jobs."""
        jobs = template_data["jobs"]
        for job_name in ["windows-validation", "github-pages"]:
            assert job_name in jobs, f"Missing optional job: {job_name}"

    # --- uv-specific tests ---

    def test_uses_setup_uv_action(self, template_content):
        """Test that template uses astral-sh/setup-uv action."""
        assert "astral-sh/setup-uv" in template_content

    def test_does_not_use_setup_python_action(self, template_content):
        """Test that template does NOT use actions/setup-python (the standard GitHub action)."""
        assert "actions/setup-python@" not in template_content

    def test_uses_uv_python_install(self, template_content):
        """Test that template uses 'uv python install' instead of setup-python."""
        assert "uv python install" in template_content

    def test_uses_uv_actions_for_deps(self, template_content):
        """Test that template uses install-deps-uv action for dependencies."""
        assert "install-deps-uv" in template_content

    def test_uses_uvx_ruff(self, template_content):
        """Test that template uses 'uvx ruff' for formatting and linting."""
        assert "uvx ruff format" in template_content
        assert "uvx ruff check" in template_content

    def test_uses_uv_actions_for_build(self, template_content):
        """Test that template uses build-dist-uv action for distribution building."""
        assert "build-dist-uv" in template_content

    def test_uses_uv_actions_for_publish(self, template_content):
        """Test that template uses pypi-publish-uv action for PyPI upload."""
        assert "pypi-publish-uv" in template_content

    def test_uses_uv_actions_for_tests(self, template_content):
        """Test that template uses run-tests-uv action for testing."""
        assert "run-tests-uv" in template_content

    def test_uses_uv_actions_for_python_setup(self, template_content):
        """Test that template uses setup-python-uv action."""
        assert "setup-python-uv" in template_content

    def test_publish_references_pypi_password(self, template_content):
        """Test that publish step passes PYPI_PASSWORD secret to action."""
        assert "PYPI_PASSWORD" in template_content

    def test_does_not_use_twine(self, template_content):
        """Test that template does NOT use twine."""
        assert "twine" not in template_content

    def test_does_not_use_pip_directly(self, template_content):
        """Test that template does NOT use 'python -m pip'."""
        assert "python -m pip" not in template_content

    def test_does_not_use_python_m_build(self, template_content):
        """Test that template does NOT use 'python -m build'."""
        assert "python -m build" not in template_content

    # --- Structural tests (same as 2025 template) ---

    def test_setup_job_has_outputs(self, template_data):
        """Test setup job has correct outputs."""
        setup_job = template_data["jobs"]["setup"]
        assert "outputs" in setup_job
        outputs = setup_job["outputs"]
        for output in [
            "project-name",
            "python-versions",
            "pytest-args",
            "coverage-enabled",
            "test-on-windows",
            "build-sdist",
            "build-wheel",
        ]:
            assert output in outputs, f"Missing output: {output}"

    def test_setup_job_uses_read_ci_config(self, template_data):
        """Test that setup job uses read-ci-config action."""
        setup_job = template_data["jobs"]["setup"]
        steps = setup_job["steps"]
        config_step = next((s for s in steps if s.get("id") == "config"), None)
        assert config_step is not None
        assert "i2mint/wads/actions/read-ci-config@master" in config_step["uses"]

    def test_validation_job_uses_matrix(self, template_data):
        """Test that validation job uses matrix strategy."""
        validation_job = template_data["jobs"]["validation"]
        assert "matrix" in validation_job["strategy"]
        assert "python-version" in validation_job["strategy"]["matrix"]

    def test_publish_job_conditional(self, template_data):
        """Test that publish job only runs on main/master."""
        publish_job = template_data["jobs"]["publish"]
        assert "if" in publish_job
        condition = publish_job["if"]
        assert "github.ref" in condition
        assert "master" in condition or "main" in condition

    def test_publish_job_has_key_steps(self, template_data):
        """Test that publish job has version, build, and publish steps."""
        publish_job = template_data["jobs"]["publish"]
        step_names = [s.get("name", "") for s in publish_job["steps"]]
        assert any("version" in n.lower() for n in step_names)
        assert any("build" in n.lower() for n in step_names)
        assert any("publish" in n.lower() or "pypi" in n.lower() for n in step_names)

    def test_windows_validation_is_conditional(self, template_data):
        """Test that Windows validation checks test-on-windows."""
        windows_job = template_data["jobs"]["windows-validation"]
        assert "if" in windows_job
        assert "test-on-windows" in windows_job["if"]

    def test_windows_validation_is_non_blocking(self, template_data):
        """Test that Windows validation has continue-on-error."""
        windows_job = template_data["jobs"]["windows-validation"]
        assert windows_job.get("continue-on-error") is True

    def test_job_dependencies(self, template_data):
        """Test that job dependencies form a valid DAG."""
        jobs = template_data["jobs"]
        assert "setup" in jobs["validation"]["needs"]
        needs = jobs["publish"]["needs"]
        if isinstance(needs, list):
            assert "validation" in needs
        else:
            assert needs == "validation"
        assert "setup" in jobs["windows-validation"]["needs"]

    def test_validation_job_still_uses_install_system_deps(self, template_data):
        """Test that install-system-deps action is still used (not replaced by uv)."""
        validation_job = template_data["jobs"]["validation"]
        steps = validation_job["steps"]
        action_uses = [s.get("uses", "") for s in steps if "uses" in s]
        assert any("install-system-deps" in u for u in action_uses)

    def test_publish_job_still_uses_git_actions(self, template_data):
        """Test that git-commit and git-tag actions are still used."""
        publish_job = template_data["jobs"]["publish"]
        steps = publish_job["steps"]
        action_uses = [s.get("uses", "") for s in steps if "uses" in s]
        assert any("git-commit" in u for u in action_uses)
        assert any("git-tag" in u for u in action_uses)

    def test_publish_job_still_uses_bump_version(self, template_data):
        """Test that bump-version-number action is still used."""
        publish_job = template_data["jobs"]["publish"]
        steps = publish_job["steps"]
        action_uses = [s.get("uses", "") for s in steps if "uses" in s]
        assert any("bump-version-number" in u for u in action_uses)


class TestUvMigration:
    """Test the CI migration to uv function."""

    def test_migrate_ci_to_uv_returns_uv_template(self):
        """Test that migrate_ci_to_uv returns the uv template content."""
        from wads.migration import migrate_ci_to_uv

        result = migrate_ci_to_uv("name: CI\non: push")
        assert "astral-sh/setup-uv" in result
        assert "build-dist-uv" in result
        assert "pypi-publish-uv" in result

    def test_migrate_ci_to_uv_adds_setuptools_warning(self):
        """Test that migration adds warning for setuptools-based projects."""
        from wads.migration import migrate_ci_to_uv

        result = migrate_ci_to_uv("name: CI\nrun: setuptools build")
        assert "MIGRATION NOTE" in result
        assert "setuptools" in result

    def test_migrate_ci_to_uv_adds_pypi_auth_warning(self):
        """Test that migration warns about PyPI auth changes."""
        from wads.migration import migrate_ci_to_uv

        result = migrate_ci_to_uv("name: CI\nPYPI_USERNAME: __token__")
        assert "MIGRATION NOTE" in result
        assert "PYPI_PASSWORD" in result or "UV_PUBLISH_TOKEN" in result

    def test_migrate_ci_to_uv_from_file(self, tmp_path):
        """Test migration from an actual file."""
        from wads.migration import migrate_ci_to_uv

        ci_file = tmp_path / "ci.yml"
        ci_file.write_text("name: CI\non: push\njobs: {}")
        result = migrate_ci_to_uv(str(ci_file))
        assert "astral-sh/setup-uv" in result


class TestCIConfigInstaller:
    """Test the installer property on CIConfig."""

    def test_installer_defaults_to_uv(self):
        """Test that installer defaults to 'uv'."""
        from wads.ci_config import CIConfig

        config = CIConfig({"project": {"name": "test"}})
        assert config.installer == "uv"

    def test_installer_reads_from_config(self):
        """Test that installer reads from tool.wads.ci.installer."""
        from wads.ci_config import CIConfig

        data = {
            "project": {"name": "test"},
            "tool": {"wads": {"ci": {"installer": "pip"}}},
        }
        config = CIConfig(data)
        assert config.installer == "pip"

    def test_installer_uv_from_config(self):
        """Test explicit uv installer config."""
        from wads.ci_config import CIConfig

        data = {
            "project": {"name": "test"},
            "tool": {"wads": {"ci": {"installer": "uv"}}},
        }
        config = CIConfig(data)
        assert config.installer == "uv"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
