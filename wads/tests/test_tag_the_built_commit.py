"""The release tag names the commit that was built, not a later branch tip (issue #161).

Merges landing minutes apart: each publish run builds its own merge commit plus the
version bump, but when the branch moved during the run, ``git-commit`` replays the bump
onto the new tip before pushing. Tagging HEAD after that put tag ``0.0.97`` on a tree
holding code the ``0.0.97`` wheel did not. ``git-commit`` now outputs the sha it
committed (before any replay), and ``git-tag`` tags that ``ref``.

The steps' shell scripts are taken straight out of ``actions/*/action.yml`` and run
against throwaway repositories, as in ``test_git_commit_push_retry``.
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
    run_push_step,
)

pytestmark = pytest.mark.skipif(
    sys.platform == "win32" or BASH is None or shutil.which("git") is None,
    reason="needs a POSIX bash and git to exercise the action scripts",
)

ROOT = Path(__file__).resolve().parents[2]
TAG, MESSAGE = "0.0.3", "Release version 0.0.3"


def _step(action: str, name: str) -> str:
    spec = yaml.safe_load((ROOT / "actions" / action / "action.yml").read_text())
    (step,) = [s for s in spec["runs"]["steps"] if s.get("name") == name]
    return step["run"]


def _bash(script: str, cwd: Path, **env):
    return subprocess.run(
        [BASH, "-c", script],
        cwd=cwd,
        capture_output=True,
        text=True,
        env={**os.environ, **env},
    )


def _commit_step(clone: Path, tmp_path: Path, *, message="**CI** bump to 0.0.3"):
    """Run git-commit's ``Commit Changes`` step; return (result, its commit-sha output)."""
    out = tmp_path / "github_output"
    out.write_text("")
    res = _bash(
        _step("git-commit", "Commit Changes"),
        clone,
        COMMIT_MESSAGE=message,
        ADD_PATTERN=".",
        ALLOW_EMPTY="false",
        GITHUB_OUTPUT=str(out),
    )
    outputs = dict(line.split("=", 1) for line in out.read_text().splitlines())
    return res, outputs.get("commit-sha")


def _create_tag(clone: Path, *, ref: str):
    return _bash(
        _step("git-tag", "Create Tag"),
        clone,
        TAG=TAG,
        TAG_MESSAGE=MESSAGE,
        FORCE="false",
        REF=ref,
    )


def _head(repo: Path, ref="HEAD") -> str:
    return _git("rev-parse", ref, cwd=repo).stdout.strip()


def test_commit_step_outputs_the_commit_it_made(remote_and_clone, tmp_path):
    _, clone = remote_and_clone
    (clone / "pyproject.toml").write_text('version = "0.0.3"\n')
    res, sha = _commit_step(clone, tmp_path)
    assert res.returncode == 0, res.stderr
    assert sha == _head(clone)
    assert _git("log", "-1", "--format=%s", cwd=clone).stdout.strip() == (
        "**CI** bump to 0.0.3"
    )


def test_commit_step_outputs_head_when_there_is_nothing_to_commit(
    remote_and_clone, tmp_path
):
    _, clone = remote_and_clone
    before = _head(clone)
    res, sha = _commit_step(clone, tmp_path)
    assert res.returncode == 0 and "No changes to commit" in res.stdout
    assert sha == before == _head(clone)


def test_the_tag_names_the_built_commit_after_a_replay(remote_and_clone, tmp_path):
    """The reported failure, end to end: bump, concurrent merge, replay, tag."""
    origin, clone = remote_and_clone
    (clone / "pyproject.toml").write_text('version = "0.0.3"\n')
    _, built = _commit_step(clone, tmp_path)
    _land_a_concurrent_merge(origin, tmp_path)  # lands README.md on main
    pushed = run_push_step(clone)
    assert pushed.returncode == 0, pushed.stdout + pushed.stderr
    assert _head(clone) != built, "the bump was replayed onto the moved branch"

    res = _create_tag(clone, ref=built)
    assert res.returncode == 0, res.stderr
    assert f"::notice::Tag {TAG} names the built commit {built}" in res.stdout
    assert _head(clone, f"{TAG}^{{commit}}") == built
    # The tag's tree is the built tree: the bump, without the concurrent merge.
    files = _git("ls-tree", "--name-only", TAG, cwd=clone).stdout.split()
    assert "README.md" not in files
    assert _git("show", f"{TAG}:pyproject.toml", cwd=clone).stdout == (
        'version = "0.0.3"\n'
    )
    # ...and it reaches the remote although no branch contains that commit.
    _git("push", "origin", f"refs/tags/{TAG}", cwd=clone)
    assert _head(origin, f"{TAG}^{{commit}}") == built
    assert _head(origin, DEFAULT_BRANCH) != built


def test_without_a_race_the_built_commit_is_the_tip(remote_and_clone, tmp_path):
    _, clone = remote_and_clone
    (clone / "pyproject.toml").write_text('version = "0.0.3"\n')
    _, built = _commit_step(clone, tmp_path)
    assert run_push_step(clone).returncode == 0
    res = _create_tag(clone, ref=built)
    assert res.returncode == 0 and "::notice::" not in res.stdout
    assert _head(clone, f"{TAG}^{{commit}}") == built == _head(clone)


@pytest.mark.parametrize("message", [MESSAGE, ""])
def test_an_empty_ref_tags_head_as_before(remote_and_clone, message):
    _, clone = remote_and_clone
    res = _bash(
        _step("git-tag", "Create Tag"),
        clone,
        TAG=TAG,
        TAG_MESSAGE=message,
        FORCE="false",
        REF="",
    )
    assert res.returncode == 0, res.stderr
    assert _head(clone, f"{TAG}^{{commit}}") == _head(clone)
    kind = _git("cat-file", "-t", TAG, cwd=clone).stdout.strip()
    assert kind == ("tag" if message else "commit")


@pytest.mark.parametrize(
    "workflow", [".github/workflows/uv-ci.yml", "wads/data/github_ci_uv.yml"]
)
def test_the_publish_job_tags_the_bump_commit_output(workflow):
    jobs = yaml.safe_load((ROOT / workflow).read_text())["jobs"]
    steps = {s.get("name"): s for s in jobs["publish"]["steps"]}
    commit_id = steps["Commit Changes"]["id"]
    ref = steps["Tag Repository"]["with"]["ref"]
    assert ref == f"${{{{ steps.{commit_id}.outputs.commit-sha }}}}"
