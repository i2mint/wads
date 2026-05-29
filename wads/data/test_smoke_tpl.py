"""Smoke tests for << name >>."""


def test_import():
    """The package imports without error."""
    import << name >>  # noqa: F401


def test_has_version_or_imports():
    """A trivial sanity check; replace with real tests."""
    import << name >> as _pkg

    assert _pkg is not None
