#!/usr/bin/env python3
"""Print the ``cargo test`` arguments for a maturin package (issue #166).

Usage (as the rust-checks action runs it)::

    cargo metadata --manifest-path M --no-deps --format-version 1 \\
        | python3 -I cargo_test_args.py M

``M`` is the binding crate's ``Cargo.toml`` (``[tool.maturin].manifest-path``, resolved
by the setup job). Prints the arguments on one line, or nothing when there is no
pure-Rust crate to test. Standard library only: it runs from the action's checkout
without installing wads.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # also under `-m`
from _checkout_import import load_wads_module  # noqa: E402


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    binding = argv[0] if argv else "Cargo.toml"
    native_build = load_wads_module("native_build")
    args = native_build.cargo_test_args(json.load(sys.stdin), binding_manifest=binding)
    print(" ".join(args))
    return 0


if __name__ == "__main__":
    sys.exit(main())
