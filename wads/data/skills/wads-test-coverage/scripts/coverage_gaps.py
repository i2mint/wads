"""Bucket every public function/class of a package by how it is covered.

Parses a coverage.py JSON report that includes per-test *contexts* (produced
with ``--cov-context=test`` + ``python -m coverage json --show-contexts``) and
classifies each public function/class region into one of three buckets:

- ``untested``      — no test or doctest executes any of its lines
- ``doctest-only``  — executed only by doctests (legitimate in this ecosystem,
                      but error paths/edge cases may still deserve real tests)
- ``test-covered``  — executed by at least one dedicated test

Doctest contexts look like ``pkg/mod.py::pkg.mod.func|run`` (the nodeid file is
the module itself; the item is a dotted object name). Dedicated-test contexts
look like ``tests/test_x.py::test_name|run``.

Requires a report from coverage.py >= 7.5 (per-region ``functions``/``classes``
data). "Public" means no component of the dotted name starts with ``_``.
Test files themselves (``tests/`` dirs, ``test_*.py``, ``conftest.py``) are
excluded from the buckets — they are not public API.

Read-only: reads the JSON report; never modifies the target repo.

Usage:
    python coverage_gaps.py [REPO] [--coverage-json PATH] [--json]

    REPO             target repo root (default: current directory)
    --coverage-json  report path; default: REPO/coverage_ctx.json,
                     falling back to REPO/coverage.json
    --json           emit machine-readable JSON instead of the human report
"""

import argparse
import json
import re
import sys
from pathlib import Path, PurePosixPath
from typing import NoReturn

_PHASE_SUFFIX = re.compile(r"\|(run|setup|teardown)$")
_DOTTED_NAME = re.compile(r"[A-Za-z_]\w*(\.[A-Za-z_]\w*)*$")

HELP_PRODUCE = (
    "Produce it from the repo root with:\n"
    "  python -m pytest --doctest-modules "
    "-o doctest_optionflags='ELLIPSIS IGNORE_EXCEPTION_DETAIL' "
    "--cov=PKG --cov-branch --cov-context=test "
    "--cov-report=term-missing --cov-report=json:coverage.json PKG\n"
    "  python -m coverage json --show-contexts -o coverage_ctx.json"
)


def _err(msg: str) -> NoReturn:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(2)


def _is_test_file(rel_path: str) -> bool:
    parts = PurePosixPath(rel_path.replace("\\", "/")).parts
    fname = parts[-1] if parts else ""
    return (
        "tests" in parts[:-1]
        or "test" in parts[:-1]
        or fname.startswith("test_")
        or fname.endswith("_test.py")
        or fname == "conftest.py"
    )


def _is_public(dotted_name: str) -> bool:
    if "<" in dotted_name:  # <lambda>, <locals> — never public API
        return False
    return all(not part.startswith("_") for part in dotted_name.split("."))


def classify_context(ctx: str) -> str:
    """Classify one coverage context as 'doctest', 'test', or 'other'."""
    base = _PHASE_SUFFIX.sub("", ctx)
    file_part, sep, item = base.partition("::")
    if not sep:
        return "other"
    if _is_test_file(file_part):
        return "test"
    last_item = item.split("::")[-1].split("[")[0]
    if last_item.startswith("test_"):
        return "test"
    if _DOTTED_NAME.fullmatch(item):
        return "doctest"  # nodeid item is a dotted object name in a pkg module
    return "test"


def _bucket_region(region: dict, file_contexts: dict) -> tuple:
    """Return (bucket, sorted context kinds) for one function/class region."""
    ctxs = set()
    for line in region.get("executed_lines", []):
        ctxs.update(file_contexts.get(str(line), []))
    ctxs.discard("")  # import-time / out-of-test execution
    kinds = {classify_context(c) for c in ctxs}
    if "test" in kinds or "other" in kinds:
        bucket = "test-covered"
    elif "doctest" in kinds:
        bucket = "doctest-only"
    else:
        bucket = "untested"
    return bucket, sorted(kinds)


def analyze(report: dict) -> dict:
    files = report.get("files", {})
    if not files:
        _err("coverage report contains no files")

    if not any("functions" in f or "classes" in f for f in files.values()):
        version = report.get("meta", {}).get("version", "unknown")
        _err(
            "report has no per-function/class regions "
            "(files.*.functions / files.*.classes). This needs coverage >= 7.5; "
            f"the report was written by coverage {version}. "
            "Upgrade coverage and regenerate the JSON."
        )
    if not any("contexts" in f for f in files.values()):
        _err(
            "report has no per-line contexts, so doctest-vs-test attribution "
            "is impossible. (Note: the coverage.json written by "
            "--cov-report=json: does NOT include contexts.)\n" + HELP_PRODUCE
        )

    modules = {}
    n_private = 0
    n_test_files = 0
    for path, fdata in sorted(files.items()):
        if _is_test_file(path):
            n_test_files += 1
            continue
        contexts = fdata.get("contexts", {})
        entries = []
        for kind, regions_key in (("function", "functions"), ("class", "classes")):
            for name, region in fdata.get(regions_key, {}).items():
                if not name:  # '' = module-level code region
                    continue
                if not _is_public(name):
                    n_private += 1
                    continue
                bucket, kinds = _bucket_region(region, contexts)
                entries.append(
                    {
                        "file": path,
                        "kind": kind,
                        "name": name,
                        "bucket": bucket,
                        "context_kinds": kinds,
                        "percent_covered": round(
                            region["summary"]["percent_covered"], 1
                        ),
                        "n_missing_lines": len(region.get("missing_lines", [])),
                        "n_missing_branches": region["summary"].get(
                            "missing_branches", 0
                        ),
                    }
                )
        if entries or fdata.get("summary", {}).get("num_statements", 0):
            modules[path] = {
                "percent_covered": round(
                    fdata.get("summary", {}).get("percent_covered", 0.0), 1
                ),
                "regions": entries,
            }

    def severity(item):
        path, mod = item
        n_untested = sum(r["bucket"] == "untested" for r in mod["regions"])
        n_doconly = sum(r["bucket"] == "doctest-only" for r in mod["regions"])
        return (-n_untested, -n_doconly, mod["percent_covered"], path)

    ordered = dict(sorted(modules.items(), key=severity))
    all_regions = [r for m in ordered.values() for r in m["regions"]]
    return {
        "meta": report.get("meta", {}),
        "totals": {
            "public_regions": len(all_regions),
            "untested": sum(r["bucket"] == "untested" for r in all_regions),
            "doctest_only": sum(r["bucket"] == "doctest-only" for r in all_regions),
            "test_covered": sum(r["bucket"] == "test-covered" for r in all_regions),
            "private_regions_skipped": n_private,
            "test_files_skipped": n_test_files,
        },
        "modules": ordered,
    }


def print_human(result: dict, source: Path) -> None:
    meta, totals = result["meta"], result["totals"]
    print(f"Coverage gap report — source: {source}")
    print(
        f"(coverage {meta.get('version', '?')}, "
        f"branch={meta.get('branch_coverage')}, "
        f"contexts={meta.get('show_contexts')})\n"
    )
    print(f"Public function/class regions: {totals['public_regions']}")
    print(f"  untested     : {totals['untested']}")
    print(f"  doctest-only : {totals['doctest_only']}")
    print(f"  test-covered : {totals['test_covered']}")
    print(
        f"(skipped: {totals['private_regions_skipped']} private region(s), "
        f"{totals['test_files_skipped']} test file(s))"
    )
    for path, mod in result["modules"].items():
        regions = mod["regions"]
        untested = [r for r in regions if r["bucket"] == "untested"]
        doconly = [r for r in regions if r["bucket"] == "doctest-only"]
        covered = [r for r in regions if r["bucket"] == "test-covered"]
        if not untested and not doconly:
            continue
        print(f"\n== {path} ({mod['percent_covered']}% covered) ==")
        for label, group in (("UNTESTED", untested), ("DOCTEST-ONLY", doconly)):
            if group:
                print(f"  {label}:")
                for r in group:
                    gap = ""
                    if r["n_missing_lines"] or r["n_missing_branches"]:
                        gap = (
                            f"  ({r['n_missing_lines']} missing lines, "
                            f"{r['n_missing_branches']} missing branches)"
                        )
                    print(f"    {r['kind']:<8} {r['name']}{gap}")
        if covered:
            print(f"  test-covered: {len(covered)} region(s)")
    if totals["untested"] == totals["doctest_only"] == 0:
        print("\nNo public gaps: every public region is exercised by a test.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bucket public functions/classes as "
        "untested / doctest-only / test-covered."
    )
    parser.add_argument(
        "repo", nargs="?", default=".", help="target repo root (default: cwd)"
    )
    parser.add_argument(
        "--coverage-json",
        default=None,
        help="path to a coverage JSON with contexts, resolved against the "
        "current directory (default: REPO/coverage_ctx.json, else "
        "REPO/coverage.json)",
    )
    parser.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON"
    )
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    if not repo.is_dir():
        _err(f"not a directory: {repo}")
    if args.coverage_json:
        source = Path(args.coverage_json)
    else:
        source = repo / "coverage_ctx.json"
        if not source.exists():
            source = repo / "coverage.json"
    if not source.exists():
        _err(f"no coverage JSON found at {source}.\n{HELP_PRODUCE}")

    try:
        report = json.loads(source.read_text())
    except json.JSONDecodeError as e:
        _err(f"cannot parse {source}: {e}")

    result = analyze(report)
    if args.json:
        result["source"] = str(source)
        print(json.dumps(result, indent=2))
    else:
        print_human(result, source)


if __name__ == "__main__":
    main()
