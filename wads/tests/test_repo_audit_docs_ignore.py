"""Tests for the legacy ``docs/*`` .gitignore finding in repo_audit."""

from wads.repo_audit import _docs_ignore_lines


def test_flags_whole_docs_ignores():
    text = "*.pyc\ndocs/*\n/docs\ndocs/\n"
    assert _docs_ignore_lines(text) == ["docs/*", "/docs", "docs/"]


def test_keeps_docs_build():
    assert _docs_ignore_lines("docs/_build/\n*.pyc\n") == []
