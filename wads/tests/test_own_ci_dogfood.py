"""i2mint/wads#198: wads' own CI runs the reusable workflow at its own commit.

So a PR that edits ``uv-ci.yml`` runs its own version in PR CI. The tools that recognise
or rewrite stubs must neither flag nor "fix" that back to ``@master``.
"""

import subprocess
from pathlib import Path

import yaml

from wads.fleet_migrate import LOCAL_REUSABLE_CALL, migrate_one_to_stub
from wads.repo_audit import classify_workflow

ROOT = Path(__file__).resolve().parents[2]
OWN_CI = ROOT / ".github" / "workflows" / "ci.yml"


def test_wads_ci_calls_its_own_uv_ci_at_this_commit():
    job = yaml.safe_load(OWN_CI.read_text())["jobs"]["ci"]
    assert job["uses"] == LOCAL_REUSABLE_CALL


def test_the_repo_doctor_recognises_a_self_hosted_stub():
    assert classify_workflow(OWN_CI.read_text())["format"] == "uv-stub-local"


def test_fleet_stub_leaves_a_self_hosted_stub_alone(tmp_path):
    repo = tmp_path / "wads"
    (repo / ".github" / "workflows").mkdir(parents=True)
    (repo / ".github" / "workflows" / "ci.yml").write_text(OWN_CI.read_text())
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    result = migrate_one_to_stub(str(repo))
    assert (result.status, result.detail) == ("skip", "calls its own uv-ci.yml")
    assert (repo / ".github" / "workflows" / "ci.yml").read_text() == OWN_CI.read_text()
