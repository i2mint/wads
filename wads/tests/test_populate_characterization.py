"""Characterization tests pinning the default ``populate`` output.

These tests snapshot the *exact* files (and their contents) that a bare
``populate`` produces for the default Python-library profile. They exist to
protect the refactor toward a declarative, template-source-driven generator
(see issue #32): the default output must stay byte-identical as the internals
change.

Golden files live in ``wads/tests/data/golden/python_lib/``. If you
*intentionally* change default output, regenerate the goldens and review the
diff in the PR.
"""

import os
import re
import subprocess
import tempfile
from pathlib import Path

import pytest

from wads.populate import populate_pkg_dir

GOLDEN_DIR = Path(__file__).parent / "data" / "golden" / "python_lib"

# Fixed inputs used to generate the goldens. Keep in sync with how the goldens
# were captured.
FIXED_ARGS = dict(
    description="Test package",
    root_url="https://github.com/myorg",
    author="John Doe",
    version="1.2.3",
    verbose=False,
)

# Files whose contents are deterministic given FIXED_ARGS and can be compared
# byte-for-byte against the golden.
EXACT_FILES = [
    "pyproject.toml",
    "README.md",
    ".gitattributes",
    ".gitignore",
    ".github/workflows/ci.yml",
]

# The complete set of files (relative paths) a default populate must create.
EXPECTED_FILESET = {
    ".gitattributes",
    ".gitignore",
    "LICENSE",
    "README.md",
    "pyproject.toml",
    ".github/workflows/ci.yml",
    "mypkg/__init__.py",
}


def _normalize_license(text: str) -> str:
    """Replace the copyright year so the test is stable across calendar years."""
    return re.sub(r"Copyright \(c\) \d{4}", "Copyright (c) YEAR", text)


@pytest.fixture
def populated_pkg(tmp_path):
    """Run a default populate in a temp git repo and yield the package dir."""
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
    populate_pkg_dir(str(pkg_dir), **FIXED_ARGS)
    return pkg_dir


def test_default_populate_creates_exact_fileset(populated_pkg):
    """A bare populate creates exactly the expected set of files (no more, no less)."""
    created = {
        os.path.relpath(os.path.join(root, f), populated_pkg).replace(os.sep, "/")
        for root, _, files in os.walk(populated_pkg)
        for f in files
    }
    # Drop anything under the .git dir (separators normalized to "/" above)
    created = {p for p in created if not p.startswith(".git/")}
    assert created == EXPECTED_FILESET


@pytest.mark.parametrize("rel_path", EXACT_FILES)
def test_default_populate_file_matches_golden(populated_pkg, rel_path):
    """Each deterministic file matches its golden byte-for-byte."""
    produced = (populated_pkg / rel_path).read_text()
    golden = (GOLDEN_DIR / rel_path).read_text()
    assert produced == golden, f"{rel_path} drifted from golden"


def test_default_populate_license_matches_golden(populated_pkg):
    """LICENSE matches the golden once the copyright year is normalized."""
    produced = _normalize_license((populated_pkg / "LICENSE").read_text())
    golden = _normalize_license((GOLDEN_DIR / "LICENSE").read_text())
    assert produced == golden


def test_default_populate_init_is_empty(populated_pkg):
    """The created package ``__init__.py`` is empty (today's behavior)."""
    assert (populated_pkg / "mypkg" / "__init__.py").read_text() == ""


# --- community files (create_community_files=True) -----------------------------

import wads  # noqa: E402

# (target relative path, template path) — community files are verbatim copies.
COMMUNITY_FILES = [
    (".editorconfig", wads.editorconfig_tpl_path),
    (".github/ISSUE_TEMPLATE/bug_report.md", wads.bug_report_tpl_path),
    (".github/ISSUE_TEMPLATE/feature_request.md", wads.feature_request_tpl_path),
    (".github/PULL_REQUEST_TEMPLATE.md", wads.pull_request_template_tpl_path),
    (".github/dependabot.yml", wads.dependabot_tpl_path),
]


@pytest.fixture
def populated_pkg_with_community(tmp_path):
    pkg_dir = tmp_path / "cpkg"
    pkg_dir.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=pkg_dir, check=True)
    subprocess.run(["git", "config", "user.email", "t@e.com"], cwd=pkg_dir, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=pkg_dir, check=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/myorg/cpkg"],
        cwd=pkg_dir,
        check=True,
    )
    populate_pkg_dir(
        str(pkg_dir),
        description="d",
        root_url="https://github.com/myorg",
        author="A",
        version="0.1.0",
        verbose=False,
        create_community_files=True,
    )
    return pkg_dir


@pytest.mark.parametrize("rel_path,tpl_path", COMMUNITY_FILES)
def test_community_files_are_verbatim_template_copies(
    populated_pkg_with_community, rel_path, tpl_path
):
    produced = (populated_pkg_with_community / rel_path).read_text()
    with open(tpl_path) as f:
        assert produced == f.read(), f"{rel_path} drifted from its template"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
