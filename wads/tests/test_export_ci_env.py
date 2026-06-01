"""Tests for the run-time env-export logic (``wads.scripts.export_ci_env``)."""

from wads.scripts.export_ci_env import _gh_env_assignment, export_ci_env


def test_exports_only_configured_and_set():
    assignments, exported, missing_req, missing_test = export_ci_env(
        required=["OPENAI_API_KEY"],
        test=["TAVILY_API_KEY"],
        extra=["UNSET_THING"],
        defaults={"LOG_LEVEL": "DEBUG"},
        secrets={"OPENAI_API_KEY": "sk-x", "TAVILY_API_KEY": "", "OTHER": "y"},
        warn=lambda m: None,
    )
    assert exported == ["LOG_LEVEL", "OPENAI_API_KEY"]
    assert "OTHER" not in exported  # passed but not declared -> not exported
    assert missing_req == []
    assert missing_test == ["TAVILY_API_KEY"]
    assert "LOG_LEVEL=DEBUG" in assignments
    assert "OPENAI_API_KEY=sk-x" in assignments


def test_required_missing_is_reported():
    _, _, missing_req, _ = export_ci_env(required=["PYPI_PASSWORD"], secrets={})
    assert missing_req == [("PYPI_PASSWORD", "PYPI_PASSWORD")]


def test_alias_resolution():
    assignments, exported, _, _ = export_ci_env(
        test=["HF_TOKEN"],
        aliases={"HF_TOKEN": "HF_WRITE_TOKEN"},
        secrets={"HF_WRITE_TOKEN": "hf_x"},
        warn=lambda m: None,
    )
    assert exported == ["HF_TOKEN"]
    assert assignments == ["HF_TOKEN=hf_x"]


def test_secret_overrides_default_of_same_name():
    assignments, exported, _, _ = export_ci_env(
        extra=["TOKEN"],
        defaults={"TOKEN": "literal"},
        secrets={"TOKEN": "from-secret"},
        warn=lambda m: None,
    )
    # default written first, secret-backed var of same name skipped (already seen),
    # so the literal default stands — defaults are authoritative when both exist.
    assert exported == ["TOKEN"]
    assert assignments == ["TOKEN=literal"]


def test_multiline_value_uses_heredoc():
    out = _gh_env_assignment("SSH_PRIVATE_KEY", "-----BEGIN-----\nabc\n-----END-----")
    assert out.startswith("SSH_PRIVATE_KEY<<")
    delim = out.splitlines()[0].split("<<", 1)[1]
    assert out.rstrip().endswith(delim)
    assert delim not in "-----BEGIN-----\nabc\n-----END-----"


def test_single_line_value_plain():
    assert _gh_env_assignment("A", "b") == "A=b"
