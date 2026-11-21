#!/usr/bin/env python3
"""Write a release version into a subpackage's ``pyproject.toml`` (i2mint/wads#220).

Usage:
    python3 -I stamp_subpackage_version.py PYPROJECT_PATH VERSION
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _checkout_import import load_wads_module  # noqa: E402


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    path, version = Path(argv[0]), argv[1]
    try:
        text = path.read_text(encoding="utf-8")
        path.write_text(
            load_wads_module("subpackages").stamp_version(text, version),
            encoding="utf-8",
        )
    except (ValueError, OSError) as e:
        print(f"::error::Stamping {path} failed: {e}", file=sys.stderr)
        return 1
    print(f"{path} -> {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
