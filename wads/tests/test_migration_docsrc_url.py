"""wads-migrate: url from root_url / git remote, and stale docsrc detection (#259)."""

import subprocess

from wads.migration import (
    git_remote_https_url,
    migrate_setuptools_to_hatching,
    stale_docsrc,
)

_META = {"name": "p", "version": "0.1.0", "description": "d", "license": "MIT"}


def _git(d, *args):
    subprocess.run(["git", "-C", str(d), *args], check=True, capture_output=True)


def test_root_url_is_an_org_root_so_project_url_is_root_slash_name():
    cfg = {"metadata": {**_META, "root_url": "https://github.com/u/"}}
    assert 'Homepage = "https://github.com/u/p"' in migrate_setuptools_to_hatching(cfg)


def test_defaults_url_beats_root_url():
    cfg = {"metadata": {**_META, "root_url": "https://github.com/org/"}}
    out = migrate_setuptools_to_hatching(cfg, defaults={"url": "https://x.io/p"})
    assert "https://x.io/p" in out and "github.com/org" not in out


def test_remote_credentials_and_port_are_dropped(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "remote", "add", "origin", "https://tok:SECRET@github.com/u/p.git")
    assert git_remote_https_url(tmp_path) == "https://github.com/u/p"
    _git(tmp_path, "remote", "set-url", "origin", "ssh://git@github.com:22/u/p.git")
    assert git_remote_https_url(tmp_path) == "https://github.com/u/p"


def test_parent_repo_remote_is_not_used(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "remote", "add", "origin", "git@github.com:u/parent.git")
    sub = tmp_path / "sub"
    sub.mkdir()
    assert git_remote_https_url(sub) is None


def test_url_falls_back_to_git_remote(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "remote", "add", "origin", "git@github.com:u/p.git")
    assert git_remote_https_url(tmp_path) == "https://github.com/u/p"
    out = migrate_setuptools_to_hatching({"metadata": _META}, project_dir=tmp_path)
    assert "https://github.com/u/p" in out


def test_no_remote_still_reports_missing_url(tmp_path):
    import pytest

    from wads.migration import MigrationError

    _git(tmp_path, "init", "-q")
    with pytest.raises(MigrationError, match="url"):
        migrate_setuptools_to_hatching({"metadata": _META}, project_dir=tmp_path)


def test_stale_docsrc(tmp_path):
    assert stale_docsrc(tmp_path) is None
    (tmp_path / "docsrc").mkdir()
    (tmp_path / "docsrc" / "conf.py").write_text(
        "p = Path(__file__).parent.parent / 'setup.cfg'\n"
    )
    assert stale_docsrc(tmp_path) == tmp_path / "docsrc"
    (tmp_path / "docsrc" / "conf.py").write_text('"""reads (setup.cfg) lazily"""\n')
    assert stale_docsrc(tmp_path) is None
    (tmp_path / "docsrc" / "conf.py").write_text("project = 'p'\n")
    assert stale_docsrc(tmp_path) is None
