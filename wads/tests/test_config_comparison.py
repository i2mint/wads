"""
Tests for config_comparison module.
"""

import pytest
from pathlib import Path
import tempfile
import os


def test_nested_get():
    """Test nested dictionary getter."""
    from wads.config_comparison import _nested_get

    d = {'a': {'b': {'c': 1}}, 'd': 2}

    assert _nested_get(d, 'a.b.c') == 1
    assert _nested_get(d, 'd') == 2
    assert _nested_get(d, 'a.b') == {'c': 1}
    assert _nested_get(d, 'x.y.z', 'default') == 'default'


def test_flatten_dict():
    """Test dictionary flattening."""
    from wads.config_comparison import _flatten_dict

    d = {'a': {'b': 1, 'c': 2}, 'd': 3}
    flat = _flatten_dict(d)

    assert flat == {'a.b': 1, 'a.c': 2, 'd': 3}


def test_find_missing_sections():
    """Test detection of missing sections."""
    from wads.config_comparison import _find_missing_sections

    template = {
        'project': {'name': '', 'version': ''},
        'tool': {'ruff': {'line-length': 88}},
    }

    actual = {
        'project': {'name': 'test', 'version': '1.0'},
    }

    ignore_keys = {'project.name', 'project.version'}
    missing = _find_missing_sections(actual, template, ignore_keys)

    assert 'tool.ruff.line-length' in missing


def test_compare_pyproject_toml_with_temp_files():
    """Test pyproject.toml comparison with temporary files."""
    from wads.config_comparison import compare_pyproject_toml
    from wads import pyproject_toml_tpl_path

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a minimal pyproject.toml
        test_pyproject = Path(tmpdir) / 'pyproject.toml'
        test_pyproject.write_text(
            """
[build-system]
requires = ["setuptools"]
build-backend = "setuptools.build_meta"

[project]
name = "testproject"
version = "0.1.0"
description = "Test"
"""
        )

        result = compare_pyproject_toml(test_pyproject)

        assert 'missing_sections' in result
        assert 'recommendations' in result
        assert isinstance(result.get('needs_attention'), bool)


def test_compare_setup_cfg():
    """Test setup.cfg analysis."""
    from wads.config_comparison import compare_setup_cfg

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a setup.cfg
        setup_cfg = Path(tmpdir) / 'setup.cfg'
        setup_cfg.write_text(
            """
[metadata]
name = testproject
version = 0.1.0

[options]
packages = find:
"""
        )

        result = compare_setup_cfg(setup_cfg)

        assert result['exists'] == True
        assert result['should_migrate'] == True
        assert 'recommendations' in result
        assert len(result['sections']) > 0


def test_summarize_config_status():
    """Test overall config status summary."""
    from wads.config_comparison import summarize_config_status

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a minimal project structure
        pyproject = Path(tmpdir) / 'pyproject.toml'
        pyproject.write_text(
            """
[project]
name = "test"
version = "0.1.0"
"""
        )

        setup_cfg = Path(tmpdir) / 'setup.cfg'
        setup_cfg.write_text(
            """
[metadata]
name = test
"""
        )

        result = summarize_config_status(tmpdir, check_ci=False)

        assert result['has_pyproject'] == True
        assert result['has_setup_cfg'] == True
        assert isinstance(result['needs_attention'], list)

        # Should flag setup.cfg as needing attention
        assert 'setup.cfg' in result['needs_attention']


def test_compare_pyproject_missing_file():
    """Test comparison when file doesn't exist."""
    from wads.config_comparison import compare_pyproject_toml

    result = compare_pyproject_toml('/nonexistent/pyproject.toml')

    # When file doesn't exist, read_pyproject_toml returns empty dict
    # So comparison just shows everything as missing
    assert 'missing_sections' in result
    assert 'needs_attention' in result


def test_compare_setup_cfg_missing():
    """Test setup.cfg comparison when file missing."""
    from wads.config_comparison import compare_setup_cfg

    result = compare_setup_cfg('/nonexistent/setup.cfg')

    assert result['exists'] == False
    assert result['should_migrate'] == False


def test_manifest_in_parsing():
    """Test MANIFEST.in parsing."""
    from wads.migration import analyze_manifest_in

    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = Path(tmpdir) / 'MANIFEST.in'

        # Create a sample MANIFEST.in
        manifest_content = """
# Include data files
include README.md
include LICENSE
recursive-include mypackage/data *.json
graft docs
prune tests
global-exclude *.pyc
"""
        manifest_path.write_text(manifest_content)

        result = analyze_manifest_in(manifest_path)

        assert result['exists'] == True
        assert result['needs_migration'] == True
        assert len(result['directives']) > 0
        assert len(result['recommendations']) > 0
        assert result['hatchling_config'] is not None

        # Check that hatchling config is generated
        assert '[tool.hatch.build.targets.wheel]' in result['hatchling_config']


def test_manifest_in_nonexistent():
    """Test MANIFEST.in analysis when file doesn't exist."""
    from wads.migration import analyze_manifest_in

    result = analyze_manifest_in('/nonexistent/MANIFEST.in')

    assert result['exists'] == False
    assert result['needs_migration'] == False
    assert result['hatchling_config'] is None


def test_compare_manifest_in():
    """Test MANIFEST.in comparison function."""
    from wads.config_comparison import compare_manifest_in

    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = Path(tmpdir) / 'MANIFEST.in'
        manifest_path.write_text('include README.md\n')

        result = compare_manifest_in(manifest_path)

        assert result['exists'] == True
        assert result['needs_migration'] == True
        assert result['needs_attention'] == True


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
