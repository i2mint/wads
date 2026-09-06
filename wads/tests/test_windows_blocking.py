"""Tests for ``[tool.wads.ci.testing].windows_blocking``.

The Windows leg of the reusable CI workflow used to carry a hardcoded
``continue-on-error: true``, so a Windows-only defect merged behind a green
tick. This pins the opt-in knob that lets a repo make that leg red, plumbed
CIConfig -> read_ci_config script -> read-ci-config action -> the setup job's
outputs -> the ``continue-on-error`` expression on ``windows-validation``.

Scope, deliberately: setting the knob makes the RUN red. It does **not** gate
the release — ``publish.needs`` stays ``[setup, validation]``, which the last
test here pins, because adding ``windows-validation`` to it would skip every
release on a repo with ``test_on_windows = false`` unless the publish gate also
grew a status function, and this suite forbids those (see
``test_workflow_gates.py``).
"""

from pathlib import Path

import pytest
import yaml

from wads.ci_config import CIConfig

REPO_ROOT = Path(__file__).resolve().parents[2]
UV_CI = REPO_ROOT / ".github" / "workflows" / "uv-ci.yml"
UV_CI_TEMPLATE = REPO_ROOT / "wads" / "data" / "github_ci_uv.yml"
READ_CI_CONFIG_ACTION = REPO_ROOT / "actions" / "read-ci-config" / "action.yml"

#: Fail-closed: only the literal string 'true' turns blocking on, so an unset
#: output ('') or an older wads that emits nothing keeps today's behaviour.
BLOCKING_EXPRESSION = "${{ needs.setup.outputs.windows-blocking != 'true' }}"

WORKFLOWS = pytest.mark.parametrize(
    "workflow_path", [UV_CI, UV_CI_TEMPLATE], ids=["reusable", "template"]
)


def _cfg(testing_block):
    return CIConfig({"tool": {"wads": {"ci": {"testing": testing_block}}}})


def _jobs(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))["jobs"]


def test_windows_blocking_defaults_to_false():
    """Absent declaration = today's behaviour: the Windows leg never blocks."""
    assert CIConfig({}).windows_blocking is False
    assert _cfg({"test_on_windows": True}).windows_blocking is False


def test_windows_blocking_reads_the_declaration():
    assert _cfg({"windows_blocking": True}).windows_blocking is True
    assert _cfg({"windows_blocking": False}).windows_blocking is False


def test_read_ci_config_emits_windows_blocking(tmp_path, monkeypatch):
    """The read_ci_config script writes windows-blocking to GITHUB_OUTPUT."""
    from wads.scripts.read_ci_config import read_and_export_ci_config

    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\n\n'
        "[tool.wads.ci.testing]\nwindows_blocking = true\n"
    )
    out_file = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))
    monkeypatch.setenv("GITHUB_ENV", str(tmp_path / "gh_env"))

    assert read_and_export_ci_config(str(tmp_path)) == 0
    assert "windows-blocking=true" in out_file.read_text(encoding="utf-8")


def test_read_ci_config_emits_false_when_undeclared(tmp_path, monkeypatch):
    """Undeclared emits 'false', which the workflow expression reads as non-blocking."""
    from wads.scripts.read_ci_config import read_and_export_ci_config

    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\n'
    )
    out_file = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))
    monkeypatch.setenv("GITHUB_ENV", str(tmp_path / "gh_env"))

    assert read_and_export_ci_config(str(tmp_path)) == 0
    assert "windows-blocking=false" in out_file.read_text(encoding="utf-8")


def test_action_declares_the_windows_blocking_output():
    """Without the action output, the setup job cannot forward the value."""
    action = yaml.safe_load(READ_CI_CONFIG_ACTION.read_text(encoding="utf-8"))
    outputs = action["outputs"]
    assert "windows-blocking" in outputs
    assert outputs["windows-blocking"]["value"] == (
        "${{ steps.config.outputs.windows-blocking }}"
    )


@WORKFLOWS
def test_setup_job_forwards_windows_blocking(workflow_path):
    """The knob is inert unless the setup job re-exports it as a job output."""
    setup_outputs = _jobs(workflow_path)["setup"]["outputs"]
    assert setup_outputs.get("windows-blocking") == (
        "${{ steps.config.outputs.windows-blocking }}"
    )


@WORKFLOWS
def test_windows_leg_continue_on_error_is_the_fail_closed_expression(workflow_path):
    """`!= 'true'` — anything but an explicit opt-in leaves the leg non-blocking.

    Matches the house convention for opt-in gates (see the licence gate), and
    degrades safely: an older ``read-ci-config`` emits no such output, and
    ``'' != 'true'`` is true, i.e. continue-on-error, i.e. today's behaviour.
    """
    win = _jobs(workflow_path)["windows-validation"]
    assert win["continue-on-error"] == BLOCKING_EXPRESSION


@WORKFLOWS
def test_windows_leg_is_still_not_a_publish_dependency(workflow_path):
    """Blocking makes the RUN red; it must not silently start gating releases.

    Adding ``windows-validation`` to ``publish.needs`` would skip every publish
    on a repo with ``test_on_windows = false`` unless the publish ``if:`` also
    grew ``!failure() && !cancelled()`` — and ``test_workflow_gates.py``
    deliberately forbids status functions there.
    """
    jobs = _jobs(workflow_path)
    assert "windows-validation" not in jobs["publish"]["needs"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
