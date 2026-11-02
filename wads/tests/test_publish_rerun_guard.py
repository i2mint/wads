"""A re-run of an old publish run refuses to re-release its old commit (issue #183).

Re-running an old run rebuilt its commit and published it under a new, higher
version, newer than code that had already shipped. The publish job's first step
now fails a re-run (attempt > 1) whose commit is no longer the default-branch tip.
The step's script is run, as written in the workflow, against throwaway repos.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from wads.tests.test_git_commit_push_retry import (
    BASH,
    DEFAULT_BRANCH,
    _commit,
    _git,
    _land_a_concurrent_merge,
    remote_and_clone,  # noqa: F401 (fixture)
)

pytestmark = pytest.mark.skipif(
    sys.platform == "win32" or BASH is None or shutil.which("git") is None,
    reason="needs a POSIX bash and git to run the step script",
)

ROOT = Path(__file__).resolve().parents[2]
STEP = "Refuse a re-run of an old commit"
WORKFLOWS = [".github/workflows/uv-ci.yml", "wads/data/github_ci_uv.yml"]


def _publish_steps(workflow):
    return yaml.safe_load((ROOT / workflow).read_text())["jobs"]["publish"]["steps"]


def _guard(clone: Path, *, attempt: str, sha: str, workflow=WORKFLOWS[0]):
    (step,) = [s for s in _publish_steps(workflow) if s.get("name") == STEP]
    return subprocess.run(
        # How GitHub runs a `run:` step with the default bash shell.
        [BASH, "--noprofile", "--norc", "-eo", "pipefail", "-c", step["run"]],
        cwd=clone,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "RUN_ATTEMPT": attempt,
            "BUILT_SHA": sha,
            "DEFAULT_BRANCH": DEFAULT_BRANCH,
        },
    )


def _head(repo):
    return _git("rev-parse", "HEAD", cwd=repo).stdout.strip()


@pytest.mark.parametrize("workflow", WORKFLOWS)
def test_the_guard_runs_right_after_checkout(workflow):
    names = [s.get("name", s.get("uses")) for s in _publish_steps(workflow)]
    assert names[:2] == ["actions/checkout@v6", STEP]


def test_a_first_attempt_always_passes_even_off_tip(remote_and_clone, tmp_path):
    """Queued publish runs legitimately build a commit that is no longer the tip."""
    origin, clone = remote_and_clone
    old = _head(clone)
    _land_a_concurrent_merge(origin, tmp_path)
    assert _guard(clone, attempt="1", sha=old).returncode == 0


def test_a_rerun_of_the_tip_passes(remote_and_clone):
    _, clone = remote_and_clone
    assert _guard(clone, attempt="2", sha=_head(clone)).returncode == 0


def test_a_rerun_of_an_old_commit_is_refused(remote_and_clone, tmp_path):
    origin, clone = remote_and_clone
    old = _head(clone)
    _land_a_concurrent_merge(origin, tmp_path)
    result = _guard(clone, attempt="3", sha=old)
    assert result.returncode == 1
    assert f"re-run attempt 3 of a publish for {old}" in result.stdout
    assert "Re-run the latest run" in result.stdout


def test_a_rerun_after_its_own_release_landed_is_refused(remote_and_clone):
    """The first attempt pushed its bump: re-running would release the same code again."""
    origin, clone = remote_and_clone
    built = _head(clone)
    _commit(clone, "pyproject.toml", 'version = "0.0.3"\n', "**CI** bump [skip ci]")
    _git("push", "origin", DEFAULT_BRANCH, cwd=clone)
    assert _guard(clone, attempt="2", sha=built).returncode == 1


def test_an_unreachable_remote_does_not_block_a_rerun(remote_and_clone, tmp_path):
    _, clone = remote_and_clone
    _git("remote", "set-url", "origin", str(tmp_path / "gone.git"), cwd=clone)
    assert _guard(clone, attempt="2", sha=_head(clone)).returncode == 0
