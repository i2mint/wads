---
name: wads-docstring-render
description: >-
  Find and fix docstrings that mis-render under epythet (Sphinx + RST +
  napoleon): single backticks showing as italics, doctests glued into
  paragraphs, literal "Returns:" or ":param" text, red asterisks from bare
  *args, collapsed bullet lists, markdown fences, smartquote-corrupted code.
  Use for "fix my docstrings", "the API docs render wrong", "my doctest shows
  as plain text", "why is this italic in the docs", "red asterisks in the
  docs", "Returns: shows literally on the page", "audit docstring RST",
  "make docstrings Sphinx-clean", "the published module page looks mangled".
  Also trigger after writing new docstrings or before a docs release. Does
  NOT cover docs publishing, GitHub Pages, or 404s (use epythet-docs), and
  does NOT measure docstring presence/coverage or README drift (use
  wads-docs-coverage).
metadata:
  audience: users
---

# Docstring Rendering Repair

This ecosystem publishes API docs straight from docstrings via epythet
(Sphinx + RST + napoleon, smartquotes ON), and **docutils error messages are
suppressed in the published pages** — so markdown habits in docstrings render
as silent garbage (italics instead of code, doctests glued into paragraphs,
literal `Returns:` text) that authors never see. This skill finds those
defects from symptoms and source scans, fixes them in frequency order, and
verifies nothing about doctest behavior changed.

**Golden rule: observe, don't invent.** Every finding comes from a command
output (a published-page grep, the scanner, epythet's diagnosis) and every
edit is verified against the catalog before it's made. These repos are
doctest-first: docstrings are simultaneously docs and tests — a rendering fix
must never change what doctest collects or executes.

## Step 0 — Resolve the target repo and package

```bash
TARGET=/path/to/repo          # the path the user gave, else the current directory
cd "$TARGET"
PKG=$(python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['name'])")
git remote get-url origin     # gives OWNER/REPO for the published-docs URL
```

If the import-package directory differs from the project name (rare), find it:
`ls -d */__init__.py` and set `PKG` to that directory.

> `import tomllib` needs Python ≥ 3.11; on 3.10 substitute
> `import tomli as tomllib` (pip-installable).

## Step 1 — Check the published docs for symptoms (optional, recommended)

Before touching source, learn which patterns this repo actually exhibits.
epythet publishes per-module pages at
`https://OWNER.github.io/REPO/module_docs/PKG/MODULE.html`. Each defect class
leaves a grep-able signature in the HTML:

| HTML signature | Meaning | Catalog pattern |
|---|---|---|
| `<cite>` | single backtick rendered as title-reference italics | 1 |
| `class="problematic"` | unescaped `*args` asterisks (red spans) | 3 |
| `&gt;&gt;&gt;` inside a `<p>` | doctest glued into a paragraph | 8 |
| literal `:param ` inside a `<p>` | broken field list | 6 |
| `<p>` starting `Returns:`/`Parameters:` | literal Google section header | 2 |
| literal ``` in text | markdown fence | 9 |

```bash
OWNER=i2mint REPO=dol PKG=dol   # placeholders — set from step 0
mkdir -p /tmp/docs-audit
for M in $(find "$TARGET/$PKG" -maxdepth 1 -name '*.py' ! -name '__*' \
           -exec basename {} .py \;); do
  page="/tmp/docs-audit/$M.html"
  if ! curl -fsSL "https://$OWNER.github.io/$REPO/module_docs/$PKG/$M.html" -o "$page"; then
    echo "$M: no published page"; continue
  fi
  flat=$(mktemp); tr '\n' ' ' < "$page" > "$flat"   # symptoms span HTML lines
  echo "$M: cite=$(grep -o '<cite>' "$page" | wc -l | tr -d ' ')" \
    "problematic=$(grep -o 'class="problematic"' "$page" | wc -l | tr -d ' ')" \
    "glued-doctest=$(grep -oE '<p>[^<]*&gt;&gt;&gt;' "$flat" | wc -l | tr -d ' ')" \
    "literal-param=$(grep -oE '<p>[^<]*:param ' "$flat" | wc -l | tr -d ' ')" \
    "literal-header=$(grep -oE '<p>(Args|Parameters|Returns?|Examples?|Raises|Note):' "$flat" | wc -l | tr -d ' ')"
done
```

Nonzero counts tell you which patterns to prioritize in step 4. (For nested
packages, extend the `find` depth and map subpaths into the URL.) No published
docs at all → that's a publishing problem: **epythet-docs** skill, not this one.

## Step 2 — Scan the source

```bash
python scripts/scan_docstrings.py "$TARGET"            # human-readable
python scripts/scan_docstrings.py "$TARGET" --json     # machine-readable
python scripts/scan_docstrings.py "$TARGET" --only doctest-glue,single-backtick
```

The scanner is stdlib-only and read-only: it AST-extracts every
module/class/function docstring and applies the catalog's pattern regexes
*inside docstrings only*, emitting `path:line [pattern-id] excerpt` plus
per-pattern counts. By default it skips `tests/`, `examples/`, `scrap/`
(epythet docs builds usually ignore them) — `--include-all` re-includes them.

⚠️ **The scanner's findings are heuristics.** They over-trigger (especially
`bare-code-prose`, which is informational) — verify each finding against
`references/rst-pattern-catalog.md` before editing. Never bulk-edit from
scanner output alone.

## Step 3 — Auto-fix the blank-line-before-doctest class (epythet)

Pattern 8 (`doctest-glue`) is the one class with a safe auto-fixer. The
verified import path (epythet >= 0.1.14):

```bash
python -c "from epythet import diagnose_doctest_code_blocks, repair_package"
# ModuleNotFoundError? -> pip install epythet
```

⚠️ **Sphinx is verifiably SILENT on this breaker.** A clean `-W -n` strict
build does NOT mean it's absent — the build succeeds and the doctest renders
as mangled paragraph text. epythet's diagnosis is the only reliable detector
(the scanner's `doctest-glue` check mirrors it).

Diagnose first (read-only; per-module or whole package):

```bash
# One module: yields (line_number, line) for each '>>>' missing its blank line
python -c "
from epythet import diagnose_doctest_code_blocks
for ln, line in diagnose_doctest_code_blocks('$TARGET/$PKG/MODULE.py'):
    print(ln, line)
"
# Whole package, dry run — prints per-file problem counts, writes NOTHING
python -c "from epythet import repair_package; print(repair_package('$TARGET/$PKG'))"
```

Then apply:

```bash
python -c "from epythet import repair_package; print(repair_package('$TARGET/$PKG', write_to_files=True))"
git -C "$TARGET" diff --stat   # review: blank-line insertions only
```

⚠️ **`repair_package` walks ALL files under the directory you give it, not
just `.py`** (verified: pointed at a directory containing a README.md, it
diagnoses — and with `write_to_files=True` would edit — inside markdown
fences). Always point it at the package *source* directory (`$TARGET/$PKG`),
never the repo root, and review `git diff` before committing.

## Step 4 — Fix the remaining findings, in frequency order

Work through `references/rst-pattern-catalog.md` top-down — it's ordered by
observed frequency, with a real before/after and a safety note per pattern.

**The headline fix is single-backtick → double-backtick** (~70% of all
observed defects). It is mechanically safe in this ecosystem — genuine
RST title-references were never observed in the audit — but eyeball each
conversion: skip role usages (``:func:`name```), hyperlink references
(`` `text`_ ``), and anything inside doctest or literal blocks.

| Finding | Action |
|---|---|
| `single-backtick` around code-like content | convert to double backticks (eyeball each) |
| `google-section` | repair to proper Google style (napoleon is on): indented body, `name (type): description`, no hyphens, no same-line content |
| `bare-asterisk` in prose | wrap the whole code fragment in ``double backticks`` |
| `field-list` | diagnose the sub-cause first — a malformed `:param name=...` poisons every field after it; a blank line alone won't fix that |
| `collapsed-bullets` / `indented-list-blockquote` | blank line before the list / dedent to the intro's level |
| `markdown-fence` | `::` literal block or `.. code-block:: python` |
| `commented-doctest` | **ask the user** — three options below |
| `bare-code-prose` | wrap in double backticks where clearly code; skip prose |
| Ambiguous intent (intentional blockquote? emphasis vs code?) | **ask the user** |

**Commented-out doctests (`# >>> ...` soup)** — present three options,
defaulting to (2), since the usual intent is "keep as documentation, exclude
from testing":

1. Delete the block (or move it to an issue).
2. Convert to an indented literal block after `::` — renders as code, NOT
   collected by doctest (doctest-neutral).
3. Fix and re-enable the doctest — only with the user's blessing; it changes
   what tests run.

### Do-no-harm checklist (apply to every edit)

- **Never change what doctest collects or executes.** Adding a blank line
  before `>>>` is safe; un-commenting `# >>>`, indenting a doctest under a
  header, or editing `>>>`/`...` line content is not.
- **Never reflow code lines** — fix markup around code, not the code.
- **Never introduce typographic quotes** (`’` `“` `”` `…`) — they're the
  corruption, not the fix.
- **Minimal edits around `Examples:` headers** — adding a blank line *after*
  the header plus indenting the body changes napoleon's parsing; the minimal
  safe fix for a glued doctest is ONLY the blank line before `>>>`.
- Keep edits per-module and reviewable: `git diff` after each module.

## Step 5 — Verify

**(a) Doctest semantics preserved.** Run the touched module's doctests before
AND after editing; results must be identical:

```bash
python -m pytest --doctest-modules \
  -o doctest_optionflags='ELLIPSIS IGNORE_EXCEPTION_DETAIL' \
  "$TARGET/$PKG/MODULE.py" -q > /tmp/doctests_after.txt 2>&1
echo "exit=$?"; tail -2 /tmp/doctests_after.txt   # compare with the before-run
```

(Capture `/tmp/doctests_before.txt` the same way before your first edit.
Never read the exit code through a pipe — capture to a file and test `$?`.)

**(b) Strict local build** — if `docsrc/` exists in the repo:

```bash
make -C "$TARGET/docsrc" html SPHINXOPTS="-W --keep-going -n" \
  > /tmp/sphinx_build.log 2>&1
echo "exit=$?"
rg -n 'WARNING|ERROR' /tmp/sphinx_build.log | head -30
```

If `docsrc/` is missing, **ask the user** before scaffolding — `epythet
quickstart "$TARGET" --ignore tests/ scrap/ examples/` writes files into the
repo. Remember: a clean strict build still doesn't prove pattern 8 is gone
(step 3's warning).

**(c) Re-grep the built HTML** for symptom signatures (same greps as step 1,
against `docsrc/_build/html/module_docs/$PKG/*.html`). Counts should drop to
zero — or to the explained residue (e.g. intentional blockquotes). The
published pages update on the next docs publish; re-run step 1 then.

## Ecosystem-level issue: smartquotes

Sphinx smartquotes (default ON; epythet's conf doesn't set it) corrupts any
*unmarked* code in plain paragraphs (`'` → `’`, `...` → `…`). Per-docstring
double-backticking fixes each instance, but the root mitigation is
`smartquotes = False` in **epythet's conf template** — that's an upstream
change. Propose filing an issue on https://github.com/i2mint/epythet; do NOT
hack the target repo's docs config.

## Scope guardrails

- **Edits docstring text only** — never code logic, signatures, imports,
  dependencies, or versions.
- **Never breaks existing tests**: doctest runs before/after must match; if a
  fix requires changing doctest behavior (option 3 above), get explicit
  user approval first.
- Diagnosis (steps 1-2, dry-runs) is read-only. Edits are applied per-module
  with review; `repair_package(write_to_files=True)` only after its dry run.
- Does NOT set up or repair docs publishing, GitHub Pages, or CI docs jobs.
- Does NOT write missing docstrings or fix README drift.
- Repo docs-config changes (e.g. local `smartquotes` override) and epythet
  changes are proposed to the user, never silently applied.

## Related skills

- Docs not published / 404 / Pages or gh-pages problems → **epythet-docs**
- Docstring *presence*, README execution/alignment, signature↔docstring
  drift → **wads-docs-coverage**
- Test coverage gaps and writing tests → **wads-test-coverage**
- CI status, stub currency, publish health → **wads-ci-health**
- Whole-repo health pass and dispatch → **wads-repo-doctor**

## Closing checklist

- [ ] Symptom counts gathered (published pages and/or scanner) before editing
- [ ] epythet `repair_package` dry-run reviewed, then applied to the package
      dir only; `git diff` shows blank-line insertions only
- [ ] Remaining findings fixed per catalog, frequency order, each verified
      against the catalog entry (not just the scanner line)
- [ ] Commented-doctest blocks resolved via a user-chosen option
- [ ] Doctests pass identically before and after on every touched module
- [ ] Strict build (`-W --keep-going -n`) clean, or failures explained
- [ ] Built/published HTML re-grepped: symptom counts at zero or explained
- [ ] smartquotes issue proposed upstream (epythet), not patched locally
