#!/usr/bin/env python3
"""Print the ``-o doctest_optionflags=...`` pytest argument CI should add, if any.

CI used to pass ``-o doctest_optionflags='ELLIPSIS IGNORE_EXCEPTION_DETAIL'``
unconditionally, which overrides the repo's own pytest configuration (the wads
template ships ``["NORMALIZE_WHITESPACE", "ELLIPSIS"]``), so doctests could pass
locally and fail in CI or the reverse. This script is the single source of the
default flags and of the rule: pass the default only when the repo's pytest config
(``pytest.ini``, ``pyproject.toml``, ``tox.ini`` or ``setup.cfg``) does not set
``doctest_optionflags``. Prints the argument (``doctest_optionflags=...``) or
nothing; stdlib only. Used by
``actions/run-tests-uv`` and, via :data:`DOCTEST_OPTIONFLAGS`, by ``wads ci-local`` (which imports the functions).
"""

import configparser
import re
import sys
from pathlib import Path
from typing import Optional

DOCTEST_OPTIONFLAGS = "ELLIPSIS IGNORE_EXCEPTION_DETAIL"
_KEY = "doctest_optionflags"
# pytest's config-file precedence: (file, section holding its ini options). pytest.ini
# always counts when present; the others only when they have their section.
_INI_FILES = (
    ("pytest.ini", "pytest"),
    ("tox.ini", "pytest"),
    ("setup.cfg", "tool:pytest"),
)
_PYPROJECT_SECTION = re.compile(
    r"^\[tool\.pytest\.ini_options\][^\n]*\n(.*?)(?=^\[|\Z)", re.MULTILINE | re.DOTALL
)
_PYPROJECT_KEY = re.compile(rf"^\s*{_KEY}\s*=", re.MULTILINE)


def _ini_sets_flags(path: Path, section: str, *, always: bool) -> Optional[bool]:
    """``None`` when pytest would not use this file; else whether it sets the flags."""
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read_string(path.read_text(encoding="utf-8", errors="replace"))
    except configparser.Error:
        return None
    if not parser.has_section(section):
        return False if always else None
    return parser.has_option(section, _KEY)


def _pyproject_sets_flags(path: Path) -> Optional[bool]:
    match = _PYPROJECT_SECTION.search(
        path.read_text(encoding="utf-8", errors="replace")
    )
    return None if match is None else bool(_PYPROJECT_KEY.search(match.group(1)))


def repo_sets_doctest_optionflags(repo: str = ".") -> bool:
    """Whether the pytest config file pytest itself would pick sets ``doctest_optionflags``.

    Mirrors pytest's precedence (``pytest.ini``, ``pyproject.toml``, ``tox.ini``,
    ``setup.cfg``; the last three only with their pytest section), stdlib only so it
    runs under any CI interpreter.

    >>> import tempfile
    >>> def check(**files):
    ...     with tempfile.TemporaryDirectory() as d:
    ...         for name, text in files.items():
    ...             Path(d, name.replace("_", ".", 1) if name.startswith("pytest_") else name).write_text(text)
    ...         return repo_sets_doctest_optionflags(d)
    >>> check()
    False
    >>> py = '[tool.pytest.ini_options]\\ndoctest_optionflags = ["ELLIPSIS"]\\n'
    >>> check(**{"pyproject.toml": py})
    True
    >>> check(**{"pyproject.toml": "[tool.pytest.ini_options]\\nx = 1\\n", "setup.cfg": "[tool:pytest]\\ndoctest_optionflags = ELLIPSIS\\n"})
    False
    """
    root = Path(repo)
    if (path := root / "pytest.ini").is_file():
        return bool(_ini_sets_flags(path, "pytest", always=True))
    if (path := root / "pyproject.toml").is_file():
        if (found := _pyproject_sets_flags(path)) is not None:
            return found
    for name, section in _INI_FILES[1:]:
        if (path := root / name).is_file():
            if (found := _ini_sets_flags(path, section, always=False)) is not None:
                return found
    return False


def doctest_optionflags_arg(repo: Optional[str] = None) -> str:
    """The ``-o`` value to pass, or ``''`` when ``repo``'s own pytest config wins.

    ``repo=None`` means "do not look": the default flags are returned.

    >>> doctest_optionflags_arg()
    'doctest_optionflags=ELLIPSIS IGNORE_EXCEPTION_DETAIL'
    """
    if repo is not None and repo_sets_doctest_optionflags(repo):
        return ""
    return f"{_KEY}={DOCTEST_OPTIONFLAGS}"


def main(argv: Optional[list[str]] = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    print(doctest_optionflags_arg(argv[0] if argv else "."))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
