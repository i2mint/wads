"""Tests for the ``wads-secrets`` CLI helpers (file edits, no network)."""

import pytest

from wads.migration import migrate_ci_to_stub
from wads.secrets_cli import (
    add,
    add_env_var_to_pyproject,
    add_secret_to_stub,
    list_,
    _repo_from_git,
)

PYPROJECT = """\
[project]
name = "demo"

[tool.wads.ci.env]
required_envvars = []
test_envvars = []
extra_envvars = []
defaults = {}
"""


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "pyproject.toml").write_text(PYPROJECT)
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "ci.yml").write_text(migrate_ci_to_stub())
    return tmp_path


def test_add_env_var_and_alias(repo):
    pp = repo / "pyproject.toml"
    changed, existing = add_env_var_to_pyproject(
        pp, "HF_TOKEN", "HF_WRITE_TOKEN", kind="required"
    )
    assert changed and existing is None
    text = pp.read_text()
    assert 'required_envvars = ["HF_TOKEN"]' in text
    assert "[tool.wads.ci.env.secret_aliases]" in text
    assert 'HF_TOKEN = "HF_WRITE_TOKEN"' in text


def test_add_env_var_idempotent(repo):
    pp = repo / "pyproject.toml"
    add_env_var_to_pyproject(pp, "OPENAI_API_KEY", "OPENAI_API_KEY", kind="extra")
    changed, existing = add_env_var_to_pyproject(
        pp, "OPENAI_API_KEY", "OPENAI_API_KEY", kind="test"
    )
    assert not changed
    assert existing == "extra_envvars"


def test_add_secret_to_stub_inserts_once(repo):
    ci = repo / ".github" / "workflows" / "ci.yml"
    changed, _ = add_secret_to_stub(ci, "OPENAI_API_KEY")
    assert changed
    assert "OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}" in ci.read_text()
    # second time is a no-op
    changed2, reason = add_secret_to_stub(ci, "OPENAI_API_KEY")
    assert not changed2 and "already" in reason
    assert ci.read_text().count("secrets.OPENAI_API_KEY") == 1


def test_add_secret_to_stub_detects_non_stub(tmp_path):
    inline = tmp_path / "ci.yml"
    inline.write_text("name: CI\non: [push]\njobs: {}\n")
    changed, reason = add_secret_to_stub(inline, "FOO")
    assert not changed
    assert "not the wads reusable-workflow stub" in reason


def test_list_reports_configured(repo, capsys):
    pp = repo / "pyproject.toml"
    add_env_var_to_pyproject(pp, "HF_TOKEN", "HF_WRITE_TOKEN", kind="required")
    list_(pyproject=str(pp))
    out = capsys.readouterr().out
    assert "HF_TOKEN" in out and "HF_WRITE_TOKEN" in out


def test_add_does_not_short_circuit_when_already_declared(repo):
    """Regression: a var already in pyproject must still get the ci.yml transport.

    Previously ``add`` returned early on an existing declaration, skipping both
    the transport edit and the GitHub secret set — so a half-configured secret
    (declared but not passed in ci.yml) could never be completed by re-running.
    """
    pp = repo / "pyproject.toml"
    ci = repo / ".github" / "workflows" / "ci.yml"
    # Pre-declare in pyproject only; ci.yml does NOT yet pass it.
    add_env_var_to_pyproject(pp, "OPENAI_API_KEY", "OPENAI_API_KEY", kind="test")
    assert "secrets.OPENAI_API_KEY" not in ci.read_text()

    rc = add(
        "OPENAI_API_KEY",
        kind="test",
        github=False,
        pyproject=str(pp),
        ci_file=str(ci),
    )
    assert rc == 0
    # The transport must now be present despite the pre-existing declaration.
    assert "OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}" in ci.read_text()


def test_add_is_idempotent_when_fully_configured(repo):
    """Running ``add`` twice is a clean no-op (exit 0, single transport line)."""
    pp = repo / "pyproject.toml"
    ci = repo / ".github" / "workflows" / "ci.yml"
    common = dict(kind="test", github=False, pyproject=str(pp), ci_file=str(ci))
    assert add("OPENAI_API_KEY", **common) == 0
    assert add("OPENAI_API_KEY", **common) == 0
    assert ci.read_text().count("secrets.OPENAI_API_KEY") == 1


def test_repo_from_git_parses_urls(tmp_path, monkeypatch):
    import wads.secrets_cli as m

    monkeypatch.setattr(
        m.subprocess,
        "check_output",
        lambda *a, **k: "git@github.com:org/repo.git\n",
    )
    assert m._repo_from_git(".") == "org/repo"
    monkeypatch.setattr(
        m.subprocess,
        "check_output",
        lambda *a, **k: "https://github.com/org/repo\n",
    )
    assert m._repo_from_git(".") == "org/repo"
