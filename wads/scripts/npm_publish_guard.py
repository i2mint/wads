#!/usr/bin/env python3
"""Refuse an npm publish that would reuse the previous PyPI release's number (i2mint/wads#210).

Run by the ``npm-publish-guard`` action in npm-ci's pack job, before anything is
installed or uploaded. A no-op when the repo has no ``pyproject.toml`` or its
``[tool.wads.ci.version].sync`` lists no manifest in the npm package; otherwise the
decision is ``wads.version_sync.npm_publish_refusal``.

Usage:
    SUBJECT='<commit subject>' python3 -I npm_publish_guard.py PACKAGE_DIR CHANGED_FILES [REPO_DIR]

``CHANGED_FILES`` holds the push's changed paths, repo relative, NUL separated
(``git diff --name-only -z``).
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _checkout_import import load_wads_module  # noqa: E402


def main(argv=None) -> int:
    """0 when npm may publish, 1 with an error annotation when it must not."""
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) not in (2, 3):
        print(__doc__, file=sys.stderr)
        return 2
    package_dir, changed_path, *rest = argv
    pyproject = Path(rest[0] if rest else ".") / "pyproject.toml"
    if not pyproject.is_file():
        print("No pyproject.toml at the repo root: nothing to check.")
        return 0
    try:
        import tomllib

        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        changed = [p for p in Path(changed_path).read_text().split("\0") if p]
        refusal = load_wads_module("version_sync").npm_publish_refusal(
            data, package_dir, changed, os.environ.get("SUBJECT", "")
        )
    except (ValueError, OSError, ImportError) as e:
        print(f"::error::npm publish guard failed: {e}", file=sys.stderr)
        return 1
    if refusal:
        print(f"::error::{refusal}", file=sys.stderr)
        return 1
    print(
        f"npm may publish {package_dir}: no PyPI release in this push moves its version."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
