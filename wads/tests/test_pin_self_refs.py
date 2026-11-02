"""The release tag pins a repo's references to its own actions (issue #170).

A caller pinned to ``uv-ci.yml@<tag>`` still ran every ``i2mint/wads/actions/*@master``
at the branch tip. The publish job now tags a commit, on top of the built bump, whose
workflow and action files say ``@<version>``; the branch keeps floating refs, and a
repo with no self-references tags the built commit unchanged.
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from wads.scripts.pin_self_refs import pin_self_refs, pinned_release_commit
from wads.tests.test_git_commit_push_retry import _commit, _git

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = """\
jobs:
  a:
    steps:
      - uses: i2mint/wads/actions/read-ci-config@master
      - uses: "i2mint/wads/actions/install-deps-uv@master"
      - uses: i2mint/isee/actions/bump-version-number@master
"""

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")


@pytest.mark.parametrize(
    "line, expected",
    [
        ("uses: i2mint/wads/actions/x@master", "uses: i2mint/wads/actions/x@0.3.0"),
        ("uses: 'i2mint/wads/actions/x@master'", "uses: 'i2mint/wads/actions/x@0.3.0'"),
        ("uses: i2mint/wads/actions/x@main", "uses: i2mint/wads/actions/x@main"),
        ("uses: i2mint/wadsx/actions/x@master", "uses: i2mint/wadsx/actions/x@master"),
        ("uses: i2mint/wads/actions/x@0.2.9", "uses: i2mint/wads/actions/x@0.2.9"),
        ("# see i2mint/wads/actions/x@master", "# see i2mint/wads/actions/x@master"),
    ],
)
def test_only_this_repos_uses_lines_on_the_branch_are_pinned(line, expected):
    assert pin_self_refs(
        line, repo="i2mint/wads", branch="master", version="0.3.0"
    ) == (expected)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
    root = tmp_path / "repo"
    _git("init", "-q", "-b", "master", str(root), cwd=tmp_path)
    _git("config", "user.email", "ci@example.invalid", cwd=root)
    _git("config", "user.name", "CI", cwd=root)
    (root / ".github" / "workflows").mkdir(parents=True)
    return root


def _pin(repo, ref="HEAD"):
    return pinned_release_commit(
        repo="i2mint/wads",
        branch="master",
        version="0.3.0",
        ref=ref,
        message="pin",
        cwd=repo,
    )


@needs_git
def test_self_refs_are_pinned_in_a_child_commit_only(repo):
    (repo / ".github" / "workflows" / "uv-ci.yml").write_text(WORKFLOW)
    _git("add", ".github", cwd=repo)
    _commit(repo, "pyproject.toml", 'version = "0.3.0"\n', "**CI** bump")
    built = _git("rev-parse", "HEAD", cwd=repo).stdout.strip()

    pinned = _pin(repo)

    assert pinned != built
    assert _git("rev-parse", f"{pinned}^", cwd=repo).stdout.strip() == built
    tagged = _git("show", f"{pinned}:.github/workflows/uv-ci.yml", cwd=repo).stdout
    assert "read-ci-config@0.3.0" in tagged and "install-deps-uv@0.3.0" in tagged
    assert "bump-version-number@master" in tagged  # another repo: untouched
    # The caller's checkout, branch and worktree list are untouched.
    assert _git("rev-parse", "HEAD", cwd=repo).stdout.strip() == built
    assert "@master" in (repo / ".github/workflows/uv-ci.yml").read_text()
    assert _git("status", "--porcelain", cwd=repo).stdout == ""
    assert len(_git("worktree", "list", cwd=repo).stdout.splitlines()) == 1


@needs_git
def test_without_self_refs_the_built_commit_is_returned(repo):
    (repo / ".github" / "workflows" / "ci.yml").write_text(
        "jobs:\n  a:\n    uses: i2mint/wads/.github/workflows/uv-ci.yml@master\n"
    )
    _git("add", ".github", cwd=repo)
    _commit(repo, "x.txt", "x", "built")
    built = _git("rev-parse", "HEAD", cwd=repo).stdout.strip()
    # This repo is not i2mint/wads in this call's eyes:
    assert (
        pinned_release_commit(
            repo="someone/else",
            branch="master",
            version="1.0.0",
            ref=built,
            message="pin",
            cwd=repo,
        )
        == built
    )


@needs_git
def test_the_script_writes_its_output(repo, tmp_path):
    (repo / ".github" / "workflows" / "uv-ci.yml").write_text(WORKFLOW)
    _git("add", ".github", cwd=repo)
    _commit(repo, "x.txt", "x", "built")
    out = tmp_path / "github_output"
    script = ROOT / "wads" / "scripts" / "pin_self_refs.py"
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            str(script),
            "--repo",
            "i2mint/wads",
            "--branch",
            "master",
            "--version",
            "0.3.0",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        env={
            "GITHUB_OUTPUT": str(out),
            "PATH": "/usr/bin:/bin:/usr/local/bin",
            "GIT_CONFIG_GLOBAL": str(tmp_path / "gitconfig"),
        },
    )
    assert result.returncode == 0, result.stderr
    sha = out.read_text().strip().removeprefix("commit-sha=")
    built = _git("rev-parse", "HEAD", cwd=repo).stdout.strip()
    assert (
        sha != built and _git("rev-parse", f"{sha}^", cwd=repo).stdout.strip() == built
    )


def test_the_action_runs_the_script_from_its_own_checkout():
    action = yaml.safe_load(
        (ROOT / "actions" / "pin-self-refs" / "action.yml").read_text()
    )
    (step,) = action["runs"]["steps"]
    assert (
        'python3 -I "$GITHUB_ACTION_PATH/../../wads/scripts/pin_self_refs.py"'
        in (step["run"])
    )
    assert action["outputs"]["commit-sha"]["value"] == (
        f"${{{{ steps.{step['id']}.outputs.commit-sha }}}}"
    )
