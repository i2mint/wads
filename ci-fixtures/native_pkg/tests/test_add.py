"""The fixture's extension loads and computes."""

from wads_native_fixture import add


def test_add():
    assert add(2, 3) == 5
