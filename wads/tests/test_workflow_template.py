"""Test the github_ci_publish_2025.yml workflow template."""

import yaml
from pathlib import Path
import pytest


class TestWorkflowTemplate:
    """Test the CI workflow template structure and validity."""

    @pytest.fixture
    def template_path(self):
        """Get path to the workflow template."""
        from wads import data_dir

        return Path(data_dir) / "github_ci_publish_2025.yml"

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
        assert 'name' in template_data
        # YAML parses 'on' as True (boolean), so check for True or 'on'
        assert True in template_data or 'on' in template_data
        assert 'jobs' in template_data
        assert isinstance(template_data['jobs'], dict)

    def test_template_has_required_jobs(self, template_data):
        """Test that template has all required jobs."""
        jobs = template_data['jobs']

        required_jobs = ['setup', 'validation', 'publish']
        for job_name in required_jobs:
            assert job_name in jobs, f"Missing required job: {job_name}"

    def test_template_has_optional_jobs(self, template_data):
        """Test that template includes optional jobs."""
        jobs = template_data['jobs']

        # These jobs should exist but may be conditional
        optional_jobs = ['windows-validation', 'github-pages']
        for job_name in optional_jobs:
            assert job_name in jobs, f"Missing optional job: {job_name}"

    def test_setup_job_structure(self, template_data):
        """Test setup job has correct structure."""
        setup_job = template_data['jobs']['setup']

        assert 'name' in setup_job
        assert 'runs-on' in setup_job
        assert 'outputs' in setup_job
        assert 'steps' in setup_job

        # Check that it outputs configuration
        outputs = setup_job['outputs']
        expected_outputs = [
            'project-name',
            'python-versions',
            'pytest-args',
            'coverage-enabled',
            'test-on-windows',
            'build-sdist',
            'build-wheel',
        ]
        for output in expected_outputs:
            assert output in outputs, f"Missing output: {output}"

    def test_setup_job_uses_read_ci_config_action(self, template_data):
        """Test that setup job uses read-ci-config action."""
        setup_job = template_data['jobs']['setup']
        steps = setup_job['steps']

        # Find the step that reads config
        config_step = next((s for s in steps if s.get('id') == 'config'), None)

        assert config_step is not None, "Missing config reading step"
        assert 'uses' in config_step
        assert 'i2mint/wads/actions/read-ci-config@master' in config_step['uses']

    def test_validation_job_structure(self, template_data):
        """Test validation job has correct structure."""
        validation_job = template_data['jobs']['validation']

        assert 'name' in validation_job
        assert 'needs' in validation_job
        assert 'setup' in validation_job['needs']
        assert 'runs-on' in validation_job
        assert 'strategy' in validation_job
        assert 'steps' in validation_job

    def test_validation_job_uses_matrix(self, template_data):
        """Test that validation job uses matrix strategy."""
        validation_job = template_data['jobs']['validation']
        strategy = validation_job['strategy']

        assert 'matrix' in strategy
        matrix = strategy['matrix']
        assert 'python-version' in matrix

    def test_validation_job_uses_config_outputs(self, template_data):
        """Test that validation job references setup outputs."""
        validation_job = template_data['jobs']['validation']

        # Convert to string to search for references
        job_str = str(validation_job)

        # Should reference setup job outputs
        assert 'needs.setup.outputs' in job_str

    def test_validation_job_has_required_steps(self, template_data):
        """Test that validation job has required steps."""
        validation_job = template_data['jobs']['validation']
        steps = validation_job['steps']

        # Get step names and uses
        step_info = [(s.get('name', ''), s.get('uses', '')) for s in steps]

        # Check for essential steps (either in name or uses)
        essential_keywords = [
            'checkout',  # actions/checkout
            'python',  # setup-python or Python in name
            'install',  # install dependencies
            'test',  # run tests
        ]

        for keyword in essential_keywords:
            assert any(
                keyword.lower() in name.lower() or keyword.lower() in uses.lower()
                for name, uses in step_info
            ), f"Missing step containing keyword: {keyword}"

    def test_validation_job_uses_wads_actions(self, template_data):
        """Test that validation job uses wads actions."""
        validation_job = template_data['jobs']['validation']
        steps = validation_job['steps']

        # Collect all action uses
        action_uses = [s.get('uses', '') for s in steps if 'uses' in s]

        # Should use wads actions
        wads_actions = [u for u in action_uses if 'i2mint/wads/actions/' in u]
        assert len(wads_actions) > 0, "Validation job should use wads actions"

    def test_publish_job_structure(self, template_data):
        """Test publish job has correct structure."""
        publish_job = template_data['jobs']['publish']

        assert 'name' in publish_job
        assert 'needs' in publish_job
        assert 'validation' in publish_job['needs']
        assert 'runs-on' in publish_job
        assert 'steps' in publish_job

    def test_publish_job_conditional_execution(self, template_data):
        """Test that publish job only runs on main/master."""
        publish_job = template_data['jobs']['publish']

        assert 'if' in publish_job
        condition = publish_job['if']

        # Should check branch
        assert 'github.ref' in condition
        assert 'master' in condition or 'main' in condition

    def test_publish_job_has_version_and_build_steps(self, template_data):
        """Test that publish job has version bump and build steps."""
        publish_job = template_data['jobs']['publish']
        steps = publish_job['steps']

        step_names = [s.get('name', '') for s in steps]

        # Should have version and build steps
        assert any('version' in name.lower() for name in step_names)
        assert any('build' in name.lower() for name in step_names)
        assert any(
            'pypi' in name.lower() or 'publish' in name.lower() for name in step_names
        )

    def test_windows_validation_is_conditional(self, template_data):
        """Test that Windows validation is conditional."""
        windows_job = template_data['jobs']['windows-validation']

        assert 'if' in windows_job
        condition = windows_job['if']

        # Should check test-on-windows output
        assert 'test-on-windows' in condition

    def test_windows_validation_is_non_blocking(self, template_data):
        """Test that Windows validation doesn't block pipeline."""
        windows_job = template_data['jobs']['windows-validation']

        # Should have continue-on-error
        assert 'continue-on-error' in windows_job
        assert windows_job['continue-on-error'] is True

    def test_all_jobs_skip_on_skip_ci(self, template_data):
        """Test that jobs respect [skip ci] commit message."""
        jobs = template_data['jobs']

        # Most jobs should skip on [skip ci]
        conditional_jobs = ['validation', 'windows-validation', 'publish']

        for job_name in conditional_jobs:
            if job_name in jobs:
                job = jobs[job_name]
                if 'if' in job:
                    assert '[skip ci]' in job['if'] or 'skip ci' in job['if']

    def test_actions_use_correct_versions(self, template_data):
        """Test that actions use appropriate version tags."""
        jobs = template_data['jobs']

        # Collect all action uses
        all_actions = []
        for job_name, job in jobs.items():
            for step in job.get('steps', []):
                if 'uses' in step:
                    all_actions.append(step['uses'])

        # Check wads actions use @master or specific version
        wads_actions = [a for a in all_actions if 'i2mint/wads/actions/' in a]
        for action in wads_actions:
            # Should have version specifier
            assert '@' in action, f"Action missing version: {action}"

    def test_no_hardcoded_secrets(self, template_content):
        """Test that template doesn't contain hardcoded secrets."""
        # Common secret patterns
        secret_patterns = [
            'password:',
            'token:',
            'api_key:',
            'secret:',
        ]

        content_lower = template_content.lower()

        for pattern in secret_patterns:
            if pattern in content_lower:
                # Make sure it's using secrets context
                assert 'secrets.' in template_content or '${{' in template_content

    def test_checkout_actions_have_correct_settings(self, template_data):
        """Test that checkout actions have appropriate settings."""
        publish_job = template_data['jobs']['publish']

        # Find checkout step in publish
        checkout_step = next(
            (
                s
                for s in publish_job['steps']
                if 'actions/checkout' in s.get('uses', '')
            ),
            None,
        )

        if checkout_step:
            with_params = checkout_step.get('with', {})
            # Publish should fetch full history for version generation
            assert 'fetch-depth' in with_params

    def test_python_setup_actions_use_matrix(self, template_data):
        """Test that Python setup uses matrix variables correctly."""
        validation_job = template_data['jobs']['validation']

        # Find Python setup step
        python_step = next(
            (
                s
                for s in validation_job['steps']
                if 'actions/setup-python' in s.get('uses', '')
            ),
            None,
        )

        assert python_step is not None
        with_params = python_step.get('with', {})
        assert 'python-version' in with_params

    def test_template_has_proper_permissions(self, template_data):
        """Test that jobs have appropriate permissions where needed."""
        # GitHub pages job should have permissions
        if 'github-pages' in template_data['jobs']:
            gh_pages_job = template_data['jobs']['github-pages']
            assert 'permissions' in gh_pages_job

    def test_job_dependencies_are_correct(self, template_data):
        """Test that job dependencies form a valid DAG."""
        jobs = template_data['jobs']

        # validation depends on setup
        assert 'setup' in jobs['validation']['needs']

        # publish depends on validation (and setup via validation)
        needs = jobs['publish']['needs']
        if isinstance(needs, list):
            assert 'validation' in needs
        else:
            assert needs == 'validation'

        # windows-validation depends on setup
        assert 'setup' in jobs['windows-validation']['needs']

    def test_template_uses_latest_action_versions(self, template_data):
        """Test that standard actions use recent versions."""
        jobs = template_data['jobs']

        # Collect all action uses
        all_actions = []
        for job_name, job in jobs.items():
            for step in job.get('steps', []):
                if 'uses' in step:
                    all_actions.append(step['uses'])

        # Check for outdated versions of common actions
        for action in all_actions:
            if 'actions/checkout@' in action:
                # Should use v4 or higher
                assert '@v4' in action or '@v5' in action or '@v6' in action

            if 'actions/setup-python@' in action:
                # Should use v5 or higher
                assert '@v5' in action or '@v6' in action


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
