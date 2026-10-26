"""The repo audit flags a stub whose on-demand pre-filter disagrees with pyproject (i2mint/wads#137)."""

from pathlib import Path

import pytest

from wads import github_ci_uv_path, github_ci_uv_stub_path
from wads.ci_trigger import render_stub_trigger, stub_customizations, stub_markers
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
    assert "recognised pre-filter" in finding["summary"]
    other = tmp_path / "other"
    other.mkdir()
    stub = render_stub_trigger(STUB, mode="on-demand")
    (finding,) = _drift(_repo(other, trigger={}, stub=stub))
    assert "on-demand shape" in finding["summary"]


def test_a_malformed_trigger_table_does_not_crash_the_audit(tmp_path):
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text(STUB)
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "pkg"\nversion = "0.1.0"\n\n[tool.wads.ci]\ntrigger = "on-demand"\n'
    )
    assert _drift(tmp_path) == []


def test_marker_comparison_is_case_insensitive_and_unicode_safe(tmp_path):
    stub = render_stub_trigger(STUB, mode="on-demand", run_ci_marker="[Déploy it]", deploy_marker="[ship]")
    repo = _repo(tmp_path, trigger={"mode": "on-demand", "run_ci_marker": "[déploy IT]", "deploy_marker": "[SHIP]"}, stub=stub)
    assert _drift(repo) == []


INLINE = Path(github_ci_uv_path).read_text()


def _inline_findings(repo):
    report = audit_repo(repo, network=False)
    return [f for f in report["findings"] if "trigger gate" in f["summary"]]


def test_an_inline_workflow_with_the_gate_has_no_drift(tmp_path):
    assert _inline_findings(_repo(tmp_path, trigger={"mode": "on-demand"}, stub=INLINE)) == []


DATA = Path(__file__).parent / "data"


def test_old_inline_templates_are_flagged_with_what_each_one_really_lacks(tmp_path):
    trigger = {"mode": "on-demand"}
    none = (DATA / "inline_ci_no_trigger_gate.yml").read_text()
    first = (DATA / "inline_ci_first_trigger_gate.yml").read_text()
    (f_none,) = _inline_findings(_repo(tmp_path, trigger=trigger, stub=none))
    assert "runs on every push" in f_none["summary"] and f_none["dispatch"] == "wads-migrate"
    other = tmp_path / "first"
    other.mkdir()
    (f_first,) = _inline_findings(_repo(other, trigger=trigger, stub=first))
    assert "[run deploy]" in f_first["summary"]


def test_old_inline_templates_are_fine_when_pyproject_is_auto(tmp_path):
    old = (DATA / "inline_ci_no_trigger_gate.yml").read_text()
    assert _inline_findings(_repo(tmp_path, trigger={}, stub=old)) == []


@pytest.mark.parametrize("marker", ["it's", 'say "hi"', "a\\b", "\\u0041", "[déjà vu]", "🚀 go"])
def test_stub_markers_round_trip_through_a_rendered_stub(marker):
    stub = render_stub_trigger(STUB, mode="on-demand", run_ci_marker=marker)
    assert stub_markers(stub) == [marker, "[run deploy]"]


def test_a_hand_extended_prefilter_is_a_customization_a_rerender_would_drop():
    stub = render_stub_trigger(STUB, mode="on-demand")
    edited = stub.replace("[run deploy]')\"", "[run deploy]') && github.actor == 'me'\"")
    assert edited != stub and "`jobs.ci.if`" in stub_customizations(edited)[1]
    assert stub_customizations(stub)[1] == []
