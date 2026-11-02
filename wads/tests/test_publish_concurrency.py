"""Publish runs are queued per repo and branch, never run side by side (issue #174).

Two merges seconds apart ran their publish jobs concurrently, both bumped to the
same next version, and the second upload was refused (a red run on master). A
job-level ``concurrency`` group with ``queue: max`` on ``publish`` queues them
(FIFO); only ``publish`` is grouped, so every merge is still validated in parallel.
"""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = pytest.mark.parametrize(
    "workflow", [".github/workflows/uv-ci.yml", "wads/data/github_ci_uv.yml"]
)


def _jobs(workflow):
    return yaml.safe_load((ROOT / workflow).read_text())["jobs"]


@WORKFLOWS
def test_publish_is_queued_per_repo_and_branch(workflow):
    concurrency = _jobs(workflow)["publish"]["concurrency"]
    assert concurrency == {
        "group": "wads-publish-${{ github.repository }}-${{ github.ref }}",
        # Keep every waiting run: with the default single pending slot, a later
        # *arrival* (not a later merge) replaces the waiting run.
        "queue": "max",
    }
    # cancel-in-progress may not be combined with queue: max (validation error),
    # and its default (false) is what a running upload needs.
    assert "cancel-in-progress" not in concurrency


@WORKFLOWS
def test_only_publish_is_serialized(workflow):
    jobs = _jobs(workflow)
    grouped = sorted(name for name, job in jobs.items() if "concurrency" in job)
    assert grouped == ["publish"]
    assert "concurrency" not in yaml.safe_load((ROOT / workflow).read_text())
