"""The repo audit flags a stub whose on-demand pre-filter disagrees with pyproject (i2mint/wads#137)."""

from pathlib import Path

from wads import github_ci_uv_stub_path
from wads.ci_trigger import render_stub_trigger
from wads.repo_audit import audit_repo

STUB = Path(github_ci_uv_stub_path).read_text()


def _repo(tmp_path, *, trigger, stub):
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text(stub)
    body = "".join(f'{k} = "{v}"\n' for k, v in trigger.items())
    (tmp_path / "pyproject.toml").write_text(
        f'[project]\nname = "pkg"\nversion = "0.1.0"\n\n[tool.wads.ci.trigger]\n{body}'
    )
    return tmp_path


def _drift(repo):
    report = audit_repo(repo, network=False)
    return [f for f in report["findings"] if "pre-filter" in f["summary"] or "on-demand shape" in f["summary"]]


def test_a_freshly_rendered_stub_has_no_drift(tmp_path):
    repo = _repo(tmp_path, trigger={"mode": "on-demand"}, stub=render_stub_trigger(STUB, mode="on-demand"))
    assert _drift(repo) == []


def test_auto_mode_with_the_plain_stub_has_no_drift(tmp_path):
    assert _drift(_repo(tmp_path, trigger={}, stub=STUB)) == []


def test_a_stub_rendered_before_the_deploy_marker_is_flagged(tmp_path):
    old = render_stub_trigger(STUB, mode="on-demand").replace(
        " || contains(github.event.head_commit.message, '[run deploy]')", ""
    )
    (finding,) = _drift(_repo(tmp_path, trigger={"mode": "on-demand"}, stub=old))
    assert "[run deploy]" in finding["summary"] and finding["dispatch"] == "wads-migrate"


def test_a_changed_marker_in_pyproject_is_flagged(tmp_path):
    stub = render_stub_trigger(STUB, mode="on-demand")
    (finding,) = _drift(_repo(tmp_path, trigger={"mode": "on-demand", "run_ci_marker": "[go]"}, stub=stub))
    assert "[go]" in finding["summary"]


def test_on_demand_pyproject_with_the_plain_stub_and_the_reverse(tmp_path):
    (finding,) = _drift(_repo(tmp_path, trigger={"mode": "on-demand"}, stub=STUB))
    assert "no pre-filter" in finding["summary"]
    other = tmp_path / "other"
    other.mkdir()
    stub = render_stub_trigger(STUB, mode="on-demand")
    (finding,) = _drift(_repo(other, trigger={}, stub=stub))
    assert "on-demand shape" in finding["summary"]
