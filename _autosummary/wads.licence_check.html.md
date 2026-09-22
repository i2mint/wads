# wads.licence_check

Audit the licence perimeter of a package’s installed dependency closure.

A licence rule nobody checks is a sentence, not a policy. This module walks the
**installed** metadata of everything a bare `pip install <pkg>` pulls in and
reports every distribution whose declared licence falls outside the perimeter.

Run it from the command line:

```default
wads-licence-check                      # the project in the current directory
wads-licence-check path/to/project
wads-licence-check . --python .venv/bin/python   # read ANOTHER environment
```

Exit code is `1` when the perimeter is breached, `0` when it holds.

Configure it in the audited project’s `pyproject.toml`:

```default
[tool.wads.licence]
enabled = true                # read by wads.ci_config for the CI gate
allowed = ["MIT", "BSD", "Apache-2.0", "ISC"]
forbidden = ["AGPL", "GPL", "LGPL", "SSPL", "BUSL", "Elastic-2.0", "RAIL"]
include-extras = []           # [] = hard deps only; ["*"] = every extra
unknown-is-failure = true
unclassified-is-failure = false

[tool.wads.licence.exceptions]
certifi = "MPL-2.0 - file-level weak copyleft over an unmodified CA bundle."
```

`allowed` and `forbidden` REPLACE the defaults, they do not extend them, so
a hand-written list is a narrowing unless it is a superset of
[`DFLT_ALLOWED`](#wads.licence_check.DFLT_ALLOWED) / [`DFLT_FORBIDDEN`](#wads.licence_check.DFLT_FORBIDDEN). [`self_check()`](#wads.licence_check.self_check) refuses to run
a policy that has narrowed away a whole licence family, which is the guard that
makes this survivable – but the honest move is to start from the defaults.

Write patterns as TOML **literal** strings (single quotes):

```default
forbidden = ['\bGPL', '\bLGPL']      # right
forbidden = ["\bGPL", "\bLGPL"]      # WRONG: \b is a backspace character
```

TOML basic strings process escapes, so `"\bGPL"` reaches the regex engine as
`"\x08GPL"` and silently matches nothing at all.

Exit codes: `0` the perimeter holds, `1` it is breached, `2` the tool could
not run (bad config, unreadable environment, a policy that cannot detect).

Three properties are load-bearing, and each has a recorded failure behind it.

**1. The precision ladder** ([`declare()`](#wads.licence_check.declare)). Read, in order, the PEP 639
`License-Expression`, then the `License ::` trove classifiers, and only then
the **first line** of the free-text `License` field. Never substring-scan that
field whole: numpy is BSD-3-Clause and its field carries an LGPL URL for a
vendored component’s notice, so a naive scan reports numpy as copyleft. A
one-field check is wrong in both directions: `click` declares a PEP 639
expression and **no** classifiers, `i2` declares neither and only a free-text
field, and Arize Phoenix declares Elastic-2.0 in the field with no classifier at
all – so a classifier-only gate sails straight past it.

**2. The transitive closure** ([`closure()`](#wads.licence_check.closure)). A copyleft distribution three
levels down is exactly as much a part of what a downstream consumer inherits as
a declared one. This is how `html2text` (GPL-3.0-or-later) sat unnoticed. The
walk reads *installed* metadata, so its answer is a fact about the environment
it runs in, not about the package – [`LicenceReport.render()`](#wads.licence_check.LicenceReport.render) says so out
loud rather than letting the number read as universal.

**3. A demonstrated true positive** ([`self_check()`](#wads.licence_check.self_check)). A detector with no
demonstrated true positive is a detector nobody has checked: emptying the
forbidden patterns left the originating test suite entirely green, because every
other assertion only ever checked that *nothing* matched. So every run first
proves the live policy still catches known-copyleft declarations *and* still
clears known-permissive ones, and refuses to report at all if it cannot.

This module’s own file imports nothing outside the standard library (`tomli`
only on Python 3.10, where `tomllib` does not yet exist), so it adds no
dependency beyond wads’s own core and needs no toolchain of its own. That is a
claim about the file, not isolation: importing it runs `wads/__init__`, which
pulls wads’s core dependencies into `sys.modules` like any other import.

### Module Attributes

| [`DFLT_ALLOWED`](#wads.licence_check.DFLT_ALLOWED)             | Permissive families, matched case-insensitively against the declaration.                                                                    |
|---------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------|
| [`DFLT_COPYLEFT`](#wads.licence_check.DFLT_COPYLEFT)            | Reciprocal (copyleft) families.                                                                                                             |
| [`DFLT_NON_COMMERCIAL`](#wads.licence_check.DFLT_NON_COMMERCIAL)      | Non-commercial / source-available families.                                                                                                 |
| [`DFLT_FORBIDDEN`](#wads.licence_check.DFLT_FORBIDDEN)           | What a policy forbids unless it says otherwise.                                                                                             |
| [`UNKNOWN_DECLARATIONS`](#wads.licence_check.UNKNOWN_DECLARATIONS)     | the terms may live in a repo file no scanner reads, which is exactly where LGPL and non-commercial model weights have been found hiding.    |
| [`LADDER`](#wads.licence_check.LADDER)                   | The metadata fields the ladder reads, in decreasing order of precision.                                                                     |
| [`COPYLEFT_CANARIES`](#wads.licence_check.COPYLEFT_CANARIES)        | Real declarations, copied from installed `dist-info` and from the official trove classifier list, that a policy is measured against.        |
| [`CANARY_FAMILIES`](#wads.licence_check.CANARY_FAMILIES)          | The families [`COPYLEFT_CANARIES`](#wads.licence_check.COPYLEFT_CANARIES) covers, in declaration order.                               |
| [`PERMISSIVE_CANARIES`](#wads.licence_check.PERMISSIVE_CANARIES)      | Real declarations that any usable policy must still clear.                                                                                  |
| [`ALL_EXTRAS`](#wads.licence_check.ALL_EXTRAS)               | `include_extras` value meaning "every optional-dependency group".                                                                           |
| [`POLICY_TOML_PATH`](#wads.licence_check.POLICY_TOML_PATH)         | Where the policy lives in `pyproject.toml`.                                                                                                 |
| [`CLEAN_STATUSES`](#wads.licence_check.CLEAN_STATUSES)           | Statuses that never fail a run.                                                                                                             |
| [`DEPENDENCIES_KEY`](#wads.licence_check.DEPENDENCIES_KEY)         | `[project]` key holding the hard requirements.                                                                                              |
| [`POLICY_TOML_KEYS`](#wads.licence_check.POLICY_TOML_KEYS)         | TOML keys accepted in `[tool.wads.licence]`.                                                                                                |
| [`LEGACY_POLICY_KEYS`](#wads.licence_check.LEGACY_POLICY_KEYS)       | Keys from the earlier, hand-written table shape that shipped in a couple of repos before this module existed, mapped to what to do instead. |
| [`EXCEPTION_TABLE_NAME_KEY`](#wads.licence_check.EXCEPTION_TABLE_NAME_KEY) | Keys read off an `[[tool.wads.licence.exceptions]]` array-of-tables entry.                                                                  |
| [`THIS_ENVIRONMENT`](#wads.licence_check.THIS_ENVIRONMENT)         | Readers bound to the interpreter running this module.                                                                                       |
| [`EXIT_OK`](#wads.licence_check.EXIT_OK)                  | Exit codes, so the CI step and a human read the same numbers.                                                                               |
| [`EXIT_BREACH`](#wads.licence_check.EXIT_BREACH)              | Exit codes, so the CI step and a human read the same numbers.                                                                               |
| [`EXIT_ERROR`](#wads.licence_check.EXIT_ERROR)               | Exit codes, so the CI step and a human read the same numbers.                                                                               |

### Functions

| [`check`](#wads.licence_check.check)([pkg_dir, policy, readers])                  | Audit a project's installed dependency closure against its policy.                                                |
|-----------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------|
| [`closure`](#wads.licence_check.closure)(names, /, \*[, read_requires, ...])        | `names` PLUS everything they pull in, as INSTALLED in this environment.                                           |
| [`declare`](#wads.licence_check.declare)(dist_name, /, \*[, read_metadata])         | The DECLARATION, in order of precision -- never the licence document.                                             |
| [`declared_dependencies`](#wads.licence_check.declared_dependencies)([pkg_dir, ...])              | Every distribution the project DECLARES, read from `pyproject.toml`.                                              |
| [`declared_licence`](#wads.licence_check.declared_licence)(dist_name, /, \*[, ...])          | The declared licence text alone -- [`declare()`](#wads.licence_check.declare) without the source. |
| [`declared_requirements`](#wads.licence_check.declared_requirements)([pkg_dir, ...])              | Every REQUIREMENT STRING the project declares, markers and all.                                                   |
| [`has_environment_marker`](#wads.licence_check.has_environment_marker)(requirement, /)             | Whether a requirement is gated on an ENVIRONMENT marker, not just an extra.                                       |
| [`main`](#wads.licence_check.main)([argv])                                       | Console-script entry point.                                                                                       |
| [`normalise`](#wads.licence_check.normalise)(name)                                    | PEP 503 normalisation, so `ruamel.yaml` and `ruamel-yaml` are one name.                                           |
| [`read_pyproject`](#wads.licence_check.read_pyproject)([pkg_dir])                          | Parse `pyproject.toml` from a directory (or a direct path to the file).                                           |
| [`readers_for`](#wads.licence_check.readers_for)(search_path, /)                        | Metadata readers that see the distributions installed on `search_path`.                                           |
| [`requirement_extra`](#wads.licence_check.requirement_extra)(requirement)                     | The extra a requirement is conditional on, or `''` if it is a hard one.                                           |
| [`requirement_name`](#wads.licence_check.requirement_name)(requirement)                      | The distribution name out of a `Requires-Dist` / requirement string.                                              |
| [`search_path_of`](#wads.licence_check.search_path_of)(python_executable, /)               | The `sys.path` of ANOTHER interpreter, so its packages can be read.                                               |
| [`self_check`](#wads.licence_check.self_check)(policy, /)                              | Prove the policy still detects, and still discriminates.                                                          |
| [`verdict`](#wads.licence_check.verdict)(name, /, \*, policy[, read_metadata, ...]) | Judge one distribution against `policy`.                                                                          |
| [`walk_closure`](#wads.licence_check.walk_closure)(requirements, /, \*[, ...])           | The closure of `requirements` (raw requirement strings), marked up.                                               |

### Classes

| [`Canary`](#wads.licence_check.Canary)(family, label, declaration)               | One real licence declaration a policy is measured against.                                           |
|---------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------|
| [`ClosureWalk`](#wads.licence_check.ClosureWalk)(names, conditional)                  | The closure, plus which of its members are reachable only conditionally.                             |
| [`Declaration`](#wads.licence_check.Declaration)(text, source)                        | What a distribution declares, and *which field* said so.                                             |
| [`LicencePolicy`](#wads.licence_check.LicencePolicy)([allowed, forbidden, ...])         | The rule set a perimeter check is run against.                                                       |
| [`LicenceReport`](#wads.licence_check.LicenceReport)(policy, declared, verdicts[, ...]) | What a run found: the closure it walked, and a verdict for every member.                             |
| [`MetadataReaders`](#wads.licence_check.MetadataReaders)(read_metadata, read_requires)    | The pair of readers [`check()`](#wads.licence_check.check) walks the closure with. |
| [`SelfCheck`](#wads.licence_check.SelfCheck)(caught, uncovered_families)            | What a policy proved about itself before it was allowed to report.                                   |
| [`Status`](#wads.licence_check.Status)()                                         | The verdicts a distribution can receive.                                                             |
| [`Verdict`](#wads.licence_check.Verdict)(name, status[, declaration, note])       | One distribution's standing against the policy.                                                      |

### Exceptions

| [`DetectorError`](#wads.licence_check.DetectorError)   | The live policy cannot detect anything, so its green result means nothing.   |
|------------------------------------------------------------------|------------------------------------------------------------------------------|

### wads.licence_check.ALL_EXTRAS *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= '\*'*

`include_extras` value meaning “every optional-dependency group”.

### wads.licence_check.CANARY_FAMILIES *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('LGPL', 'GPL', 'AGPL', 'Nethack')*

The families [`COPYLEFT_CANARIES`](#wads.licence_check.COPYLEFT_CANARIES) covers, in declaration order.

### wads.licence_check.CLEAN_STATUSES *: [frozenset](https://docs.python.org/3/builtins/stdtypes.html#frozenset)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= frozenset({'allowed', 'excepted', 'not-applicable'})*

Statuses that never fail a run. `NOT_INSTALLED` is deliberately absent:
a hard dependency the check could not read is the same confident-green
failure as reading the wrong environment. A dependency gated on an
environment marker gets `NOT_APPLICABLE` instead, which is clean.

### wads.licence_check.COPYLEFT_CANARIES *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[Canary](#wads.licence_check.Canary), ...]* *= (('LGPL', 'argh / PyGithub (legacy LGPL classifier)', 'License :: OSI Approved :: GNU Library or Lesser General Public License (LGPL)'), ('LGPL', 'LGPLv2 classifier', 'License :: OSI Approved :: GNU Lesser General Public License v2 (LGPLv2)'), ('LGPL', 'LGPLv2+ classifier', 'License :: OSI Approved :: GNU Lesser General Public License v2 or later (LGPLv2+)'), ('LGPL', 'LGPLv3 classifier', 'License :: OSI Approved :: GNU Lesser General Public License v3 (LGPLv3)'), ('LGPL', 'LGPLv3+ classifier', 'License :: OSI Approved :: GNU Lesser General Public License v3 or later (LGPLv3+)'), ('LGPL', 'spelled-out LGPL', 'GNU Lesser General Public License'), ('LGPL', 'bare LGPLv3+', 'LGPLv3+'), ('LGPL', 'soxr', 'LGPL-2.1-or-later'), ('GPL', 'GPLv3 classifier', 'License :: OSI Approved :: GNU General Public License v3 (GPLv3)'), ('GPL', 'GPLv2+ classifier', 'License :: OSI Approved :: GNU General Public License v2 or later (GPLv2+)'), ('GPL', 'spelled-out GPL', 'GNU General Public License v2 or later'), ('GPL', 'html2text', 'GPL-3.0-or-later'), ('AGPL', 'AGPLv3+ classifier', 'License :: OSI Approved :: GNU Affero General Public License v3 or later (AGPLv3+)'), ('AGPL', 'AGPLv3 classifier', 'License :: OSI Approved :: GNU Affero General Public License v3'), ('AGPL', 'spelled-out AGPL', 'GNU Affero General Public License v3'), ('AGPL', 'bare AGPLv3', 'AGPLv3'), ('AGPL', 'ultralytics', 'AGPL-3.0'), ('Nethack', 'Nethack GPL classifier', 'License :: OSI Approved :: Nethack General Public License'))*

Real declarations, copied from installed `dist-info` and from the official
trove classifier list, that a policy is measured against. See
[`self_check()`](#wads.licence_check.self_check), which requires each FAMILY to be caught whole or not at
all.

The list is deliberately wider than the acronyms: it was hand-picked from the
same mental model as the patterns once, and the four LGPL spellings that
escaped were exactly the ones nobody thought to write down. Every officially
published GPL-family trove classifier spelling is here, plus the bare
acronym-with-version and the fully-spelled-out prose forms.

### *class* wads.licence_check.Canary(family, label, declaration)

Bases: [`NamedTuple`](https://docs.python.org/3/library/typing.html#typing.NamedTuple)

One real licence declaration a policy is measured against.

`family` is what makes the measurement useful. Permitting a whole family
is a coherent stance somebody can take on purpose – LGPL for dynamically
linked libraries is the usual one. Catching *part* of a family is never a
stance: it means the author meant to catch it and the spelling got away.
[`self_check()`](#wads.licence_check.self_check) allows the first and refuses the second.

#### declaration *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

Alias for field number 2

#### family *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

Alias for field number 0

#### label *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

Alias for field number 1

### *class* wads.licence_check.ClosureWalk(names, conditional)

Bases: [`NamedTuple`](https://docs.python.org/3/library/typing.html#typing.NamedTuple)

The closure, plus which of its members are reachable only conditionally.

`conditional` is every name that could ONLY be reached by following a
requirement gated on an environment marker (`python_version`,
`sys_platform`, …). Those are the names whose absence from the
environment being read is expected rather than alarming; every other absence
means the check did not get to look at something the project genuinely
requires.

#### conditional *: [frozenset](https://docs.python.org/3/builtins/stdtypes.html#frozenset)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]*

Alias for field number 1

#### names *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]*

Alias for field number 0

### wads.licence_check.DEPENDENCIES_KEY *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'dependencies'*

`[project]` key holding the hard requirements. Named because two different
absences of it mean two different things – see [`declared_requirements()`](#wads.licence_check.declared_requirements).

### wads.licence_check.DFLT_ALLOWED *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('\\\\bMIT\\\\b', '\\\\bBSD\\\\b', '\\\\b0BSD\\\\b', '\\\\bApache[- ]?2', '\\\\bApache Software License\\\\b', '\\\\bISC\\\\b', '\\\\bPython Software Foundation\\\\b', '\\\\bPSF\\\\b', '\\\\bHPND\\\\b', '\\\\bUnlicense\\\\b', '\\\\bCC0\\\\b', '\\\\bZlib\\\\b', '\\\\bBoost Software License\\\\b', '\\\\bBSL[- ]?1\\\\.0\\\\b')*

Permissive families, matched case-insensitively against the declaration.
`\b0BSD\b` is its own entry because `\bBSD\b` cannot reach inside
`0BSD` – there is no word boundary between a digit and a letter – so the
SPDX id of one of the most permissive licences in existence would otherwise
land in UNCLASSIFIED.

### wads.licence_check.DFLT_COPYLEFT *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('\\\\bAGPL', '\\\\bAffero\\\\b', '\\\\bGPL(?![\\\\w.+-]\*\\\\s+with\\\\b)', '\\\\bGNU General Public\\\\b', '\\\\bLGPL', '\\\\bLesser General Public\\\\b', '\\\\bLibrary General Public\\\\b', '\\\\bNethack General Public\\\\b', '\\\\bEUPL\\\\b')*

Reciprocal (copyleft) families.

Every pattern here is anchored at its LEFT edge only, and that asymmetry is
the whole point. `\bGPL` cannot reach inside `LGPL` (there is no word
boundary between `L` and `G`), so LGPL and AGPL need their own entries –
but a TRAILING `\b` on those entries is a hole, not a safeguard: it cannot
match `LGPLv3`, `LGPLv2+` or `AGPLv3`, which is every modern trove
classifier and most SPDX-adjacent free text. A gate built to catch copyleft
spent its first life letting the four commonest LGPL spellings straight
through. [`COPYLEFT_CANARIES`](#wads.licence_check.COPYLEFT_CANARIES) now pins all of them.

Every family carries a spelled-out pattern beside its acronym, because the
prose forms (“GNU General Public License v2 or later”) carry no acronym at
all. They are deliberately family-SPECIFIC rather than one broad `General
Public License`: a policy that permits one family and gates on the others is
a coherent stance, and a cross-family pattern makes it inexpressible –
[`self_check()`](#wads.licence_check.self_check) would see a family caught in part and refuse to run.

The lookahead on `\bGPL` spares the SPDX `WITH <exception>` spellings
(`GPL-2.0-only WITH Classpath-exception-2.0`, `GPLv2 with linking
exception`) and nothing subtler; anything subtler belongs in `exceptions`,
with a written reason, rather than in a regex nobody will re-derive.

### wads.licence_check.DFLT_FORBIDDEN *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('\\\\bAGPL', '\\\\bAffero\\\\b', '\\\\bGPL(?![\\\\w.+-]\*\\\\s+with\\\\b)', '\\\\bGNU General Public\\\\b', '\\\\bLGPL', '\\\\bLesser General Public\\\\b', '\\\\bLibrary General Public\\\\b', '\\\\bNethack General Public\\\\b', '\\\\bEUPL\\\\b', '\\\\bBusiness Source\\\\b', '\\\\bBUSL\\\\b', '\\\\bSSPL\\\\b', '\\\\bElastic[- ]?(2\\\\.0|License|v2)\\\\b', '(?:\\\\b|-)(?:open)?rail(?:-m)?\\\\b', '\\\\bCC[- ]BY[- ]NC\\\\b', '\\\\bNon[- ]?Commercial\\\\b', '\\\\bProprietary\\\\b')*

What a policy forbids unless it says otherwise.

### wads.licence_check.DFLT_NON_COMMERCIAL *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('\\\\bBusiness Source\\\\b', '\\\\bBUSL\\\\b', '\\\\bSSPL\\\\b', '\\\\bElastic[- ]?(2\\\\.0|License|v2)\\\\b', '(?:\\\\b|-)(?:open)?rail(?:-m)?\\\\b', '\\\\bCC[- ]BY[- ]NC\\\\b', '\\\\bNon[- ]?Commercial\\\\b', '\\\\bProprietary\\\\b')*

Non-commercial / source-available families. These are not copyleft, but they
restrict redistribution or hosting, and a classifier-only gate cannot see
them: Arize Phoenix ships Elastic-2.0 in its `License` field with no trove
classifier at all.

### *class* wads.licence_check.Declaration(text, source)

Bases: [`NamedTuple`](https://docs.python.org/3/library/typing.html#typing.NamedTuple)

What a distribution declares, and *which field* said so.

Carrying the source is not decoration: it is the difference between “argh is
LGPL” and “argh is LGPL according to its trove classifier”, and only the
second is a claim a reader can go and check.

#### *property* is_blank *: [bool](https://docs.python.org/3/builtins/functions.html#bool)*

True when the distribution declared nothing usable.

#### source *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

Alias for field number 1

#### text *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

Alias for field number 0

### *exception* wads.licence_check.DetectorError

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

The live policy cannot detect anything, so its green result means nothing.

### wads.licence_check.EXCEPTION_TABLE_NAME_KEY *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'dependency'*

Keys read off an `[[tool.wads.licence.exceptions]]` array-of-tables entry.
`dependency` and `reason` are required; the rest are adjudication
provenance and are folded into the rendered reason so a reader sees when the
call was made and where to go and argue with it.

### wads.licence_check.EXIT_BREACH *= 1*

Exit codes, so the CI step and a human read the same numbers.

### wads.licence_check.EXIT_ERROR *= 2*

Exit codes, so the CI step and a human read the same numbers.

### wads.licence_check.EXIT_OK *= 0*

Exit codes, so the CI step and a human read the same numbers.

### wads.licence_check.LADDER *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('License-Expression', 'Classifier', 'License')*

The metadata fields the ladder reads, in decreasing order of precision.

### wads.licence_check.LEGACY_POLICY_KEYS *: [Mapping](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= mappingproxy({'allow': 'rename it to \`allowed\` (it pairs with \`forbidden\`, where \`allow\` had no counterpart)', 'deny': 'rename it to \`forbidden\`', 'project_licence': "drop it -- the project's own licence is \`[project].license\`, and restating it here is a second source of truth that nothing reads", 'project-licence': "drop it -- the project's own licence is \`[project].license\`, and restating it here is a second source of truth that nothing reads"})*

Keys from the earlier, hand-written table shape that shipped in a couple of
repos before this module existed, mapped to what to do instead.

Two spellings of the same table is worse than either one: a repo written
against the other shape reads as configured and is not. These are rejected
rather than silently aliased – but rejected with the migration, not with a
bare “unknown key”, because the person hitting this did not choose it.

### *class* wads.licence_check.LicencePolicy(allowed=('\\\\\\\\bMIT\\\\\\\\b', '\\\\\\\\bBSD\\\\\\\\b', '\\\\\\\\b0BSD\\\\\\\\b', '\\\\\\\\bApache[- ]?2', '\\\\\\\\bApache Software License\\\\\\\\b', '\\\\\\\\bISC\\\\\\\\b', '\\\\\\\\bPython Software Foundation\\\\\\\\b', '\\\\\\\\bPSF\\\\\\\\b', '\\\\\\\\bHPND\\\\\\\\b', '\\\\\\\\bUnlicense\\\\\\\\b', '\\\\\\\\bCC0\\\\\\\\b', '\\\\\\\\bZlib\\\\\\\\b', '\\\\\\\\bBoost Software License\\\\\\\\b', '\\\\\\\\bBSL[- ]?1\\\\\\\\.0\\\\\\\\b'), forbidden=('\\\\\\\\bAGPL', '\\\\\\\\bAffero\\\\\\\\b', '\\\\\\\\bGPL(?![\\\\\\\\w.+-]\*\\\\\\\\s+with\\\\\\\\b)', '\\\\\\\\bGNU General Public\\\\\\\\b', '\\\\\\\\bLGPL', '\\\\\\\\bLesser General Public\\\\\\\\b', '\\\\\\\\bLibrary General Public\\\\\\\\b', '\\\\\\\\bNethack General Public\\\\\\\\b', '\\\\\\\\bEUPL\\\\\\\\b', '\\\\\\\\bBusiness Source\\\\\\\\b', '\\\\\\\\bBUSL\\\\\\\\b', '\\\\\\\\bSSPL\\\\\\\\b', '\\\\\\\\bElastic[- ]?(2\\\\\\\\.0|License|v2)\\\\\\\\b', '(?:\\\\\\\\b|-)(?:open)?rail(?:-m)?\\\\\\\\b', '\\\\\\\\bCC[- ]BY[- ]NC\\\\\\\\b', '\\\\\\\\bNon[- ]?Commercial\\\\\\\\b', '\\\\\\\\bProprietary\\\\\\\\b'), exceptions=mappingproxy({}), include_extras=(), unknown_is_failure=True, unclassified_is_failure=False)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

The rule set a perimeter check is run against.

`exceptions` maps a distribution name to the WRITTEN reason it is
tolerated. Listing beats silence: a name here is a decision somebody made
and can be asked about, where a name quietly missing from `forbidden` is
not.

#### exception_for(name,)

The recorded reason `name` is tolerated, or `''`.

Matched on the PEP 503 normalised name, so a policy written with
`typing_extensions` still clears the distribution installed metadata
calls `typing-extensions`. Getting this wrong is invisible: the
exception simply never applies and the report keeps flagging a name
somebody believes they already adjudicated.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> LicencePolicy(exceptions={'Ruamel.YAML': 'audited'}).exception_for(
...     'ruamel-yaml')
'audited'
```

#### *classmethod* from_mapping(config,)

Build a policy from a `[tool.wads.licence]` table.

Accepts both TOML-style `include-extras` and Python-style
`include_extras`. An unrecognised key is an error rather than a
silently ignored typo – a misspelt `forbiden` would leave the
perimeter on its defaults while reading as configured.

Value TYPES are checked too, and for the same reason the key names are:
`allowed = "MIT"` used to become the three regexes `M`, `I`, `T`
without a word, and an `exceptions` array-of-tables used to collapse
into `{'dependency': 'reason'}`. Both read as configured. Neither was.

* **Return type:**
  [`LicencePolicy`](#wads.licence_check.LicencePolicy)

```pycon
>>> policy = LicencePolicy.from_mapping(
...     {'allowed': ['MIT'], 'include-extras': ['*'], 'unknown-is-failure': False}
... )
>>> policy.allowed, policy.include_extras, policy.unknown_is_failure
(('MIT',), ('*',), False)
>>> policy.forbidden == DFLT_FORBIDDEN  # untouched keys keep their defaults
True
```

`exceptions` takes either the terse map or the array-of-tables that
carries an adjudication record (see `_exceptions_mapping()`):

```pycon
>>> LicencePolicy.from_mapping({'exceptions': [
...     {'dependency': 'PyGithub', 'reason': 'Accepted.', 'decided': '2026-08-30'}
... ]}).exception_for('pygithub')
'Accepted. [decided: 2026-08-30]'
```

```pycon
>>> try:
...     LicencePolicy.from_mapping({'forbiden': ['GPL']})
... except ValueError as error:
...     print(error)
unknown [tool.wads.licence] key 'forbiden'; known keys are: allowed, enabled,
exceptions, forbidden, include-extras, unclassified-is-failure, unknown-is-failure
```

A key from the earlier hand-written table shape is rejected with the
migration rather than with a bare “unknown key”:

```pycon
>>> try:
...     LicencePolicy.from_mapping({'allow': ['MIT']})
... except ValueError as error:
...     print(error)
[tool.wads.licence] key 'allow' is from the earlier table shape: rename it to
`allowed` (it pairs with `forbidden`, where `allow` had no counterpart)
```

#### *classmethod* from_pyproject(pkg_dir='.', , , pyproject=None)

The policy declared in `[tool.wads.licence]`, or the defaults.

* **Return type:**
  [`LicencePolicy`](#wads.licence_check.LicencePolicy)

#### matched_allowed(declaration,)

The first permissive pattern `declaration` matches, or `''`.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

#### matched_forbidden(declaration,)

The first forbidden pattern `declaration` matches, or `''`.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

#### permissive_option(declaration,)

A disjunct of `declaration` that is permissive and not forbidden.

SPDX’s `OR` is a genuine choice offered to the recipient, so a
declaration is only as restrictive as its most permissive option. Reading
the whole string as one blob gets that backwards – `marisa-trie`
declares `MIT AND (BSD-2-Clause OR LGPL-2.1-or-later)` and was failed on
the option nobody has to take:

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> LicencePolicy().permissive_option('MIT AND (BSD-2-Clause OR LGPL-2.1-or-later)')
'MIT AND (BSD-2-Clause'
```

When every option is restricted there is nothing to pick, and the
declaration stands as it is:

```pycon
>>> LicencePolicy().permissive_option('LGPL-2.1-only OR MPL-1.1')
''
```

### *class* wads.licence_check.LicenceReport(policy, declared, verdicts, canaries=(), uncovered_families=(), pkg_dir='.')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

What a run found: the closure it walked, and a verdict for every member.

#### as_dict()

A JSON-serialisable view, for fleet-wide sweeps.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

#### *property* closure *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]*

Every distribution the walk reached.

#### *property* failures *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[Verdict](#wads.licence_check.Verdict), ...]*

The verdicts that make this run fail, under this policy.

#### of_status(\*statuses)

Every verdict whose status is one of `statuses`.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`Verdict`](#wads.licence_check.Verdict), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]

#### *property* ok *: [bool](https://docs.python.org/3/builtins/functions.html#bool)*

Whether the perimeter holds.

#### render()

A human-readable report, failures first.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

#### *property* stale_exceptions *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]*

Recorded exceptions for distributions the walk never reached.

An exception for a distribution that has left the tree is stale advice,
and one whose licence has since changed is worse: it reads as
adjudicated when nobody has looked at the current terms. Reported, not
failed – an extra is often the reason, and breaking a build over a
tidiness issue is how gates get switched off.

### *class* wads.licence_check.MetadataReaders(read_metadata, read_requires)

Bases: [`NamedTuple`](https://docs.python.org/3/library/typing.html#typing.NamedTuple)

The pair of readers [`check()`](#wads.licence_check.check) walks the closure with.

#### read_metadata *: [Callable](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[[str](https://docs.python.org/3/builtins/stdtypes.html#str)], [Any](https://docs.python.org/3/library/typing.html#typing.Any)]*

Alias for field number 0

#### read_requires *: [Callable](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[[str](https://docs.python.org/3/builtins/stdtypes.html#str)], [list](https://docs.python.org/3/builtins/stdtypes.html#list) | [None](https://docs.python.org/3/builtins/constants.html#None)]*

Alias for field number 1

### wads.licence_check.PERMISSIVE_CANARIES *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('MIT', 'BSD-3-Clause', '0BSD', 'Apache-2.0', 'Apache Software License', 'ISC', 'BSL-1.0', 'License :: OSI Approved :: Boost Software License 1.0 (BSL-1.0)')*

Real declarations that any usable policy must still clear. A policy that
flags these is not strict, it is broken, and it would fail every repo.
`BSL-1.0` is the Boost Software License, permissive and OSI-approved –
it is here because a `\bBSL\b` pattern aimed at the Business Source
License (`BUSL-1.1`) flags it, and that pattern shipped once already.

### wads.licence_check.POLICY_TOML_KEYS *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('enabled', 'allowed', 'forbidden', 'exceptions', 'include-extras', 'unknown-is-failure', 'unclassified-is-failure')*

TOML keys accepted in `[tool.wads.licence]`. `enabled` is read by
[`wads.ci_config`](wads.ci_config.html.md#module-wads.ci_config) for the CI gate rather than by the policy itself.

### wads.licence_check.POLICY_TOML_PATH *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('tool', 'wads', 'licence')*

Where the policy lives in `pyproject.toml`.

### *class* wads.licence_check.SelfCheck(caught, uncovered_families)

Bases: [`NamedTuple`](https://docs.python.org/3/library/typing.html#typing.NamedTuple)

What a policy proved about itself before it was allowed to report.

#### caught *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]*

Alias for field number 0

#### uncovered_families *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]*

Alias for field number 1

### *class* wads.licence_check.Status

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

The verdicts a distribution can receive. Not an Enum: these are printed.

### wads.licence_check.THIS_ENVIRONMENT *= (<function metadata>, <function requires>)*

Readers bound to the interpreter running this module.

### wads.licence_check.UNKNOWN_DECLARATIONS *: [frozenset](https://docs.python.org/3/builtins/stdtypes.html#frozenset)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= frozenset({'', 'NOASSERTION', 'NONE', 'UNKNOWN'})*

the
terms may live in a repo file no scanner reads, which is exactly where LGPL
and non-commercial model weights have been found hiding.

* **Type:**
  Declarations that say nothing. Blank is not “fine”, it is *unaudited*

### *class* wads.licence_check.Verdict(name, status, declaration=('', ''), note='')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One distribution’s standing against the policy.

#### *property* is_clean *: [bool](https://docs.python.org/3/builtins/functions.html#bool)*

Whether this verdict is one that never fails a run.

### wads.licence_check.check(pkg_dir='.', /, \*, policy=None, readers=(<function metadata>, <function requires>))

Audit a project’s installed dependency closure against its policy.

`policy=None` loads `[tool.wads.licence]` from the project’s
`pyproject.toml`, falling back to the module defaults.

Raises [`DetectorError`](#wads.licence_check.DetectorError) before reading anything if the live policy
could not detect every known-copyleft canary declaration, if the project does
not declare its dependencies statically, and again if not one declared
dependency is installed – all states in which a green result would be a lie
rather than a finding.

A dependency that IS declared and is NOT installed here is a failure, not a
footnote: it is a piece of the perimeter nobody looked at, and the previous
all-or-nothing refusal let one installed survivor turn three unread copyleft
dependencies into a green. The one honest exception is a requirement gated on
an environment marker (`tomli; python_version < "3.11"`), which gets
`NOT_APPLICABLE` and is reported without failing.

* **Return type:**
  [`LicenceReport`](#wads.licence_check.LicenceReport)

### wads.licence_check.closure(names, /, \*, read_requires=<function requires>, include_extras=())

`names` PLUS everything they pull in, as INSTALLED in this environment.

Checking only the declared names is a smaller claim than it reads as:
`pip install <pkg>` installs their transitive closure, and a copyleft
distribution three levels down is exactly as much a part of what a
downstream consumer inherits.

By default the walk skips requirements gated on `extra == "..."`, because
a bare install does not take them. `include_extras=('*',)` takes all of
them; a tuple of names takes those.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]

```pycon
>>> tree = {
...     'citeget': ['html2text', 'requests', 'pytest; extra == "test"'],
...     'html2text': [],
...     'requests': ['certifi'],
...     'certifi': [],
... }
>>> closure(['citeget'], read_requires=tree.get)
('certifi', 'citeget', 'html2text', 'requests')
>>> closure(['citeget'], read_requires=tree.get, include_extras=('test',))
('certifi', 'citeget', 'html2text', 'pytest', 'requests')
```

An uninstalled name simply ends that branch – it is still reported by
[`check()`](#wads.licence_check.check), but it cannot contribute requirements it does not have:

```pycon
>>> closure(['citeget', 'nowhere'], read_requires=tree.get)
('certifi', 'citeget', 'html2text', 'nowhere', 'requests')
```

[`walk_closure()`](#wads.licence_check.walk_closure) is the same walk, and additionally says which members
are reachable only through an environment-marker-gated requirement.

### wads.licence_check.declare(dist_name, /, \*, read_metadata=<function metadata>)

The DECLARATION, in order of precision – never the licence document.

`read_metadata` is the seam onto the metadata source; it must return
something with `.get` / `.get_all`, which is what both
[`importlib.metadata.metadata()`](https://docs.python.org/3/library/importlib.metadata.html#importlib.metadata.metadata) and a parsed `METADATA` email message
give you.

* **Return type:**
  [`Declaration`](#wads.licence_check.Declaration)

```pycon
>>> from email import message_from_string
>>> def fake(name, records=None):
...     return message_from_string(records[name])
>>> import functools
>>> records = {
...     'click': 'License-Expression: BSD-3-Clause\n',
...     'argh': ('Classifier: License :: OSI Approved :: '
...              'GNU Library or Lesser General Public License (LGPL)\n'),
...     'i2': 'License: Apache Software License\n',
... }
>>> read = functools.partial(fake, records=records)
>>> declare('click', read_metadata=read)
Declaration(text='BSD-3-Clause', source='License-Expression')
>>> declare('i2', read_metadata=read)
Declaration(text='Apache Software License', source='License')
>>> declare('argh', read_metadata=read).source
'Classifier'
```

The free-text field is read ONE LINE deep. numpy’s field is the whole
48k-character licence document, and it contains an LGPL URL for a vendored
component’s notice – substring-scanning it reports BSD-3-Clause numpy as
copyleft:

```pycon
>>> numpy_field = 'Copyright (c) 2005-2024, NumPy Developers.\n  http://x/lgpl'
>>> read_numpy = functools.partial(fake, records={'numpy': f'License: {numpy_field}'})
>>> declare('numpy', read_metadata=read_numpy).text
'Copyright (c) 2005-2024, NumPy Developers.'
```

### wads.licence_check.declared_dependencies(pkg_dir='.', , , include_extras=(), pyproject=None)

Every distribution the project DECLARES, read from `pyproject.toml`.

Derived, never restated: a dependency added to `pyproject.toml` and
forgotten in a hand-written list is a dependency the perimeter never looks
at, and the perimeter reads as green either way.

[`declared_requirements()`](#wads.licence_check.declared_requirements) without the version specifiers and markers.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]

```pycon
>>> declared_dependencies(pyproject={'project': {
...     'dependencies': ['html2text', 'requests>=2'],
...     'optional-dependencies': {'test': ['pytest']},
... }})
('html2text', 'requests')
>>> declared_dependencies(include_extras=('test',), pyproject={'project': {
...     'dependencies': ['html2text'],
...     'optional-dependencies': {'test': ['pytest']},
... }})
('html2text', 'pytest')
```

### wads.licence_check.declared_licence(dist_name, /, \*, read_metadata=<function metadata>)

The declared licence text alone – [`declare()`](#wads.licence_check.declare) without the source.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### wads.licence_check.declared_requirements(pkg_dir='.', , , include_extras=(), pyproject=None)

Every REQUIREMENT STRING the project declares, markers and all.

Requirement strings rather than bare names, because the marker is the
information: `tomli; python_version < "3.11"` being absent from a 3.12
environment is expected, and `html2text` being absent is the check not
having looked.

Parsed with a real TOML parser rather than scanned as text. That is not a
style preference: a text scan that ends the `dependencies` array at the
first `]` stops at the first requirement carrying an extra
(`"uvicorn[standard]"`) and silently drops every name below it – one line
disarming the whole check. A parser cannot have that bug.

An ABSENT `dependencies` key, or one listed in `dynamic`, is refused
rather than read as zero. `dependencies = []` is a project saying it has
none; a missing key is a project whose requirements live somewhere this
function cannot see (`setup.py`, `requirements.txt`), and reporting
“declared: 0 … PERIMETER HOLDS” over it is the confident-green failure this
module exists to stop.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]

```pycon
>>> declared_requirements(pyproject={'project': {
...     'dependencies': ['html2text', 'requests>=2'],
...     'optional-dependencies': {'test': ['pytest']},
... }})
('html2text', 'requests>=2')
>>> try:
...     declared_requirements(pyproject={'project': {
...         'name': 'x', 'dynamic': ['dependencies']}})
... except DetectorError as error:
...     print(str(error)[:59])
this project lists `dependencies` in [project].dynamic, so
```

### wads.licence_check.has_environment_marker(requirement,)

Whether a requirement is gated on an ENVIRONMENT marker, not just an extra.

This is the one honest reason a declared dependency can be missing from the
environment being read. The gate runs on one interpreter, on one OS, so a
dependency gated on `python_version < "3.11"` or `sys_platform ==
"win32"` is structurally invisible – and an absent-but-required
distribution is the same confident-green failure as reading the wrong
environment altogether. Telling the two apart is what lets one be a note and
the other a failure.

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

```pycon
>>> has_environment_marker('tomli>=1.0.0; python_version < "3.11"')
True
>>> has_environment_marker('pytest; extra == "test"')
False
>>> has_environment_marker('requests>=2')
False
```

### wads.licence_check.main(argv=None)

Console-script entry point. Returns the process exit code.

* **Return type:**
  [`int`](https://docs.python.org/3/builtins/functions.html#int)

### wads.licence_check.normalise(name)

PEP 503 normalisation, so `ruamel.yaml` and `ruamel-yaml` are one name.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> normalise('Ruamel.YAML')
'ruamel-yaml'
```

### wads.licence_check.read_pyproject(pkg_dir='.')

Parse `pyproject.toml` from a directory (or a direct path to the file).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### wads.licence_check.readers_for(search_path,)

Metadata readers that see the distributions installed on `search_path`.

* **Return type:**
  [`MetadataReaders`](#wads.licence_check.MetadataReaders)

```pycon
>>> import sys
>>> readers = readers_for(sys.path)
>>> readers.read_metadata('wads')['Name']
'wads'
```

### wads.licence_check.requirement_extra(requirement)

The extra a requirement is conditional on, or `''` if it is a hard one.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> requirement_extra('anthropic; extra == "vision"')
'vision'
>>> requirement_extra('pydantic>=2')
''
```

### wads.licence_check.requirement_name(requirement)

The distribution name out of a `Requires-Dist` / requirement string.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> requirement_name('uvicorn[standard]>=0.20; python_version >= "3.9"')
'uvicorn'
```

### wads.licence_check.search_path_of(python_executable,)

The `sys.path` of ANOTHER interpreter, so its packages can be read.

This is what lets the CI gate run the tool from an isolated `uvx`
environment while auditing the project’s own `.venv`. Without it the tool
would read *its own* dependencies and report a confident, wrong green.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]

### wads.licence_check.self_check(policy,)

Prove the policy still detects, and still discriminates. Or refuse to run.

Three failure modes, all observed. A policy whose `forbidden` list has been
emptied reports every repo clean and nobody notices, because every other
assertion in a licence check only ever says that *nothing* matched. A policy
so broad it flags `MIT` fails every repo, which gets the gate switched off
within the day. And – the one that actually shipped – a policy that catches
*some* spellings of a family while missing the commonest ones reads as a pass
on the strength of the spellings it does catch.

So the bar is per FAMILY, caught whole or not at all. Permitting a family
outright is a stance somebody can take on purpose and defend; catching four
of a family’s nine spellings is never a stance, it is the bug. A family
nobody covers is reported rather than assumed – see
`LicenceReport.uncovered_families`, which puts it in every run’s output
so “we do not gate on GPL here” is a visible fact rather than an inference.

* **Return type:**
  [`SelfCheck`](#wads.licence_check.SelfCheck)

```pycon
>>> checked = self_check(LicencePolicy())
>>> len(checked.caught) == len(COPYLEFT_CANARIES), checked.uncovered_families
(True, ())
```

Dropping a whole family is allowed, and is then stated out loud:

```pycon
>>> lgpl_ok = LicencePolicy(forbidden=tuple(
...     p for p in DFLT_FORBIDDEN if 'LGPL' not in p and 'Lesser' not in p))
>>> self_check(lgpl_ok).uncovered_families
('LGPL',)
```

Catching only PART of a family is not. This is the shape of the real bug:
`\bLGPL\b` catches the legacy classifier and misses `LGPLv3`:

```pycon
>>> try:
...     self_check(LicencePolicy(forbidden=(r'\bAGPL', r'\bGNU Affero\b',
...                                        r'\bLGPL\b')))
... except DetectorError as error:
...     print('LGPLv3 classifier' in str(error))
True
```

A policy that detects nothing refuses to report:

```pycon
>>> try:
...     self_check(LicencePolicy(forbidden=()))
... except DetectorError as error:
...     print(str(error)[:52])
this policy's `forbidden` patterns catch none of the
```

And so does one broad enough to flag everything:

```pycon
>>> try:
...     self_check(LicencePolicy(forbidden=(r'\bAGPL', r'\bApache\b')))
... except DetectorError as error:
...     print('over-broad, and it names what it wrongly flagged:',
...           'Apache-2.0' in str(error))
over-broad, and it names what it wrongly flagged: True
```

### wads.licence_check.verdict(name, /, \*, policy, read_metadata=<function metadata>, conditional=False)

Judge one distribution against `policy`.

An adjudicated exception wins over everything, including a forbidden match:
that is what recording one *means*, and the reason travels with it.

* **Return type:**
  [`Verdict`](#wads.licence_check.Verdict)

```pycon
>>> from email import message_from_string
>>> import functools
>>> records = {'html2text': 'License-Expression: GPL-3.0-or-later\n',
...            'requests': 'License-Expression: Apache-2.0\n',
...            'certifi': 'License-Expression: MPL-2.0\n',
...            'mystery': 'Name: mystery\n'}
>>> read = functools.partial(lambda n, r: message_from_string(r[n]), r=records)
>>> verdict('html2text', policy=LicencePolicy(), read_metadata=read).status
'forbidden'
>>> verdict('requests', policy=LicencePolicy(), read_metadata=read).status
'allowed'
```

MPL-2.0 is deliberately neither: it is file-level weak copyleft, so it is
not forbidden, and it matches no permissive family either. It surfaces as
`unclassified` – a decision to make, not a build to break.

```pycon
>>> verdict('certifi', policy=LicencePolicy(), read_metadata=read).status
'unclassified'
>>> verdict('mystery', policy=LicencePolicy(), read_metadata=read).status
'unknown'
```

A declaration matching a forbidden AND a permissive pattern is not simply
forbidden. Where SPDX’s `OR` says the recipient picks, the permissive pick
is taken; where the two spellings merely sit side by side – which is what
joining a distribution’s `License ::` classifiers produces – nobody knows
which applies to which file, so it becomes a question rather than a failure:

```pycon
>>> both = {'marisa-trie': ('License-Expression: '
...                         'MIT AND (BSD-2-Clause OR LGPL-2.1-or-later)\n'),
...         'docutils': ('Classifier: License :: Public Domain\n'
...                      'Classifier: License :: OSI Approved :: BSD License\n'
...                      'Classifier: License :: OSI Approved :: '
...                      'GNU General Public License (GPL)\n')}
>>> read_both = functools.partial(lambda n, r: message_from_string(r[n]), r=both)
>>> verdict('marisa-trie', policy=LicencePolicy(), read_metadata=read_both).status
'allowed'
>>> verdict('docutils', policy=LicencePolicy(), read_metadata=read_both).status
'unclassified'
```

### wads.licence_check.walk_closure(requirements, /, \*, read_requires=<function requires>, include_extras=())

The closure of `requirements` (raw requirement strings), marked up.

* **Return type:**
  [`ClosureWalk`](#wads.licence_check.ClosureWalk)

```pycon
>>> tree = {'app': ['requests', 'tomli; python_version < "3.11"'],
...         'requests': ['certifi'], 'certifi': [], 'tomli': []}
>>> walk = walk_closure(['app'], read_requires=tree.get)
>>> walk.names
('app', 'certifi', 'requests', 'tomli')
>>> sorted(walk.conditional)
['tomli']
```
