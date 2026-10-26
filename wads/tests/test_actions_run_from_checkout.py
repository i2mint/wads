"""Actions run their scripts from their own checkout, never from a PyPI wheel (#156)."""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ACTIONS = ("read-ci-config", "set-env-vars", "build-dist")
# The actions pin Python 3.11 (tomllib); on older interpreters tomli lives in site-packages.
_NO_SITE = ["-S"] if sys.version_info >= (3, 11) else []
PYPROJECT = '[project]\nname = "demo"\nversion = "0.0.1"\n'


@pytest.mark.parametrize("action", ACTIONS)
def test_action_does_not_use_installed_wads(action):
    text = (ROOT / "actions" / action / "action.yml").read_text()
    assert "pip install" not in text
    assert "python3 -m wads" not in text
    assert "GITHUB_ACTION_PATH/../../wads/scripts/" in text


@pytest.mark.parametrize(
    "script, env",
    [
        ("read_ci_config.py", {"GITHUB_OUTPUT": "out.txt"}),
        ("set_env_vars.py", {"SECRETS_CONTEXT": "{}"}),
    ],
)
def test_script_runs_isolated_without_wads_package(script, env, tmp_path):
    """`-I [-S]`: no site-packages, no PYTHONPATH, no cwd -> only the checkout is usable."""
    (tmp_path / "pyproject.toml").write_text(PYPROJECT)
    result = subprocess.run(
        [sys.executable, "-I", *_NO_SITE, str(ROOT / "wads" / "scripts" / script), "."],
        cwd=tmp_path,
        env={**env, "PATH": ""},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
