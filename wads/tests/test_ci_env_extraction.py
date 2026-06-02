"""Tests for lossless CI env extraction during migration (issue #45 follow-up).

`wads-migrate ci-to-stub` / `ci-to-uv` / `fleet-stub` must carry secret-backed
env vars declared only in the old workflow YAML into `[tool.wads.ci.env]`, so a
migration never silently drops secrets the tests rely on.
"""

import pytest

from wads.migration import carry_ci_env_into_pyproject, extract_ci_env_vars

INLINE_UV_CI = """\
name: Continuous Integration (uv)
on: [push, pull_request]
env:
  PROJECT_NAME: myproj
  LOG_LEVEL: DEBUG
  OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY || '' }}
  HF_TOKEN: ${{ secrets.HF_WRITE_TOKEN }}
jobs:
  validation:
    steps:
      - run: pytest
  publish:
    steps:
      - uses: i2mint/wads/actions/pypi-publish-uv@master
        with:
          pypi-token: ${{ secrets.PYPI_PASSWORD }}
      - uses: x
        env:
          KAGGLE_KEY: ${{ secrets.KAGGLE_KEY }}
"""

STUB_CI = """\
name: Continuous Integration
on: [push, pull_request]
jobs:
  ci:
    uses: i2mint/wads/.github/workflows/uv-ci.yml@master
    secrets:
      PYPI_PASSWORD: ${{ secrets.PYPI_PASSWORD }}
      OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
"""


def test_extract_from_env_blocks_only():
    got = extract_ci_env_vars(INLINE_UV_CI)
    # workflow-level + step-level env, alias resolved, literals/infra excluded
    assert got == {
        "OPENAI_API_KEY": "OPENAI_API_KEY",
        "HF_TOKEN": "HF_WRITE_TOKEN",
        "KAGGLE_KEY": "KAGGLE_KEY",
    }
    # PROJECT_NAME (literal) and PYPI_PASSWORD (infra, and in `with:` not `env:`)
    assert "PROJECT_NAME" not in got and "PYPI_PASSWORD" not in got


def test_stub_secrets_passthrough_is_ignored():
    # A reusable-workflow `secrets:` block is transport, not env usage.
    assert extract_ci_env_vars(STUB_CI) == {}


def test_extract_handles_garbage():
    assert extract_ci_env_vars(":: not yaml ::\n  - [") == {}
    assert extract_ci_env_vars("") == {}


@pytest.fixture
def pyproject(tmp_path):
    p = tmp_path / "pyproject.toml"
    p.write_text(
        '[project]\nname = "demo"\n\n'
        "[tool.wads.ci.env]\n"
        "required_envvars = []\ntest_envvars = []\nextra_envvars = []\ndefaults = {}\n"
    )
    return p


def test_carry_adds_vars_and_alias(pyproject):
    added = carry_ci_env_into_pyproject(INLINE_UV_CI, pyproject)
    assert set(added) == {"OPENAI_API_KEY", "HF_TOKEN", "KAGGLE_KEY"}
    text = pyproject.read_text()
    assert "OPENAI_API_KEY" in text and "KAGGLE_KEY" in text
    assert 'HF_TOKEN = "HF_WRITE_TOKEN"' in text  # alias recorded


def test_carry_is_idempotent(pyproject):
    carry_ci_env_into_pyproject(INLINE_UV_CI, pyproject)
    again = carry_ci_env_into_pyproject(INLINE_UV_CI, pyproject)
    assert again == []  # nothing new to add the second time


def test_carry_noop_when_nothing_to_carry(pyproject):
    assert carry_ci_env_into_pyproject(STUB_CI, pyproject) == []
