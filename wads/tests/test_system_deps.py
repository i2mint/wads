"""Quick test to verify system dependencies functionality."""

import sys

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from wads.ci_config import CIConfig


def test_system_deps_list():
    """Test system dependencies as a simple list (Ubuntu only)."""
    pyproject_data = {
        "project": {"name": "test-project"},
        "tool": {
            "wads": {
                "ci": {"testing": {"system_dependencies": ["ffmpeg", "libsndfile1"]}}
            }
        },
    }

    config = CIConfig(pyproject_data)

    # Check property
    assert config.system_dependencies == ["ffmpeg", "libsndfile1"]

    # Check normalization
    normalized = config._normalize_system_deps()
    assert normalized == {
        "ubuntu": ["ffmpeg", "libsndfile1"],
        "macos": [],
        "windows": [],
    }

    # Check pre-test steps generation
    pre_test_steps = config.generate_pre_test_steps()
    assert "Install System Dependencies" in pre_test_steps
    assert "sudo apt-get update" in pre_test_steps
    assert "sudo apt-get install -y ffmpeg libsndfile1" in pre_test_steps

    print("✅ test_system_deps_list passed")


def test_system_deps_dict():
    """Test system dependencies as a platform-specific dict."""
    pyproject_data = {
        "project": {"name": "test-project"},
        "tool": {
            "wads": {
                "ci": {
                    "testing": {
                        "system_dependencies": {
                            "ubuntu": ["ffmpeg", "libsndfile1"],
                            "macos": ["ffmpeg", "libsndfile"],
                            "windows": ["ffmpeg"],
                        }
                    }
                }
            }
        },
    }

    config = CIConfig(pyproject_data)

    # Check normalization
    normalized = config._normalize_system_deps()
    assert normalized == {
        "ubuntu": ["ffmpeg", "libsndfile1"],
        "macos": ["ffmpeg", "libsndfile"],
        "windows": ["ffmpeg"],
    }

    # Check Ubuntu pre-test steps
    pre_test_steps = config.generate_pre_test_steps()
    assert "sudo apt-get install -y ffmpeg libsndfile1" in pre_test_steps

    # Check Windows validation job
    windows_job = config.generate_windows_validation_job()
    assert "choco install -y ffmpeg" in windows_job

    print("✅ test_system_deps_dict passed")


def test_no_system_deps():
    """Test that no system deps results in empty steps."""
    pyproject_data = {
        "project": {"name": "test-project"},
        "tool": {"wads": {"ci": {"testing": {}}}},
    }

    config = CIConfig(pyproject_data)

    # Should return empty list by default
    assert config.system_dependencies == []

    # Should generate no steps
    pre_test_steps = config.generate_pre_test_steps()
    assert pre_test_steps == ""

    print("✅ test_no_system_deps passed")


def test_system_deps_with_pre_test_commands():
    """Test system deps combined with custom pre-test commands."""
    pyproject_data = {
        "project": {"name": "test-project"},
        "tool": {
            "wads": {
                "ci": {
                    "commands": {"pre_test": ["python setup_data.py", "echo 'Ready'"]},
                    "testing": {"system_dependencies": ["ffmpeg"]},
                }
            }
        },
    }

    config = CIConfig(pyproject_data)

    # Should have both system deps and pre-test commands
    pre_test_steps = config.generate_pre_test_steps()
    assert "Install System Dependencies" in pre_test_steps
    assert "sudo apt-get install -y ffmpeg" in pre_test_steps
    assert "Pre-test Setup" in pre_test_steps
    assert "python setup_data.py" in pre_test_steps
    assert "echo 'Ready'" in pre_test_steps

    print("✅ test_system_deps_with_pre_test_commands passed")


def test_ci_template_substitutions():
    """Test that system deps are included in template substitutions."""
    pyproject_data = {
        "project": {"name": "test-project"},
        "tool": {
            "wads": {
                "ci": {
                    "testing": {
                        "system_dependencies": ["ffmpeg"],
                        "python_versions": ["3.10", "3.12"],
                    }
                }
            }
        },
    }

    config = CIConfig(pyproject_data)
    substitutions = config.to_ci_template_substitutions()

    # Check that PRE_TEST_STEPS includes system deps
    assert "#PRE_TEST_STEPS#" in substitutions
    assert "ffmpeg" in substitutions["#PRE_TEST_STEPS#"]

    print("✅ test_ci_template_substitutions passed")


if __name__ == "__main__":
    test_system_deps_list()
    test_system_deps_dict()
    test_no_system_deps()
    test_system_deps_with_pre_test_commands()
    test_ci_template_substitutions()

    print("\n" + "=" * 60)
    print("✅ All tests passed!")
    print("=" * 60)
