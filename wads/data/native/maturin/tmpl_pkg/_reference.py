"""The pure-Python implementation, kept as the oracle for differential tests.

In a port this is the original code, frozen verbatim. It is not exported and
must not be "improved": its behaviour, including the exceptions it raises, is
the contract the Rust core is tested against.
"""


def hamming(a: str, b: str) -> int:
    """Count the positions at which ``a`` and ``b`` hold different characters."""
    if len(a) != len(b):
        msg = f"sequences differ in length: {len(a)} != {len(b)}"
        raise ValueError(msg)
    return sum(x != y for x, y in zip(a, b))
