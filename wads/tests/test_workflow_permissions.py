"""Least-privilege GITHUB_TOKEN in the uv workflows (issue #113).

Jobs that run the repo's code (tests, lint, installs) get a read-only token
and keep no git credentials on disk, so test code or a compromised dependency
cannot push. Only the jobs whose job is to push (publish, Pages) may write,
and the publish job does not restore the cache the test jobs write.
"""

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = {
    "reusable": REPO_ROOT / ".github" / "workflows" / "uv-ci.yml",
    "inline": REPO_ROOT / "wads" / "data" / "github_ci_uv.yml",
}
READ_ONLY_JOBS = ("setup", "validation", "windows-validation")
WRITING_JOBS = {"publish", "github-pages"}


def _jobs(path):
    return yaml.safe_load(path.read_text())["jobs"]


def _checkouts(job):
    return [
        step
        for step in job.get("steps", [])
        if str(step.get("uses", "")).startswith("actions/checkout@")
    ]


@pytest.mark.parametrize("which", sorted(WORKFLOWS))
@pytest.mark.parametrize("job_name", READ_ONLY_JOBS)
def test_repo_code_jobs_are_read_only(which, job_name):
    job = _jobs(WORKFLOWS[which])[job_name]
    assert job.get("permissions") == {"contents": "read"}
    checkouts = _checkouts(job)
    assert checkouts, f"{job_name} has no checkout"
    for step in checkouts:
        assert (step.get("with") or {}).get("persist-credentials") is False


@pytest.mark.parametrize("which", sorted(WORKFLOWS))
def test_only_pushing_jobs_can_write(which):
    for name, job in _jobs(WORKFLOWS[which]).items():
        perms = job.get("permissions")
        assert perms is not None, f"{name} inherits the caller's permissions"
        writes = {scope for scope, level in perms.items() if level == "write"}
        if name not in WRITING_JOBS:
            assert not writes, f"{name} can write {writes}"


@pytest.mark.parametrize("which", sorted(WORKFLOWS))
def test_publish_job_does_not_restore_the_shared_uv_cache(which):
    steps = _jobs(WORKFLOWS[which])["publish"]["steps"]
    uv_setups = [s for s in steps if str(s.get("uses", "")).startswith("astral-sh/setup-uv@")]
    assert uv_setups
    for step in uv_setups:
        assert (step.get("with") or {}).get("enable-cache") is False
