"""Tests for the opt-in tests/-folder overlay (issue #4)."""

import subprocess

import pytest

from wads.profiles import apply_tests_overlay, make_tests_overlay_artifacts
from wads.populate import populate_pkg_dir


def test_make_tests_overlay_artifacts_embed_name():
    arts = make_tests_overlay_artifacts("mypkg")
    targets = {a.target for a in arts}
    assert "tests/__init__.py" in targets
    assert "tests/test_mypkg.py" in targets
    assert "tests/util.py" in targets


def test_apply_tests_overlay_writes_smoke_test(tmp_path):
    result = apply_tests_overlay(str(tmp_path), project_name="mypkg")
    assert "tests/test_mypkg.py" in result.added
    smoke = (tmp_path / "tests" / "test_mypkg.py").read_text()
    # Jinja delimiters rendered, package name injected
    assert "import mypkg" in smoke
    assert "<<" not in smoke and ">>" not in smoke
    # data accessor present
    assert (tmp_path / "tests" / "util.py").exists()
    assert "tests/data" in (tmp_path / "tests" / "util.py").read_text()


def test_apply_tests_overlay_without_data_util(tmp_path):
    apply_tests_overlay(str(tmp_path), project_name="p", with_data_util=False)
    assert not (tmp_path / "tests" / "util.py").exists()
    assert (tmp_path / "tests" / "test_p.py").exists()


def test_smoke_test_is_valid_python(tmp_path):
    apply_tests_overlay(str(tmp_path), project_name="somepkg")
    import ast

    ast.parse((tmp_path / "tests" / "test_somepkg.py").read_text())
    ast.parse((tmp_path / "tests" / "util.py").read_text())


def test_populate_create_tests_flag(tmp_path):
    pkg_dir = tmp_path / "mypkg"
    pkg_dir.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=pkg_dir, check=True)
    subprocess.run(["git", "config", "user.email", "t@e.com"], cwd=pkg_dir, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=pkg_dir, check=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/myorg/mypkg"],
        cwd=pkg_dir,
        check=True,
    )
    populate_pkg_dir(
        str(pkg_dir),
        description="d",
        root_url="https://github.com/myorg",
        version="0.1.0",
        verbose=False,
        create_tests=True,
    )
    assert (pkg_dir / "tests" / "__init__.py").exists()
    assert (pkg_dir / "tests" / "test_mypkg.py").exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
