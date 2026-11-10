#!/usr/bin/env python3
"""Write the release version into the manifests ``[tool.wads.ci.version].sync`` lists.

Run by the ``sync-version`` action in uv-ci's publish jobs, right after the version
bump, so the bump commit carries every manifest (i2mint/wads#210).

Usage:
    python3 -I sync_version.py VERSION FILES_JSON [REPO_DIR]
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _checkout_import import load_wads_module  # noqa: E402


def main(argv=None) -> int:
    """Sync ``VERSION`` into each file of ``FILES_JSON``; 1 with an error annotation on failure."""
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) not in (2, 3):
        print(__doc__, file=sys.stderr)
        return 2
    version, files_json, *rest = argv
    repo_dir = rest[0] if rest else "."
    try:
        files = json.loads(files_json)
        written = load_wads_module("version_sync").sync_version(repo_dir, files, version)
    except (ValueError, OSError) as e:
        print(f"::error::Version sync failed: {e}", file=sys.stderr)
        return 1
    for path in written:
        print(f"{path} -> {version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
