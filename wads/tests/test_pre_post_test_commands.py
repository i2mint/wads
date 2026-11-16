"""``[tool.wads.ci.commands]`` pre_test / post_test reach the reusable workflow (#203)."""

import re
from pathlib import Path

import yaml

from wads.ci_config import CIConfig
from wads.scripts.read_ci_config import read_and_export_ci_config
from wads.scripts.run_ci_commands import run_commands

ROOT = Path(__file__).resolve().parents[2]


def test_read_ci_config_emits_command_lists(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\n\n'
        '[tool.wads.ci.commands]\npre_test = ["echo a", "echo b"]\n'
    )
    out = tmp_path / "out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setenv("GITHUB_ENV", str(tmp_path / "env"))
    assert read_and_export_ci_config(str(tmp_path)) == 0
    text = out.read_text()
    assert 'pre-test-commands=["echo a", "echo b"]' in text
    assert "post-test-commands=[]" in text


def test_run_commands_stops_at_first_failure():
    ran = []

    def run(cmd, **kw):
        ran.append(cmd)
        return 3 if cmd == "bad" else 0

    assert run_commands('["ok", "bad", "never"]', run=run) == 3
    assert ran == ["ok", "bad"]


def test_run_commands_empty_inputs_do_nothing():
    for empty in ("", "[]", None, []):
        assert run_commands(empty, run=lambda c, **k: 1) == 0


def test_run_commands_really_runs_the_shell(tmp_path, capsys):
    marker = tmp_path / "m"
    assert run_commands([f"echo x > {marker}"]) == 0
    assert marker.exists()
    assert run_commands(["exit 7"]) == 7


def test_workflow_threads_commands_to_every_test_run():
    wf = yaml.safe_load((ROOT / ".github/workflows/uv-ci.yml").read_text())
    setup_out = wf["jobs"]["setup"]["outputs"]
    assert {"pre-test-commands", "post-test-commands"} <= set(setup_out)
    for job in ("validation", "windows-validation"):
        (step,) = [
            s
            for s in wf["jobs"][job]["steps"]
            if s.get("uses", "").startswith("i2mint/wads/actions/run-tests-uv")
        ]
        assert step["with"]["pre-test-commands"] == (
            "${{ needs.setup.outputs.pre-test-commands }}"
        )
        assert step["with"]["post-test-commands"] == (
            "${{ needs.setup.outputs.post-test-commands }}"
        )


def test_action_runs_post_test_even_after_a_test_failure():
    action = yaml.safe_load((ROOT / "actions/run-tests-uv/action.yml").read_text())
    names = [s["name"] for s in action["runs"]["steps"]]
    assert names.index("Pre-test commands") < names.index("Run Tests")
    post = action["runs"]["steps"][names.index("Post-test commands")]
    assert names.index("Post-test commands") > names.index("Run Tests")
    assert post["if"] == "always()"


def test_ci_local_runs_pre_and_post_test_around_pytest():
    from wads.ci_local import _leg_steps

    config = CIConfig(
        {
            "project": {"name": "demo"},
            "tool": {
                "wads": {
                    "ci": {
                        "commands": {"pre_test": ["echo pre"], "post_test": ["echo post"]}
                    }
                }
            },
        }
    )
    steps = _leg_steps(
        config, label="py3.12", venv="/w/v", version="3.12", platform="posix"
    )
    labels = [s.name for s in steps]
    assert labels.index("py3.12: pre_test 1/1") < labels.index("py3.12: tests")
    assert labels.index("py3.12: tests") < labels.index("py3.12: post_test 1/1")
    (pre,) = [s for s in steps if s.name.endswith("pre_test 1/1")]
    assert pre.argv == ("bash", "-c", "echo pre")

