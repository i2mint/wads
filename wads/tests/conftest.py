"""
Pytest configuration and hooks for wads tests.
"""

import pytest
from collections import Counter
from pathlib import Path


@pytest.fixture
def sample_pyproject(tmp_path):
    """Create a sample pyproject.toml for testing."""
    content = """
[project]
name = "test-project"
version = "0.1.0"
description = "A test project"

[tool.wads.ci.testing]
python_versions = ["3.10", "3.12"]
coverage_enabled = true
pytest_args = ["-v"]
exclude_paths = ["examples", "scrap"]

[tool.wads.ci.env]
required_envvars = ["API_KEY"]
test_envvars = ["TEST_SECRET"]
defaults = {LOG_LEVEL = "INFO"}

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
"""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(content)
    return pyproject


@pytest.fixture
def sample_package(tmp_path):
    """Create a sample package structure for testing."""
    pkg_dir = tmp_path / "test_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text('__version__ = "0.1.0"')

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

    return tmp_path


@pytest.fixture
def github_env_files(tmp_path):
    """Create temporary files for GitHub Actions environment."""
    files = {
        'output': tmp_path / 'github_output.txt',
        'env': tmp_path / 'github_env.txt',
        'summary': tmp_path / 'github_summary.md',
    }

    for file in files.values():
        file.touch()

    return files


@pytest.fixture
def github_actions_env(github_env_files, tmp_path):
    """Mock GitHub Actions environment variables."""
    return {
        'GITHUB_OUTPUT': str(github_env_files['output']),
        'GITHUB_ENV': str(github_env_files['env']),
        'GITHUB_STEP_SUMMARY': str(github_env_files['summary']),
        'GITHUB_WORKSPACE': str(tmp_path),
        'GITHUB_REPOSITORY': 'test/test-repo',
        'GITHUB_REF': 'refs/heads/main',
    }


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test (slower)"
    )
    config.addinivalue_line("markers", "requires_git: mark test as requiring git")
    config.addinivalue_line(
        "markers", "requires_network: mark test as requiring network access"
    )


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """
    Custom hook to count and display error messages in the summary.
    Provides a grouped view of errors to make logs more readable.
    """
    terminalreporter.section("Error Summary Analysis")

    # Collect all error messages
    error_counts = Counter()
    for report in terminalreporter.stats.get("failed", []):
        if report.longrepr:
            # Extract the last line of the error (usually the Exception message)
            msg = str(report.longrepr).split("\n")[-1]
            error_counts[msg] += 1

    for report in terminalreporter.stats.get("error", []):
        if report.longrepr:
            msg = str(report.longrepr).split("\n")[-1]
            error_counts[msg] += 1

    # Print the counts
    if error_counts:
        terminalreporter.write_line("Counts of error types:")
        for error, count in error_counts.most_common():
            terminalreporter.write_line(f"  {count}x: {error}")
    else:
        terminalreporter.write_line("No distinct errors found to summarize.")
