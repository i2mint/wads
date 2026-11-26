"""populate takes the owner from the git remote when no root_url is given (#247)."""

import subprocess

from wads.populate import _root_url_from_git_remote


def test_root_url_from_remote(tmp_path):
    subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "remote", "add", "origin",
         "git@github.com:neworg/pkg.git"],
        check=True,
    )
    assert _root_url_from_git_remote(tmp_path) == {
        "root_url": "https://github.com/neworg/"
    }


def test_no_remote_gives_nothing(tmp_path):
    subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True)
    assert _root_url_from_git_remote(tmp_path) == {}
