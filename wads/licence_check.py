"""Audit the licence perimeter of a package's installed dependency closure.

A licence rule nobody checks is a sentence, not a policy. This module walks the
**installed** metadata of everything a bare ``pip install <pkg>`` pulls in and
reports every distribution whose declared licence falls outside the perimeter.

Run it from the command line::

    wads-licence-check                      # the project in the current directory
    wads-licence-check path/to/project
    wads-licence-check . --python .venv/bin/python   # read ANOTHER environment

Exit code is ``1`` when the perimeter is breached, ``0`` when it holds.

Configure it in the audited project's ``pyproject.toml``::

    [tool.wads.licence]
    enabled = true                # read by wads.ci_config for the CI gate
    allowed = ["MIT", "BSD", "Apache-2.0", "ISC"]
    forbidden = ["AGPL", "GPL", "LGPL", "SSPL", "BUSL", "Elastic-2.0", "RAIL"]
    include-extras = []           # [] = hard deps only; ["*"] = every extra
    unknown-is-failure = true
    unclassified-is-failure = false

    [tool.wads.licence.exceptions]
    certifi = "MPL-2.0 - file-level weak copyleft over an unmodified CA bundle."

``allowed`` and ``forbidden`` REPLACE the defaults, they do not extend them, so
a hand-written list is a narrowing unless it is a superset of
:data:`DFLT_ALLOWED` / :data:`DFLT_FORBIDDEN`. :func:`self_check` refuses to run
a policy that has narrowed away a whole licence family, which is the guard that
makes this survivable -- but the honest move is to start from the defaults.

Write patterns as TOML **literal** strings (single quotes)::

    forbidden = ['\\bGPL', '\\bLGPL']      # right
    forbidden = ["\\bGPL", "\\bLGPL"]      # WRONG: \\b is a backspace character

TOML basic strings process escapes, so ``"\\bGPL"`` reaches the regex engine as
``"\\x08GPL"`` and silently matches nothing at all.

Exit codes: ``0`` the perimeter holds, ``1`` it is breached, ``2`` the tool could
not run (bad config, unreadable environment, a policy that cannot detect).

Three properties are load-bearing, and each has a recorded failure behind it.

**1. The precision ladder** (:func:`declare`). Read, in order, the PEP 639
``License-Expression``, then the ``License ::`` trove classifiers, and only then
the **first line** of the free-text ``License`` field. Never substring-scan that
field whole: numpy is BSD-3-Clause and its field carries an LGPL URL for a
vendored component's notice, so a naive scan reports numpy as copyleft. A
one-field check is wrong in both directions: ``click`` declares a PEP 639
expression and **no** classifiers, ``i2`` declares neither and only a free-text
field, and Arize Phoenix declares Elastic-2.0 in the field with no classifier at
all -- so a classifier-only gate sails straight past it.

**2. The transitive closure** (:func:`closure`). A copyleft distribution three
levels down is exactly as much a part of what a downstream consumer inherits as
a declared one. This is how ``html2text`` (GPL-3.0-or-later) sat unnoticed. The
walk reads *installed* metadata, so its answer is a fact about the environment
it runs in, not about the package -- :meth:`LicenceReport.render` says so out
loud rather than letting the number read as universal.

**3. A demonstrated true positive** (:func:`self_check`). A detector with no
demonstrated true positive is a detector nobody has checked: emptying the
forbidden patterns left the originating test suite entirely green, because every
other assertion only ever checked that *nothing* matched. So every run first
proves the live policy still catches known-copyleft declarations *and* still
clears known-permissive ones, and refuses to report at all if it cannot.

This module's own file imports nothing outside the standard library (``tomli``
only on Python 3.10, where ``tomllib`` does not yet exist), so it adds no
dependency beyond wads's own core and needs no toolchain of its own. That is a
claim about the file, not isolation: importing it runs ``wads/__init__``, which
pulls wads's core dependencies into ``sys.modules`` like any other import.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import re
import subprocess
import sys
import types
from collections.abc import Callable, Iterable, Mapping
from importlib.metadata import PackageNotFoundError
from importlib.metadata import metadata as _metadata
from importlib.metadata import requires as _requires
from pathlib import Path
from typing import Any, NamedTuple, Optional

if sys.version_info >= (3, 11):  # pragma: no cover - version-dependent
    import tomllib
else:  # pragma: no cover - version-dependent
    try:
        import tomli as tomllib
    except ImportError:  # pragma: no cover
        tomllib = None  # type: ignore[assignment]


# --------------------------------------------------------------------------------------
# Policy vocabulary. Every default is a named constant, never a literal in a branch.
# --------------------------------------------------------------------------------------

#: Permissive families, matched case-insensitively against the declaration.
#: ``\b0BSD\b`` is its own entry because ``\bBSD\b`` cannot reach inside
#: ``0BSD`` -- there is no word boundary between a digit and a letter -- so the
#: SPDX id of one of the most permissive licences in existence would otherwise
#: land in UNCLASSIFIED.
DFLT_ALLOWED: tuple[str, ...] = (
    r"\bMIT\b",
    r"\bBSD\b",
    r"\b0BSD\b",
    r"\bApache[- ]?2",
    r"\bApache Software License\b",
    r"\bISC\b",
    r"\bPython Software Foundation\b",
    r"\bPSF\b",
    r"\bHPND\b",
    r"\bUnlicense\b",
    r"\bCC0\b",
    r"\bZlib\b",
    r"\bBoost Software License\b",
    r"\bBSL[- ]?1\.0\b",
)

#: Reciprocal (copyleft) families.
#:
#: Every pattern here is anchored at its LEFT edge only, and that asymmetry is
#: the whole point. ``\bGPL`` cannot reach inside ``LGPL`` (there is no word
#: boundary between ``L`` and ``G``), so LGPL and AGPL need their own entries --
#: but a TRAILING ``\b`` on those entries is a hole, not a safeguard: it cannot
#: match ``LGPLv3``, ``LGPLv2+`` or ``AGPLv3``, which is every modern trove
#: classifier and most SPDX-adjacent free text. A gate built to catch copyleft
#: spent its first life letting the four commonest LGPL spellings straight
#: through. :data:`COPYLEFT_CANARIES` now pins all of them.
#:
#: Every family carries a spelled-out pattern beside its acronym, because the
#: prose forms ("GNU General Public License v2 or later") carry no acronym at
#: all. They are deliberately family-SPECIFIC rather than one broad ``General
#: Public License``: a policy that permits one family and gates on the others is
#: a coherent stance, and a cross-family pattern makes it inexpressible --
#: :func:`self_check` would see a family caught in part and refuse to run.
#:
#: The lookahead on ``\bGPL`` spares the SPDX ``WITH <exception>`` spellings
#: (``GPL-2.0-only WITH Classpath-exception-2.0``, ``GPLv2 with linking
#: exception``) and nothing subtler; anything subtler belongs in ``exceptions``,
#: with a written reason, rather than in a regex nobody will re-derive.
DFLT_COPYLEFT: tuple[str, ...] = (
    r"\bAGPL",
    r"\bAffero\b",
    r"\bGPL(?![\w.+-]*\s+with\b)",
    r"\bGNU General Public\b",
    r"\bLGPL",
    r"\bLesser General Public\b",
    r"\bLibrary General Public\b",
    r"\bNethack General Public\b",
    r"\bEUPL\b",
)

#: Non-commercial / source-available families. These are not copyleft, but they
#: restrict redistribution or hosting, and a classifier-only gate cannot see
#: them: Arize Phoenix ships Elastic-2.0 in its ``License`` field with no trove
#: classifier at all.
DFLT_NON_COMMERCIAL: tuple[str, ...] = (
    r"\bBusiness Source\b",
    # `\bBUSL\b` alone. NOT `\bBSL\b`: that is the SPDX id of the Boost
    # Software License 1.0 (`BSL-1.0`), which is permissive and OSI-approved.
    # The Business Source License is `BUSL-1.1`. One shared TLA, opposite
    # meanings -- `BSL-1.0` is pinned in PERMISSIVE_CANARIES so the confusion
    # cannot come back.
    r"\bBUSL\b",
    r"\bSSPL\b",
    r"\bElastic[- ]?(2\.0|License|v2)\b",
    # RAIL is almost never spelled bare: model licences arrive as
    # `creativeml-openrail-m` / `bigscience-openrail-m`. The leading
    # `(?:\b|-)` and trailing `\b` keep `guardrails-ai` and `railway` out.
    r"(?:\b|-)(?:open)?rail(?:-m)?\b",
    r"\bCC[- ]BY[- ]NC\b",
    r"\bNon[- ]?Commercial\b",
    r"\bProprietary\b",
)

#: What a policy forbids unless it says otherwise.
DFLT_FORBIDDEN: tuple[str, ...] = DFLT_COPYLEFT + DFLT_NON_COMMERCIAL

#: Declarations that say nothing. Blank is not "fine", it is *unaudited*: the
#: terms may live in a repo file no scanner reads, which is exactly where LGPL
#: and non-commercial model weights have been found hiding.
UNKNOWN_DECLARATIONS: frozenset[str] = frozenset({"", "UNKNOWN", "NONE", "NOASSERTION"})

#: The metadata fields the ladder reads, in decreasing order of precision.
LADDER: tuple[str, ...] = ("License-Expression", "Classifier", "License")


class Canary(NamedTuple):
    """One real licence declaration a policy is measured against.

    ``family`` is what makes the measurement useful. Permitting a whole family
    is a coherent stance somebody can take on purpose -- LGPL for dynamically
    linked libraries is the usual one. Catching *part* of a family is never a
    stance: it means the author meant to catch it and the spelling got away.
    :func:`self_check` allows the first and refuses the second.
    """

    family: str
    label: str
    declaration: str


#: Real declarations, copied from installed ``dist-info`` and from the official
#: trove classifier list, that a policy is measured against. See
#: :func:`self_check`, which requires each FAMILY to be caught whole or not at
#: all.
#:
#: The list is deliberately wider than the acronyms: it was hand-picked from the
#: same mental model as the patterns once, and the four LGPL spellings that
#: escaped were exactly the ones nobody thought to write down. Every officially
#: published GPL-family trove classifier spelling is here, plus the bare
#: acronym-with-version and the fully-spelled-out prose forms.
COPYLEFT_CANARIES: tuple[Canary, ...] = (
    Canary(
        "LGPL",
        "argh / PyGithub (legacy LGPL classifier)",
        "License :: OSI Approved :: GNU Library or Lesser General Public License (LGPL)",
    ),
    Canary(
        "LGPL",
        "LGPLv2 classifier",
        "License :: OSI Approved :: GNU Lesser General Public License v2 (LGPLv2)",
    ),
    Canary(
        "LGPL",
        "LGPLv2+ classifier",
        "License :: OSI Approved :: GNU Lesser General Public License v2 or later "
        "(LGPLv2+)",
    ),
    Canary(
        "LGPL",
        "LGPLv3 classifier",
        "License :: OSI Approved :: GNU Lesser General Public License v3 (LGPLv3)",
    ),
    Canary(
        "LGPL",
        "LGPLv3+ classifier",
        "License :: OSI Approved :: GNU Lesser General Public License v3 or later "
        "(LGPLv3+)",
    ),
    Canary("LGPL", "spelled-out LGPL", "GNU Lesser General Public License"),
    Canary("LGPL", "bare LGPLv3+", "LGPLv3+"),
    Canary("LGPL", "soxr", "LGPL-2.1-or-later"),
    Canary(
        "GPL",
        "GPLv3 classifier",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
    ),
    Canary(
        "GPL",
        "GPLv2+ classifier",
        "License :: OSI Approved :: GNU General Public License v2 or later (GPLv2+)",
    ),
    Canary("GPL", "spelled-out GPL", "GNU General Public License v2 or later"),
    Canary("GPL", "html2text", "GPL-3.0-or-later"),
    Canary(
        "AGPL",
        "AGPLv3+ classifier",
        "License :: OSI Approved :: GNU Affero General Public License v3 or later "
        "(AGPLv3+)",
    ),
    Canary(
        "AGPL",
        "AGPLv3 classifier",
        "License :: OSI Approved :: GNU Affero General Public License v3",
    ),
    Canary("AGPL", "spelled-out AGPL", "GNU Affero General Public License v3"),
    Canary("AGPL", "bare AGPLv3", "AGPLv3"),
    Canary("AGPL", "ultralytics", "AGPL-3.0"),
    Canary(
        "Nethack",
        "Nethack GPL classifier",
        "License :: OSI Approved :: Nethack General Public License",
    ),
)

#: The families :data:`COPYLEFT_CANARIES` covers, in declaration order.
CANARY_FAMILIES: tuple[str, ...] = tuple(
    dict.fromkeys(canary.family for canary in COPYLEFT_CANARIES)
)

#: Real declarations that any usable policy must still clear. A policy that
#: flags these is not strict, it is broken, and it would fail every repo.
#: ``BSL-1.0`` is the Boost Software License, permissive and OSI-approved --
#: it is here because a ``\bBSL\b`` pattern aimed at the Business Source
#: License (``BUSL-1.1``) flags it, and that pattern shipped once already.
PERMISSIVE_CANARIES: tuple[str, ...] = (
    "MIT",
    "BSD-3-Clause",
    "0BSD",
    "Apache-2.0",
    "Apache Software License",
    "ISC",
    "BSL-1.0",
    "License :: OSI Approved :: Boost Software License 1.0 (BSL-1.0)",
)

#: ``include_extras`` value meaning "every optional-dependency group".
ALL_EXTRAS: str = "*"

#: Where the policy lives in ``pyproject.toml``.
POLICY_TOML_PATH: tuple[str, ...] = ("tool", "wads", "licence")


class Status:
    """The verdicts a distribution can receive. Not an Enum: these are printed."""

    ALLOWED = "allowed"
    EXCEPTED = "excepted"
    FORBIDDEN = "forbidden"
    UNKNOWN = "unknown"
    UNCLASSIFIED = "unclassified"
    NOT_INSTALLED = "not-installed"
    NOT_APPLICABLE = "not-applicable"


#: Statuses that never fail a run. ``NOT_INSTALLED`` is deliberately absent:
#: a hard dependency the check could not read is the same confident-green
#: failure as reading the wrong environment. A dependency gated on an
#: environment marker gets ``NOT_APPLICABLE`` instead, which is clean.
CLEAN_STATUSES: frozenset[str] = frozenset(
    {Status.ALLOWED, Status.EXCEPTED, Status.NOT_APPLICABLE}
)


# --------------------------------------------------------------------------------------
# The precision ladder
# --------------------------------------------------------------------------------------


class Declaration(NamedTuple):
    """What a distribution declares, and *which field* said so.

    Carrying the source is not decoration: it is the difference between "argh is
    LGPL" and "argh is LGPL according to its trove classifier", and only the
    second is a claim a reader can go and check.
    """

    text: str
    source: str  # one of LADDER, or "" when nothing was declared

    @property
    def is_blank(self) -> bool:
        """True when the distribution declared nothing usable."""
        return self.text.strip().upper() in UNKNOWN_DECLARATIONS


def declare(
    dist_name: str,
    /,
    *,
    read_metadata: Callable[[str], Any] = _metadata,
) -> Declaration:
    """The DECLARATION, in order of precision -- never the licence document.

    ``read_metadata`` is the seam onto the metadata source; it must return
    something with ``.get`` / ``.get_all``, which is what both
    :func:`importlib.metadata.metadata` and a parsed ``METADATA`` email message
    give you.

    >>> from email import message_from_string
    >>> def fake(name, records=None):
    ...     return message_from_string(records[name])
    >>> import functools
    >>> records = {
    ...     'click': 'License-Expression: BSD-3-Clause\\n',
    ...     'argh': ('Classifier: License :: OSI Approved :: '
    ...              'GNU Library or Lesser General Public License (LGPL)\\n'),
    ...     'i2': 'License: Apache Software License\\n',
    ... }
    >>> read = functools.partial(fake, records=records)
    >>> declare('click', read_metadata=read)
    Declaration(text='BSD-3-Clause', source='License-Expression')
    >>> declare('i2', read_metadata=read)
    Declaration(text='Apache Software License', source='License')
    >>> declare('argh', read_metadata=read).source
    'Classifier'

    The free-text field is read ONE LINE deep. numpy's field is the whole
    48k-character licence document, and it contains an LGPL URL for a vendored
    component's notice -- substring-scanning it reports BSD-3-Clause numpy as
    copyleft:

    >>> numpy_field = 'Copyright (c) 2005-2024, NumPy Developers.\\n  http://x/lgpl'
    >>> read_numpy = functools.partial(fake, records={'numpy': f'License: {numpy_field}'})
    >>> declare('numpy', read_metadata=read_numpy).text
    'Copyright (c) 2005-2024, NumPy Developers.'
    """
    meta = read_metadata(dist_name)
    expression = (meta.get("License-Expression") or "").strip()
    if expression and expression.upper() not in UNKNOWN_DECLARATIONS:
        return Declaration(expression, "License-Expression")
    classifiers = [
        c for c in (meta.get_all("Classifier") or []) if c.startswith("License ::")
    ]
    if classifiers:
        return Declaration(" | ".join(classifiers), "Classifier")
    field = (meta.get("License") or "").strip()
    lines = field.splitlines()
    return Declaration(lines[0].strip() if lines else "", "License" if field else "")


def declared_licence(
    dist_name: str,
    /,
    *,
    read_metadata: Callable[[str], Any] = _metadata,
) -> str:
    """The declared licence text alone -- :func:`declare` without the source."""
    return declare(dist_name, read_metadata=read_metadata).text


# --------------------------------------------------------------------------------------
# The dependency closure
# --------------------------------------------------------------------------------------

#: SPDX's disjunction operator, which is uppercase by specification -- so this
#: cannot mistake the word "or" inside "GNU General Public License v2 or later"
#: for a choice the recipient gets to make.
_SPDX_OR = re.compile(r"\bOR\b")

_SPLIT_REQUIREMENT = re.compile(r"[<>=!~\[; ()]")
_EXTRA_MARKER = re.compile(r"""extra\s*==\s*["']([^"']+)["']""")
#: The ``extra == "..."`` clauses alone; what remains of a marker after they are
#: removed is an environment condition.
_MARKER_WITHOUT_EXTRA = re.compile(r"""extra\s*==\s*["'][^"']+["']""")


def normalise(name: str) -> str:
    """PEP 503 normalisation, so ``ruamel.yaml`` and ``ruamel-yaml`` are one name.

    >>> normalise('Ruamel.YAML')
    'ruamel-yaml'
    """
    return re.sub(r"[-_.]+", "-", name).strip().lower()


def requirement_name(requirement: str) -> str:
    """The distribution name out of a ``Requires-Dist`` / requirement string.

    >>> requirement_name('uvicorn[standard]>=0.20; python_version >= "3.9"')
    'uvicorn'
    """
    return normalise(_SPLIT_REQUIREMENT.split(requirement.strip(), maxsplit=1)[0])


def requirement_extra(requirement: str) -> str:
    """The extra a requirement is conditional on, or ``''`` if it is a hard one.

    >>> requirement_extra('anthropic; extra == "vision"')
    'vision'
    >>> requirement_extra('pydantic>=2')
    ''
    """
    found = _EXTRA_MARKER.search(requirement)
    return found.group(1) if found else ""


def has_environment_marker(requirement: str, /) -> bool:
    """Whether a requirement is gated on an ENVIRONMENT marker, not just an extra.

    This is the one honest reason a declared dependency can be missing from the
    environment being read. The gate runs on one interpreter, on one OS, so a
    dependency gated on ``python_version < "3.11"`` or ``sys_platform ==
    "win32"`` is structurally invisible -- and an absent-but-required
    distribution is the same confident-green failure as reading the wrong
    environment altogether. Telling the two apart is what lets one be a note and
    the other a failure.

    >>> has_environment_marker('tomli>=1.0.0; python_version < "3.11"')
    True
    >>> has_environment_marker('pytest; extra == "test"')
    False
    >>> has_environment_marker('requests>=2')
    False
    """
    _, separator, marker = requirement.partition(";")
    if not separator:
        return False
    return bool(_MARKER_WITHOUT_EXTRA.sub("", marker).strip(" \t()andor"))


def _wanted(extra: str, include_extras: Iterable[str]) -> bool:
    """Whether a requirement gated on ``extra`` is part of what we audit."""
    if not extra:
        return True
    wanted = tuple(include_extras)
    return ALL_EXTRAS in wanted or extra in wanted


def _reachable(
    requirements: Iterable[str],
    /,
    *,
    read_requires: Callable[[str], Optional[list]],
    include_extras: Iterable[str],
    follow_conditional: bool,
) -> set[str]:
    """Names reachable from ``requirements``, optionally through marker-gated edges."""
    seen: set[str] = set()
    queue = [
        r
        for r in requirements
        if _wanted(requirement_extra(r), include_extras)
        and (follow_conditional or not has_environment_marker(r))
    ]
    while queue:
        requirement = queue.pop()
        name = requirement_name(requirement)
        if not name or name in seen:
            continue
        seen.add(name)
        try:
            declared = read_requires(name) or []
        except PackageNotFoundError:
            continue
        for child in declared:
            if not _wanted(requirement_extra(child), include_extras):
                continue
            if not follow_conditional and has_environment_marker(child):
                continue
            queue.append(child)
    return seen


class ClosureWalk(NamedTuple):
    """The closure, plus which of its members are reachable only conditionally.

    ``conditional`` is every name that could ONLY be reached by following a
    requirement gated on an environment marker (``python_version``,
    ``sys_platform``, ...). Those are the names whose absence from the
    environment being read is expected rather than alarming; every other absence
    means the check did not get to look at something the project genuinely
    requires.
    """

    names: tuple[str, ...]
    conditional: frozenset[str]


def walk_closure(
    requirements: Iterable[str],
    /,
    *,
    read_requires: Callable[[str], Optional[list]] = _requires,
    include_extras: Iterable[str] = (),
) -> ClosureWalk:
    """The closure of ``requirements`` (raw requirement strings), marked up.

    >>> tree = {'app': ['requests', 'tomli; python_version < "3.11"'],
    ...         'requests': ['certifi'], 'certifi': [], 'tomli': []}
    >>> walk = walk_closure(['app'], read_requires=tree.get)
    >>> walk.names
    ('app', 'certifi', 'requests', 'tomli')
    >>> sorted(walk.conditional)
    ['tomli']
    """
    requirements = list(requirements)
    unconditional = _reachable(
        requirements,
        read_requires=read_requires,
        include_extras=include_extras,
        follow_conditional=False,
    )
    everything = _reachable(
        requirements,
        read_requires=read_requires,
        include_extras=include_extras,
        follow_conditional=True,
    )
    return ClosureWalk(tuple(sorted(everything)), frozenset(everything - unconditional))


def closure(
    names: Iterable[str],
    /,
    *,
    read_requires: Callable[[str], Optional[list]] = _requires,
    include_extras: Iterable[str] = (),
) -> tuple[str, ...]:
    """``names`` PLUS everything they pull in, as INSTALLED in this environment.

    Checking only the declared names is a smaller claim than it reads as:
    ``pip install <pkg>`` installs their transitive closure, and a copyleft
    distribution three levels down is exactly as much a part of what a
    downstream consumer inherits.

    By default the walk skips requirements gated on ``extra == "..."``, because
    a bare install does not take them. ``include_extras=('*',)`` takes all of
    them; a tuple of names takes those.

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

    An uninstalled name simply ends that branch -- it is still reported by
    :func:`check`, but it cannot contribute requirements it does not have:

    >>> closure(['citeget', 'nowhere'], read_requires=tree.get)
    ('certifi', 'citeget', 'html2text', 'nowhere', 'requests')

    :func:`walk_closure` is the same walk, and additionally says which members
    are reachable only through an environment-marker-gated requirement.
    """
    return walk_closure(
        names, read_requires=read_requires, include_extras=include_extras
    ).names


# --------------------------------------------------------------------------------------
# Reading the audited project's declarations and its policy
# --------------------------------------------------------------------------------------


def _pyproject_path(pkg_dir: str | Path) -> Path:
    path = Path(pkg_dir)
    return path / "pyproject.toml" if path.is_dir() else path


def read_pyproject(pkg_dir: str | Path = ".") -> dict:
    """Parse ``pyproject.toml`` from a directory (or a direct path to the file)."""
    path = _pyproject_path(pkg_dir)
    if not path.is_file():
        raise FileNotFoundError(
            f"no pyproject.toml at {path} -- wads-licence-check audits a project "
            "directory, so point it at one (or pass the file itself)"
        )
    if tomllib is None:  # pragma: no cover - only reachable on a bare 3.10
        raise ImportError(
            "reading pyproject.toml needs a TOML parser: Python 3.11+ ships "
            "`tomllib`, and on 3.10 wads declares `tomli`. Install `tomli`."
        )
    with open(path, "rb") as stream:
        return tomllib.load(stream)


#: ``[project]`` key holding the hard requirements. Named because two different
#: absences of it mean two different things -- see :func:`declared_requirements`.
DEPENDENCIES_KEY: str = "dependencies"


def declared_requirements(
    pkg_dir: str | Path = ".",
    /,
    *,
    include_extras: Iterable[str] = (),
    pyproject: Optional[dict] = None,
) -> tuple[str, ...]:
    """Every REQUIREMENT STRING the project declares, markers and all.

    Requirement strings rather than bare names, because the marker is the
    information: ``tomli; python_version < "3.11"`` being absent from a 3.12
    environment is expected, and ``html2text`` being absent is the check not
    having looked.

    Parsed with a real TOML parser rather than scanned as text. That is not a
    style preference: a text scan that ends the ``dependencies`` array at the
    first ``]`` stops at the first requirement carrying an extra
    (``"uvicorn[standard]"``) and silently drops every name below it -- one line
    disarming the whole check. A parser cannot have that bug.

    An ABSENT ``dependencies`` key, or one listed in ``dynamic``, is refused
    rather than read as zero. ``dependencies = []`` is a project saying it has
    none; a missing key is a project whose requirements live somewhere this
    function cannot see (``setup.py``, ``requirements.txt``), and reporting
    "declared: 0 ... PERIMETER HOLDS" over it is the confident-green failure this
    module exists to stop.

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
    """
    if pyproject is None:
        pyproject = read_pyproject(pkg_dir)
    project = pyproject.get("project", {}) or {}
    dynamic = project.get("dynamic", []) or []
    if DEPENDENCIES_KEY in dynamic:
        raise DetectorError(
            f"this project lists `{DEPENDENCIES_KEY}` in [project].dynamic, so "
            "pyproject.toml does not say what it requires and this check would "
            "report an empty closure as a clean one. Point it at a project that "
            f"declares `{DEPENDENCIES_KEY}` statically, or audit the resolved "
            "environment another way."
        )
    if DEPENDENCIES_KEY not in project:
        raise DetectorError(
            f"this project declares no `[project].{DEPENDENCIES_KEY}` at all. An "
            "absent key is not the same claim as an empty one: write "
            f"`{DEPENDENCIES_KEY} = []` if the project really has no hard "
            "requirements, so that a zero-length closure is something somebody "
            "asserted rather than something nobody wrote down."
        )
    requirements = list(project.get(DEPENDENCIES_KEY) or [])
    optional = project.get("optional-dependencies", {}) or {}
    for group, group_requirements in optional.items():
        if _wanted(group, include_extras):
            requirements.extend(group_requirements)
    return tuple(requirements)


def declared_dependencies(
    pkg_dir: str | Path = ".",
    /,
    *,
    include_extras: Iterable[str] = (),
    pyproject: Optional[dict] = None,
) -> tuple[str, ...]:
    """Every distribution the project DECLARES, read from ``pyproject.toml``.

    Derived, never restated: a dependency added to ``pyproject.toml`` and
    forgotten in a hand-written list is a dependency the perimeter never looks
    at, and the perimeter reads as green either way.

    :func:`declared_requirements` without the version specifiers and markers.

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
    """
    names: list[str] = []
    for requirement in declared_requirements(
        pkg_dir, include_extras=include_extras, pyproject=pyproject
    ):
        name = requirement_name(requirement)
        if name and name not in names:
            names.append(name)
    return tuple(names)


#: TOML keys accepted in ``[tool.wads.licence]``. ``enabled`` is read by
#: :mod:`wads.ci_config` for the CI gate rather than by the policy itself.
POLICY_TOML_KEYS: tuple[str, ...] = (
    "enabled",
    "allowed",
    "forbidden",
    "exceptions",
    "include-extras",
    "unknown-is-failure",
    "unclassified-is-failure",
)

#: Keys from the earlier, hand-written table shape that shipped in a couple of
#: repos before this module existed, mapped to what to do instead.
#:
#: Two spellings of the same table is worse than either one: a repo written
#: against the other shape reads as configured and is not. These are rejected
#: rather than silently aliased -- but rejected with the migration, not with a
#: bare "unknown key", because the person hitting this did not choose it.
LEGACY_POLICY_KEYS: Mapping[str, str] = types.MappingProxyType(
    {
        "allow": (
            "rename it to `allowed` (it pairs with `forbidden`, where `allow` "
            "had no counterpart)"
        ),
        "deny": "rename it to `forbidden`",
        "project_licence": (
            "drop it -- the project's own licence is `[project].license`, and "
            "restating it here is a second source of truth that nothing reads"
        ),
        "project-licence": (
            "drop it -- the project's own licence is `[project].license`, and "
            "restating it here is a second source of truth that nothing reads"
        ),
    }
)

#: Keys read off an ``[[tool.wads.licence.exceptions]]`` array-of-tables entry.
#: ``dependency`` and ``reason`` are required; the rest are adjudication
#: provenance and are folded into the rendered reason so a reader sees when the
#: call was made and where to go and argue with it.
EXCEPTION_TABLE_NAME_KEY: str = "dependency"
EXCEPTION_TABLE_REASON_KEY: str = "reason"
EXCEPTION_TABLE_PROVENANCE_KEYS: tuple[str, ...] = (
    "licence",
    "license",
    "scope",
    "decided",
    "decided_in",
)


def _exception_reason(entry: Mapping[str, Any], /) -> str:
    """One array-of-tables exception entry, rendered as a single reason string.

    The provenance fields are the point of the array-of-tables shape: a reason
    with a date and an issue link behind it is an adjudication somebody can be
    asked about, where a bare sentence is an opinion.

    >>> _exception_reason({'dependency': 'PyGithub', 'reason': 'Accepted.',
    ...                    'scope': 'core', 'decided': '2026-08-30',
    ...                    'decided_in': 'https://example.invalid/issues/10'})
    'Accepted. [scope: core; decided: 2026-08-30; decided_in: https://example.invalid/issues/10]'
    """
    reason = str(entry.get(EXCEPTION_TABLE_REASON_KEY, "")).strip()
    provenance = [
        f"{key}: {entry[key]}"
        for key in EXCEPTION_TABLE_PROVENANCE_KEYS
        if entry.get(key)
    ]
    return f"{reason} [{'; '.join(provenance)}]" if provenance else reason


def _exceptions_mapping(value: Any, /) -> dict[str, str]:
    """Normalise either accepted ``exceptions`` shape into name -> reason.

    Both shapes are real and both are kept. The map is the terse one::

        [tool.wads.licence.exceptions]
        certifi = "MPL-2.0, weak copyleft over an unmodified CA bundle."

    The array-of-tables is the one that carries an adjudication record::

        [[tool.wads.licence.exceptions]]
        dependency = "PyGithub"
        decided = "2026-08-30"
        decided_in = "https://github.com/owner/repo/issues/10"
        reason = "Accepted, not removable: ..."

    >>> _exceptions_mapping({'certifi': 'weak copyleft, unmodified CA bundle'})
    {'certifi': 'weak copyleft, unmodified CA bundle'}
    >>> _exceptions_mapping([{'dependency': 'PyGithub', 'reason': 'Accepted.'}])
    {'PyGithub': 'Accepted.'}

    A ``dict()`` over a two-key table used to produce ``{'dependency': 'reason'}``
    -- silently, and only for entries that happened to have exactly two keys.
    Both shapes are now recognised explicitly, and anything else says so:

    >>> try:
    ...     _exceptions_mapping(['PyGithub'])
    ... except ValueError as error:
    ...     print(error)
    [tool.wads.licence].exceptions entry 1 must be a table with a `dependency` and
    a `reason` key; got 'PyGithub'
    """
    if isinstance(value, Mapping):
        bad = [k for k, v in value.items() if not isinstance(v, str)]
        if bad:
            raise ValueError(
                "[tool.wads.licence].exceptions maps a distribution name to the "
                f"WRITTEN reason it is tolerated; {bad} map to something that is "
                "not a string. (For an entry with a date and an issue link, use "
                "the [[tool.wads.licence.exceptions]] array-of-tables form.)"
            )
        return dict(value)
    if isinstance(value, str) or not isinstance(value, Iterable):
        raise ValueError(
            "[tool.wads.licence].exceptions must be a table of name -> reason, or "
            "an array of [[tool.wads.licence.exceptions]] tables each carrying a "
            f"`dependency` and a `reason`; got {type(value).__name__}"
        )
    mapping: dict[str, str] = {}
    for position, entry in enumerate(value, start=1):
        if not isinstance(entry, Mapping) or EXCEPTION_TABLE_NAME_KEY not in entry:
            raise ValueError(
                f"[tool.wads.licence].exceptions entry {position} must be a table "
                f"with a `{EXCEPTION_TABLE_NAME_KEY}` and\na "
                f"`{EXCEPTION_TABLE_REASON_KEY}` key; got {entry!r}"
            )
        reason = _exception_reason(entry)
        if not reason:
            raise ValueError(
                f"[tool.wads.licence].exceptions entry {position} "
                f"({entry[EXCEPTION_TABLE_NAME_KEY]!r}) has no `"
                f"{EXCEPTION_TABLE_REASON_KEY}`. An exception without a written "
                "reason is a name nobody can be asked about -- which is the state "
                "recording one is supposed to end."
            )
        mapping[str(entry[EXCEPTION_TABLE_NAME_KEY])] = reason
    return mapping


def _string_tuple(key: str, value: Any, /) -> tuple[str, ...]:
    """Validate a list-of-strings TOML value.

    ``tuple("MIT")`` is ``('M', 'I', 'T')`` -- a plausible typo that silently
    turns a policy into three single-letter regexes:

    >>> try:
    ...     _string_tuple('allowed', 'MIT')
    ... except ValueError as error:
    ...     print(error)
    [tool.wads.licence].allowed must be a list of strings, not a bare string:
    write allowed = ["MIT"]
    >>> _string_tuple('allowed', ['MIT', 'BSD'])
    ('MIT', 'BSD')
    """
    if isinstance(value, str):
        raise ValueError(
            f"[tool.wads.licence].{key} must be a list of strings, not a bare "
            f"string:\nwrite {key} = [{value!r}]".replace("'", '"')
        )
    if not isinstance(value, Iterable):
        raise ValueError(
            f"[tool.wads.licence].{key} must be a list of strings; got "
            f"{type(value).__name__}"
        )
    items = tuple(value)
    bad = [item for item in items if not isinstance(item, str)]
    if bad:
        raise ValueError(
            f"[tool.wads.licence].{key} must be a list of strings; {bad} "
            f"{'is' if len(bad) == 1 else 'are'} not"
        )
    return items


@dataclasses.dataclass(frozen=True)
class LicencePolicy:
    """The rule set a perimeter check is run against.

    ``exceptions`` maps a distribution name to the WRITTEN reason it is
    tolerated. Listing beats silence: a name here is a decision somebody made
    and can be asked about, where a name quietly missing from ``forbidden`` is
    not.
    """

    allowed: tuple[str, ...] = DFLT_ALLOWED
    forbidden: tuple[str, ...] = DFLT_FORBIDDEN
    exceptions: Mapping[str, str] = types.MappingProxyType({})
    include_extras: tuple[str, ...] = ()
    unknown_is_failure: bool = True
    unclassified_is_failure: bool = False

    @classmethod
    def from_mapping(cls, config: Mapping[str, Any], /) -> "LicencePolicy":
        """Build a policy from a ``[tool.wads.licence]`` table.

        Accepts both TOML-style ``include-extras`` and Python-style
        ``include_extras``. An unrecognised key is an error rather than a
        silently ignored typo -- a misspelt ``forbiden`` would leave the
        perimeter on its defaults while reading as configured.

        Value TYPES are checked too, and for the same reason the key names are:
        ``allowed = "MIT"`` used to become the three regexes ``M``, ``I``, ``T``
        without a word, and an ``exceptions`` array-of-tables used to collapse
        into ``{'dependency': 'reason'}``. Both read as configured. Neither was.

        >>> policy = LicencePolicy.from_mapping(
        ...     {'allowed': ['MIT'], 'include-extras': ['*'], 'unknown-is-failure': False}
        ... )
        >>> policy.allowed, policy.include_extras, policy.unknown_is_failure
        (('MIT',), ('*',), False)
        >>> policy.forbidden == DFLT_FORBIDDEN  # untouched keys keep their defaults
        True

        ``exceptions`` takes either the terse map or the array-of-tables that
        carries an adjudication record (see :func:`_exceptions_mapping`):

        >>> LicencePolicy.from_mapping({'exceptions': [
        ...     {'dependency': 'PyGithub', 'reason': 'Accepted.', 'decided': '2026-08-30'}
        ... ]}).exception_for('pygithub')
        'Accepted. [decided: 2026-08-30]'

        >>> try:
        ...     LicencePolicy.from_mapping({'forbiden': ['GPL']})
        ... except ValueError as error:
        ...     print(error)
        unknown [tool.wads.licence] key 'forbiden'; known keys are: allowed, enabled,
        exceptions, forbidden, include-extras, unclassified-is-failure, unknown-is-failure

        A key from the earlier hand-written table shape is rejected with the
        migration rather than with a bare "unknown key":

        >>> try:
        ...     LicencePolicy.from_mapping({'allow': ['MIT']})
        ... except ValueError as error:
        ...     print(error)
        [tool.wads.licence] key 'allow' is from the earlier table shape: rename it to
        `allowed` (it pairs with `forbidden`, where `allow` had no counterpart)
        """
        known = set(POLICY_TOML_KEYS) | {
            key.replace("-", "_") for key in POLICY_TOML_KEYS
        }
        kwargs: dict[str, Any] = {}
        for key, value in config.items():
            if key in LEGACY_POLICY_KEYS:
                raise ValueError(
                    f"[tool.wads.licence] key {key!r} is from the earlier table "
                    f"shape: {LEGACY_POLICY_KEYS[key]}"
                )
            if key not in known:
                raise ValueError(
                    f"unknown [tool.wads.licence] key {key!r}; known keys are: "
                    + ", ".join(sorted(POLICY_TOML_KEYS))
                )
            if key == "enabled":
                continue
            field_name = key.replace("-", "_")
            if field_name == "exceptions":
                kwargs[field_name] = _exceptions_mapping(value)
            elif field_name in ("unknown_is_failure", "unclassified_is_failure"):
                kwargs[field_name] = bool(value)
            else:
                kwargs[field_name] = _string_tuple(key, value)
        return cls(**kwargs)

    @classmethod
    def from_pyproject(
        cls, pkg_dir: str | Path = ".", /, *, pyproject: Optional[dict] = None
    ) -> "LicencePolicy":
        """The policy declared in ``[tool.wads.licence]``, or the defaults."""
        if pyproject is None:
            pyproject = read_pyproject(pkg_dir)
        table: Any = pyproject
        for key in POLICY_TOML_PATH:
            table = (table or {}).get(key, {})
        return cls.from_mapping(table or {})

    def exception_for(self, name: str, /) -> str:
        """The recorded reason ``name`` is tolerated, or ``''``.

        Matched on the PEP 503 normalised name, so a policy written with
        ``typing_extensions`` still clears the distribution installed metadata
        calls ``typing-extensions``. Getting this wrong is invisible: the
        exception simply never applies and the report keeps flagging a name
        somebody believes they already adjudicated.

        >>> LicencePolicy(exceptions={'Ruamel.YAML': 'audited'}).exception_for(
        ...     'ruamel-yaml')
        'audited'
        """
        target = normalise(name)
        return next(
            (
                reason
                for candidate, reason in self.exceptions.items()
                if normalise(candidate) == target
            ),
            "",
        )

    def matched_forbidden(self, declaration: str, /) -> str:
        """The first forbidden pattern ``declaration`` matches, or ``''``."""
        return next(
            (p for p in self.forbidden if re.search(p, declaration, re.I)),
            "",
        )

    def permissive_option(self, declaration: str, /) -> str:
        """A disjunct of ``declaration`` that is permissive and not forbidden.

        SPDX's ``OR`` is a genuine choice offered to the recipient, so a
        declaration is only as restrictive as its most permissive option. Reading
        the whole string as one blob gets that backwards -- ``marisa-trie``
        declares ``MIT AND (BSD-2-Clause OR LGPL-2.1-or-later)`` and was failed on
        the option nobody has to take:

        >>> LicencePolicy().permissive_option('MIT AND (BSD-2-Clause OR LGPL-2.1-or-later)')
        'MIT AND (BSD-2-Clause'

        When every option is restricted there is nothing to pick, and the
        declaration stands as it is:

        >>> LicencePolicy().permissive_option('LGPL-2.1-only OR MPL-1.1')
        ''
        """
        options = [o for o in _SPDX_OR.split(declaration) if o.strip()]
        if len(options) < 2:
            return ""
        return next(
            (
                option.strip()
                for option in options
                if self.matched_allowed(option) and not self.matched_forbidden(option)
            ),
            "",
        )

    def matched_allowed(self, declaration: str, /) -> str:
        """The first permissive pattern ``declaration`` matches, or ``''``."""
        return next(
            (p for p in self.allowed if re.search(p, declaration, re.I)),
            "",
        )


# --------------------------------------------------------------------------------------
# The self-check: a detector nobody has demonstrated is a detector nobody has checked
# --------------------------------------------------------------------------------------


class DetectorError(RuntimeError):
    """The live policy cannot detect anything, so its green result means nothing."""


class SelfCheck(NamedTuple):
    """What a policy proved about itself before it was allowed to report."""

    caught: tuple[str, ...]
    uncovered_families: tuple[str, ...]


def self_check(policy: LicencePolicy, /) -> SelfCheck:
    """Prove the policy still detects, and still discriminates. Or refuse to run.

    Three failure modes, all observed. A policy whose ``forbidden`` list has been
    emptied reports every repo clean and nobody notices, because every other
    assertion in a licence check only ever says that *nothing* matched. A policy
    so broad it flags ``MIT`` fails every repo, which gets the gate switched off
    within the day. And -- the one that actually shipped -- a policy that catches
    *some* spellings of a family while missing the commonest ones reads as a pass
    on the strength of the spellings it does catch.

    So the bar is per FAMILY, caught whole or not at all. Permitting a family
    outright is a stance somebody can take on purpose and defend; catching four
    of a family's nine spellings is never a stance, it is the bug. A family
    nobody covers is reported rather than assumed -- see
    :attr:`LicenceReport.uncovered_families`, which puts it in every run's output
    so "we do not gate on GPL here" is a visible fact rather than an inference.

    >>> checked = self_check(LicencePolicy())
    >>> len(checked.caught) == len(COPYLEFT_CANARIES), checked.uncovered_families
    (True, ())

    Dropping a whole family is allowed, and is then stated out loud:

    >>> lgpl_ok = LicencePolicy(forbidden=tuple(
    ...     p for p in DFLT_FORBIDDEN if 'LGPL' not in p and 'Lesser' not in p))
    >>> self_check(lgpl_ok).uncovered_families
    ('LGPL',)

    Catching only PART of a family is not. This is the shape of the real bug:
    ``\\bLGPL\\b`` catches the legacy classifier and misses ``LGPLv3``:

    >>> try:
    ...     self_check(LicencePolicy(forbidden=(r'\\bAGPL', r'\\bGNU Affero\\b',
    ...                                        r'\\bLGPL\\b')))
    ... except DetectorError as error:
    ...     print('LGPLv3 classifier' in str(error))
    True

    A policy that detects nothing refuses to report:

    >>> try:
    ...     self_check(LicencePolicy(forbidden=()))
    ... except DetectorError as error:
    ...     print(str(error)[:52])
    this policy's `forbidden` patterns catch none of the

    And so does one broad enough to flag everything:

    >>> try:
    ...     self_check(LicencePolicy(forbidden=(r'\\bAGPL', r'\\bApache\\b')))
    ... except DetectorError as error:
    ...     print('over-broad, and it names what it wrongly flagged:',
    ...           'Apache-2.0' in str(error))
    over-broad, and it names what it wrongly flagged: True
    """
    caught = tuple(
        canary.label
        for canary in COPYLEFT_CANARIES
        if policy.matched_forbidden(canary.declaration)
    )
    if not caught:
        raise DetectorError(
            "this policy's `forbidden` patterns catch none of the known-copyleft "
            "declarations "
            + ", ".join(repr(c.declaration) for c in COPYLEFT_CANARIES)
            + " -- it would report every project clean. Fix "
            "[tool.wads.licence].forbidden, or set enabled = false and say so."
        )
    over_broad = [c for c in PERMISSIVE_CANARIES if policy.matched_forbidden(c)]
    if over_broad:
        raise DetectorError(
            "this policy's `forbidden` patterns also flag the permissive "
            f"declarations {over_broad} -- it would fail every project. Check "
            "[tool.wads.licence].forbidden for an over-broad pattern."
        )
    uncovered: list[str] = []
    for family in CANARY_FAMILIES:
        members = [c for c in COPYLEFT_CANARIES if c.family == family]
        missed = [c for c in members if not policy.matched_forbidden(c.declaration)]
        if not missed:
            continue
        if len(missed) == len(members):
            uncovered.append(family)
            continue
        raise DetectorError(
            f"this policy catches {len(members) - len(missed)} of the "
            f"{len(members)} known spellings of {family}, and misses the rest. "
            "Partial coverage of a licence family is never a stance -- it reads "
            "as a pass on the strength of the spellings it does catch, which is "
            "how LGPLv2/v2+/v3/v3+ once sailed through a gate built to stop "
            f"them. Either cover {family} whole or do not gate on it at all "
            "(dropping the family is allowed, and is reported in every run). "
            "Not caught:\n"
            + "\n".join(f"  - {c.label}: {c.declaration!r}" for c in missed)
            + "\n(In pyproject.toml, write patterns as TOML LITERAL strings -- "
            "single quotes -- or `\\b` becomes a backspace character rather than a "
            "regex word boundary. To tolerate one distribution rather than a "
            "whole family, record it in [tool.wads.licence.exceptions] with a "
            "reason; do not narrow the pattern.)"
        )
    return SelfCheck(caught, tuple(uncovered))


# --------------------------------------------------------------------------------------
# Verdicts and the report
# --------------------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Verdict:
    """One distribution's standing against the policy."""

    name: str
    status: str
    declaration: Declaration = Declaration("", "")
    note: str = ""

    @property
    def is_clean(self) -> bool:
        """Whether this verdict is one that never fails a run."""
        return self.status in CLEAN_STATUSES

    def __str__(self) -> str:
        source = f" [{self.declaration.source}]" if self.declaration.source else ""
        text = self.declaration.text or "<nothing declared>"
        note = f" -- {self.note}" if self.note else ""
        return f"{self.name}: {text}{source}{note}"


def verdict(
    name: str,
    /,
    *,
    policy: LicencePolicy,
    read_metadata: Callable[[str], Any] = _metadata,
    conditional: bool = False,
) -> Verdict:
    """Judge one distribution against ``policy``.

    An adjudicated exception wins over everything, including a forbidden match:
    that is what recording one *means*, and the reason travels with it.

    >>> from email import message_from_string
    >>> import functools
    >>> records = {'html2text': 'License-Expression: GPL-3.0-or-later\\n',
    ...            'requests': 'License-Expression: Apache-2.0\\n',
    ...            'certifi': 'License-Expression: MPL-2.0\\n',
    ...            'mystery': 'Name: mystery\\n'}
    >>> read = functools.partial(lambda n, r: message_from_string(r[n]), r=records)
    >>> verdict('html2text', policy=LicencePolicy(), read_metadata=read).status
    'forbidden'
    >>> verdict('requests', policy=LicencePolicy(), read_metadata=read).status
    'allowed'

    MPL-2.0 is deliberately neither: it is file-level weak copyleft, so it is
    not forbidden, and it matches no permissive family either. It surfaces as
    ``unclassified`` -- a decision to make, not a build to break.

    >>> verdict('certifi', policy=LicencePolicy(), read_metadata=read).status
    'unclassified'
    >>> verdict('mystery', policy=LicencePolicy(), read_metadata=read).status
    'unknown'

    A declaration matching a forbidden AND a permissive pattern is not simply
    forbidden. Where SPDX's ``OR`` says the recipient picks, the permissive pick
    is taken; where the two spellings merely sit side by side -- which is what
    joining a distribution's ``License ::`` classifiers produces -- nobody knows
    which applies to which file, so it becomes a question rather than a failure:

    >>> both = {'marisa-trie': ('License-Expression: '
    ...                         'MIT AND (BSD-2-Clause OR LGPL-2.1-or-later)\\n'),
    ...         'docutils': ('Classifier: License :: Public Domain\\n'
    ...                      'Classifier: License :: OSI Approved :: BSD License\\n'
    ...                      'Classifier: License :: OSI Approved :: '
    ...                      'GNU General Public License (GPL)\\n')}
    >>> read_both = functools.partial(lambda n, r: message_from_string(r[n]), r=both)
    >>> verdict('marisa-trie', policy=LicencePolicy(), read_metadata=read_both).status
    'allowed'
    >>> verdict('docutils', policy=LicencePolicy(), read_metadata=read_both).status
    'unclassified'
    """
    key = normalise(name)
    try:
        declaration = declare(name, read_metadata=read_metadata)
    except PackageNotFoundError:
        if conditional:
            return Verdict(
                key,
                Status.NOT_APPLICABLE,
                note=(
                    "required only under an environment marker that does not "
                    "hold here (a python_version / sys_platform gate), so its "
                    "absence is expected -- but it is also unaudited: run the "
                    "check on an environment where the marker holds"
                ),
            )
        return Verdict(
            key,
            Status.NOT_INSTALLED,
            note=(
                "declared, but NOT INSTALLED in the environment being read, so "
                "nothing was read for it. This check reads installed metadata: "
                "an absent hard dependency is a hole in the audit, not a pass. "
                "Install the project (`pip install -e .`) or point --python at "
                "the environment that has it"
            ),
        )
    reason = policy.exception_for(name)
    if reason:
        return Verdict(key, Status.EXCEPTED, declaration, note=reason)
    forbidden = policy.matched_forbidden(declaration.text)
    if forbidden:
        option = policy.permissive_option(declaration.text)
        if option:
            return Verdict(
                key,
                Status.ALLOWED,
                declaration,
                note=(
                    f"dual-licensed; the permissive option `{option}` is taken "
                    f"(the declaration also matches forbidden pattern `{forbidden}`)"
                ),
            )
        allowed = policy.matched_allowed(declaration.text)
        if allowed:
            return Verdict(
                key,
                Status.UNCLASSIFIED,
                declaration,
                note=(
                    f"matches forbidden pattern `{forbidden}` AND permissive "
                    f"pattern `{allowed}` in the same declaration, with no `OR` "
                    "saying which one you get to pick. That is a question for a "
                    "human, not a build failure -- read its LICENSE and record "
                    "the answer in [tool.wads.licence.exceptions] with a reason"
                ),
            )
        return Verdict(
            key,
            Status.FORBIDDEN,
            declaration,
            note=f"matches forbidden pattern `{forbidden}`",
        )
    if declaration.is_blank:
        return Verdict(
            key,
            Status.UNKNOWN,
            declaration,
            note=(
                "declares no licence in its installed metadata; the terms may "
                "live in a repo file no scanner reads. Read its LICENSE and "
                "record it in [tool.wads.licence.exceptions] with a dated reason"
            ),
        )
    if policy.matched_allowed(declaration.text):
        return Verdict(key, Status.ALLOWED, declaration)
    return Verdict(
        key,
        Status.UNCLASSIFIED,
        declaration,
        note=(
            "matches no permissive family and no forbidden pattern. Either it "
            "is a real problem or it is an adjudicated exception -- and an "
            "exception belongs in [tool.wads.licence.exceptions] with its reason"
        ),
    )


@dataclasses.dataclass(frozen=True)
class LicenceReport:
    """What a run found: the closure it walked, and a verdict for every member."""

    policy: LicencePolicy
    declared: tuple[str, ...]
    verdicts: tuple[Verdict, ...]
    canaries: tuple[str, ...] = ()
    uncovered_families: tuple[str, ...] = ()
    pkg_dir: str = "."

    @property
    def stale_exceptions(self) -> tuple[str, ...]:
        """Recorded exceptions for distributions the walk never reached.

        An exception for a distribution that has left the tree is stale advice,
        and one whose licence has since changed is worse: it reads as
        adjudicated when nobody has looked at the current terms. Reported, not
        failed -- an extra is often the reason, and breaking a build over a
        tidiness issue is how gates get switched off.
        """
        reached = {v.name for v in self.verdicts}
        return tuple(
            sorted(
                name
                for name in self.policy.exceptions
                if normalise(name) not in reached
            )
        )

    def of_status(self, *statuses: str) -> tuple[Verdict, ...]:
        """Every verdict whose status is one of ``statuses``."""
        return tuple(v for v in self.verdicts if v.status in statuses)

    @property
    def closure(self) -> tuple[str, ...]:
        """Every distribution the walk reached."""
        return tuple(v.name for v in self.verdicts)

    @property
    def failures(self) -> tuple[Verdict, ...]:
        """The verdicts that make this run fail, under this policy."""
        statuses = [Status.FORBIDDEN, Status.NOT_INSTALLED]
        if self.policy.unknown_is_failure:
            statuses.append(Status.UNKNOWN)
        if self.policy.unclassified_is_failure:
            statuses.append(Status.UNCLASSIFIED)
        return self.of_status(*statuses)

    @property
    def ok(self) -> bool:
        """Whether the perimeter holds."""
        return not self.failures

    def as_dict(self) -> dict:
        """A JSON-serialisable view, for fleet-wide sweeps."""
        return {
            "pkg_dir": self.pkg_dir,
            "ok": self.ok,
            "declared": list(self.declared),
            "closure": list(self.closure),
            "canaries_caught": list(self.canaries),
            "uncovered_families": list(self.uncovered_families),
            "stale_exceptions": list(self.stale_exceptions),
            "verdicts": [
                {
                    "name": v.name,
                    "status": v.status,
                    "licence": v.declaration.text,
                    "source": v.declaration.source,
                    "note": v.note,
                }
                for v in self.verdicts
            ],
        }

    def render(self) -> str:
        """A human-readable report, failures first."""
        lines = [
            f"Licence perimeter for {self.pkg_dir}",
            f"  declared: {len(self.declared)}    closure: {len(self.closure)}",
            f"  detector self-check: caught {len(self.canaries)} of "
            f"{len(COPYLEFT_CANARIES)} known-copyleft canary declarations",
        ]
        if self.uncovered_families:
            # A policy that does not gate on a family is a decision, and it
            # belongs in the output of every run rather than in the diff of the
            # commit that made it. Otherwise "PERIMETER HOLDS" is read as
            # "nothing copyleft is in here", which it is not.
            lines.append(
                "  NOT GATED ON by this policy: "
                + ", ".join(self.uncovered_families)
                + " -- distributions under "
                + ("it" if len(self.uncovered_families) == 1 else "them")
                + " are reported below as unclassified, not as failures"
            )
        lines += [
            "",
            "  This reads INSTALLED metadata, so it describes the environment it",
            "  ran in. A resolution that picks different versions elsewhere is",
            "  invisible here.",
            "",
        ]
        for title, statuses in (
            ("FORBIDDEN", (Status.FORBIDDEN,)),
            ("UNDECLARED (unaudited)", (Status.UNKNOWN,)),
            ("UNCLASSIFIED (neither permissive nor forbidden)", (Status.UNCLASSIFIED,)),
            (
                "NOT INSTALLED (declared, but nothing was read for it)",
                (Status.NOT_INSTALLED,),
            ),
            (
                "NOT APPLICABLE (environment-marker gated, not audited here)",
                (Status.NOT_APPLICABLE,),
            ),
            ("EXCEPTED (adjudicated)", (Status.EXCEPTED,)),
        ):
            found = self.of_status(*statuses)
            if found:
                lines.append(f"{title}:")
                lines.extend(f"  - {v}" for v in found)
                lines.append("")
        if self.stale_exceptions:
            lines.append(
                "STALE EXCEPTIONS (recorded, but no longer in the closure -- "
                "drop them or say why they stay):"
            )
            lines.extend(f"  - {name}" for name in self.stale_exceptions)
            lines.append("")
        allowed = self.of_status(Status.ALLOWED)
        lines.append(f"{len(allowed)} distributions matched a permissive family.")
        lines.append("")
        # A bare "PERIMETER HOLDS" printed directly under a list of unadjudicated
        # rows reads as "nothing to see here" to anyone skimming a CI log, and
        # the last line is the only one most people read. Carry the count.
        unadjudicated = len(
            self.of_status(Status.UNCLASSIFIED, Status.UNKNOWN, Status.NOT_APPLICABLE)
        )
        held = "PERIMETER HOLDS"
        if unadjudicated:
            held += f" ({unadjudicated} not adjudicated -- see the sections above)"
        lines.append(held if self.ok else f"PERIMETER BREACHED: {len(self.failures)}")
        return "\n".join(lines)


# --------------------------------------------------------------------------------------
# Reading another environment's metadata (the seam onto the metadata source)
# --------------------------------------------------------------------------------------


class MetadataReaders(NamedTuple):
    """The pair of readers :func:`check` walks the closure with."""

    read_metadata: Callable[[str], Any]
    read_requires: Callable[[str], Optional[list]]


#: Readers bound to the interpreter running this module.
THIS_ENVIRONMENT = MetadataReaders(_metadata, _requires)


def search_path_of(python_executable: str | Path, /) -> tuple[str, ...]:
    """The ``sys.path`` of ANOTHER interpreter, so its packages can be read.

    This is what lets the CI gate run the tool from an isolated ``uvx``
    environment while auditing the project's own ``.venv``. Without it the tool
    would read *its own* dependencies and report a confident, wrong green.
    """
    completed = subprocess.run(
        [str(python_executable), "-c", "import sys, json; print(json.dumps(sys.path))"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"could not read sys.path from {python_executable!s}: "
            f"{completed.stderr.strip() or 'no output'}"
        )
    return tuple(p for p in json.loads(completed.stdout) if p)


def readers_for(search_path: Iterable[str], /) -> MetadataReaders:
    """Metadata readers that see the distributions installed on ``search_path``.

    >>> import sys
    >>> readers = readers_for(sys.path)
    >>> readers.read_metadata('wads')['Name']
    'wads'
    """
    from importlib.metadata import Distribution, DistributionFinder

    context = DistributionFinder.Context(path=list(search_path))
    found = {}
    for dist in Distribution.discover(context=context):
        name = dist.metadata["Name"]
        if name:
            found.setdefault(normalise(name), dist)

    def _find(name: str):
        dist = found.get(normalise(name))
        if dist is None:
            raise PackageNotFoundError(name)
        return dist

    return MetadataReaders(
        lambda name: _find(name).metadata,
        lambda name: _find(name).requires,
    )


# --------------------------------------------------------------------------------------
# The check
# --------------------------------------------------------------------------------------


def check(
    pkg_dir: str | Path = ".",
    /,
    *,
    policy: Optional[LicencePolicy] = None,
    readers: MetadataReaders = THIS_ENVIRONMENT,
) -> LicenceReport:
    """Audit a project's installed dependency closure against its policy.

    ``policy=None`` loads ``[tool.wads.licence]`` from the project's
    ``pyproject.toml``, falling back to the module defaults.

    Raises :class:`DetectorError` before reading anything if the live policy
    could not detect every known-copyleft canary declaration, if the project does
    not declare its dependencies statically, and again if not one declared
    dependency is installed -- all states in which a green result would be a lie
    rather than a finding.

    A dependency that IS declared and is NOT installed here is a failure, not a
    footnote: it is a piece of the perimeter nobody looked at, and the previous
    all-or-nothing refusal let one installed survivor turn three unread copyleft
    dependencies into a green. The one honest exception is a requirement gated on
    an environment marker (``tomli; python_version < "3.11"``), which gets
    ``NOT_APPLICABLE`` and is reported without failing.
    """
    pyproject = read_pyproject(pkg_dir)
    if policy is None:
        policy = LicencePolicy.from_pyproject(pkg_dir, pyproject=pyproject)
    checked = self_check(policy)
    requirements = declared_requirements(
        pkg_dir, include_extras=policy.include_extras, pyproject=pyproject
    )
    declared = declared_dependencies(
        pkg_dir, include_extras=policy.include_extras, pyproject=pyproject
    )
    walk = walk_closure(
        requirements,
        read_requires=readers.read_requires,
        include_extras=policy.include_extras,
    )
    verdicts = tuple(
        verdict(
            name,
            policy=policy,
            read_metadata=readers.read_metadata,
            conditional=name in walk.conditional,
        )
        for name in walk.names
    )
    unread = [v for v in verdicts if v.status == Status.NOT_INSTALLED]
    if declared and len(unread) == len(verdicts):
        raise DetectorError(
            f"not one of the {len(declared)} declared dependencies of {pkg_dir} is "
            "installed in the environment being read, so there is nothing here to "
            "check and a green result would mean nothing. Install the project "
            "(`pip install -e .`) or point --python at the environment that has it."
        )
    return LicenceReport(
        policy=policy,
        declared=declared,
        verdicts=verdicts,
        canaries=checked.caught,
        uncovered_families=checked.uncovered_families,
        pkg_dir=str(pkg_dir),
    )


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------

#: Exit codes, so the CI step and a human read the same numbers.
EXIT_OK, EXIT_BREACH, EXIT_ERROR = 0, 1, 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wads-licence-check",
        description=(
            "Audit the licence perimeter of a package's installed dependency "
            "closure. Exits 1 when the perimeter is breached."
        ),
    )
    parser.add_argument(
        "pkg_dir",
        nargs="?",
        default=".",
        help="project directory (or path to a pyproject.toml). Default: .",
    )
    parser.add_argument(
        "--python",
        default=None,
        help=(
            "read the installed metadata of ANOTHER interpreter's environment "
            "(e.g. .venv/bin/python). Use this whenever the tool itself runs "
            "from an isolated environment, such as under `uvx`."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit the report as JSON instead of text (for fleet sweeps).",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    """Console-script entry point. Returns the process exit code."""
    args = _parser().parse_args(argv)
    # Everything that can fail lives inside the try. `readers_for(search_path_of
    # (...))` used to sit outside it, so a bad `--python` exited 1 -- the code
    # that means PERIMETER BREACHED -- with a traceback. A tool whose error path
    # is indistinguishable from its finding path has no error path.
    try:
        readers = (
            readers_for(search_path_of(args.python))
            if args.python
            else THIS_ENVIRONMENT
        )
        report = check(args.pkg_dir, readers=readers)
    except (
        DetectorError,
        FileNotFoundError,
        ValueError,
        RuntimeError,
        TypeError,
        OSError,
        re.error,
    ) as error:
        print(f"wads-licence-check: {error}", file=sys.stderr)
        return EXIT_ERROR
    print(json.dumps(report.as_dict(), indent=2) if args.json else report.render())
    return EXIT_OK if report.ok else EXIT_BREACH


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
