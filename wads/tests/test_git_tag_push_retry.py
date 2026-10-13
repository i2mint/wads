"""Behavioural tests for the ``git-tag`` action's tag push.

Right after the publish job pushes the version-bump commit, GitHub can reject
the tag that points at it with "missing necessary objects" for a moment, which
left a release on PyPI with no tag and a red run (i2mint/wads#122).

The ``Push Tag`` step's script is taken straight out of
``actions/git-tag/action.yml`` and run against a throwaway bare ``origin`` whose
``pre-receive`` hook rejects the first N pushes, so the retry is verified, not
assumed.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from wads.tests.test_git_commit_push_retry import BASH, _commit, _configure, _git

pytestmark = pytest.mark.skipif(
    sys.platform == "win32" or BASH is None or shutil.which("git") is None,
    reason="needs a POSIX bash and git to exercise the tag-push script",
)

TAG = "0.0.10"
MESSAGE = "Release version 0.0.10"


def push_tag_script() -> str:
    """The shell script of the action's ``Push Tag`` step, as CI would run it."""
    root = Path(__file__).resolve().parents[2]
    action = yaml.safe_load((root / "actions" / "git-tag" / "action.yml").read_text())
    (step,) = [s for s in action["runs"]["steps"] if s.get("name") == "Push Tag"]
    return step["run"]


REJECTING_HOOK = """#!/bin/sh
# Reject the first $REJECTIONS pushes, as GitHub did right after the bump push.
n=$(cat "$COUNTER" 2>/dev/null || echo 0)
echo $((n + 1)) > "$COUNTER"
if [ "$n" -lt "$REJECTIONS" ]; then
  echo "error: missing necessary objects" >&2
  exit 1
fi
"""


@pytest.fixture
def tagged_clone(tmp_path, monkeypatch):
    """A bare ``origin`` with a rejecting hook, and a clone holding an annotated tag."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "home" / "gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", os.devnull)
    (tmp_path / "home").mkdir()
    origin = tmp_path / "origin.git"
    _git("init", "--bare", "-b", "main", str(origin), cwd=tmp_path)
    clone = tmp_path / "clone"
    _git("clone", str(origin), str(clone), cwd=tmp_path)
    _configure(clone)
    _commit(clone, "pyproject.toml", 'version = "0.0.10"\n', "**CI** bump")
    _git("push", "origin", "main", cwd=clone)
    _git("tag", "-a", TAG, "-m", MESSAGE, cwd=clone)
    hook = origin / "hooks" / "pre-receive"
    hook.write_text(REJECTING_HOOK)
    hook.chmod(0o755)
    return origin, clone


def run_push_tag(
    clone: Path, tmp_path: Path, *, rejections: int, retries="3", delay="0"
):
    env = {
        **os.environ,
        "TAG": TAG,
        "TAG_MESSAGE": MESSAGE,
        "FORCE": "false",
        "PUSH_RETRIES": retries,
        "PUSH_RETRY_DELAY": delay,
        "REJECTIONS": str(rejections),
        "COUNTER": str(tmp_path / "pushes"),
    }
    return subprocess.run(
        [BASH, "-c", push_tag_script()], cwd=clone, capture_output=True, text=True,
        env=env,
    )


def _remote_tag(origin: Path):
    return _git("tag", "--list", TAG, cwd=origin).stdout.strip()


def test_a_clean_push_lands_on_the_first_attempt(tagged_clone, tmp_path):
    origin, clone = tagged_clone
    res = run_push_tag(clone, tmp_path, rejections=0)
    assert res.returncode == 0, res.stderr
    assert "retrying" not in res.stdout
    assert _remote_tag(origin) == TAG


def test_a_transient_rejection_is_retried(tagged_clone, tmp_path):
    """The reported failure: the first push is refused, a retry lands the tag."""
    origin, clone = tagged_clone
    res = run_push_tag(clone, tmp_path, rejections=2)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "retrying in 0s (1/3)" in res.stdout and "(2/3)" in res.stdout
    assert _remote_tag(origin) == TAG
    # The annotated tag object itself landed, not a lightweight copy.
    local = _git("rev-parse", f"refs/tags/{TAG}", cwd=clone).stdout
    assert _git("rev-parse", f"refs/tags/{TAG}", cwd=origin).stdout == local


def test_exhausted_retries_fail_with_the_restore_command(tagged_clone, tmp_path):
    origin, clone = tagged_clone
    res = run_push_tag(clone, tmp_path, rejections=99, retries="2")
    assert res.returncode == 1
    commit = _git("rev-parse", "HEAD", cwd=clone).stdout.strip()
    assert "::error::" in res.stdout and f"git tag -a {TAG} {commit} -m" in res.stdout
    assert _remote_tag(origin) == ""
    assert (tmp_path / "pushes").read_text().strip() == "3"  # 1 + 2 retries


def test_zero_retries_keeps_the_single_attempt(tagged_clone, tmp_path):
    _, clone = tagged_clone
    res = run_push_tag(clone, tmp_path, rejections=1, retries="0")
    assert res.returncode == 1
    assert (tmp_path / "pushes").read_text().strip() == "1"


def test_a_tag_already_on_the_remote_counts_as_pushed(tagged_clone, tmp_path):
    """Re-running the step once the tag is on the remote is not an error."""
    origin, clone = tagged_clone
    hook = origin / "hooks" / "pre-receive"
    hook.unlink()
    _git("push", "origin", f"refs/tags/{TAG}", cwd=clone)
    hook.write_text(REJECTING_HOOK)  # every further push is refused
    hook.chmod(0o755)
    res = run_push_tag(clone, tmp_path, rejections=99)
    assert res.returncode == 0, res.stdout + res.stderr


def test_a_failing_ls_remote_still_retries(tagged_clone, tmp_path):
    """The already-there probe failing must not end the step early (review of #123)."""
    origin, clone = tagged_clone
    # Every upload-pack (ls-remote) fails; receive-pack (push) still works.
    _git("config", "remote.origin.uploadpack", "false", cwd=clone)
    res = run_push_tag(clone, tmp_path, rejections=1)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "(1/3)" in res.stdout and _remote_tag(origin) == TAG


def test_a_non_numeric_retry_count_falls_back_to_the_default(tagged_clone, tmp_path):
    _, clone = tagged_clone
    res = run_push_tag(clone, tmp_path, rejections=99, retries="abc")
    assert res.returncode == 1 and "not a number" in res.stdout
    assert (tmp_path / "pushes").read_text().strip() == "4"  # 1 + 3 retries
