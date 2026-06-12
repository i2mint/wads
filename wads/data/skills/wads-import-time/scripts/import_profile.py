#!/usr/bin/env python3
"""Profile a package's import time from `python -X importtime` output.

Runs `python -X importtime -c "import PKG"` TWICE in the target repo (the
second run measures with warm .pyc caches — first-run compile noise is the
classic importtime measurement trap), parses the stderr report, and prints
the top offenders by self and cumulative time, each attributed to a
category: package-internal, third-party, stdlib, or environment noise
(site / .pth processing / editable-install finders).

Usage:
    python import_profile.py [REPO_PATH] [--pkg NAME] [--top N] [--json]
    python import_profile.py /path/to/repo --log existing_importtime.log

REPO_PATH defaults to the current directory. --pkg defaults to
[project].name from the repo's pyproject.toml (hyphens -> underscores).
With --log, an existing importtime stderr capture is parsed instead of
running anything (--pkg required if there's no pyproject.toml).

Read-only with respect to the target repo's source. (Importing the package
writes ordinary __pycache__ files, as any test run would.)

stdlib-only; works on Python >= 3.10 (pyproject parsing needs >= 3.11 or
tomli — pass --pkg explicitly to skip pyproject parsing).
"""

import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

LINE_RE = re.compile(r"^import time:\s*(\d+) \|\s*(\d+) \| (\s*)(\S.*?)\s*$")
ENV_NOISE_TOPS = {"site", "sitecustomize", "usercustomize", "_distutils_hack"}


def _read_pkg_from_pyproject(repo: Path) -> str | None:
    pp = repo / "pyproject.toml"
    if not pp.is_file():
        return None
    try:
        import tomllib
    except ImportError:  # Python 3.10
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError:
            return None
    try:
        name = tomllib.load(pp.open("rb"))["project"]["name"]
    except Exception:
        return None
    return name.replace("-", "_")


def run_importtime(repo: Path, pkg: str) -> str:
    """Run `python -X importtime -c "import pkg"` twice; return 2nd stderr."""
    import os

    # Put the local checkout first on sys.path EXPLICITLY. Relying on the
    # implicit cwd entry of `python -c` is not deterministic: PYTHONSAFEPATH
    # (or -P) removes it, silently profiling the *installed* package instead.
    src = repo / "src"
    local = src if (src / pkg.split(".")[0]).is_dir() else repo  # src layout
    prev = os.environ.get("PYTHONPATH")
    env = dict(
        os.environ,
        PYTHONPATH=str(local) + (os.pathsep + prev if prev else ""),
    )
    cmd = [sys.executable, "-X", "importtime", "-c", f"import {pkg}"]
    last = None
    for _ in range(2):  # 1st run warms .pyc caches; only the 2nd counts
        last = subprocess.run(cmd, cwd=repo, env=env, capture_output=True, text=True)
    assert last is not None
    if last.returncode != 0:
        traceback = "\n".join(
            ln for ln in last.stderr.splitlines() if not ln.startswith("import time:")
        )
        sys.exit(
            f"`import {pkg}` failed (exit {last.returncode}) — fix import "
            f"cleanliness first:\n{traceback}"
        )
    return last.stderr


def parse(log_text: str) -> list[dict]:
    """Parse importtime lines -> [{name, self_us, cum_us, depth}], file order."""
    rows = []
    for line in log_text.splitlines():
        m = LINE_RE.match(line)
        if not m:
            continue  # header line, warnings, other stderr chatter
        self_us, cum_us, indent, name = m.groups()
        rows.append(
            {
                "name": name,
                "self_us": int(self_us),
                "cum_us": int(cum_us),
                "depth": len(indent) // 2,
            }
        )
    if not rows:
        sys.exit("no `import time:` lines found — is this -X importtime stderr?")
    return rows


def categorize(name: str, pkg_top: str) -> str:
    top = name.split(".")[0]
    if top == pkg_top:
        return "package"
    if top in ENV_NOISE_TOPS or top.startswith("__editable__"):
        return "env-noise"
    if top in sys.stdlib_module_names:
        return "stdlib"
    return "third-party"


def build_report(rows: list[dict], pkg: str, top_n: int) -> dict:
    pkg_top = pkg.split(".")[0]
    for r in rows:
        r["category"] = categorize(r["name"], pkg_top)

    root = next((r for r in rows if r["name"] == pkg and r["depth"] == 0), None)
    total_us = root["cum_us"] if root else max(r["cum_us"] for r in rows)
    overhead_us = sum(r["self_us"] for r in rows if r["category"] == "env-noise")

    by_top: dict[str, dict] = defaultdict(lambda: {"self_us": 0, "modules": 0})
    for r in rows:
        t = r["name"].split(".")[0]
        by_top[t]["self_us"] += r["self_us"]
        by_top[t]["modules"] += 1
        by_top[t]["category"] = r["category"]
    top_level = sorted(
        ({"name": k, **v} for k, v in by_top.items()),
        key=lambda d: -d["self_us"],
    )

    keep = ("name", "self_us", "cum_us", "category")
    return {
        "pkg": pkg,
        "python": sys.version.split()[0],
        "total_us": total_us,
        "env_overhead_us": overhead_us,
        "modules_imported": len(rows),
        "top_self": [
            {k: r[k] for k in keep}
            for r in sorted(rows, key=lambda r: -r["self_us"])[:top_n]
        ],
        "top_cumulative": [
            {k: r[k] for k in keep}
            for r in sorted(rows, key=lambda r: -r["cum_us"])[:top_n]
        ],
        "by_top_level": top_level[:top_n],
    }


def _ms(us: int) -> str:
    return f"{us / 1000:8.1f}"


def print_human(rep: dict) -> None:
    print(f"import {rep['pkg']}  (python {rep['python']}, warm-cache run)")
    print(
        f"  total: {rep['total_us'] / 1000:.1f} ms cumulative   "
        f"env noise (site/.pth/editable finders): "
        f"{rep['env_overhead_us'] / 1000:.1f} ms self  "
        f"[{rep['modules_imported']} modules]"
    )
    for key, title in (
        ("top_self", "top modules by SELF time (the module's own body)"),
        ("top_cumulative", "top modules by CUMULATIVE time (module + its imports)"),
    ):
        print(f"\n{title}:")
        print(f"{'self ms':>9} {'cum ms':>9}  {'category':<11} name")
        for r in rep[key]:
            print(
                f"{_ms(r['self_us'])} {_ms(r['cum_us'])}  "
                f"{r['category']:<11} {r['name']}"
            )
    print("\nby top-level package (summed self time — the lazy-import shortlist):")
    print(f"{'self ms':>9} {'mods':>5}  {'category':<11} name")
    for r in rep["by_top_level"]:
        print(
            f"{_ms(r['self_us'])} {r['modules']:>5}  "
            f"{r['category']:<11} {r['name']}"
        )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("repo", nargs="?", default=".", help="target repo (default: cwd)")
    ap.add_argument("--pkg", help="import name (default: [project].name, _-normalized)")
    ap.add_argument("--top", type=int, default=10, help="rows per table (default 10)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--log", help="parse an existing importtime stderr file instead")
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    pkg = args.pkg or _read_pkg_from_pyproject(repo)
    if not pkg:
        sys.exit("cannot determine package: no readable pyproject.toml; pass --pkg")

    if args.log:
        try:
            log_text = Path(args.log).read_text()
        except OSError as e:
            sys.exit(f"cannot read --log file {args.log}: {e}")
    else:
        log_text = run_importtime(repo, pkg)
    rep = build_report(parse(log_text), pkg, args.top)
    if args.json:
        print(json.dumps(rep, indent=2))
    else:
        print_human(rep)


if __name__ == "__main__":
    main()
