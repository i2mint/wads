"""The public API: these tests must pass unchanged whichever backend is built."""

import inspect

import pytest

import tmpl_pkg


def test_hamming():
    assert tmpl_pkg.hamming("karolin", "kathrin") == 3


def test_length_mismatch_raises_value_error():
    with pytest.raises(ValueError, match="differ in length"):
        tmpl_pkg.hamming("ab", "a")


def test_native_extension_is_loaded():
    """Fails on a silent fallback or a stale build instead of passing."""
    from tmpl_pkg import _core

    assert _core.__file__.endswith((".so", ".pyd")), _core.__file__


def test_core_signature_matches_stub():
    from tmpl_pkg import _core

    assert str(inspect.signature(_core.hamming)) == "(a, b, /)"
