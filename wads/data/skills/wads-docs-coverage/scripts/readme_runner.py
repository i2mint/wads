#!/usr/bin/env python3
"""Run the fenced Python code blocks of a repo's README and report PASS/FAIL per block.

SECURITY WARNING
----------------
This script EXECUTES the code found in the README. Only run it on repos you
trust. By default, blocks execute in a throwaway temp directory (so README
code that writes files does not touch the target repo), with the repo root
prepended to ``sys.path`` so ``import <pkg>`` resolves to the local source.

Usage
-----
    python readme_runner.py [TARGET] [--json] [--run-in-repo] [--timeout N]

TARGET  path to a repo directory (its README.md is used) or directly to a
        markdown file. Defaults to the current working directory.

How blocks are handled
----------------------
* Fenced blocks whose info string starts with ``python``/``py``/``pycon``/
  ``pydocstring`` are collected in document order (info-string extras like
  ``python title=...`` are tolerated).
* A block containing ``>>>`` examples runs as a doctest with
  ``ELLIPSIS | NORMALIZE_WHITESPACE``; any other block runs via ``exec``.
* Globals are SHARED across blocks in document order — READMEs are sequential
  narratives, so an import or definition in block 1 is visible in block 3.
* A block is SKIPPED (not failed) when:
  - one of the lines immediately before its opening fence contains the HTML
    comment ``<!-- wads-docs: skip -->`` (anything after ``skip`` is treated
    as a free-form reason), or
  - it looks like an obvious illustrative placeholder: ALL_CAPS tokens in
    string literals or path segments (``Files('PATH_TO_TARGET_FOLDER')``),
    example.com URLs, angle-bracket placeholders (``<your-api-key>``), or
    fake credentials.

Exit code: 0 when no block FAILs, 1 when at least one fails, 2 on usage error.
"""

from __future__ import annotations

import argparse
import contextlib
import doctest
import io
import json
import os
import re
import shutil
import signal
import sys
import tempfile
import traceback
from pathlib import Path

# Fence regex (```LANG\n...```), tolerant of info-string extras; the info
# string is filtered against PYTHON_INFO_TOKENS below. Both fences are
# anchored at line start so INLINE triple-backtick spans (e.g.
# "install with ```pip install pkg```") can't pair with real fences and
# shift every subsequent block.
FENCE_RE = re.compile(
    r"^[ ]{0,3}```([^\n]*)\n(.*?)^[ ]{0,3}```[ \t]*$", re.DOTALL | re.MULTILINE
)
PYTHON_INFO_TOKENS = {"python", "python3", "py", "pycon", "pydocstring"}

SKIP_MARKER_RE = re.compile(r"<!--\s*wads-docs:\s*skip\b([^>]*)-->", re.IGNORECASE)
# How many lines immediately above the opening fence may carry the marker.
SKIP_MARKER_LOOKBACK = 3

PLACEHOLDER_PATTERNS = (
    (
        re.compile(r"['\"][^'\"\n]*\b[A-Z][A-Z0-9]+(?:_[A-Z0-9]+)+\b"),
        "ALL_CAPS placeholder in a string literal",
    ),
    (
        re.compile(r"/[A-Z][A-Z0-9_]+(?:/[A-Z][A-Z0-9_]*)+\b"),
        "ALL_CAPS path segments",
    ),
    (re.compile(r"\bexample\.(?:com|org|net)\b"), "example.com URL"),
    (
        re.compile(r"<\s*(?:your|my|insert|path|the)\b[^<>\n]*>", re.IGNORECASE),
        "angle-bracket placeholder",
    ),
    (re.compile(r"<[A-Z][A-Z0-9_]{2,}>"), "angle-bracket ALL_CAPS placeholder"),
    (
        re.compile(
            r"\b(?:your|my|fake|dummy)[-_ ]?(?:api[-_ ]?key|token|secret|password)\b",
            re.IGNORECASE,
        ),
        "fake credential placeholder",
    ),
    (re.compile(r"\bsk-(?:x{3,}|\.{3})", re.IGNORECASE), "fake credential placeholder"),
)

DETAIL_MAX_CHARS = 3000


class BlockTimeout(BaseException):
    """Raised when a block exceeds the per-block timeout.

    Inherits BaseException so README code catching ``Exception`` can't swallow it.
    """


@contextlib.contextmanager
def time_limit(seconds):
    """Limit wall-clock time of a with-block (Unix only; no-op elsewhere)."""
    if seconds <= 0 or not hasattr(signal, "SIGALRM"):
        yield
        return

    def _handler(signum, frame):
        raise BlockTimeout(f"block exceeded {seconds}s timeout")

    old = signal.signal(signal.SIGALRM, _handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


def find_readme(target: Path) -> Path:
    """Resolve TARGET (repo dir or markdown file) to a markdown file path."""
    if target.is_file():
        return target
    if target.is_dir():
        candidates = sorted(
            p for p in target.iterdir() if p.is_file() and p.name.lower() == "readme.md"
        ) or sorted(
            p
            for p in target.iterdir()
            if p.is_file()
            and p.name.lower().startswith("readme")
            and p.suffix.lower() in {".md", ".markdown"}
        )
        if candidates:
            return candidates[0]
        raise FileNotFoundError(f"no README*.md found in {target}")
    raise FileNotFoundError(f"no such file or directory: {target}")


def extract_blocks(text: str) -> list[dict]:
    """Extract fenced python blocks with line numbers and skip/placeholder flags."""
    lines = text.splitlines()
    blocks = []
    for match in FENCE_RE.finditer(text):
        info = match.group(1).strip()
        first_token = info.split()[0].lower() if info.split() else ""
        if first_token not in PYTHON_INFO_TOKENS:
            continue
        body = match.group(2)
        fence_line = text[: match.start()].count("\n") + 1
        end_line = text[: match.end()].count("\n") + 1
        skip_reason = None
        lookback = lines[max(0, fence_line - 1 - SKIP_MARKER_LOOKBACK) : fence_line - 1]
        for prev in lookback:
            marker = SKIP_MARKER_RE.search(prev)
            if marker:
                note = marker.group(1).strip(" -:")
                skip_reason = f"marker{': ' + note if note else ''}"
                break
        placeholder_reason = None
        if skip_reason is None:
            for pattern, reason in PLACEHOLDER_PATTERNS:
                if pattern.search(body):
                    placeholder_reason = reason
                    break
        blocks.append(
            {
                "index": len(blocks) + 1,
                "info": info,
                "body": body,
                "start_line": fence_line,
                "body_line": fence_line + 1,
                "end_line": end_line,
                "skip_reason": skip_reason,
                "placeholder_reason": placeholder_reason,
            }
        )
    return blocks


def _truncate(text: str, limit: int = DETAIL_MAX_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [truncated, {len(text)} chars total]"


def run_doctest_block(block, globs, display_name, timeout):
    """Run a '>>>'-style block via doctest; mutate shared globs with its state."""
    parser = doctest.DocTestParser()
    test = parser.get_doctest(
        block["body"],
        globs,
        name=f"block-{block['index']}",
        filename=display_name,
        lineno=block["body_line"] - 1,  # doctest reports lineno + example line + 1
    )
    runner = doctest.DocTestRunner(
        optionflags=doctest.ELLIPSIS | doctest.NORMALIZE_WHITESPACE, verbose=False
    )
    report = io.StringIO()
    try:
        with time_limit(timeout):
            results = runner.run(test, out=report.write, clear_globs=False)
    except BlockTimeout as exc:
        globs.update(test.globs)
        return "FAIL", str(exc), 0
    globs.update(test.globs)
    if results.failed:
        return "FAIL", _truncate(report.getvalue()), results.attempted
    return "PASS", None, results.attempted


def run_exec_block(block, globs, display_name, timeout):
    """Run a plain script block via exec into the shared globals."""
    pseudo_file = f"{display_name}:block-{block['index']}"
    try:
        code = compile(block["body"], pseudo_file, "exec")
    except SyntaxError as exc:
        abs_line = block["body_line"] + (exc.lineno or 1) - 1
        return "FAIL", f"SyntaxError: {exc.msg} (README line {abs_line})"
    captured = io.StringIO()
    try:
        with time_limit(timeout), contextlib.redirect_stdout(captured):
            exec(code, globs)
    except BlockTimeout as exc:
        return "FAIL", str(exc)
    except BaseException as exc:  # noqa: BLE001 — report any failure, incl. SystemExit
        abs_line = None
        for frame in traceback.extract_tb(exc.__traceback__):
            if frame.filename == pseudo_file:
                abs_line = block["body_line"] + (frame.lineno or 1) - 1
        where = f" (README line {abs_line})" if abs_line else ""
        return "FAIL", _truncate(f"{type(exc).__name__}: {exc}{where}")
    return "PASS", None


def run_blocks(blocks, display_name, timeout):
    """Run all blocks in document order with shared globals; return result dicts."""
    shared_globs = {"__name__": "__readme__"}
    results = []
    for block in blocks:
        kind = "doctest" if ">>>" in block["body"] else "exec"
        record = {
            "index": block["index"],
            "start_line": block["start_line"],
            "end_line": block["end_line"],
            "kind": kind,
            "status": None,
            "detail": None,
            "skip_reason": None,
            "examples": None,
        }
        if block["skip_reason"]:
            record["status"] = "SKIP"
            record["skip_reason"] = block["skip_reason"]
        elif block["placeholder_reason"]:
            record["status"] = "SKIP"
            record["skip_reason"] = f"placeholder: {block['placeholder_reason']}"
        elif kind == "doctest":
            status, detail, attempted = run_doctest_block(
                block, shared_globs, display_name, timeout
            )
            record.update(status=status, detail=detail, examples=attempted)
        else:
            status, detail = run_exec_block(block, shared_globs, display_name, timeout)
            record.update(status=status, detail=detail)
        results.append(record)
    return results


def print_human_report(readme_path, results):
    print(f"README: {readme_path}  ({len(results)} python block(s))")
    for r in results:
        location = f"lines {r['start_line']}-{r['end_line']}"
        extra = ""
        if r["status"] == "SKIP":
            extra = f"  ({r['skip_reason']})"
        elif r["kind"] == "doctest" and r["examples"] is not None:
            extra = f"  ({r['examples']} example(s))"
        print(f"  [{r['index']:>2}] {location:<16} {r['kind']:<8} {r['status']}{extra}")
    failures = [r for r in results if r["status"] == "FAIL"]
    if failures:
        print("\nFAIL details:")
        for r in failures:
            print(f"\n--- block {r['index']} (lines {r['start_line']}-{r['end_line']}) ---")
            print(r["detail"] or "(no detail)")
    counts = summarize(results)
    print(
        f"\nSummary: {counts['total']} block(s) — "
        f"{counts['passed']} passed, {counts['failed']} failed, {counts['skipped']} skipped"
    )


def summarize(results):
    return {
        "total": len(results),
        "passed": sum(1 for r in results if r["status"] == "PASS"),
        "failed": sum(1 for r in results if r["status"] == "FAIL"),
        "skipped": sum(1 for r in results if r["status"] == "SKIP"),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Execute a README's fenced python blocks and report per-block "
        "PASS/FAIL/SKIP. WARNING: this runs the README's code — trusted repos only.",
    )
    parser.add_argument(
        "target",
        nargs="?",
        default=".",
        help="repo directory (its README.md is used) or a markdown file [default: cwd]",
    )
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument(
        "--run-in-repo",
        action="store_true",
        help="execute blocks with cwd = repo root instead of a temp dir "
        "(use when examples read repo-relative files; README code may then "
        "write into the repo)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="per-block timeout in seconds, 0 = no limit (Unix only) [default: 60]",
    )
    args = parser.parse_args(argv)

    try:
        readme_path = find_readme(Path(args.target).resolve())
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    repo_root = readme_path.parent
    text = readme_path.read_text(encoding="utf-8")
    blocks = extract_blocks(text)

    print(
        "readme_runner: executing README code blocks — only run on trusted repos.",
        file=sys.stderr,
    )

    sys.path.insert(0, str(repo_root))
    original_cwd = os.getcwd()
    temp_dir = None
    if args.run_in_repo:
        os.chdir(repo_root)
    else:
        temp_dir = tempfile.mkdtemp(prefix="readme_runner_")
        os.chdir(temp_dir)
    try:
        results = run_blocks(blocks, readme_path.name, args.timeout)
    finally:
        os.chdir(original_cwd)
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)

    if args.json:
        print(
            json.dumps(
                {
                    "readme": str(readme_path),
                    "blocks": results,
                    "summary": summarize(results),
                },
                indent=2,
            )
        )
    else:
        print_human_report(readme_path, results)
    return 1 if any(r["status"] == "FAIL" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
