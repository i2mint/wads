"""``[tool.wads.ci.commands]`` pre_test / post_test reach the reusable workflow (#203)."""

import sys
from pathlib import Path

import pytest
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


@pytest.mark.skipif(
    sys.platform == "win32", reason="a bare bash is WSL there; CI sets WADS_BASH"
)
def test_run_commands_really_runs_the_shell(tmp_path, capsys):
    marker = tmp_path / "m"
    assert run_commands([f"echo x > {marker}"]) == 0
    assert marker.exists()
    assert run_commands(["exit 7"]) == 7


def test_workflow_threads_commands_to_every_test_run():
    for path in (".github/workflows/uv-ci.yml", "wads/data/github_ci_uv.yml"):
        _check_workflow(yaml.safe_load((ROOT / path).read_text()))


def _check_workflow(wf):
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
    assert post["if"] == "${{ !cancelled() }}"


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



def test_commands_run_under_bash(monkeypatch):
    monkeypatch.delenv("WADS_BASH", raising=False)
    seen = []
    import wads.scripts.run_ci_commands as m

    real = m.subprocess.run
    m.subprocess.run = lambda argv, **kw: (seen.append(argv), type("R", (), {"returncode": 0}))[1]
    try:
        assert m._default_run("[[ a == a ]]") == 0
        monkeypatch.setenv("WADS_BASH", "/x/bash")
        m._default_run("true")
    finally:
        m.subprocess.run = real
    assert seen == [["bash", "-c", "[[ a == a ]]"], ["/x/bash", "-c", "true"]]


def test_a_string_command_is_one_command_and_junk_is_an_error():
    def cfg(v):
        return CIConfig({"tool": {"wads": {"ci": {"commands": {"pre_test": v}}}}})

    assert cfg("make data").commands_pre_test == ["make data"]
    assert cfg("").commands_pre_test == []
    import pytest

    for bad in (3, ["ok", 4], {"a": 1}):
        with pytest.raises(ValueError, match="pre_test"):
            cfg(bad).commands_pre_test


def test_read_ci_config_warns_about_commands_ci_never_runs(tmp_path, monkeypatch, capsys):
    """#228: `test` / `lint` / `format` in [tool.wads.ci.commands] are not run."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\n\n'
        '[tool.wads.ci.commands]\ntest = ["pytest"]\nlint = ["ruff check ."]\n'
    )
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "out"))
    monkeypatch.setenv("GITHUB_ENV", str(tmp_path / "env"))
    assert read_and_export_ci_config(str(tmp_path)) == 0
    out = capsys.readouterr().out
    assert "::warning title=CI commands ignored::[tool.wads.ci.commands].lint" in out
    assert "commands].test" not in out, "the scaffolded default test is not a warning"


def test_no_warning_when_only_pre_and_post_test_are_set(tmp_path, monkeypatch, capsys):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\n\n'
        '[tool.wads.ci.commands]\npre_test = ["echo a"]\n'
    )
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "out"))
    monkeypatch.setenv("GITHUB_ENV", str(tmp_path / "env"))
    assert read_and_export_ci_config(str(tmp_path)) == 0
    assert "CI commands ignored" not in capsys.readouterr().out
