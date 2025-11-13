"""Tests for migration module."""

import os
import tempfile
from pathlib import Path

import pytest

from wads.migration import (
    migrate_setuptools_to_hatching,
    migrate_github_ci_old_to_new,
    MigrationError,
    _normalize_setup_cfg_input,
    _parse_list_field,
)


# Sample setup.cfg content for testing
SAMPLE_SETUP_CFG = """
[metadata]
name = testproject
version = 0.1.0
url = https://github.com/test/testproject
description = A test project
license = MIT
keywords =
    testing
    migration
author = Test Author
author_email = test@example.com

[options]
packages = find:
include_package_data = True
zip_safe = False
install_requires =
    requests
    click>=7.0

[options.extras_require]
dev =
    pytest
    black

[options.entry_points]
console_scripts =
    testcli = testproject.cli:main
"""


def test_normalize_setup_cfg_dict():
    """Test normalizing dict input."""
    cfg_dict = {"metadata": {"name": "test"}}
    result = _normalize_setup_cfg_input(cfg_dict)
    assert result == cfg_dict


def test_normalize_setup_cfg_string():
    """Test normalizing string content input."""
    result = _normalize_setup_cfg_input(SAMPLE_SETUP_CFG)
    assert "metadata" in result
    assert result["metadata"]["name"] == "testproject"


def test_parse_list_field_multiline():
    """Test parsing multi-line list fields."""
    field = "\n    testing\n    migration\n"
    result = _parse_list_field(field)
    assert result == ["testing", "migration"]


def test_parse_list_field_comma_separated():
    """Test parsing comma-separated list fields."""
    field = "testing, migration, tools"
    result = _parse_list_field(field)
    assert result == ["testing", "migration", "tools"]


def test_parse_list_field_empty():
    """Test parsing empty field."""
    assert _parse_list_field("") == []
    assert _parse_list_field(None) == []


def test_migrate_setuptools_basic():
    """Test basic migration from setup.cfg to pyproject.toml."""
    result = migrate_setuptools_to_hatching(SAMPLE_SETUP_CFG)

    # Check it's valid TOML-ish output
    assert 'name = "testproject"' in result
    assert 'version = "0.1.0"' in result
    assert 'description = "A test project"' in result
    # Keywords should be present (format may vary)
    assert '"testing"' in result
    assert '"migration"' in result


def test_migrate_setuptools_with_defaults():
    """Test migration with defaults for missing fields."""
    minimal_cfg = """
[metadata]
name = minimal
version = 1.0.0
"""

    defaults = {
        "description": "A minimal project",
        "url": "https://example.com",
        "license": "MIT",
    }

    result = migrate_setuptools_to_hatching(minimal_cfg, defaults=defaults)
    assert 'name = "minimal"' in result
    assert "A minimal project" in result


def test_migrate_setuptools_missing_required_fields():
    """Test that missing required fields raise MigrationError."""
    minimal_cfg = """
[metadata]
name = minimal
"""

    with pytest.raises(MigrationError) as exc_info:
        migrate_setuptools_to_hatching(minimal_cfg)

    assert "Missing required fields" in str(exc_info.value)
    assert "version" in str(exc_info.value)


def test_migrate_setuptools_from_file():
    """Test migration from actual file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".cfg", delete=False) as f:
        f.write(SAMPLE_SETUP_CFG)
        temp_path = f.name

    try:
        result = migrate_setuptools_to_hatching(temp_path)
        assert 'name = "testproject"' in result
    finally:
        os.unlink(temp_path)


def test_migrate_setuptools_dependencies():
    """Test that dependencies are properly migrated."""
    result = migrate_setuptools_to_hatching(SAMPLE_SETUP_CFG)

    # Check dependencies section (format may vary)
    assert "dependencies" in result
    assert '"requests"' in result or "requests" in result
    assert "click" in result


def test_migrate_ci_missing_project_name():
    """Test CI migration raises error when project name is missing."""
    old_ci = """
name: Old CI
env:
  PROJECT_NAME: #PROJECT_NAME#
"""

    with pytest.raises(MigrationError) as exc_info:
        migrate_github_ci_old_to_new(old_ci)

    assert "PROJECT_NAME" in str(exc_info.value)


def test_migrate_ci_with_defaults():
    """Test CI migration with defaults."""
    old_ci = """
name: Old CI
env:
  PROJECT_NAME: #PROJECT_NAME#
"""

    result = migrate_github_ci_old_to_new(
        old_ci, defaults={"project_name": "myproject"}
    )

    assert "PROJECT_NAME: myproject" in result


def test_migrate_ci_extracts_project_name():
    """Test CI migration extracts existing project name."""
    old_ci = """
name: Old CI
env:
  PROJECT_NAME: existing_project
"""

    result = migrate_github_ci_old_to_new(old_ci)
    assert "PROJECT_NAME: existing_project" in result


def test_custom_rules():
    """Test using custom transformation rules."""
    custom_rules = {
        "project.name": lambda cfg: cfg.get("metadata", {}).get("name", "").upper(),
        "project.version": lambda cfg: cfg.get("metadata", {}).get("version"),
        "project.description": lambda cfg: "Custom description",
        "project.url": lambda cfg: "https://custom.url",
        "project.license": lambda cfg: "MIT",
    }

    cfg_dict = {
        "metadata": {
            "name": "test",
            "version": "1.0.0",
        }
    }

    result = migrate_setuptools_to_hatching(cfg_dict, rules=custom_rules)
    assert 'name = "TEST"' in result
    assert "Custom description" in result
