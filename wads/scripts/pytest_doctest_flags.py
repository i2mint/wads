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
``actions/run-tests-uv`` and, via :data:`DOCTEST_OPTIONFLAGS`, by ``wads ci-local``.
"""

import re
import sys
from pathlib import Path
from typing import Iterable

DOCTEST_OPTIONFLAGS = "ELLIPSIS IGNORE_EXCEPTION_DETAIL"
# The files pytest reads its ini options from.
PYTEST_CONFIG_FILES = ("pytest.ini", "pyproject.toml", "tox.ini", "setup.cfg")
_KEY = re.compile(r"^\s*doctest_optionflags\s*[=:]", re.MULTILINE)


def repo_sets_doctest_optionflags(
    repo: str = ".", *, config_files: Iterable[str] = PYTEST_CONFIG_FILES
) -> bool:
    """Whether the repo's pytest config sets ``doctest_optionflags``.

    A text match on the key (stdlib only, so it runs under any CI interpreter).

    >>> import tempfile
    >>> with tempfile.TemporaryDirectory() as d:
    ...     repo_sets_doctest_optionflags(d)
    False
    >>> with tempfile.TemporaryDirectory() as d:
    ...     _ = Path(d, "pyproject.toml").write_text(
    ...         '[tool.pytest.ini_options]\\ndoctest_optionflags = ["ELLIPSIS"]\\n')
    ...     repo_sets_doctest_optionflags(d)
    True
    """
    for name in config_files:
        path = Path(repo) / name
        if path.is_file() and _KEY.search(
            path.read_text(encoding="utf-8", errors="replace")
        ):
            return True
    return False


def doctest_optionflags_arg(*, repo_sets_flags: bool) -> str:
    """The ``-o`` value to pass, or ``''`` when the repo's own config wins.

    >>> doctest_optionflags_arg(repo_sets_flags=False)
    'doctest_optionflags=ELLIPSIS IGNORE_EXCEPTION_DETAIL'
    >>> doctest_optionflags_arg(repo_sets_flags=True)
    ''
    """
    return "" if repo_sets_flags else f"doctest_optionflags={DOCTEST_OPTIONFLAGS}"


def main(argv: list[str] = sys.argv[1:]) -> int:
    repo = argv[0] if argv else "."
    print(doctest_optionflags_arg(repo_sets_flags=repo_sets_doctest_optionflags(repo)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
