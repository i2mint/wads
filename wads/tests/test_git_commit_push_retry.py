"""Behavioural tests for the ``git-commit`` action's push-back step.

The CI publish job uploads to PyPI and *then* pushes the version-bump commit
back to the default branch. When a second PR is merged while the run is in
flight, that push is rejected as non-fast-forward: the release is on PyPI but
its bump commit and tag never land, and the run goes red (i2mint/wads#81).

These tests take the ``Push Changes`` step's shell script straight out of
``actions/git-commit/action.yml`` and run it against throwaway local
repositories that reproduce the race, so the recovery is verified rather than
assumed. They cover the four paths that matter:

- nothing moved: exactly one push attempt, as before the fix;
- the branch moved: the bump commit is replayed on top and lands;
- retries disabled: the historical single-attempt failure is still available;
- the replay conflicts: it fails loudly and leaves no rebase in progress.

They need a POSIX shell, and skip where there is none — the publish job that
runs this step is ubuntu-only.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


def _working_bash():
    """Path to a bash that can actually run a script, or None.

    Presence is not enough. On a Windows runner ``shutil.which("bash")`` finds
    WSL's stub in ``System32``, which answers every invocation with "Windows
    Subsystem for Linux has no installed distributions" and runs nothing — so
    the candidate is probed rather than trusted.
    """
    candidate = shutil.which("bash")
    if candidate is None:
        return None
    try:
        probe = subprocess.run(
            [candidate, "-c", "echo ok"], capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return candidate if probe.stdout.strip() == "ok" else None


BASH = _working_bash()

# The step under test runs as `shell: bash` in the publish job, which is
# `runs-on: ubuntu-latest` — it never executes on Windows. Testing it under Git
# Bash would only add Windows path and quoting semantics that production never
# meets, so the Windows leg of the matrix skips rather than reports noise.
pytestmark = pytest.mark.skipif(
    sys.platform == "win32" or BASH is None or shutil.which("git") is None,
    reason="needs a POSIX bash and git to exercise the push-back script",
)

DEFAULT_BRANCH = "main"
PUSH_STEP_NAME = "Push Changes"


def _repo_root() -> Path:
    """Directory holding the ``actions/`` tree (works from a checkout)."""
    return Path(__file__).resolve().parents[2]


def push_step_script() -> str:
    """The shell script of the action's push step, as CI would run it."""
    action = yaml.safe_load(
        (_repo_root() / "actions" / "git-commit" / "action.yml").read_text()
    )
    steps = action["runs"]["steps"]
    (step,) = [s for s in steps if s.get("name") == PUSH_STEP_NAME]
    return step["run"]


def _git(*args, cwd, check=True):
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=check,
        capture_output=True,
        text=True,
    )


def _commit(path: Path, filename: str, content: str, message: str):
    (path / filename).write_text(content)
    _git("add", filename, cwd=path)
    _git("commit", "-m", message, cwd=path)


@pytest.fixture
def remote_and_clone(tmp_path, monkeypatch):
    """A bare 'origin' with one commit, plus a clone sitting on it.

    Returns ``(origin, clone)``. Git identity is set per-repository and the
    home directory is redirected, so the developer's own config cannot leak in.
    """
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "home" / "gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", os.devnull)
    (tmp_path / "home").mkdir()

    origin = tmp_path / "origin.git"
    _git("init", "--bare", "-b", DEFAULT_BRANCH, str(origin), cwd=tmp_path)

    seed = tmp_path / "seed"
    _git("clone", str(origin), str(seed), cwd=tmp_path)
    _configure(seed)
    _commit(seed, "pyproject.toml", 'version = "0.0.2"\n', "seed")
    _git("push", "-u", "origin", DEFAULT_BRANCH, cwd=seed)

    clone = tmp_path / "clone"
    _git("clone", str(origin), str(clone), cwd=tmp_path)
    _configure(clone)
    return origin, clone


def _configure(path: Path):
    _git("config", "user.email", "ci@example.invalid", cwd=path)
    _git("config", "user.name", "CI", cwd=path)


def run_push_step(clone: Path, *, retries: str = "3", branch: str = ""):
    """Run the action's push step in ``clone``, as the composite action does."""
    return subprocess.run(
        [BASH, "-c", push_step_script()],
        cwd=clone,
        capture_output=True,
        text=True,
        env={**os.environ, "TARGET_BRANCH": branch, "REBASE_RETRIES": retries},
    )


def _land_a_concurrent_merge(origin: Path, tmp_path: Path, *, filename="README.md"):
    """Push an unrelated commit to ``origin``, as a second merge would."""
    other = tmp_path / f"other-{filename}"
    _git("clone", str(origin), str(other), cwd=tmp_path)
    _configure(other)
    _commit(other, filename, "merged while the run was in flight\n", "another merge")
    _git("push", "origin", DEFAULT_BRANCH, cwd=other)


def _subjects(repo: Path, ref: str):
    out = _git("log", "--format=%s", ref, cwd=repo).stdout
    return out.split("\n")[:-1] if out else []


class TestPushBackRecovery:
    """The rejection path added for i2mint/wads#81."""

    def test_unmoved_branch_pushes_on_the_first_attempt(
        self, remote_and_clone, tmp_path
    ):
        """The normal case is unchanged: one push, no fetch, no rebase."""
        origin, clone = remote_and_clone
        _commit(clone, "pyproject.toml", 'version = "0.0.3"\n', "**CI** bump to 0.0.3")

        result = run_push_step(clone)

        assert result.returncode == 0, result.stderr
        assert "Rebasing onto it" not in result.stdout
        assert _subjects(origin, DEFAULT_BRANCH)[0] == "**CI** bump to 0.0.3"

    def test_bump_is_replayed_when_a_merge_lands_during_the_run(
        self, remote_and_clone, tmp_path
    ):
        """The reported failure: the bump lands on top instead of going red."""
        origin, clone = remote_and_clone
        _commit(clone, "pyproject.toml", 'version = "0.0.3"\n', "**CI** bump to 0.0.3")
        _land_a_concurrent_merge(origin, tmp_path)

        result = run_push_step(clone)

        assert result.returncode == 0, result.stdout + result.stderr
        assert "Rebasing onto it and retrying (1/3)" in result.stdout
        # The bump ends up on top of the merge, and nothing is lost.
        assert _subjects(origin, DEFAULT_BRANCH)[:2] == [
            "**CI** bump to 0.0.3",
            "another merge",
        ]

    def test_repeated_races_are_retried_up_to_the_budget(
        self, remote_and_clone, tmp_path
    ):
        """Losing the race twice in a row still lands within the budget."""
        origin, clone = remote_and_clone
        _commit(clone, "pyproject.toml", 'version = "0.0.3"\n', "**CI** bump to 0.0.3")
        _land_a_concurrent_merge(origin, tmp_path, filename="a.md")
        _land_a_concurrent_merge(origin, tmp_path, filename="b.md")

        result = run_push_step(clone)

        assert result.returncode == 0, result.stdout + result.stderr
        assert _subjects(origin, DEFAULT_BRANCH)[0] == "**CI** bump to 0.0.3"

    def test_zero_retries_keeps_the_historical_failure(
        self, remote_and_clone, tmp_path
    ):
        """The retry is a knob, not a law: 0 restores the pre-fix behaviour."""
        origin, clone = remote_and_clone
        _commit(clone, "pyproject.toml", 'version = "0.0.3"\n', "**CI** bump to 0.0.3")
        _land_a_concurrent_merge(origin, tmp_path)

        result = run_push_step(clone, retries="0")

        assert result.returncode == 1
        assert "could not be replayed after 0 rebase attempt(s)" in result.stdout

    def test_conflicting_replay_fails_cleanly(self, remote_and_clone, tmp_path):
        """A genuine conflict aborts the rebase rather than wedging the repo."""
        origin, clone = remote_and_clone
        _commit(clone, "pyproject.toml", 'version = "0.0.3"\n', "**CI** bump to 0.0.3")
        # The concurrent merge rewrites the very line the bump rewrote.
        other = tmp_path / "conflicting"
        _git("clone", str(origin), str(other), cwd=tmp_path)
        _configure(other)
        _commit(other, "pyproject.toml", 'version = "9.9.9"\n', "hand-edited version")
        _git("push", "origin", DEFAULT_BRANCH, cwd=other)

        result = run_push_step(clone)

        assert result.returncode == 1
        assert "conflict with it" in result.stdout
        # No rebase left in progress for a human to trip over.
        assert not (clone / ".git" / "rebase-merge").exists()
        assert not (clone / ".git" / "rebase-apply").exists()

    def test_pushing_another_branch_does_not_rebase_the_checked_out_one(
        self, remote_and_clone, tmp_path
    ):
        """An explicit, non-checked-out `branch` keeps single-attempt behaviour."""
        origin, clone = remote_and_clone
        _git("checkout", "-b", "side", cwd=clone)
        _commit(clone, "side.md", "side work\n", "side commit")
        _land_a_concurrent_merge(origin, tmp_path)

        result = run_push_step(clone, branch=DEFAULT_BRANCH)

        # `main` is not checked out here, so there is nothing safe to replay.
        assert result.returncode == 1
        assert "0 rebase attempt(s)" in result.stdout
        assert _subjects(clone, "side")[0] == "side commit"


class TestPushStepContract:
    """Guards on the shape of the step, for readers of the action file."""

    def test_retry_budget_is_an_input_not_a_literal(self):
        """No magic number: the budget is a documented, overridable input."""
        action = yaml.safe_load(
            (_repo_root() / "actions" / "git-commit" / "action.yml").read_text()
        )
        knob = action["inputs"]["push-rebase-retries"]
        assert knob["description"].strip()
        assert knob["default"] == "3"

    def test_step_reads_its_inputs_from_env(self):
        """Interpolating inputs into bash directly is how quoting bugs start."""
        action = yaml.safe_load(
            (_repo_root() / "actions" / "git-commit" / "action.yml").read_text()
        )
        (step,) = [
            s for s in action["runs"]["steps"] if s.get("name") == PUSH_STEP_NAME
        ]
        assert set(step["env"]) == {"TARGET_BRANCH", "REBASE_RETRIES"}
        assert "${{" not in step["run"]
