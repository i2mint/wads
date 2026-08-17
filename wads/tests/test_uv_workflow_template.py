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
        """Test that publish job only runs on the repo's default branch."""
        publish_job = template_data["jobs"]["publish"]
        assert "if" in publish_job
        condition = publish_job["if"]
        assert "github.ref" in condition
        # Gates on the actual default branch (not a literal master/main), so it
        # stays correct for repos whose default branch is named differently.
        assert "github.event.repository.default_branch" in condition

    def test_setup_job_exposes_publish_gate_outputs(self, template_data):
        """Test setup job exposes the publish gate outputs for the publish job."""
        outputs = template_data["jobs"]["setup"]["outputs"]
        for output in ["publish-enabled", "skip-ci-marker", "publish-marker"]:
            assert output in outputs, f"Missing output: {output}"

    def test_publish_job_honors_publish_gate(self, template_data):
        """Test that the publish job `if:` is gated by the publish config."""
        condition = template_data["jobs"]["publish"]["if"]
        # Skip marker (configurable) instead of a hardcoded '[skip ci]'.
        assert "needs.setup.outputs.skip-ci-marker" in condition
        # Fail-closed publish gate: only runs on an explicit 'true'.
        assert "needs.setup.outputs.publish-enabled == 'true'" in condition
        # Per-commit override to force a publish when publishing is disabled.
        assert "needs.setup.outputs.publish-marker" in condition

    def test_github_pages_does_not_depend_on_publish(self, template_data):
        """Test docs publishing survives the publish job being disabled/skipped."""
        needs = template_data["jobs"]["github-pages"]["needs"]
        assert "publish" not in needs

    def test_run_tests_step_honors_tests_enabled(self, template_data):
        """Test that the validation test step is gated by tests-enabled."""
        assert "tests-enabled" in template_data["jobs"]["setup"]["outputs"]
        steps = template_data["jobs"]["validation"]["steps"]
        run_tests = next((s for s in steps if s.get("name") == "Run Tests"), None)
        assert run_tests is not None
        assert "tests-enabled" in run_tests.get("if", "")

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


class TestCIConfigPublish:
    """Test the publish gate properties on CIConfig."""

    def test_publish_enabled_defaults_to_true(self):
        """Test that publishing is enabled by default."""
        from wads.ci_config import CIConfig

        config = CIConfig({"project": {"name": "test"}})
        assert config.publish_enabled is True

    def test_publish_enabled_reads_from_config(self):
        """Test that publish_enabled reads tool.wads.ci.publish.enabled."""
        from wads.ci_config import CIConfig

        data = {
            "project": {"name": "test"},
            "tool": {"wads": {"ci": {"publish": {"enabled": False}}}},
        }
        assert CIConfig(data).publish_enabled is False

    def test_markers_default(self):
        """Test that the commit-message markers have sensible defaults."""
        from wads.ci_config import CIConfig

        config = CIConfig({"project": {"name": "test"}})
        assert config.publish_skip_ci_marker == "[skip ci]"
        assert config.publish_marker == "[publish]"

    def test_markers_read_from_config(self):
        """Test that the markers can be overridden in pyproject.toml."""
        from wads.ci_config import CIConfig

        data = {
            "project": {"name": "test"},
            "tool": {
                "wads": {
                    "ci": {
                        "publish": {
                            "skip_ci_marker": "[no ci]",
                            "publish_marker": "[ship it]",
                        }
                    }
                }
            },
        }
        config = CIConfig(data)
        assert config.publish_skip_ci_marker == "[no ci]"
        assert config.publish_marker == "[ship it]"


class TestCIConfigTesting:
    """Test the tests_enabled property on CIConfig."""

    def test_tests_enabled_defaults_to_true(self):
        """Test that the CI test step is enabled by default."""
        from wads.ci_config import CIConfig

        assert CIConfig({"project": {"name": "test"}}).tests_enabled is True

    def test_tests_enabled_reads_from_config(self):
        """Test that tests_enabled reads tool.wads.ci.testing.enabled."""
        from wads.ci_config import CIConfig

        data = {
            "project": {"name": "test"},
            "tool": {"wads": {"ci": {"testing": {"enabled": False}}}},
        }
        assert CIConfig(data).tests_enabled is False


class TestSecretEnvScoping:
    """Issue #61: secret-backed env vars must never be in scope for the setup
    job. A workflow-level secret gets registered as a log mask for every job,
    and GitHub then refuses to emit any job OUTPUT containing its value — a
    short value (e.g. a test level of "3") silently blanks python-versions
    and the test matrix expands to nothing."""

    SECRET_CI = {
        "project": {"name": "demo"},
        "tool": {
            "wads": {
                "ci": {
                    "env": {
                        "required_envvars": [],
                        "test_envvars": ["OPENAI_API_KEY", "HF_TOKEN"],
                        "extra_envvars": ["COSMO_TEST_LEVEL"],
                        "defaults": {"PYTHONUNBUFFERED": "1"},
                        "secret_aliases": {"HF_TOKEN": "HF_WRITE_TOKEN"},
                    },
                }
            }
        },
    }

    @pytest.fixture
    def template_content(self):
        """Load the inline uv template's raw content."""
        from wads import data_dir

        return (Path(data_dir) / "github_ci_uv.yml").read_text()

    def _render(self, template_content, pyproject_data):
        from wads.ci_config import CIConfig

        rendered = template_content
        substitutions = CIConfig(pyproject_data).to_ci_template_substitutions()
        for placeholder, value in substitutions.items():
            rendered = rendered.replace(placeholder, value)
        return rendered

    def test_workflow_level_env_has_no_secrets(self, template_content):
        """Workflow-level env carries only PROJECT_NAME + literal defaults."""
        data = yaml.safe_load(self._render(template_content, self.SECRET_CI))
        workflow_env = data["env"]
        assert workflow_env["PROJECT_NAME"] == "demo"
        assert str(workflow_env["PYTHONUNBUFFERED"]) == "1"
        assert "secrets." not in str(workflow_env)

    def test_setup_job_sees_no_secrets(self, template_content):
        """The job that emits python-versions must reference no secret."""
        import json

        data = yaml.safe_load(self._render(template_content, self.SECRET_CI))
        setup_job = data["jobs"]["setup"]
        assert "env" not in setup_job
        assert "secrets." not in json.dumps(setup_job)

    def test_validation_job_gets_secret_env(self, template_content):
        """Secret-backed vars land in the validation job's env, aliased
        names reading their backing secret."""
        data = yaml.safe_load(self._render(template_content, self.SECRET_CI))
        env = data["jobs"]["validation"]["env"]
        assert env["OPENAI_API_KEY"] == "${{ secrets.OPENAI_API_KEY || '' }}"
        assert env["COSMO_TEST_LEVEL"] == "${{ secrets.COSMO_TEST_LEVEL || '' }}"
        assert env["HF_TOKEN"] == "${{ secrets.HF_WRITE_TOKEN || '' }}"

    def test_windows_job_gets_secret_env_and_keeps_utf8(self, template_content):
        """The windows job's existing UTF-8 env entries survive the merge."""
        data = yaml.safe_load(self._render(template_content, self.SECRET_CI))
        env = data["jobs"]["windows-validation"]["env"]
        assert str(env["PYTHONUTF8"]) == "1"
        assert env["COSMO_TEST_LEVEL"] == "${{ secrets.COSMO_TEST_LEVEL || '' }}"

    def test_no_secret_vars_renders_valid_yaml_without_env(self, template_content):
        """With nothing declared, the validation job has no env key at all
        (an empty env: mapping would be invalid), and no placeholder leaks."""
        rendered = self._render(template_content, {"project": {"name": "demo"}})
        for placeholder in ("#ENV_BLOCK#", "#TEST_ENV_BLOCK#", "#TEST_ENV_VARS#"):
            assert placeholder not in rendered
        data = yaml.safe_load(rendered)
        assert "env" not in data["jobs"]["validation"]
        # windows keeps its literal UTF-8 entries even with no secret vars
        assert str(data["jobs"]["windows-validation"]["env"]["PYTHONUTF8"]) == "1"

    def test_default_is_authoritative_over_same_named_secret(self, template_content):
        """A var in BOTH env.defaults and an envvars bucket renders only at
        workflow level (the committed default), never as a job-level
        `${{ secrets.X || '' }}` that would override it with '' in the test
        jobs (adversarial-review finding; matches export-ci-env semantics)."""
        config = {
            "project": {"name": "demo"},
            "tool": {
                "wads": {
                    "ci": {
                        "env": {
                            "extra_envvars": ["COSMO_TEST_LEVEL"],
                            "defaults": {"COSMO_TEST_LEVEL": "3"},
                        }
                    }
                }
            },
        }
        data = yaml.safe_load(self._render(template_content, config))
        assert str(data["env"]["COSMO_TEST_LEVEL"]) == "3"
        # the only declared var is defaulted, so the test jobs add nothing
        assert "env" not in data["jobs"]["validation"]
        assert "COSMO_TEST_LEVEL" not in data["jobs"]["windows-validation"]["env"]

    def test_windows_literal_env_keys_are_not_duplicated(self, template_content):
        """Declaring PYTHONUTF8 as an envvar must not render a duplicate key
        in the windows job's env mapping (which fails the whole workflow at
        parse time); the validation job still receives it."""
        config = {
            "project": {"name": "demo"},
            "tool": {"wads": {"ci": {"env": {"test_envvars": ["PYTHONUTF8"]}}}},
        }
        rendered = self._render(template_content, config)
        data = yaml.safe_load(rendered)
        assert (
            data["jobs"]["validation"]["env"]["PYTHONUTF8"]
            == "${{ secrets.PYTHONUTF8 || '' }}"
        )
        assert str(data["jobs"]["windows-validation"]["env"]["PYTHONUTF8"]) == "1"
        # exactly one PYTHONUTF8 key line inside the windows job's env
        windows_section = rendered[rendered.index("windows-validation:") :]
        windows_section = windows_section[: windows_section.index("steps:")]
        assert windows_section.count("PYTHONUTF8:") == 1

    def test_migrate_warns_about_test_job_scoping(self, tmp_path):
        """migrate_ci_to_uv announces the #61 scoping change when the repo
        declares secret-backed vars, and stays quiet when it declares none."""
        from wads.migration import migrate_ci_to_uv

        wf = tmp_path / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "ci.yml").write_text("name: old\non: push\n")
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "demo"\n\n'
            "[tool.wads.ci.env]\nextra_envvars = [\"COSMO_TEST_LEVEL\"]\n"
        )
        result = migrate_ci_to_uv(wf / "ci.yml")
        assert "scoped to the test jobs" in result

        (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo"\n')
        result = migrate_ci_to_uv(wf / "ci.yml")
        assert "scoped to the test jobs" not in result

    def test_minimal_placeholder_render_helper(self, template_content):
        """render_minimal_env_placeholders (used by the populate static path
        and the migrate fallback) leaks no placeholders and stays valid."""
        from wads.ci_config import render_minimal_env_placeholders

        rendered = render_minimal_env_placeholders(template_content, "demo")
        for placeholder in ("#ENV_BLOCK#", "#TEST_ENV_BLOCK#", "#TEST_ENV_VARS#"):
            assert placeholder not in rendered
        data = yaml.safe_load(rendered)
        assert data["env"]["PROJECT_NAME"] == "demo"
        assert "env" not in data["jobs"]["validation"]

    def test_fallback_render_strips_placeholders(self):
        """migrate_ci_to_uv without a pyproject.toml (string input) must not
        leak placeholders and must stay valid YAML."""
        from wads.migration import migrate_ci_to_uv

        result = migrate_ci_to_uv("name: CI\non: push")
        assert "#ENV_BLOCK#" not in result
        assert "#TEST_ENV" not in result
        data = yaml.safe_load(result)
        assert "env" not in data["jobs"]["validation"]
        assert "secrets." not in str(data.get("env", {}))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
