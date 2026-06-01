"""Tests for the CI secret superset SSOT and its YAML renderings.

The canonical list lives in :mod:`wads.ci_secrets`. GitHub requires the
reusable workflow's ``on.workflow_call.secrets`` block to be static literal
YAML, so a *copy* of the names lives in ``.github/workflows/uv-ci.yml``. These
tests pin that copy to the Python SSOT so the two can never drift.
"""

from pathlib import Path

import pytest
import yaml

from wads.ci_secrets import (
    DEFAULT_CI_SECRETS,
    InvalidSecretName,
    is_valid_secret_name,
    normalize_secret_name,
    render_stub_secrets_passthrough,
    render_workflow_call_secrets,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
UV_CI = REPO_ROOT / ".github" / "workflows" / "uv-ci.yml"


def test_superset_is_deduped_and_nonempty():
    assert len(DEFAULT_CI_SECRETS) == len(set(DEFAULT_CI_SECRETS))
    assert "PYPI_PASSWORD" in DEFAULT_CI_SECRETS
    assert len(DEFAULT_CI_SECRETS) > 20


def test_every_superset_name_is_valid():
    for name in DEFAULT_CI_SECRETS:
        assert is_valid_secret_name(name), name


def test_normalize_secret_name():
    assert normalize_secret_name("my-api.key") == "MY_API_KEY"
    assert normalize_secret_name("  hf token ") == "HF_TOKEN"
    assert normalize_secret_name("OPENAI_API_KEY") == "OPENAI_API_KEY"


@pytest.mark.parametrize(
    "bad",
    ["sk-proj-abc/123+x=", "GITHUB_TOKEN", "", "   ", "a" * 100],
)
def test_normalize_rejects_value_like_and_reserved(bad):
    with pytest.raises(InvalidSecretName):
        normalize_secret_name(bad)


def _secrets_from_workflow(path: Path):
    """Return the declared ``on.workflow_call.secrets`` names, in file order."""
    data = yaml.safe_load(path.read_text())
    # PyYAML parses the bare key `on:` as the boolean True.
    on = data.get("on", data.get(True))
    return list(on["workflow_call"]["secrets"].keys())


def test_uv_ci_secrets_match_ssot_exactly():
    """The reusable workflow's secret superset must equal DEFAULT_CI_SECRETS.

    If this fails, you edited one side only. Regenerate the YAML block from
    wads.ci_secrets.render_workflow_call_secrets() (or update DEFAULT_CI_SECRETS).
    """
    declared = _secrets_from_workflow(UV_CI)
    assert declared == list(DEFAULT_CI_SECRETS)


def test_rendered_workflow_block_roundtrips():
    """The rendered block parses to exactly the SSOT names."""
    block = render_workflow_call_secrets(indent=6)
    fake = "on:\n  workflow_call:\n    secrets:\n" + block + "\n"
    parsed = yaml.safe_load(fake)
    on = parsed.get("on", parsed.get(True))
    assert list(on["workflow_call"]["secrets"].keys()) == list(DEFAULT_CI_SECRETS)


def test_stub_passthrough_render():
    out = render_stub_secrets_passthrough(["PYPI_PASSWORD", "NPM_TOKEN"])
    assert out == (
        "      PYPI_PASSWORD: ${{ secrets.PYPI_PASSWORD }}\n"
        "      NPM_TOKEN: ${{ secrets.NPM_TOKEN }}"
    )
