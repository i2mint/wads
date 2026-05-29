"""Test utilities for << name >>.

Provides access to files under ``tests/data`` so tests can load fixtures by
name. Pattern adapted from common i2mint test layouts.

>>> # data_path('example.json')  # -> absolute path under tests/data
"""

import os

_TESTS_DIR = os.path.dirname(__file__)
_DATA_DIR = os.path.join(_TESTS_DIR, "data")


def data_path(*relpath: str) -> str:
    """Absolute path to a file under ``tests/data``."""
    return os.path.join(_DATA_DIR, *relpath)


def data_bytes(*relpath: str) -> bytes:
    """Read bytes of a file under ``tests/data``."""
    with open(data_path(*relpath), "rb") as f:
        return f.read()
