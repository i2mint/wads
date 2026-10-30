"""The setup job warns when ``testpaths`` hides the package's doctests (i2mint/wads#56)."""

import subprocess
import sys
from pathlib import Path

from wads.ci_config import doctests_hidden_by_testpaths

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "read_ci_config.py"


def _repo(tmp_path, testpaths, *, doctest=True):
    pkg = tmp_path / "my_pkg"
    pkg.mkdir()
    (pkg / "m.py").write_text('"""\n>>> 1\n1\n"""\n' if doctest else "x = 1\n")
    (tmp_path / "tests").mkdir()
    toml = f'[project]\nname = "my-pkg"\nversion = "0.0.1"\n'
    if testpaths is not None:
        toml += f"[tool.pytest.ini_options]\ntestpaths = {testpaths!r}\n".replace(
            "'", '"'
        )
    (tmp_path / "pyproject.toml").write_text(toml)
    return tmp_path


def _warnings(repo):
    out = subprocess.run(
        [sys.executable, str(SCRIPT), str(repo)], capture_output=True, text=True
    )
    assert out.returncode == 0, out.stderr
    return [l for l in out.stdout.splitlines() if "Doctests not collected" in l]


def test_warns_when_testpaths_excludes_package_with_doctests(tmp_path):
    assert len(_warnings(_repo(tmp_path, ["tests"]))) == 1


def test_silent_when_package_is_collected_or_unset_or_no_doctests(tmp_path_factory):
    for testpaths, doctest in [
        (["my_pkg"], True),
        ([""], True),
        (None, True),
        (["tests"], False),
    ]:
        repo = _repo(tmp_path_factory.mktemp("r"), testpaths, doctest=doctest)
        assert _warnings(repo) == [], (testpaths, doctest)


def test_testpath_inside_package_does_not_cover_it(tmp_path):
    repo = _repo(tmp_path, ["my_pkg/tests"])
    assert doctests_hidden_by_testpaths(
        {
            "project": {"name": "my-pkg"},
            "tool": {"pytest": {"ini_options": {"testpaths": ["my_pkg/tests"]}}},
        },
        repo,
    ) == ["my_pkg"]
