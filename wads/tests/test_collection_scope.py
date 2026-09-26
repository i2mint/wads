"""wads's own CI collects its package doctests, not only ``wads/tests``.

The ``run-tests-uv`` action runs ``pytest --doctest-modules`` with no path, so
``[tool.pytest.ini_options].testpaths`` alone decides what is collected
(i2mint/wads#56). With ``testpaths = ["wads/tests"]`` every doctest in the
package was skipped in CI while it stayed green, and two of them had drifted
into failing. These tests pin the scope so it cannot silently shrink again.
"""

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.skipif(
    not (REPO_ROOT / "pyproject.toml").is_file(),
    reason="needs a source checkout (runs pytest's collection on the repo)",
)


@pytest.fixture(scope="module")
def collected_ids():
    """Node ids CI's pathless ``pytest --doctest-modules`` would collect."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "--doctest-modules",
         "-p", "no:cacheprovider"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-3000:]
    return [line for line in result.stdout.splitlines() if "::" in line]


def test_package_doctests_are_collected(collected_ids):
    assert "wads/licence_check.py::wads.licence_check.LicencePolicy.from_mapping" in (
        collected_ids
    )


def test_test_modules_are_still_collected(collected_ids):
    assert any(i.startswith("wads/tests/test_licence_check.py::") for i in collected_ids)


def test_templates_under_data_are_not_collected(collected_ids):
    """``wads/data`` holds templates (e.g. ``test_smoke_tpl.py``), not Python."""
    assert not [i for i in collected_ids if i.startswith("wads/data/")]
