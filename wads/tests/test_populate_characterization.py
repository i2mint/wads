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
        os.path.relpath(os.path.join(root, f), populated_pkg)
        for root, _, files in os.walk(populated_pkg)
        for f in files
        if ".git/" not in os.path.join(root, f) and not root.endswith("/.git")
    }
    # Drop anything under the .git dir
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
