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


def test_only_the_config_file_pytest_would_use_counts(tmp_path):
    from wads.scripts.pytest_doctest_flags import repo_sets_doctest_optionflags

    flags = "doctest_optionflags = ELLIPSIS\n"
    (tmp_path / "setup.cfg").write_text("[tool:pytest]\n" + flags)
    assert repo_sets_doctest_optionflags(str(tmp_path))
    # pyproject.toml with a pytest section outranks setup.cfg, so setup.cfg is ignored
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\ntestpaths = []\n"
    )
    assert not repo_sets_doctest_optionflags(str(tmp_path))


def test_the_key_under_another_section_does_not_count(tmp_path):
    from wads.scripts.pytest_doctest_flags import repo_sets_doctest_optionflags

    (tmp_path / "tox.ini").write_text(
        "[flake8]\ndoctest_optionflags = x\n[pytest]\nq = 1\n"
    )
    assert not repo_sets_doctest_optionflags(str(tmp_path))
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\ntestpaths = []\n[tool.other]\ndoctest_optionflags = "x"\n'
    )
    assert not repo_sets_doctest_optionflags(str(tmp_path))


def test_pytest_args_are_honoured(tmp_path):
    from wads.scripts.pytest_doctest_flags import doctest_optionflags_arg

    default = f"doctest_optionflags={DOCTEST_OPTIONFLAGS}"
    repo = str(tmp_path)
    # an explicit -o in the extra args wins over everything
    assert doctest_optionflags_arg(repo, pytest_args="-o doctest_optionflags=ELLIPSIS") == ""
    assert doctest_optionflags_arg(repo, pytest_args="-odoctest_optionflags=ELLIPSIS") == ""
    # -c names the one config file that counts
    (tmp_path / "other.ini").write_text("[pytest]\ndoctest_optionflags = ELLIPSIS\n")
    assert doctest_optionflags_arg(repo, pytest_args="-x -c other.ini") == ""
    assert doctest_optionflags_arg(repo, pytest_args="--config-file=missing.ini") == default
    # --rootdir moves the search
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "pytest.ini").write_text("[pytest]\ndoctest_optionflags = ELLIPSIS\n")
    assert doctest_optionflags_arg(repo, pytest_args="--rootdir sub") == ""
    assert doctest_optionflags_arg(repo, pytest_args="-x") == default


def test_the_cli_takes_pytest_args(tmp_path):
    script = REPO_ROOT / "wads" / "scripts" / "pytest_doctest_flags.py"
    run = subprocess.run(
        [sys.executable, "-I", "-S", str(script), str(tmp_path), "--pytest-args", "-o doctest_optionflags=X"],
        capture_output=True, text=True, check=True,
    )
    assert run.stdout.strip() == ""


def test_every_pytest_runner_action_uses_the_shared_script():
    for name in ("run-tests-uv", "run-tests", "windows-tests"):
        text = (REPO_ROOT / "actions" / name / "action.yml").read_text()
        assert "pytest_doctest_flags.py" in text, name
        assert 'doctest_optionflags="ELLIPSIS' not in text, name
