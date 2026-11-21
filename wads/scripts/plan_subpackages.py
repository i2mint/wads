#!/usr/bin/env python3
"""Decide which subpackages release now (``[[tool.wads.ci.packages]]``, i2mint/wads#220).

Run by the ``plan-subpackages`` action in uv-ci's ``sub-plan`` job, in a checkout with the
full history and tags. Prints nothing but GitHub Actions outputs:

- ``releases``: JSON list of ``{package, dir, tag_prefix, version}``, one per subpackage
  that releases (``wads.subpackages.plan_release``);
- ``wheel-matrix``: the ``sub-wheels`` matrix rows (one per release x target, each carrying
  its ``version``).

Usage:
    python3 -I plan_subpackages.py [REPO_DIR]
"""

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _checkout_import import load_wads_module  # noqa: E402


def _toml(path: Path) -> dict:
    try:
        import tomllib
    except ImportError:  # Python < 3.11
        import tomli as tomllib
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _git(repo: Path, *args: str, check=True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=check
    )


def plan(repo: Path) -> tuple[list, list]:
    """``(releases, wheel_matrix)`` for the repo at ``repo``."""
    sub = load_wads_module("subpackages")
    packages = sub.subpackage_configs(
        _toml(repo / "pyproject.toml"),
        read_pyproject=lambda d: _toml(repo / d / "pyproject.toml"),
    )
    tags = _git(repo, "tag", "--list").stdout.split()
    releases, matrix = [], []
    for package in packages:
        committed = _toml(repo / package.dir / "pyproject.toml")["project"].get(
            "version", ""
        )

        def changed_since(tag: str, *, _dir=package.dir) -> bool:
            # exit 1 = differences; any other failure: assume changed (release > skip)
            return (
                _git(
                    repo, "diff", "--quiet", tag, "HEAD", "--", _dir, check=False
                ).returncode
                != 0
            )

        version = sub.plan_release(
            package, tags=tags, committed_version=committed, changed_since=changed_since
        )
        if version is None:
            print(
                f"{package.name}: no change under {package.dir}/, not released",
                file=sys.stderr,
            )
            continue
        print(f"{package.name}: releasing {version}", file=sys.stderr)
        releases.append(
            {
                "package": package.name,
                "dir": package.dir,
                "tag_prefix": package.tag_prefix,
                "version": version,
            }
        )
        matrix += [{**row, "version": version} for row in package.wheel_matrix()]
    return releases, matrix


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    repo = Path(argv[0] if argv else ".").resolve()
    try:
        releases, matrix = plan(repo)
    except (ValueError, OSError, KeyError) as e:
        print(f"::error::Subpackage plan failed: {e}", file=sys.stderr)
        return 1
    out = os.environ.get("GITHUB_OUTPUT")
    lines = f"releases={json.dumps(releases)}\nwheel-matrix={json.dumps(matrix)}\n"
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(lines)
    else:
        print(lines, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
