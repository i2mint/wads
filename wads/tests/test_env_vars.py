"""Test environment variables configuration in CI."""

import tempfile
from pathlib import Path
from wads.ci_config import CIConfig


def test_env_vars_parsing():
    """Test that environment variables are correctly parsed from pyproject.toml."""

    # Create a test pyproject.toml with env vars
    pyproject_content = """
[project]
name = "test-project"
version = "0.1.0"

[tool.wads.ci]
project_name = "test-project"

[tool.wads.ci.env]
required_envvars = ["DATABASE_URL", "API_KEY"]
test_envvars = ["OPENAI_API_KEY", "TEST_SECRET"]
extra_envvars = ["FEATURE_FLAG_X"]
defaults = {LOG_LEVEL = "DEBUG", TESTING = "true"}
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        pyproject_path = tmpdir_path / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        # Load config
        config = CIConfig.from_file(pyproject_path)

        # Test required env vars
        assert config.env_vars_required == ["DATABASE_URL", "API_KEY"]

        # Test test env vars
        assert config.env_vars_test == ["OPENAI_API_KEY", "TEST_SECRET"]

        # Test extra env vars
        assert config.env_vars_extra == ["FEATURE_FLAG_X"]

        # Test all env vars
        assert set(config.env_vars_all) == {
            "DATABASE_URL",
            "API_KEY",
            "OPENAI_API_KEY",
            "TEST_SECRET",
            "FEATURE_FLAG_X",
        }

        # Test defaults
        assert config.env_vars_defaults == {"LOG_LEVEL": "DEBUG", "TESTING": "true"}

        print("✅ All env vars tests passed!")


def test_env_vars_yaml_generation():
    """Test that env vars YAML is correctly generated."""

    pyproject_content = """
[project]
name = "test-project"

[tool.wads.ci.env]
required_envvars = ["API_KEY"]
test_envvars = ["TEST_KEY"]
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        pyproject_path = tmpdir_path / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        config = CIConfig.from_file(pyproject_path)

        # Generate env vars YAML
        env_yaml = config.generate_env_vars_yaml()

        # Check that it contains the expected vars
        assert "API_KEY: ${{ secrets.API_KEY || '' }}" in env_yaml
        assert "TEST_KEY: ${{ secrets.TEST_KEY || '' }}" in env_yaml

        print("✅ Env vars YAML generation test passed!")


def test_env_vars_in_template_substitutions():
    """Test that env vars are included in template substitutions."""

    pyproject_content = """
[project]
name = "my-project"

[tool.wads.ci.env]
required_envvars = ["REQUIRED_VAR"]
test_envvars = ["TEST_VAR"]
defaults = {DEFAULT_VAR = "default_value"}
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        pyproject_path = tmpdir_path / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        config = CIConfig.from_file(pyproject_path)

        # Get substitutions
        substitutions = config.to_ci_template_substitutions()

        # Check that PROJECT_NAME is there
        assert substitutions["#PROJECT_NAME#"] == "my-project"

        # Check that ENV_VARS includes the expected content
        env_vars = substitutions["#ENV_VARS#"]
        assert "REQUIRED_VAR" in env_vars
        assert "TEST_VAR" in env_vars
        assert "secrets.REQUIRED_VAR" in env_vars

        print("✅ Template substitutions test passed!")


if __name__ == "__main__":
    test_env_vars_parsing()
    test_env_vars_yaml_generation()
    test_env_vars_in_template_substitutions()
    print("\n" + "=" * 70)
    print("✅ ALL TESTS PASSED!")
    print("=" * 70)
