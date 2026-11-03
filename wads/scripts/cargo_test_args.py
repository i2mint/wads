#!/usr/bin/env python3
"""Print the ``cargo test`` arguments for a maturin package (issue #166).

Usage (from the package root, as the rust-checks action runs it)::

    cargo metadata --no-deps --format-version 1 | python3 -I cargo_test_args.py [PROJECT_DIR]

Prints the arguments on one line, or nothing when there is no pure-Rust crate to test.
The binding crate is ``[tool.maturin].manifest-path`` (default ``Cargo.toml``). Standard
library only: it runs from the action's checkout without installing wads.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # also under `-m`
from _checkout_import import load_wads_module  # noqa: E402

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
    import tomli as tomllib


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    project_dir = Path(argv[0] if argv else ".")
    with open(project_dir / "pyproject.toml", "rb") as f:
        pyproject = tomllib.load(f)
    manifest = pyproject.get("tool", {}).get("maturin", {}).get("manifest-path")
    binding = project_dir / (manifest or "Cargo.toml")
    native_build = load_wads_module("native_build")
    args = native_build.cargo_test_args(
        json.load(sys.stdin), binding_manifest=str(binding)
    )
    print(" ".join(args))
    return 0


if __name__ == "__main__":
    sys.exit(main())
