"""Tests for the ``wads-secrets`` CLI helpers (file edits, no network)."""

import pytest

from wads.migration import migrate_ci_to_stub
from wads.secrets_cli import (
    add,
    add_env_var_to_pyproject,
    add_secret_to_stub,
    list_,
    stub_transport_mode,
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


def _make_repo(tmp_path, stub_text):
    (tmp_path / "pyproject.toml").write_text(PYPROJECT)
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "ci.yml").write_text(stub_text)
    return tmp_path


@pytest.fixture
def repo(tmp_path):
    """A repo with the default (JSON-transport) stub."""
    return _make_repo(tmp_path, migrate_ci_to_stub())


@pytest.fixture
def named_repo(tmp_path):
    """A repo with a legacy named-transport stub."""
    return _make_repo(tmp_path, migrate_ci_to_stub(transport="named"))


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


def test_json_stub_needs_no_transport_edit(repo):
    """The default stub transports everything; add_secret_to_stub is a no-op."""
    ci = repo / ".github" / "workflows" / "ci.yml"
    assert stub_transport_mode(ci) == "json"
    before = ci.read_text()
    changed, reason = add_secret_to_stub(ci, "OPENAI_API_KEY")
    assert not changed and "JSON transport" in reason
    assert ci.read_text() == before  # untouched


def test_add_secret_to_stub_inserts_once(named_repo):
    ci = named_repo / ".github" / "workflows" / "ci.yml"
    assert stub_transport_mode(ci) == "named"
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


def test_add_does_not_short_circuit_when_already_declared(named_repo):
    """Regression: a var already in pyproject must still get the ci.yml transport.

    Previously ``add`` returned early on an existing declaration, skipping both
    the transport edit and the GitHub secret set — so a half-configured secret
    (declared but not passed in ci.yml) could never be completed by re-running.
    (Named-transport stub: the JSON stub has no per-secret transport at all.)
    """
    pp = named_repo / "pyproject.toml"
    ci = named_repo / ".github" / "workflows" / "ci.yml"
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


def test_add_is_idempotent_when_fully_configured(named_repo):
    """Running ``add`` twice is a clean no-op (exit 0, single transport line)."""
    pp = named_repo / "pyproject.toml"
    ci = named_repo / ".github" / "workflows" / "ci.yml"
    common = dict(kind="test", github=False, pyproject=str(pp), ci_file=str(ci))
    assert add("OPENAI_API_KEY", **common) == 0
    assert add("OPENAI_API_KEY", **common) == 0
    assert ci.read_text().count("secrets.OPENAI_API_KEY") == 1


def test_add_on_json_stub_declares_without_stub_edit(repo, capsys):
    """On a JSON-transport stub, `add` edits pyproject only — and any secret
    name is fine (no superset warning, even for out-of-superset names)."""
    pp = repo / "pyproject.toml"
    ci = repo / ".github" / "workflows" / "ci.yml"
    before = ci.read_text()
    rc = add(
        "COSMO_TEST_LEVEL",  # not in the legacy superset
        kind="extra",
        github=False,
        pyproject=str(pp),
        ci_file=str(ci),
    )
    assert rc == 0
    assert ci.read_text() == before
    out = capsys.readouterr().out
    assert "COSMO_TEST_LEVEL" in pp.read_text()
    assert "superset" not in out  # no scary warning on the JSON transport


def test_add_on_named_stub_refuses_outside_superset_edit(named_repo, capsys):
    """Issue #63: a named-transport stub passing an out-of-superset secret
    cannot start — `add` must REFUSE the stub edit, not create the broken
    state and then warn about it."""
    pp = named_repo / "pyproject.toml"
    ci = named_repo / ".github" / "workflows" / "ci.yml"
    before = ci.read_text()
    rc = add(
        "COSMO_TEST_LEVEL",
        kind="extra",
        github=False,
        pyproject=str(pp),
        ci_file=str(ci),
    )
    assert rc == 0
    assert ci.read_text() == before  # the breaking edit must NOT happen
    assert "COSMO_TEST_LEVEL" in pp.read_text()  # declaration still recorded
    out = capsys.readouterr().out
    assert "superset" in out and "FAIL TO START" in out and "NOT edited" in out
    assert "--variable" in out  # points at the non-sensitive-value remedy


def test_add_variable_on_inline_workflow_warns(tmp_path, capsys):
    """--variable on an inline workflow must warn: inline env blocks read
    secrets only, so a repo variable would silently never arrive."""
    tmp = _make_repo(tmp_path, "name: CI\non: [push]\njobs: {}\n")
    rc = add(
        "COSMO_TEST_LEVEL",
        kind="extra",
        github=False,
        variable=True,
        pyproject=str(tmp / "pyproject.toml"),
        ci_file=str(tmp / ".github" / "workflows" / "ci.yml"),
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "inline workflow" in out and "defaults" in out


def test_add_variable_skips_transport_and_superset(repo, capsys):
    """--variable: pyproject declaration only; repo vars need no transport."""
    pp = repo / "pyproject.toml"
    ci = repo / ".github" / "workflows" / "ci.yml"
    before = ci.read_text()
    rc = add(
        "COSMO_TEST_LEVEL",
        kind="extra",
        github=False,
        variable=True,
        pyproject=str(pp),
        ci_file=str(ci),
    )
    assert rc == 0
    assert ci.read_text() == before
    assert "COSMO_TEST_LEVEL" in pp.read_text()
    out = capsys.readouterr().out
    assert "vars context" in out


def test_json_stub_pinned_to_old_tag_warns(capsys):
    """Reviewer finding F2: a JSON stub pinned to a pre-JSON tag cannot start;
    migrate_ci_to_stub must warn on any non-master pin with json transport."""
    stub = migrate_ci_to_stub(pin="@0.2.14")
    assert "uv-ci.yml@0.2.14" in stub
    err = capsys.readouterr().err
    assert "CANNOT START" in err and "--transport named" in err
    # named transport with a pin is fine — no warning
    migrate_ci_to_stub(pin="@0.2.14", transport="named")
    assert "CANNOT START" not in capsys.readouterr().err


def test_named_stub_warns_outside_superset_names(tmp_path, capsys):
    """Named-mode generation warns per out-of-superset name (issue #63)."""
    (tmp_path / "pyproject.toml").write_text(
        PYPROJECT.replace("extra_envvars = []", 'extra_envvars = ["COSMO_TEST_LEVEL"]')
    )
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    ci = wf / "ci.yml"
    ci.write_text("name: x\n")
    stub = migrate_ci_to_stub(str(ci), transport="named")
    err = capsys.readouterr().err
    assert "COSMO_TEST_LEVEL" in err and "startup_failure" in err
    assert "COSMO_TEST_LEVEL: ${{ secrets.COSMO_TEST_LEVEL }}" in stub


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


def test_short_secret_value_warns_mask_hazard(monkeypatch, capsys):
    """Issue #61 suggested fix (2): a short secret value is a log-mask
    hazard — warn and point at --variable, but still set the value (it's a
    warning, not a refusal)."""
    import wads.secrets_cli as m

    monkeypatch.setattr(m, "_gh_available", lambda: True)
    set_calls = []
    monkeypatch.setattr(
        m,
        "set_github_secret",
        lambda *a, **k: set_calls.append((a, k)) or True,
    )

    m._maybe_set_github_value(
        "org/demo", "COSMO_TEST_LEVEL", "COSMO_TEST_LEVEL", "3", "ci.yml"
    )
    out = capsys.readouterr().out
    assert "mask" in out and "--variable" in out
    assert len(set_calls) == 1

    # A value of typical credential length does not warn
    m._maybe_set_github_value(
        "org/demo", "API_KEY", "API_KEY", "sk-0123456789abcdef", "ci.yml"
    )
    assert "mask" not in capsys.readouterr().out

    # Repository variables are never masked, so no warning there
    m._maybe_set_github_value(
        "org/demo",
        "COSMO_TEST_LEVEL",
        "COSMO_TEST_LEVEL",
        "3",
        "ci.yml",
        variable=True,
    )
    assert "mask" not in capsys.readouterr().out
