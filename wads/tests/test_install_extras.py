"""Tests for CI install-extras configuration ([tool.wads.ci.install].extras).

Lets a repo declare which extras its CI should install (e.g. "create"), plumbed
through CIConfig -> read_ci_config script -> read-ci-config action -> reusable
workflow's install-deps step.
"""

import os
from pathlib import Path

import pytest

from wads.ci_config import CIConfig


def _cfg(install_block):
    return CIConfig({"tool": {"wads": {"ci": {"install": install_block}}}})


def test_install_extras_default_empty():
    assert CIConfig({}).install_extras == ""


def test_install_extras_string():
    assert _cfg({"extras": "create"}).install_extras == "create"


def test_install_extras_comma_string_normalized():
    assert _cfg({"extras": " create , test "}).install_extras == "create,test"


def test_install_extras_list():
    assert _cfg({"extras": ["create", "test"]}).install_extras == "create,test"


def test_install_extras_empty_values_dropped():
    assert _cfg({"extras": ["create", "", "  "]}).install_extras == "create"


def test_wads_own_pyproject_installs_create():
    """wads's own pyproject opts its CI into the create extra."""
    repo_root = Path(__file__).resolve().parents[2]
    cfg = CIConfig.from_file(repo_root / "pyproject.toml")
    assert cfg.install_extras == "create"


def test_read_ci_config_emits_install_extras(tmp_path, monkeypatch):
    """The read_ci_config script writes install-extras to GITHUB_OUTPUT."""
    from wads.scripts.read_ci_config import read_and_export_ci_config

    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\n\n'
        '[tool.wads.ci.install]\nextras = "create"\n'
    )
    out_file = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))
    # GITHUB_ENV is also written to; point it somewhere harmless.
    monkeypatch.setenv("GITHUB_ENV", str(tmp_path / "gh_env"))

    rc = read_and_export_ci_config(str(tmp_path))
    assert rc == 0
    output = out_file.read_text()
    assert "install-extras=create" in output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
