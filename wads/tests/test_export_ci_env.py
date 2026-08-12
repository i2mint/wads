"""Tests for the run-time env-export logic (``wads.scripts.export_ci_env``)."""

import json

from wads.scripts.export_ci_env import (
    _gh_env_assignment,
    export_ci_env,
    merge_transported_secrets,
)


def test_exports_only_configured_and_set():
    plan = export_ci_env(
        required=["OPENAI_API_KEY"],
        test=["TAVILY_API_KEY"],
        extra=["UNSET_THING"],
        defaults={"LOG_LEVEL": "DEBUG"},
        secrets={"OPENAI_API_KEY": "sk-x", "TAVILY_API_KEY": "", "OTHER": "y"},
        warn=lambda m: None,
    )
    assert plan.exported == ["LOG_LEVEL", "OPENAI_API_KEY"]
    assert "OTHER" not in plan.exported  # passed but not declared -> not exported
    assert plan.missing_required == []
    assert plan.missing_test == ["TAVILY_API_KEY"]
    assert "LOG_LEVEL=DEBUG" in plan.assignments
    assert "OPENAI_API_KEY=sk-x" in plan.assignments


def test_required_missing_is_reported():
    plan = export_ci_env(required=["PYPI_PASSWORD"], secrets={})
    assert plan.missing_required == [("PYPI_PASSWORD", "PYPI_PASSWORD")]


def test_alias_resolution():
    plan = export_ci_env(
        test=["HF_TOKEN"],
        aliases={"HF_TOKEN": "HF_WRITE_TOKEN"},
        secrets={"HF_WRITE_TOKEN": "hf_x"},
        warn=lambda m: None,
    )
    assert plan.exported == ["HF_TOKEN"]
    assert plan.assignments == ["HF_TOKEN=hf_x"]


def test_secret_overrides_default_of_same_name():
    plan = export_ci_env(
        extra=["TOKEN"],
        defaults={"TOKEN": "literal"},
        secrets={"TOKEN": "from-secret"},
        warn=lambda m: None,
    )
    # default written first, secret-backed var of same name skipped (already seen),
    # so the literal default stands — defaults are authoritative when both exist.
    assert plan.exported == ["TOKEN"]
    assert plan.assignments == ["TOKEN=literal"]


def test_multiline_value_uses_heredoc():
    out = _gh_env_assignment("SSH_PRIVATE_KEY", "-----BEGIN-----\nabc\n-----END-----")
    assert out.startswith("SSH_PRIVATE_KEY<<")
    delim = out.splitlines()[0].split("<<", 1)[1]
    assert out.rstrip().endswith(delim)
    assert delim not in "-----BEGIN-----\nabc\n-----END-----"


def test_single_line_value_plain():
    assert _gh_env_assignment("A", "b") == "A=b"


# ---------------------------------------------------------------------------
# JSON transport blob (WADS_CI_SECRETS_JSON) — issue #63
# ---------------------------------------------------------------------------

CALLER_SECRETS = {
    "OPENAI_API_KEY": "sk-blob",
    "COSMO_TEST_LEVEL": "3",  # deliberately outside the legacy superset
    "github_token": "ghs_x",
}


def _blob(double_encoded=True):
    """The transported value as GitHub produces it from toJSON (2-space indent)."""
    once = json.dumps(CALLER_SECRETS, indent=2)
    return json.dumps(once) if double_encoded else once


def test_merge_expands_double_encoded_blob():
    merged = merge_transported_secrets({"WADS_CI_SECRETS_JSON": _blob()})
    assert merged == {"OPENAI_API_KEY": "sk-blob", "COSMO_TEST_LEVEL": "3"}


def test_merge_expands_single_encoded_blob():
    merged = merge_transported_secrets(
        {"WADS_CI_SECRETS_JSON": _blob(double_encoded=False)}
    )
    assert merged["COSMO_TEST_LEVEL"] == "3"


def test_merge_named_secret_wins_and_infra_keys_dropped():
    merged = merge_transported_secrets(
        {"WADS_CI_SECRETS_JSON": _blob(), "OPENAI_API_KEY": "sk-named"}
    )
    assert merged["OPENAI_API_KEY"] == "sk-named"
    assert "github_token" not in merged
    assert "WADS_CI_SECRETS_JSON" not in merged


def test_merge_tolerates_malformed_blob():
    merged = merge_transported_secrets(
        {"WADS_CI_SECRETS_JSON": "not json", "A": "x"}
    )
    assert merged == {"A": "x"}


def test_blob_sourced_values_are_export_equivalent_to_named():
    """An out-of-superset name transported via the blob exports normally."""
    plan = export_ci_env(
        extra=["COSMO_TEST_LEVEL"],
        secrets={"WADS_CI_SECRETS_JSON": _blob()},
        warn=lambda m: None,
    )
    assert plan.exported == ["COSMO_TEST_LEVEL"]
    assert plan.assignments == ["COSMO_TEST_LEVEL=3"]


def test_blob_sourced_values_are_masked():
    plan = export_ci_env(
        extra=["OPENAI_API_KEY"],
        defaults={"LOG_LEVEL": "DEBUG"},
        secrets={"WADS_CI_SECRETS_JSON": _blob()},
        warn=lambda m: None,
    )
    # secret-sourced values are re-masked; literal defaults are not.
    assert plan.mask_values == ["sk-blob"]


# ---------------------------------------------------------------------------
# Repo-variable fallback (vars context)
# ---------------------------------------------------------------------------


def test_vars_fallback_for_non_secret_values():
    plan = export_ci_env(
        extra=["COSMO_TEST_LEVEL"],
        secrets={},
        vars_={"COSMO_TEST_LEVEL": "3"},
        warn=lambda m: None,
    )
    assert plan.assignments == ["COSMO_TEST_LEVEL=3"]
    assert plan.mask_values == []  # variables are not sensitive -> no mask


def test_secret_beats_variable_of_same_name():
    plan = export_ci_env(
        extra=["X"],
        secrets={"X": "from-secret"},
        vars_={"X": "from-var"},
        warn=lambda m: None,
    )
    assert plan.assignments == ["X=from-secret"]
    assert plan.mask_values == ["from-secret"]


def test_required_satisfied_by_variable():
    plan = export_ci_env(
        required=["COSMO_TEST_LEVEL"],
        vars_={"COSMO_TEST_LEVEL": "3"},
        warn=lambda m: None,
    )
    assert plan.missing_required == []
    assert plan.exported == ["COSMO_TEST_LEVEL"]


def test_alias_applies_to_variable_lookup():
    plan = export_ci_env(
        extra=["VERBOSITY"],
        aliases={"VERBOSITY": "COSMO_TEST_LEVEL"},
        vars_={"COSMO_TEST_LEVEL": "3"},
        warn=lambda m: None,
    )
    assert plan.assignments == ["VERBOSITY=3"]


# ---------------------------------------------------------------------------
# main(): always-required merge + mask emission + GITHUB_ENV writing
# ---------------------------------------------------------------------------


def test_main_always_required_and_masks(tmp_path, monkeypatch, capsys):
    from wads.scripts import export_ci_env as mod

    gh_env = tmp_path / "github_env"
    monkeypatch.setenv("GITHUB_ENV", str(gh_env))
    monkeypatch.setenv("WADS_ENV_ALWAYS_REQUIRED", '["PYPI_PASSWORD"]')
    monkeypatch.setenv(
        "WADS_SECRETS_JSON",
        json.dumps({"WADS_CI_SECRETS_JSON": json.dumps(json.dumps(
            {"PYPI_PASSWORD": "pypi-tok", "github_token": "t"}, indent=2))}),
    )
    for unset in ("WADS_ENV_REQUIRED", "WADS_ENV_TEST", "WADS_ENV_EXTRA",
                  "WADS_ENV_DEFAULTS", "WADS_ENV_ALIASES", "WADS_VARS_JSON"):
        monkeypatch.delenv(unset, raising=False)

    assert mod.main() == 0
    out = capsys.readouterr().out
    assert "::add-mask::pypi-tok" in out
    assert "PYPI_PASSWORD=pypi-tok" in gh_env.read_text()


def test_masks_percent_escape(tmp_path, monkeypatch, capsys):
    """A value containing literal %25/%0A must register the percent-ESCAPED
    mask, or the runner's percent-decoding registers the wrong string and the
    real value stays unmasked (reviewer finding F3)."""
    from wads.scripts import export_ci_env as mod

    monkeypatch.setenv("GITHUB_ENV", str(tmp_path / "github_env"))
    monkeypatch.setenv("WADS_ENV_EXTRA", '["DATABASE_URL"]')
    monkeypatch.setenv(
        "WADS_SECRETS_JSON",
        json.dumps({"DATABASE_URL": "postgres://u:p%25w@host/db"}),
    )
    for unset in ("WADS_ENV_REQUIRED", "WADS_ENV_ALWAYS_REQUIRED", "WADS_ENV_TEST",
                  "WADS_ENV_DEFAULTS", "WADS_ENV_ALIASES", "WADS_VARS_JSON"):
        monkeypatch.delenv(unset, raising=False)

    assert mod.main() == 0
    out = capsys.readouterr().out
    assert "::add-mask::postgres://u:p%2525w@host/db" in out


def test_malformed_secrets_json_is_redacted(tmp_path, monkeypatch, capsys):
    """A parse failure of the secrets context must never echo the raw value."""
    import pytest

    from wads.scripts import export_ci_env as mod

    monkeypatch.setenv("GITHUB_ENV", str(tmp_path / "github_env"))
    monkeypatch.setenv("WADS_SECRETS_JSON", '{"SECRET_VALUE": "sk-leakme"')  # truncated
    with pytest.raises(SystemExit):
        mod.main()
    err = capsys.readouterr().err
    assert "sk-leakme" not in err
    assert "withheld" in err


def test_main_fails_on_missing_always_required(tmp_path, monkeypatch, capsys):
    from wads.scripts import export_ci_env as mod

    monkeypatch.setenv("GITHUB_ENV", str(tmp_path / "github_env"))
    monkeypatch.setenv("WADS_ENV_ALWAYS_REQUIRED", '["PYPI_PASSWORD"]')
    monkeypatch.setenv("WADS_SECRETS_JSON", "{}")
    for unset in ("WADS_ENV_REQUIRED", "WADS_ENV_TEST", "WADS_ENV_EXTRA",
                  "WADS_ENV_DEFAULTS", "WADS_ENV_ALIASES", "WADS_VARS_JSON"):
        monkeypatch.delenv(unset, raising=False)

    assert mod.main() == 1
    assert "PYPI_PASSWORD" in capsys.readouterr().err
