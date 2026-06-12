# RST docstring rendering — pattern catalog

Twelve docstring mistake patterns that mis-render under epythet (Sphinx + RST +
napoleon + smartquotes-on), **ordered by observed frequency** in an audit of 30
published module pages across six i2mint GitHub Pages sites (dol, i2, creek,
mongodol, wads, py2store). Each entry: rendered symptom, grep-able source
signature, a real confirmed before/after, the fix, and a safety note.

Pattern ids match the output of `scripts/scan_docstrings.py`.

| # | id | observed frequency |
|---|---|---|
| 1 | `single-backtick` | 597 occurrences on 24/29 pages (~70% of all defects) |
| 2 | `google-section` | 81 literal header paragraphs |
| 3 | `bare-asterisk` | 60 red "problematic" spans on 12 pages |
| 4 | `accidental-blockquote` | 38 blockquotes, ~20 clearly unintended |
| 5 | `collapsed-bullets` | 27 paragraphs on 8 pages |
| 6 | `field-list` | 14 paragraphs, mostly i2 |
| 7 | `commented-doctest` | 11 paragraphs on 6 pages |
| 8 | `doctest-glue` | 10 paragraphs on 8 pages |
| 9 | `markdown-fence` | 5 literal ``` + ~6 single-tick fence blocks |
| 10 | `bare-code-prose` | unranked — nearly every paragraph that mentions code |
| 11 | `over-indent-continuation` | ~2 confirmed, high-visibility |
| 12 | `indented-list-blockquote` | module headers (i2/signatures and others) |

**Meta-finding — authors get no warning.** docutils system messages are
suppressed in the published pages (no `<div class="system-message">` renders
anywhere); the only in-page evidence of a source error is the red asterisks of
pattern 3. Authors therefore get zero feedback unless they run a strict local
build — which is why these mistakes persist across years of releases.

---

## 1. `single-backtick` — \`code\` renders as italic title-reference, not code

**By far the most frequent defect (~70% of all observed).** Worst page:
https://i2mint.github.io/i2/module_docs/i2/signatures.html (319 instances).

- **Rendered symptom:** `Sig`, `dict`, `mk_wrapper` appear as italicized
  `<cite>` text — visually like emphasis, not code. A pair of single backticks
  spanning lines swallows all the words between into one italic run.
- **Cause:** markdown habit. In RST a single backtick is the *default role*
  (title reference); inline code needs **double** backticks.
- **Source signature:** `rg -nP '(?<![\x60:])\x60[A-Za-z_][\w.()*]*\x60(?!\x60)' --type py`
  (lone backtick pairs around identifier-like content; `\x60` = backtick).
- **Before** (creek/labeling.py:97; rendered at
  https://i2mint.github.io/creek/module_docs/creek/labeling.html):

  ```
  A LabeledElement that uses a `dict` as the labels container.
  ```

- **After:**

  ```
  A LabeledElement that uses a ``dict`` as the labels container.
  ```

- **Fix:** convert single backticks to double backticks.
- **Safety:** mechanically safe in this ecosystem — genuine title-references
  were never observed in the audit — but eyeball each one. Do NOT touch:
  role usages (``:func:`name```), hyperlink references (`` `text`_ ``), or
  content inside doctest/literal blocks. If the author meant *emphasis*, use
  `*text*` instead of doubling.

## 2. `google-section` — literal "Returns:" / "Parameters:" text

napoleon IS enabled in epythet's conf, yet 81 literal section headers render as
plain paragraph text. Three distinct sub-causes that look identical in output:

- **Rendered symptom:** the paragraph literally starts with `Returns:` /
  `Parameters:` / `Examples:` instead of a styled field/rubric; the body
  renders as one wrapped paragraph (with literal hyphens when bullets were
  used).
- **Source signature:** `rg -n '^\s*(Returns?|Args|Parameters|Examples?|Raises|Yields|Note):\s*\S' --type py`
  (same-line content); for the other two sub-causes use the scanner.

**(a) Content on the same line as the header** — napoleon needs the body
indented on *following* lines. Before (dol/appendable.py:306):

```
Returns: an item -> (key, val) function
```

After (either form):

```
Returns:
    an item -> (key, val) function
```

or the RST field form: `:return: an item -> (key, val) function`.

**(b) Section body not indented under the header** — before (dol/filesys.py
`create_directories`, ~lines 80-100; rendered at
https://i2mint.github.io/dol/module_docs/dol/filesys.html):

```
Returns:
bool: True if the directory was created successfully, False otherwise.
```

After:

```
Returns:
    bool: True if the directory was created successfully, False otherwise.
```

**(c) Markdown hyphen-bullets as the section body** — before
(dol/caching.py:1549):

```
Parameters:
- func (callable, optional): The method to be decorated. If not provided, ...
```

After (proper Google style — indented entries, no hyphens, `Args:` for
parameters):

```
Args:
    func (callable, optional): The method to be decorated. If not
        provided, a partially applied decorator will be returned.
```

- **Safety:** prefer repairing to proper Google style (napoleon is on) over
  converting to `:param:` fields. napoleon's exact requirements: content
  indented under the header, `name (type): description` entries, no hyphen
  bullets, no same-line content. ⚠️ For `Examples:` headers be minimal: if the
  body is a doctest, the safe fix is ONLY a blank line before `>>>` (see
  pattern 8) — indenting the doctest under the header changes what napoleon
  emits and risks altering doctest collection.

## 3. `bare-asterisk` — unescaped `*args` produces red "problematic" spans

- **Rendered symptom:** `*` / `**` wrapped in `<span class="problematic">`
  (red, hyperlinked to a removed footnote) — e.g.
  https://i2mint.github.io/dol/module_docs/dol/appendable.html shows
  `key_str_format.format(<span class="problematic">*</span>key_params)`.
  This is the ONLY pattern that leaves a visible error marker on the page.
- **Cause:** bare `*args` / `**kwargs` / `*key_params` in plain paragraph
  text — docutils parses `*` as an emphasis opener with no closer.
- **Source signature:** `rg -nP '(?<![\w\x60*])\*{1,2}[A-Za-z_]\w*' --type py`
  (noisy: also matches valid `*emphasis*` and napoleon `*args:` entries —
  verify each).
- **Before** (dol/appendable.py:302):

  ```
  such that key_str_format.format(*key_params) or
  ```

- **After:**

  ```
  such that ``key_str_format.format(*key_params)`` or
  ```

- **Fix:** wrap the whole code fragment in double backticks. Escaping (`\*`)
  works but code markup is almost always what was meant.
- **Safety:** leave matched `*emphasis*` / `**strong**` pairs alone; leave
  `*args:` entry names inside Google `Args:` sections alone (napoleon handles
  those).

## 4. `accidental-blockquote` — stray indentation becomes a quote

- **Rendered symptom:** an indented chunk renders as an indented prose
  `<blockquote>` (proportional font, smartquote-corrupted) instead of a code
  block; or a wrapped continuation line floats off as its own blockquote.
- **Cause (flavor a):** indented code/text after a paragraph WITHOUT `::`.
- **Cause (flavor b):** wrapped continuation lines indented deeper than the
  first line of their sentence (dol/caching.py:1550-1551 — "will be returned
  for later application." floats off alone).
- **Source signature:** indented non-bullet block right after a blank line,
  where the preceding paragraph doesn't end with `::` (use the scanner — pure
  regex over-triggers badly here).
- **Before** (dol/sources.py:944-948):

  ```
  Note: A more significant version of Attrs, along with many tools based on it,
  was moved to pypi package: guide.


      pip install guide
  ```

- **After:**

  ```
  A more significant version of Attrs, along with many tools based on it,
  was moved to pypi package guide::

      pip install guide
  ```

- **Fix:** for intended code, end the intro with `::` + blank line + indent.
  For wrapped prose, keep continuation lines at the SAME indent as the first
  line of the sentence.
- **Safety:** roughly half the audited blockquotes were intentional — judge
  each; never "fix" a deliberate quotation.

## 5. `collapsed-bullets` — list glued into one paragraph

- **Rendered symptom:** `Main Use Cases:` followed by `- Property caching: ...`
  renders as ONE `<p>` with literal hyphens and hard-wrapped lines — no `<ul>`.
  Seen on https://i2mint.github.io/wads/module_docs/wads/pack.html,
  dol/base, dol/caching, i2/signatures, i2/wrapper.
- **Cause:** RST requires a blank line before a list; markdown doesn't.
- **Source signature:** `rg -nU '^[^\n\s-][^\n]*\n\s*- ' --type py` (non-bullet
  line directly followed by a bullet; the scanner is more precise).
- **Before** (dol/caching.py:7-8, module docstring):

  ```
  Main Use Cases:
  - Property caching: Cache expensive computations that only need to be run once
  ```

- **After:**

  ```
  Main Use Cases:

  - Property caching: Cache expensive computations that only need to be run once
  ```

- **Fix:** one blank line between the intro line and the first bullet; also
  keep a blank line after the list.
- **Safety:** pure whitespace insertion — but if the "intro" is a Google
  section header (`Parameters:`), this is pattern 2(c) instead: fix the
  section, don't just add a blank line.

## 6. `field-list` — literal `:param x: ...` text in a paragraph

Three distinct causes that look identical in output (literal `:param` text)
but need different edits:

- **Rendered symptom:** `:param attrs: An attribute name...` rendered inline
  in the paragraph as plain text instead of a Parameters table.

**(a) No blank line between description and the first field** — before
(i2/deco.py:427-428):

```
Asserts, at construction time, that the class contains a specific set of attributes
:param attrs: An attribute name (string) or a list of attribute names ...
```

After: insert one blank line between the paragraph and `:param`.

**(b) Continuation lines not indented** — before (i2/wrapper.py:1223-1224):

```
:param inner_sig: The signature of wrapped, inner
function itself)
```

After (continuation indented under the field):

```
:param inner_sig: The signature of wrapped, inner
    function itself
```

**(c) Malformed field names** — before (i2/signatures.py:734):

```
:param include_all_when_var_keywords_in_params=False,
```

A `=False,` inside the field name is invalid syntax and **poisons all
subsequent fields** — fixing only the blank line will NOT resolve the
paragraph. After:

```
:param include_all_when_var_keywords_in_params: Whether to ... Defaults to False.
```

- **Source signature:** `rg -n '^\s*:param\s+[^:\n]*=' --type py` for (c);
  the scanner detects all three.
- **Safety:** diagnose which sub-cause applies before editing; in a long field
  list, one malformed name breaks everything below it.

## 7. `commented-doctest` — `# >>> ...` soup

- **Rendered symptom:** blocks like `# >>> def bar(x, y=1, **kwargs1):` render
  as plain paragraphs with literal `#`, `>>>`, smartquote-curled quotes and
  `…` — readers can't tell it's intentionally disabled code. Seen on
  i2/signatures, i2/routing_forest, i2/deco, i2/footprints, dol/paths,
  dol/util.
- **Cause:** doctests disabled by prefixing `#` inside the docstring (often
  with `# TODO:`); docutils treats them as ordinary text.
- **Source signature:** `rg -n '^\s*#\s*>>>' --type py`
- **Real example:** i2/signatures.py:1915-1937 (a `# TODO:` block that even
  contains markdown ``` fences and a `# >>>` run).
- **Fix — three options** (present them; default to the second):
  1. **Delete** the block (or move it to an issue/TODO file).
  2. **Convert to an indented literal block after `::`** — renders as code,
     is NOT collected by doctest:

     ```
     TODO: Would like to make this work (reordering)::

         >>> # currently fails with:
         >>> # ValueError: non-default argument follows default argument
     ```

  3. **Fix and re-enable** the doctest (only if you can make it pass).
- **Safety:** option 3 changes what doctest collects and executes — run the
  module's doctests after. Options 1-2 are doctest-neutral.

## 8. `doctest-glue` — doctest glued into the preceding paragraph

- **Rendered symptom:** `>>>` prompts appear inline inside a `<p>`, no grey
  doctest box, and the code is smartquote-corrupted (`('apple',)` becomes
  `(‘apple’,)`) — uncopyable and unrunnable.
- **Cause:** no blank line between narrative text and the `>>>` line.
- **Source signature:** non-blank, non-doctest line directly followed by a
  `>>>` line (the scanner and epythet's `diagnose_doctest_code_blocks` both
  detect this exactly).
- **Before** (creek/infinite_sequence.py:325-326 — note the correct sibling 8
  lines earlier in the same docstring, "You can slice with step:" + blank
  line + doctest, renders perfectly):

  ```
  You can slice with negatives
  >>> s[2:-2]
  [2, 3]
  ```

- **After:**

  ```
  You can slice with negatives:

  >>> s[2:-2]
  [2, 3]
  ```

- **Fix:** ONLY add a blank line before the `>>>` line. Auto-fixable:
  `from epythet import repair_package` (see SKILL.md step 3).
- **Safety:** ⚠️ a strict Sphinx build (`-W -n`) is verifiably SILENT on this
  breaker — a clean build does not mean it's absent. Never touch the `>>>`
  line's content or its expected output; the blank line above is the entire
  fix.

## 9. `markdown-fence` — ``` fences in RST docstrings

- **Rendered symptom A:** literal ```` ```python ```` and ```` ``` ```` lines
  visible in output, the code between rendered as plain wrapped paragraphs
  (https://i2mint.github.io/i2/module_docs/i2/footprints.html).
- **Rendered symptom B (single-tick fence):** a lone `` ` `` on a line before
  and after code renders the whole block as one giant multi-line `<cite>`
  italic run (dol/trans `mk_wrapper`).
- **Source signature:** `rg -n '^\s*(#\s*)?\x60{3}|^\s*\x60\s*$' --type py`
- **Before** (dol/trans.py:2466-2468):

  ````
  ```
  wrapper = mk_wrapper(wrap_cls)
  ```
  ````

- **After:**

  ```
  ::

      wrapper = mk_wrapper(wrap_cls)
  ```

  (or `.. code-block:: python` + blank line + indented code).
- **Safety:** if the fenced content is a `>>>` session, converting to a
  literal block keeps it OUT of doctest collection (status quo preserved);
  un-fencing it into a bare doctest block would make doctest start executing
  it — don't do that unless the user wants the example tested.

## 10. `bare-code-prose` — unmarked inline code, smartquote-corrupted

- **Rendered symptom:** expressions like `wrapped_func = decorator(func,
  **params)` or `cache=lambda self: Files(f'/cache/{self.user_id}/')` appear
  in proportional font with typographic quotes (`'` → `’`, `"` → `”`) and
  Unicode ellipsis `…` — copy-paste produces a SyntaxError. Amplifies
  patterns 2, 4, 7, 8 (any code landing in a plain `<p>` gets corrupted).
- **Cause:** code embedded in plain paragraph text with no inline markup,
  combined with Sphinx `smartquotes` defaulting to ON (epythet's conf does
  not set it).
- **Source signature:** code-ish fragments (dotted calls, `lambda`, kwarg
  calls) outside backticks — the scanner's `bare-code-prose` check;
  informational, highest false-positive rate.
- **Before** (dol/caching.py:837-838):

  ```
  This enables instance-specific caching, e.g.:
  cache=lambda self: Files(f'/cache/{self.user_id}/')
  ```

- **After:**

  ```
  This enables instance-specific caching, e.g.
  ``cache=lambda self: Files(f'/cache/{self.user_id}/')``
  ```

- **Fix:** wrap every inline code fragment in double backticks.
- **Safety / ecosystem note:** the smartquote corruption itself is an
  epythet-conf-level issue — `smartquotes = False` in epythet's conf template
  would stop corrupting *unmarked* code ecosystem-wide. Propose that as an
  issue on https://github.com/i2mint/epythet — do NOT hack the target repo's
  docs config.

## 11. `over-indent-continuation` — accidental definition list

- **Rendered symptom:** mid-sentence text becomes a bold `<dt>` ("A string
  format such that") with the rest in an indented `<dd>`; in flattened text,
  words run together ("A string format such
  thatkey_str_format.format(*key_params)") — plus pattern-3 red asterisks.
  Confirmed on https://i2mint.github.io/dol/module_docs/dol/appendable.html.
- **Cause:** continuation lines indented several levels deeper than their
  first line — docutils parses term + definition.
- **Before** (dol/appendable.py:300-302 — continuation 8 spaces deeper):

  ```
  key_str_format: A string format such that
          key_str_format.format(*key_params) or
  ```

- **After** (uniform 4-space continuation, code in double backticks):

  ```
  key_str_format: A string format such that
      ``key_str_format.format(*key_params)`` or ``key_str_format.format(**key_params)``
      will produce the desired key string
  ```

- **Fix:** re-indent continuations to exactly 4 spaces beyond the entry's
  first line.
- **Safety:** whitespace-only on prose lines; never re-indent doctest or
  literal-block lines.

## 12. `indented-list-blockquote` — list wrapped in a blockquote

- **Rendered symptom:** a "How to:" list renders inside `<blockquote>`,
  indented oddly relative to surrounding text, sometimes with sub-items
  detached (module header of
  https://i2mint.github.io/i2/module_docs/i2/signatures.html).
- **Cause:** the bullet list is indented relative to its intro paragraph; in
  RST, indentation relative to the preceding paragraph means block quote.
- **Before** (i2/signatures.py:3-5, module docstring):

  ```
  How to:

      - get names, kinds, defaults, annotations
  ```

- **After** (list at the SAME indentation as the intro, blank lines around):

  ```
  How to:

  - get names, kinds, defaults, annotations
  - make signatures flexibly
  ```

- **Fix:** dedent the list to the intro paragraph's level.
- **Safety:** whitespace-only; keep blank lines before and after the list.
