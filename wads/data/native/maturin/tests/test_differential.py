"""Differential tests: the Rust core against the frozen pure-Python reference.

PLACEHOLDER: one property per ported function. Generate the inputs where Rust
and Python differ (non-ASCII text, empty input, huge integers, NaN and signed
zero, ...) and compare results AND exception types. The full method and more
templates are in the pyo3-port skill.
"""

from hypothesis import given
from hypothesis import strategies as st

from tmpl_pkg import _core, _reference

# Rust `&str` extraction rejects lone surrogates, which Python strings allow.
# Excluding them is a decision about the contract: record it, do not hide it.
TEXT = st.text(alphabet=st.characters(exclude_categories=("Cs",)), max_size=20)


def _outcome(f, *args):
    try:
        return ("ok", f(*args))
    except Exception as e:  # noqa: BLE001 -- exception *types* are the public contract
        return ("err", type(e))


@given(a=TEXT, b=TEXT)
def test_hamming_matches_reference(a, b):
    assert _outcome(_core.hamming, a, b) == _outcome(_reference.hamming, a, b)


@given(a=TEXT)
def test_hamming_matches_reference_on_equal_lengths(a):
    b = a[::-1]
    assert _outcome(_core.hamming, a, b) == _outcome(_reference.hamming, a, b)
