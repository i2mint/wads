"""repo_audit flags URLs whose owner differs from the git remote's (#247)."""

import subprocess

from wads import repo_audit as ra


def _repo(tmp_path, remote, urls, readme=""):
    subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "remote", "add", "origin", remote], check=True
    )
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "pkg"\nversion = "0.1.0"\n[project.urls]\n' + urls
    )
    (tmp_path / "README.md").write_text(readme)
    return tmp_path


def _summaries(tmp_path):
    return [f["summary"] for f in ra._audit(tmp_path, network=False).findings]


def test_transferred_repo_urls_are_flagged(tmp_path):
    repo = _repo(
        tmp_path,
        "git@github.com:neworg/pkg.git",
        'Homepage = "https://github.com/olduser/pkg"\n',
        "[docs](https://olduser.github.io/pkg/)",
    )
    s = _summaries(repo)
    assert any("[project.urls]" in x and "olduser" in x for x in s)
    assert any("README.md" in x for x in s)


def test_matching_owner_and_unrelated_links_are_quiet(tmp_path):
    repo = _repo(
        tmp_path,
        "https://github.com/neworg/pkg.git",
        'Homepage = "https://github.com/NewOrg/pkg"\n',
        "see https://github.com/other/unrelated",
    )
    assert not any("owner other" in x for x in _summaries(repo))


def test_badges_codecov_raw_and_sentence_end():
    text = (
        "![](https://img.shields.io/github/license/old/pkg) "
        "https://codecov.io/gh/old/pkg https://raw.githubusercontent.com/old/pkg/x "
        "see github.com/Old/pkg. mygithub.com/old/pkg"
    )
    found = ra.owner_mismatched_urls(text, "new/pkg")
    assert len(found) == 4 and not any(f.startswith("mygithub") for f in found)


def test_long_letter_run_is_fast():
    import time

    t = time.time()
    ra.owner_mismatched_urls("A" * 40000, "new/pkg")
    assert time.time() - t < 1
