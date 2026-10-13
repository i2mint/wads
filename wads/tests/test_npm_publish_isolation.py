"""npm publish isolation in the reusable npm workflows (issue #114).

Only the `publish` job can mint an OIDC token (npm trusted publishing), and it
runs none of the repo's code: no checkout, no install, no build, and
`npm publish <tarball> --ignore-scripts`. Install, build and lifecycle scripts
run in `pack`, which holds no publish credential.
"""

from pathlib import Path

import pytest
import yaml

WORKFLOWS_DIR = Path(__file__).resolve().parents[2] / ".github" / "workflows"
NPM_WORKFLOWS = ("npm-ci.yml", "npm-ci-monorepo.yml")


def _workflow(name):
    return yaml.safe_load((WORKFLOWS_DIR / name).read_text())


@pytest.mark.parametrize("name", NPM_WORKFLOWS)
def test_only_publish_job_can_mint_an_oidc_token(name):
    wf = _workflow(name)
    assert "id-token" not in wf["permissions"]
    for job_name, job in wf["jobs"].items():
        has_id_token = (job.get("permissions") or {}).get("id-token") == "write"
        assert has_id_token == (job_name == "publish"), job_name


@pytest.mark.parametrize("name", NPM_WORKFLOWS)
def test_publish_job_runs_no_repo_code(name):
    job = _workflow(name)["jobs"]["publish"]
    assert job["needs"] == ["setup", "pack"]
    uses = [str(step.get("uses", "")) for step in job["steps"]]
    assert not any(u.startswith(("actions/checkout@", "pnpm/")) for u in uses)
    runs = "\n".join(
        line
        for step in job["steps"]
        for line in step.get("run", "").splitlines()
        if not line.strip().startswith("#")
    ) + "\n"
    for forbidden in ("npm ci", "npm install\n", "pnpm ", "npm run", "npm pack"):
        assert forbidden not in runs, forbidden
    publish_lines = [l for l in runs.splitlines() if "npm publish" in l]
    assert publish_lines and all("--ignore-scripts" in l for l in publish_lines)


@pytest.mark.parametrize("name", NPM_WORKFLOWS)
def test_pack_and_publish_share_the_opt_in_gate(name):
    jobs = _workflow(name)["jobs"]
    assert jobs["pack"]["if"] == jobs["publish"]["if"]
    assert "id-token" not in (jobs["pack"].get("permissions") or {})
