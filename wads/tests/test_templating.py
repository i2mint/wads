"""Tests for the declarative templating engine (wads.templating)."""

import os

import pytest

from wads.templating import (
    Artifact,
    FilesystemTemplateSource,
    GithubTemplateSource,
    apply_placeholders,
    generate,
    make_jinja_env,
    render,
)


# --- rendering -----------------------------------------------------------------


def test_render_custom_delimiters():
    assert render("hi << who >>", {"who": "there"}) == "hi there"


def test_render_does_not_touch_github_actions_expressions():
    """The custom delimiters must leave ${{ ... }} untouched."""
    content = "token: ${{ secrets.FOO }} and << name >>"
    assert render(content, {"name": "x"}) == "token: ${{ secrets.FOO }} and x"


def test_render_keeps_trailing_newline():
    assert render("line\n", {}) == "line\n"


def test_render_strict_undefined_raises():
    import jinja2

    with pytest.raises(jinja2.UndefinedError):
        render("<< missing >>", {})


def test_apply_placeholders():
    out = apply_placeholders("#A#-#B#", {"#A#": "1", "#B#": "2"})
    assert out == "1-2"


# --- template sources ----------------------------------------------------------


def test_dict_is_a_template_source():
    """A plain dict is a valid template source (issue #3 in-memory mapping)."""
    source = {"f.txt": "<< v >>"}
    art = Artifact.from_jinja("f.txt", "f.txt", source)
    assert art.content({"v": "ok"}) == "ok"


def test_filesystem_template_source(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "a.txt").write_text("A")
    (tmp_path / "sub" / "b.txt").write_text("B")
    src = FilesystemTemplateSource(str(tmp_path))
    assert src["a.txt"] == "A"
    assert src["sub/b.txt"] == "B"
    assert set(src) == {"a.txt", "sub/b.txt"}
    assert len(src) == 2
    with pytest.raises(KeyError):
        src["nope.txt"]


def test_github_template_source_url_construction():
    """URL building is pure; we don't hit the network here."""
    src = GithubTemplateSource("i2mint/wads", ref="master", subdir="wads/data")
    assert (
        src._raw_url("pyproject_toml_tpl.toml")
        == "https://raw.githubusercontent.com/i2mint/wads/master/"
        "wads/data/pyproject_toml_tpl.toml"
    )
    src2 = GithubTemplateSource("o/r")
    assert src2._raw_url("x") == "https://raw.githubusercontent.com/o/r/master/x"


# --- artifacts + generate ------------------------------------------------------


def test_generate_writes_fileset(tmp_path):
    source = {
        "gitignore": "*.pyc\n",
        "ci.yml": "name: << name >>\n",
        "legacy": "proj=#NAME#",
    }
    artifacts = [
        Artifact.from_copy(".gitignore", "gitignore", source),
        Artifact.from_jinja(".github/workflows/ci.yml", "ci.yml", source),
        Artifact.from_placeholder(
            "legacy.txt", "legacy", source, lambda ctx: {"#NAME#": ctx["name"]}
        ),
    ]
    result = generate(str(tmp_path), artifacts, {"name": "demo"})
    assert set(result.added) == {
        ".gitignore",
        ".github/workflows/ci.yml",
        "legacy.txt",
    }
    assert (tmp_path / ".gitignore").read_text() == "*.pyc\n"
    assert (tmp_path / ".github/workflows/ci.yml").read_text() == "name: demo\n"
    assert (tmp_path / "legacy.txt").read_text() == "proj=demo"


def test_generate_skips_existing_unless_overwrite(tmp_path):
    (tmp_path / "keep.txt").write_text("ORIGINAL")
    source = {"k": "NEW"}
    arts = [Artifact.from_copy("keep.txt", "k", source)]

    result = generate(str(tmp_path), arts, {})
    assert result.skipped == ["keep.txt"]
    assert (tmp_path / "keep.txt").read_text() == "ORIGINAL"

    result = generate(str(tmp_path), arts, {}, overwrite="keep.txt")
    assert result.added == ["keep.txt"]
    assert (tmp_path / "keep.txt").read_text() == "NEW"


def test_generate_respects_when_condition(tmp_path):
    source = {"x": "X"}
    arts = [
        Artifact.from_copy("yes.txt", "x", source, when=lambda ctx: True),
        Artifact.from_copy("no.txt", "x", source, when=lambda ctx: False),
    ]
    result = generate(str(tmp_path), arts, {})
    assert result.added == ["yes.txt"]
    assert not (tmp_path / "no.txt").exists()


def test_generate_content_none_skips(tmp_path):
    arts = [Artifact("maybe.txt", lambda ctx: None)]
    result = generate(str(tmp_path), arts, {})
    assert result.added == []
    assert not (tmp_path / "maybe.txt").exists()


def test_generate_reports_errors_without_aborting(tmp_path):
    def boom(ctx):
        raise ValueError("nope")

    source = {"x": "X"}
    arts = [
        Artifact("bad.txt", boom),
        Artifact.from_copy("good.txt", "x", source),
    ]
    result = generate(str(tmp_path), arts, {})
    assert result.added == ["good.txt"]
    assert result.errored and result.errored[0][0] == "bad.txt"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
