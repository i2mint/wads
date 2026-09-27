"""i2mint/wads#59: warn when CI never installs a repo's declared test extra.

``[tool.wads.ci.install].extras`` defaults to empty, so CI installs core
dependencies only. A repo that keeps test tooling in a ``dev``/``test`` extra
and never sets ``extras`` gets a job that silently lacks it (a missing
``pytest-asyncio`` even turns async tests into skips). Installing such extras
automatically would change every repo's CI at once, which is the owner's call,
so this adds the additive half: a loud ``::warning::`` in every CI log.
"""

import textwrap

import pytest

from wads.ci_config import CIConfig
from wads.scripts.read_ci_config import read_and_export_ci_config


def _config(optional_deps: dict, install: dict | None = None) -> CIConfig:
    data = {"project": {"name": "mypkg", "optional-dependencies": optional_deps}}
    if install is not None:
        data["tool"] = {"wads": {"ci": {"install": install}}}
    return CIConfig(data)


def test_a_dev_extra_with_real_tooling_is_reported_when_extras_is_unset():
    config = _config({"dev": ["pytest", "httpx>=0.27", "pytest-asyncio"]})
    assert config.uninstalled_test_extras == {"dev": ["httpx", "pytest-asyncio"]}


def test_tools_ci_provides_on_its_own_are_not_reported():
    """run-tests-uv installs pytest (+ pytest-cov); ruff comes from its action."""
    config = _config({"test": ["pytest>=7", "pytest-cov", "Ruff", "coverage[toml]"]})
    assert config.uninstalled_test_extras == {}


@pytest.mark.parametrize("install", [{"extras": ""}, {"extras": "dev"}, {"extras": []}])
def test_an_explicit_extras_setting_is_respected(install):
    """``extras = ""`` is the documented opt-out; any explicit value is a choice."""
    config = _config({"dev": ["httpx"]}, install=install)
    assert config.uninstalled_test_extras == {}


def test_only_conventional_test_extra_names_count():
    config = _config({"docs": ["sphinx"], "gpu": ["torch"], "Testing": ["hypothesis"]})
    assert config.uninstalled_test_extras == {"Testing": ["hypothesis"]}


def test_self_references_and_unparsable_entries_do_not_crash():
    config = _config({"dev": ["mypkg[test]", "not a requirement !!", "numpy"]})
    assert config.uninstalled_test_extras == {"dev": ["numpy"]}


def test_read_ci_config_prints_a_github_warning(tmp_path, monkeypatch, capsys):
    for var in ("GITHUB_OUTPUT", "GITHUB_ENV", "GITHUB_STEP_SUMMARY"):
        monkeypatch.delenv(var, raising=False)
    (tmp_path / "pyproject.toml").write_text(
        textwrap.dedent(
            """\
            [project]
            name = "mypkg"
            version = "0.1.0"

            [project.optional-dependencies]
            dev = ["pytest", "httpx"]
            """
        )
    )
    assert read_and_export_ci_config(tmp_path) == 0
    out = capsys.readouterr().out
    warning = [line for line in out.splitlines() if line.startswith("::warning")]
    assert len(warning) == 1
    assert "httpx" in warning[0] and "extras" in warning[0] and "dev" in warning[0]


def test_read_ci_config_is_quiet_when_nothing_is_missing(tmp_path, monkeypatch, capsys):
    for var in ("GITHUB_OUTPUT", "GITHUB_ENV", "GITHUB_STEP_SUMMARY"):
        monkeypatch.delenv(var, raising=False)
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "mypkg"\nversion = "0.1.0"\n'
        '[project.optional-dependencies]\ndev = ["pytest"]\n'
    )
    assert read_and_export_ci_config(tmp_path) == 0
    assert "::warning" not in capsys.readouterr().out
