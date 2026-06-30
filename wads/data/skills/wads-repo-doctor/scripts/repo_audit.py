#!/usr/bin/env python3
"""Thin shim → the SSOT classifier in ``wads.repo_audit``.

The repo-audit logic now lives in the importable module ``wads/repo_audit.py``
(its single source of truth, shared by the wads-repo-doctor skill, priv's
``fleet_status``, and CI). This script just forwards to it so the documented
``python scripts/repo_audit.py [REPO] [--json] [--no-network]`` invocation keeps
working. Prefer ``python -m wads.repo_audit`` or
``from wads.repo_audit import audit_repo``.
"""

import sys
from pathlib import Path

try:
    from wads.repo_audit import main
except ModuleNotFoundError:  # wads not importable: add the bundled package root
    # this file: <root>/wads/data/skills/wads-repo-doctor/scripts/repo_audit.py
    sys.path.insert(0, str(Path(__file__).resolve().parents[5]))
    from wads.repo_audit import main

if __name__ == "__main__":
    raise SystemExit(main())
