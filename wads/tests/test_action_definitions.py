"""Test GitHub Actions action.yml files."""

import yaml
from pathlib import Path
import pytest


class TestActionDefinitions:
    """Test that action.yml files are valid and properly structured."""

    @pytest.fixture
    def actions_dir(self):
        """Get actions directory path."""
        # Get wads package directory
        import wads

        wads_dir = Path(wads.__file__).parent.parent
        actions_path = wads_dir / "actions"

        # If not found, try relative to this file
        if not actions_path.exists():
            test_dir = Path(__file__).parent.parent.parent
            actions_path = test_dir / "actions"

        return actions_path

    @pytest.fixture
    def action_files(self, actions_dir):
        """Get all action.yml files."""
        if not actions_dir.exists():
            pytest.skip(f"Actions directory not found: {actions_dir}")

        return list(actions_dir.rglob("action.yml"))

    def test_actions_directory_exists(self, actions_dir):
        """Test that actions directory exists."""
        assert actions_dir.exists(), f"Actions directory not found: {actions_dir}"
        assert actions_dir.is_dir()

    def test_actions_exist(self, action_files):
        """Test that action.yml files exist."""
        assert len(action_files) > 0, "No action.yml files found"

    def test_all_actions_have_valid_yaml(self, action_files):
        """Test that all action.yml files are valid YAML."""
        for action_file in action_files:
            with open(action_file) as f:
                data = yaml.safe_load(f)

            assert data is not None, f"Empty YAML in {action_file}"
            assert isinstance(data, dict), f"Invalid YAML structure in {action_file}"

    def test_all_actions_have_required_fields(self, action_files):
        """Test that all actions have required fields."""
        for action_file in action_files:
            with open(action_file) as f:
                data = yaml.safe_load(f)

            # Required fields
            assert 'name' in data, f"Missing 'name' in {action_file}"
            assert 'description' in data, f"Missing 'description' in {action_file}"
            assert 'runs' in data, f"Missing 'runs' in {action_file}"

            # Runs should have required structure
            runs = data['runs']
            assert 'using' in runs, f"Missing 'using' in {action_file}/runs"

    def test_composite_actions_have_steps(self, action_files):
        """Test that composite actions have steps."""
        for action_file in action_files:
            with open(action_file) as f:
                data = yaml.safe_load(f)

            runs = data['runs']
            if runs.get('using') == 'composite':
                assert 'steps' in runs, f"Composite action missing steps: {action_file}"
                assert isinstance(runs['steps'], list)
                assert len(runs['steps']) > 0

    def test_action_inputs_have_descriptions(self, action_files):
        """Test that action inputs have descriptions."""
        for action_file in action_files:
            with open(action_file) as f:
                data = yaml.safe_load(f)

            if 'inputs' in data:
                for input_name, input_def in data['inputs'].items():
                    assert (
                        'description' in input_def
                    ), f"Input '{input_name}' missing description in {action_file}"

    def test_action_outputs_have_descriptions(self, action_files):
        """Test that action outputs have descriptions."""
        for action_file in action_files:
            with open(action_file) as f:
                data = yaml.safe_load(f)

            if 'outputs' in data:
                for output_name, output_def in data['outputs'].items():
                    assert (
                        'description' in output_def
                    ), f"Output '{output_name}' missing description in {action_file}"

    def test_script_actions_reference_valid_scripts(self, actions_dir):
        """Test that actions referencing scripts use correct paths."""
        # Actions that should use scripts
        script_actions = {
            'read-ci-config': 'read_ci_config',
            'build-dist': 'build_dist',
            'set-env-vars': 'set_env_vars',
        }

        for action_name, script_name in script_actions.items():
            action_file = actions_dir / action_name / "action.yml"
            if not action_file.exists():
                continue

            content = action_file.read_text()

            # Should reference the Python script
            assert (
                'wads.scripts' in content
            ), f"{action_name} should reference wads.scripts"
            assert (
                script_name in content
            ), f"{action_name} should reference {script_name}"

    def test_actions_use_python3_not_python(self, action_files):
        """Test that actions use python3 explicitly."""
        for action_file in action_files:
            content = action_file.read_text()

            # If it runs python, should use python3 or sys.executable
            if 'python -m' in content and 'python3 -m' not in content:
                # Allow 'python -m pip' as it's called via sys.executable
                if 'python -m pip' not in content:
                    pytest.fail(f"{action_file} uses 'python' instead of 'python3'")

    def test_bash_steps_have_error_handling(self, action_files):
        """Test that complex bash steps have error handling."""
        for action_file in action_files:
            with open(action_file) as f:
                data = yaml.safe_load(f)

            runs = data.get('runs', {})
            if runs.get('using') != 'composite':
                continue

            for step in runs.get('steps', []):
                if step.get('shell') == 'bash' and 'run' in step:
                    run_script = step['run']
                    # Only check truly complex scripts (not simple wrappers)
                    # Check for scripts with multiple commands and logic
                    line_count = len(
                        [
                            l
                            for l in run_script.split('\n')
                            if l.strip() and not l.strip().startswith('#')
                        ]
                    )

                    if line_count > 5:  # More than 5 non-comment lines
                        # Skip if it's just calling external tools
                        if 'python3 -m' in run_script or 'python -m' in run_script:
                            # Simple Python module wrapper
                            if line_count < 10:
                                continue

                        # Should have some form of error handling
                        has_error_handling = (
                            'set -e' in run_script
                            or 'set -eo' in run_script
                            or '|| ' in run_script
                            or 'EXIT_CODE=$?' in run_script
                            or 'exit $' in run_script
                            or 'if ' in run_script
                        )
                        assert (
                            has_error_handling
                        ), f"Complex bash step in {action_file} missing error handling (lines: {line_count})"

    def test_actions_have_proper_shell_specification(self, action_files):
        """Test that steps specify shell when needed."""
        for action_file in action_files:
            with open(action_file) as f:
                data = yaml.safe_load(f)

            runs = data.get('runs', {})
            if runs.get('using') != 'composite':
                continue

            for step in runs.get('steps', []):
                if 'run' in step:
                    # Composite action steps should specify shell
                    assert (
                        'shell' in step
                    ), f"Step with 'run' missing 'shell' in {action_file}"

    def test_install_deps_action_structure(self, actions_dir):
        """Test install-deps action has correct structure."""
        action_file = actions_dir / "install-deps" / "action.yml"
        if not action_file.exists():
            pytest.skip("install-deps action not found")

        with open(action_file) as f:
            data = yaml.safe_load(f)

        # Should have inputs for different package sources
        inputs = data.get('inputs', {})
        assert 'pypi-packages' in inputs or 'dependency-files' in inputs

    def test_build_dist_action_structure(self, actions_dir):
        """Test build-dist action has correct structure."""
        action_file = actions_dir / "build-dist" / "action.yml"
        if not action_file.exists():
            pytest.skip("build-dist action not found")

        with open(action_file) as f:
            data = yaml.safe_load(f)

        # Should have inputs for build options
        inputs = data.get('inputs', {})
        assert 'output-dir' in inputs
        assert 'sdist' in inputs or 'wheel' in inputs

    def test_read_ci_config_action_outputs(self, actions_dir):
        """Test read-ci-config action has necessary outputs."""
        action_file = actions_dir / "read-ci-config" / "action.yml"
        if not action_file.exists():
            pytest.skip("read-ci-config action not found")

        with open(action_file) as f:
            data = yaml.safe_load(f)

        # Should have outputs for CI configuration
        outputs = data.get('outputs', {})
        expected_outputs = [
            'project-name',
            'python-versions',
            'pytest-args',
            'coverage-enabled',
        ]

        for output in expected_outputs:
            assert output in outputs, f"Missing output: {output}"

    def test_set_env_vars_action_structure(self, actions_dir):
        """Test set-env-vars action has correct structure."""
        action_file = actions_dir / "set-env-vars" / "action.yml"
        if not action_file.exists():
            pytest.skip("set-env-vars action not found")

        with open(action_file) as f:
            data = yaml.safe_load(f)

        # Should accept pyproject path input
        inputs = data.get('inputs', {})
        assert 'pyproject-path' in inputs

    def test_actions_dont_hardcode_credentials(self, action_files):
        """Test that actions don't contain hardcoded credentials."""
        sensitive_patterns = [
            'password',
            'token',
            'api_key',
            'secret',
        ]

        for action_file in action_files:
            content = action_file.read_text().lower()

            for pattern in sensitive_patterns:
                if pattern in content:
                    # Make sure it's using inputs or secrets, not hardcoded
                    assert (
                        'inputs.' in content
                        or 'secrets.' in content
                        or '${{' in content
                    ), f"Possible hardcoded credential in {action_file}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
