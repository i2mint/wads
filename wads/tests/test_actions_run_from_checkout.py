"""Actions run their scripts from their own checkout, never from a PyPI wheel (#156)."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ACTIONS = ("read-ci-config", "set-env-vars", "build-dist")
# The actions pin Python 3.11 (tomllib); on older interpreters tomli lives in site-packages.
_NO_SITE = ["-S"] if sys.version_info >= (3, 11) else []
# Windows needs SYSTEMROOT to even start Python; nothing else leaks in.
_BASE_ENV = {k: os.environ[k] for k in ("SYSTEMROOT",) if k in os.environ}
PYPROJECT = (
    '[project]\nname = "demo"\nversion = "0.0.1"\n'
    '[project.optional-dependencies]\ndev = ["pytest", "httpx>=0.27"]\n'
)


@pytest.mark.parametrize("action", ACTIONS)
def test_action_does_not_use_installed_wads(action):
    text = (ROOT / "actions" / action / "action.yml").read_text()
    assert "install --quiet 'wads" not in text and "install wads" not in text
    assert "python3 -m wads" not in text and "python -m wads" not in text
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
        env={**_BASE_ENV, **env, "PATH": ""},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_read_ci_config_emits_outputs_and_test_extra_warning(tmp_path):
    """The #59 warning needs `packaging`; an isolated run must not swallow it."""
    (tmp_path / "pyproject.toml").write_text(PYPROJECT)
    out = tmp_path / "out.txt"
    result = subprocess.run(
        [sys.executable, "-I", str(ROOT / "wads" / "scripts" / "read_ci_config.py"), "."],
        cwd=tmp_path,
        env={**_BASE_ENV, "GITHUB_OUTPUT": str(out), "PATH": ""},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "project-name=demo" in out.read_text()
    assert "Test extra not installed" in result.stdout + result.stderr
