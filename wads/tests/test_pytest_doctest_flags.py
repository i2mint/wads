"""The CLI of ``wads/scripts/pytest_doctest_flags.py``, as ``actions/run-tests-uv`` runs it."""

import subprocess
import sys
from pathlib import Path

from wads.scripts.pytest_doctest_flags import DOCTEST_OPTIONFLAGS

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_the_script_prints_nothing_when_the_repo_sets_flags(tmp_path):
    script = REPO_ROOT / "wads" / "scripts" / "pytest_doctest_flags.py"
    run = lambda: subprocess.run(
        [sys.executable, "-I", "-S", str(script), str(tmp_path)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert run() == f"doctest_optionflags={DOCTEST_OPTIONFLAGS}"
    (tmp_path / "pytest.ini").write_text("[pytest]\ndoctest_optionflags = ELLIPSIS\n")
    assert run() == ""
