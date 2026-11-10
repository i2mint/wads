"""tmpl_pkg: TODO one line on what the package does (Rust core, Python facade).

This module is the public API and the single source of truth for signatures,
defaults and docstrings. The compiled ``tmpl_pkg._core`` takes every argument
explicitly; nothing outside this package should import it.

>>> hamming("karolin", "kathrin")
3
"""

from importlib.metadata import version as _version

from tmpl_pkg import _core

# pyproject.toml [project].version is the SSOT; the Cargo crates stay at 0.0.0.
__version__ = _version("tmpl_pkg")

__all__ = ["hamming"]


def hamming(a: str, b: str) -> int:
    """Count the positions at which ``a`` and ``b`` hold different characters.

    Raises ``ValueError`` when the strings differ in length.

    >>> hamming("abc", "abd")
    1
    """
    return _core.hamming(a, b)
