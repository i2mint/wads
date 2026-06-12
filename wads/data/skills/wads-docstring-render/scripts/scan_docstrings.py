#!/usr/bin/env python3
"""Scan Python docstrings for RST/napoleon rendering hazards (epythet/Sphinx).

Walks .py files under a repo (or package) directory, extracts docstrings via
ast (module, class, function), and applies heuristic regexes for the 12
mistake patterns cataloged in references/rst-pattern-catalog.md (single
backticks rendering as <cite> italics, doctests glued into paragraphs,
literal "Returns:"/":param" text, bare *args asterisks, collapsed bullet
lists, markdown fences, ...).

Usage:
    python scan_docstrings.py [REPO_OR_PKG_DIR] [--json] [--only ID[,ID...]]
                              [--exclude NAME ...] [--include-all]

READ-ONLY: this script never modifies anything. Output lines look like
    path/to/mod.py:42 [single-backtick] ... `dict` ...
followed by per-pattern counts.

IMPORTANT: these are HEURISTICS calibrated on the i2mint ecosystem; they
over-trigger (especially `bare-code-prose`, which is informational) and can
miss exotic cases. Verify each finding against the pattern catalog before
editing; never edit mechanically from this output alone.
"""

import argparse
import ast
import json
import re
import sys
from pathlib import Path

# Directories never worth scanning.
ALWAYS_EXCLUDE = {
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "venv",
    "site-packages",
}
# Not rendered by epythet's default docs build (quickstart ignores these);
# excluded by default, re-included with --include-all.
DOCS_EXCLUDE = {"tests", "test", "examples", "scrap"}

SECTION_WORDS = (
    r"(Args|Arguments|Parameters|Params|Returns?|Yields?|Raises|Examples?|"
    r"Notes?|Warnings?|Warns|Attributes|See Also|References|Todo|"
    r"Keyword Args|Keyword Arguments|Other Parameters|Methods)"
)
RE_SECTION = re.compile(rf"^(\s*){SECTION_WORDS}:\s*(\S.*)?$")
RE_FIELD = re.compile(
    r"^\s*:(param|parameter|arg|argument|key|keyword|type|returns?|rtype|"
    r"raises?|except|exception|var|ivar|cvar|vartype|meta)\b"
)
RE_MALFORMED_PARAM = re.compile(r"^\s*:param\s+[^:\n]*=")
RE_BULLET = re.compile(r"^\s*([-*+]|\d+[.)])\s+\S")
RE_FENCE = re.compile(r"^\s*(#\s*)?```")
RE_TICK_FENCE = re.compile(r"^\s*`\s*$")
RE_COMMENTED_DOCTEST = re.compile(r"^\s*#\s*>>>")
RE_ROLE = re.compile(r":[A-Za-z][\w:.+-]*:`[^`\n]*`")
RE_DOUBLE_TICK = re.compile(r"``[^`\n]*?``")
RE_SINGLE_TICK = re.compile(r"(?<![`:\\\w])`([^`\s][^`\n]{0,78}?)`(?![`_\w])")
RE_NAPOLEON_STAR_ARG = re.compile(r"^\s*\*{1,2}\w+\s*(\([^)]*\))?:")
RE_BOLD_SPAN = re.compile(r"\*\*[^*\n]+?\*\*")
RE_EM_SPAN = re.compile(r"(?<!\*)\*[^*\n]+?\*(?!\*)")
RE_BARE_STAR = re.compile(r"(?<![\w*])\*{1,2}[A-Za-z_]\w*")
RE_DOTTED_CALL = re.compile(r"\b[A-Za-z_]\w*(\.\w+)+\([^()\n]*\)")
RE_LAMBDA = re.compile(r"\blambda(\s+\w|\s*:)")
RE_KWARG_CALL = re.compile(r"\b\w+\([^()\n]*=[^()\n]*\)")

PATTERN_IDS = [
    "single-backtick",
    "google-section",
    "bare-asterisk",
    "accidental-blockquote",
    "collapsed-bullets",
    "field-list",
    "commented-doctest",
    "doctest-glue",
    "markdown-fence",
    "bare-code-prose",
    "over-indent-continuation",
    "indented-list-blockquote",
]


def _strip_inline_code(line):
    """Remove RST roles, double- and single-backtick spans from a line."""
    line = RE_ROLE.sub(" ", line)
    line = RE_DOUBLE_TICK.sub(" ", line)
    line = re.sub(r"`[^`\n]*`", " ", line)
    return line


def _indent(line):
    return len(line) - len(line.lstrip()) if line.strip() else None


def analyze_docstring(raw, base_lineno, add):
    """Run all pattern checks on one docstring. `add(pattern, idx, detail,
    excerpt)` records a finding at docstring line index `idx` (0-based)."""
    lines = raw.split("\n")
    n = len(lines)
    indents = [_indent(l) for l in lines]
    # The first line of a docstring that starts on the same line as the
    # opening quotes has no leading indentation in the raw string, so its
    # indent is unrepresentative — exclude it from indentation comparisons.
    if lines and lines[0].strip():
        indents[0] = None

    # --- precompute doctest-block membership ---------------------------
    in_doctest = [False] * n
    block = False
    for i, l in enumerate(lines):
        s = l.strip()
        if not s:
            block = False
            continue
        if s.startswith(">>>"):
            block = True
        in_doctest[i] = block

    # --- precompute literal-block membership (after a `::` intro) ------
    in_literal = [False] * n
    i = 0
    while i < n:
        s = lines[i].rstrip()
        if s.endswith("::") and not in_doctest[i] and indents[i] is not None:
            intro = indents[i]
            j = i + 1
            while j < n and (
                not lines[j].strip()
                or (indents[j] is not None and indents[j] > intro)
            ):
                if lines[j].strip():
                    in_literal[j] = True
                j += 1
            i = j
        else:
            i += 1

    def prev_nonblank(i):
        for j in range(i - 1, -1, -1):
            if lines[j].strip():
                return j
        return None

    def next_nonblank(i):
        for j in range(i + 1, n):
            if lines[j].strip():
                return j
        return None

    in_md_fence = False
    para_has_bullet = False  # bullets seen since last blank line

    for i, line in enumerate(lines):
        s = line.strip()
        if not s:
            para_has_bullet = False
            continue

        # markdown fences (incl. '# ```' inside commented-out blocks)
        if RE_FENCE.match(line):
            if not in_md_fence:
                add("markdown-fence", i, "``` fence", line)
            in_md_fence = not in_md_fence
            continue
        if in_md_fence:
            continue
        if RE_TICK_FENCE.match(line) and not in_doctest[i]:
            add("markdown-fence", i, "single-backtick fence line", line)
            continue

        # commented-out doctest soup
        if RE_COMMENTED_DOCTEST.match(line):
            add("commented-doctest", i, "", line)
            continue

        # doctest start lines: only the glue check applies
        if s.startswith(">>>"):
            if i > 0 and lines[i - 1].strip() and not in_doctest[i - 1]:
                add(
                    "doctest-glue",
                    i,
                    "no blank line before '>>>'",
                    lines[i - 1].strip() + " / " + s,
                )
            para_has_bullet = False
            continue
        if in_doctest[i] or in_literal[i]:
            continue

        is_bullet = bool(RE_BULLET.match(line))
        msec = RE_SECTION.match(line)

        # Google-style section headers
        # ('Examples::' is a legitimate RST literal-block intro — skip it)
        if msec and not line.rstrip().endswith("::"):
            content = msec.group(3)
            if content:
                add("google-section", i, "content on same line as header", line)
            else:
                j = next_nonblank(i)
                if j is not None:
                    nxt = lines[j]
                    if RE_BULLET.match(nxt):
                        add(
                            "google-section",
                            i,
                            "markdown bullets as section body",
                            line.strip() + " / " + nxt.strip(),
                        )
                    elif (
                        indents[j] is not None
                        and indents[i] is not None
                        and indents[j] <= indents[i]
                        and not nxt.strip().startswith(">>>")
                        and not RE_SECTION.match(nxt)
                    ):
                        add(
                            "google-section",
                            i,
                            "section body not indented under header",
                            line.strip() + " / " + nxt.strip(),
                        )
            para_has_bullet = False
            continue

        # RST field lists (:param x: ...)
        if RE_FIELD.match(line):
            if RE_MALFORMED_PARAM.match(line):
                add(
                    "field-list",
                    i,
                    "malformed field name ('=' in :param name) — poisons "
                    "all following fields",
                    line,
                )
            p = i - 1
            if (
                p >= 0
                and lines[p].strip()
                and not RE_FIELD.match(lines[p])
                and not in_doctest[p]
                and indents[p] is not None
                and indents[i] is not None
                and indents[p] <= indents[i]
            ):
                add(
                    "field-list",
                    i,
                    "no blank line between paragraph and field list",
                    lines[p].strip() + " / " + line.strip(),
                )
            if (
                i + 1 < n
                and lines[i + 1].strip()
                and not RE_FIELD.match(lines[i + 1])
                and indents[i + 1] is not None
                and indents[i] is not None
                and indents[i + 1] <= indents[i]
                and not lines[i + 1].strip().startswith(">>>")
            ):
                add(
                    "field-list",
                    i + 1,
                    "field continuation line not indented",
                    line.strip() + " / " + lines[i + 1].strip(),
                )
            para_has_bullet = False
            continue

        if is_bullet:
            p = i - 1
            if p >= 0 and lines[p].strip():
                prev = lines[p]
                if (
                    not RE_BULLET.match(prev)
                    and not RE_SECTION.match(prev)
                    and not para_has_bullet
                    and not in_doctest[p]
                ):
                    add(
                        "collapsed-bullets",
                        i,
                        "no blank line between intro text and list",
                        prev.strip() + " / " + line.strip(),
                    )
            elif i > 0 and not lines[i - 1].strip():
                p = prev_nonblank(i)
                if (
                    p is not None
                    and indents[p] is not None
                    and indents[i] is not None
                    and indents[i] > indents[p]
                    and not RE_BULLET.match(lines[p])
                    and not RE_SECTION.match(lines[p])
                    and not lines[p].rstrip().endswith("::")
                ):
                    add(
                        "indented-list-blockquote",
                        i,
                        "list indented deeper than intro paragraph",
                        lines[p].strip() + " / " + line.strip(),
                    )
            para_has_bullet = True
        else:
            # accidental blockquote: deeper-indented block after a blank line
            if i > 0 and not lines[i - 1].strip():
                p = prev_nonblank(i)
                if (
                    p is not None
                    and indents[p] is not None
                    and indents[i] is not None
                    and indents[i] > indents[p]
                    and not in_doctest[p]
                    and not lines[p].rstrip().endswith("::")
                    and not RE_SECTION.match(lines[p])
                    and not RE_FIELD.match(lines[p])
                    and not RE_BULLET.match(lines[p])
                    and not s.startswith(".. ")
                ):
                    add(
                        "accidental-blockquote",
                        i,
                        "indented block after blank line, intro has no '::'",
                        line,
                    )
            # accidental definition list: much deeper continuation, no blank
            elif i > 0 and lines[i - 1].strip():
                pi = indents[i - 1]
                if (
                    pi is not None
                    and indents[i] is not None
                    and indents[i] >= pi + 5
                    and not in_doctest[i - 1]
                    and not lines[i - 1].rstrip().endswith("::")
                    and not RE_SECTION.match(lines[i - 1])
                    and not RE_FIELD.match(lines[i - 1])
                    and not RE_BULLET.match(lines[i - 1])
                ):
                    add(
                        "over-indent-continuation",
                        i,
                        "continuation indented far deeper than its first "
                        "line (accidental definition list)",
                        lines[i - 1].strip() + " / " + line.strip(),
                    )

        # ---- inline checks on prose lines ----------------------------
        no_roles = RE_ROLE.sub(" ", line)
        no_double = RE_DOUBLE_TICK.sub(" ", no_roles)
        m = RE_SINGLE_TICK.search(no_double)
        if m:
            add("single-backtick", i, "", line)

        if not RE_NAPOLEON_STAR_ARG.match(line):
            stripped = _strip_inline_code(line)
            stripped = RE_BOLD_SPAN.sub(" ", stripped)
            stripped = RE_EM_SPAN.sub(" ", stripped)
            if RE_BARE_STAR.search(stripped):
                add("bare-asterisk", i, "unescaped *name in prose", line)

        code_free = _strip_inline_code(line)
        if (
            RE_DOTTED_CALL.search(code_free)
            or RE_LAMBDA.search(code_free)
            or RE_KWARG_CALL.search(code_free)
        ):
            add(
                "bare-code-prose",
                i,
                "informational: code-like fragment without ``markup``",
                line,
            )


def iter_docstrings(tree):
    """Yield (node, docstring_expr) for module/class/function docstrings."""
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            continue
        body = getattr(node, "body", None)
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            yield node, body[0].value


def scan_file(path, root, only, findings, counts, errors):
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (SyntaxError, UnicodeDecodeError, ValueError) as e:
        errors.append(f"{path.relative_to(root)}: {e.__class__.__name__}: {e}")
        return

    rel = str(path.relative_to(root))

    for _node, expr in iter_docstrings(tree):
        raw = expr.value
        base = expr.lineno
        # If the literal spans fewer source lines than the string has
        # (escaped newlines, concatenation), line numbers are approximate.
        span = (expr.end_lineno or expr.lineno) - expr.lineno + 1
        approx = span != len(raw.split("\n"))

        def add(pattern, idx, detail, excerpt, _base=base, _approx=approx):
            if only and pattern not in only:
                return
            line_no = _base + idx
            findings.append(
                {
                    "path": rel,
                    "line": line_no,
                    "approx_line": _approx,
                    "pattern": pattern,
                    "detail": detail,
                    "excerpt": excerpt.strip()[:100],
                }
            )
            counts[pattern] = counts.get(pattern, 0) + 1

        analyze_docstring(raw, base, add)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "root",
        nargs="?",
        default=".",
        help="repo or package directory to scan (default: cwd)",
    )
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument(
        "--only",
        default="",
        help=f"comma-separated pattern ids to report (from: {', '.join(PATTERN_IDS)})",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="extra directory name to exclude (repeatable)",
    )
    parser.add_argument(
        "--include-all",
        action="store_true",
        help="also scan tests/, examples/, scrap/ (excluded by default since "
        "epythet docs builds usually ignore them)",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"error: not a directory: {root}", file=sys.stderr)
        return 2

    only = {p.strip() for p in args.only.split(",") if p.strip()}
    unknown = only - set(PATTERN_IDS)
    if unknown:
        print(f"error: unknown pattern ids: {sorted(unknown)}", file=sys.stderr)
        return 2

    exclude = ALWAYS_EXCLUDE | set(args.exclude)
    if not args.include_all:
        exclude |= DOCS_EXCLUDE

    findings, counts, errors = [], {}, []
    files_scanned = 0
    for path in sorted(root.rglob("*.py")):
        rel_parts = path.relative_to(root).parts
        if any(p in exclude or p.startswith(".") for p in rel_parts[:-1]):
            continue
        files_scanned += 1
        scan_file(path, root, only, findings, counts, errors)

    findings.sort(key=lambda f: (f["path"], f["line"]))

    if args.json:
        print(
            json.dumps(
                {
                    "files_scanned": files_scanned,
                    "total_findings": len(findings),
                    "counts": dict(
                        sorted(counts.items(), key=lambda kv: -kv[1])
                    ),
                    "findings": findings,
                    "errors": errors,
                },
                indent=2,
            )
        )
    else:
        for f in findings:
            mark = "~" if f["approx_line"] else ""
            detail = f" ({f['detail']})" if f["detail"] else ""
            print(
                f"{f['path']}:{mark}{f['line']} [{f['pattern']}]{detail} "
                f"{f['excerpt']}"
            )
        print()
        print(f"# files scanned: {files_scanned}")
        print(f"# total findings: {len(findings)}")
        for pat, cnt in sorted(counts.items(), key=lambda kv: -kv[1]):
            print(f"#   {pat}: {cnt}")
        for e in errors:
            print(f"# parse error: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
