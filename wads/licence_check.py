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

The module imports nothing outside the standard library (``tomli`` only on
Python 3.10, where ``tomllib`` does not yet exist), so it can run in the CI of
any repo without dragging a toolchain in behind it.
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
DFLT_ALLOWED: tuple[str, ...] = (
    r"\bMIT\b",
    r"\bBSD\b",
    r"\bApache[- ]?2",
    r"\bApache Software License\b",
    r"\bISC\b",
    r"\bPython Software Foundation\b",
    r"\bPSF\b",
    r"\bHPND\b",
    r"\bUnlicense\b",
    r"\bCC0\b",
    r"\bZlib\b",
)

#: Reciprocal (copyleft) families. ``\bGPL`` does not match inside ``LGPL``
#: (no word boundary between ``L`` and ``G``), which is why LGPL needs its own
#: pattern. The lookahead spares the "GPL with <exception>" spellings only;
#: anything subtler belongs in ``exceptions``, with a reason, not in a regex.
DFLT_COPYLEFT: tuple[str, ...] = (
    r"\bAGPL\b",
    r"\bGNU Affero\b",
    r"\bGPL(?!v?\d*\s*with)",
    r"\bLGPL\b",
    r"\bGNU Library or Lesser\b",
    r"\bEUPL\b",
)

#: Non-commercial / source-available families. These are not copyleft, but they
#: restrict redistribution or hosting, and a classifier-only gate cannot see
#: them: Arize Phoenix ships Elastic-2.0 in its ``License`` field with no trove
#: classifier at all.
DFLT_NON_COMMERCIAL: tuple[str, ...] = (
    r"\bBusiness Source\b",
    r"\bBUSL\b",
    r"\bBSL\b",
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

#: Real declarations, copied from installed ``dist-info``, that any usable policy
#: must still catch. See :func:`self_check`.
COPYLEFT_CANARIES: tuple[tuple[str, str], ...] = (
    (
        "argh / PyGithub",
        "License :: OSI Approved :: GNU Library or Lesser General Public License (LGPL)",
    ),
    ("html2text", "GPL-3.0-or-later"),
    ("ultralytics", "AGPL-3.0"),
    ("soxr", "LGPL-2.1-or-later"),
)

#: Real declarations that any usable policy must still clear. A policy that
#: flags these is not strict, it is broken, and it would fail every repo.
PERMISSIVE_CANARIES: tuple[str, ...] = ("MIT", "BSD-3-Clause", "Apache-2.0", "ISC")

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


#: Statuses that never fail a run.
CLEAN_STATUSES: frozenset[str] = frozenset({Status.ALLOWED, Status.EXCEPTED})


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

_SPLIT_REQUIREMENT = re.compile(r"[<>=!~\[; ()]")
_EXTRA_MARKER = re.compile(r"""extra\s*==\s*["']([^"']+)["']""")


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


def _wanted(extra: str, include_extras: Iterable[str]) -> bool:
    """Whether a requirement gated on ``extra`` is part of what we audit."""
    if not extra:
        return True
    wanted = tuple(include_extras)
    return ALL_EXTRAS in wanted or extra in wanted


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
    """
    seen: set[str] = set()
    queue = [normalise(n) for n in names]
    while queue:
        name = queue.pop()
        if name in seen:
            continue
        seen.add(name)
        try:
            declared = read_requires(name) or []
        except PackageNotFoundError:
            continue
        for requirement in declared:
            if not _wanted(requirement_extra(requirement), include_extras):
                continue
            queue.append(requirement_name(requirement))
    return tuple(sorted(seen))


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

    Parsed with a real TOML parser rather than scanned as text. That is not a
    style preference: a text scan that ends the ``dependencies`` array at the
    first ``]`` stops at the first requirement carrying an extra
    (``"uvicorn[standard]"``) and silently drops every name below it -- one line
    disarming the whole check. A parser cannot have that bug.

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
    if pyproject is None:
        pyproject = read_pyproject(pkg_dir)
    project = pyproject.get("project", {})
    requirements = list(project.get("dependencies", []) or [])
    optional = project.get("optional-dependencies", {}) or {}
    for group, group_requirements in optional.items():
        if _wanted(group, include_extras):
            requirements.extend(group_requirements)
    names: list[str] = []
    for requirement in requirements:
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

        >>> policy = LicencePolicy.from_mapping(
        ...     {'allowed': ['MIT'], 'include-extras': ['*'], 'unknown-is-failure': False}
        ... )
        >>> policy.allowed, policy.include_extras, policy.unknown_is_failure
        (('MIT',), ('*',), False)
        >>> policy.forbidden == DFLT_FORBIDDEN  # untouched keys keep their defaults
        True
        >>> try:
        ...     LicencePolicy.from_mapping({'forbiden': ['GPL']})
        ... except ValueError as error:
        ...     print(error)
        unknown [tool.wads.licence] key 'forbiden'; known keys are: allowed, enabled,
        exceptions, forbidden, include-extras, unclassified-is-failure, unknown-is-failure
        """
        known = set(POLICY_TOML_KEYS) | {
            key.replace("-", "_") for key in POLICY_TOML_KEYS
        }
        kwargs: dict[str, Any] = {}
        for key, value in config.items():
            if key not in known:
                raise ValueError(
                    f"unknown [tool.wads.licence] key {key!r}; known keys are: "
                    + ", ".join(sorted(POLICY_TOML_KEYS))
                )
            if key == "enabled":
                continue
            field_name = key.replace("-", "_")
            if field_name == "exceptions":
                kwargs[field_name] = dict(value)
            elif field_name in ("unknown_is_failure", "unclassified_is_failure"):
                kwargs[field_name] = bool(value)
            else:
                kwargs[field_name] = tuple(value)
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


def self_check(policy: LicencePolicy, /) -> tuple[str, ...]:
    """Prove the policy still detects, and still discriminates. Or refuse to run.

    Two failure modes, both observed. A policy whose ``forbidden`` list has been
    emptied reports every repo clean and nobody notices, because every other
    assertion in a licence check only ever says that *nothing* matched. And a
    policy so broad it flags ``MIT`` fails every repo, which gets the gate
    switched off within the day.

    Returns the labels of the canaries this policy caught.

    >>> self_check(LicencePolicy())
    ('argh / PyGithub', 'html2text', 'ultralytics', 'soxr')

    A policy that detects nothing refuses to report:

    >>> try:
    ...     self_check(LicencePolicy(forbidden=()))
    ... except DetectorError as error:
    ...     print(str(error)[:52])
    this policy's `forbidden` patterns catch none of the

    So does one broad enough to flag everything:

    >>> try:
    ...     self_check(LicencePolicy(forbidden=(r'\\bAGPL\\b', r'\\bApache\\b')))
    ... except DetectorError as error:
    ...     print('over-broad, and it names what it wrongly flagged:',
    ...           'Apache-2.0' in str(error))
    over-broad, and it names what it wrongly flagged: True
    """
    caught = tuple(
        label
        for label, declaration in COPYLEFT_CANARIES
        if policy.matched_forbidden(declaration)
    )
    if not caught:
        raise DetectorError(
            "this policy's `forbidden` patterns catch none of the known-copyleft "
            "declarations "
            + ", ".join(repr(d) for _, d in COPYLEFT_CANARIES)
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
    return caught


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
    """
    key = normalise(name)
    try:
        declaration = declare(name, read_metadata=read_metadata)
    except PackageNotFoundError:
        return Verdict(
            key,
            Status.NOT_INSTALLED,
            note=(
                "not installed here, so nothing was read for it -- this check "
                "reads installed metadata"
            ),
        )
    reason = policy.exception_for(name)
    if reason:
        return Verdict(key, Status.EXCEPTED, declaration, note=reason)
    forbidden = policy.matched_forbidden(declaration.text)
    if forbidden:
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
        statuses = [Status.FORBIDDEN]
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
            f"  detector self-check: caught {len(self.canaries)} known-copyleft "
            f"canaries ({', '.join(self.canaries)})",
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
            ("NOT INSTALLED (not read)", (Status.NOT_INSTALLED,)),
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
        lines.append(
            "PERIMETER HOLDS"
            if self.ok
            else f"PERIMETER BREACHED: {len(self.failures)}"
        )
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
    could not detect a known-copyleft declaration, and again if not one declared
    dependency is installed -- both are states in which a green result would be
    a lie rather than a finding.
    """
    pyproject = read_pyproject(pkg_dir)
    if policy is None:
        policy = LicencePolicy.from_pyproject(pkg_dir, pyproject=pyproject)
    canaries = self_check(policy)
    declared = declared_dependencies(
        pkg_dir, include_extras=policy.include_extras, pyproject=pyproject
    )
    walked = closure(
        declared,
        read_requires=readers.read_requires,
        include_extras=policy.include_extras,
    )
    verdicts = tuple(
        verdict(name, policy=policy, read_metadata=readers.read_metadata)
        for name in walked
    )
    installed = [v for v in verdicts if v.status != Status.NOT_INSTALLED]
    if declared and not installed:
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
        canaries=canaries,
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
    readers = (
        readers_for(search_path_of(args.python)) if args.python else THIS_ENVIRONMENT
    )
    try:
        report = check(args.pkg_dir, readers=readers)
    except (DetectorError, FileNotFoundError, ValueError, RuntimeError) as error:
        print(f"wads-licence-check: {error}", file=sys.stderr)
        return EXIT_ERROR
    print(json.dumps(report.as_dict(), indent=2) if args.json else report.render())
    return EXIT_OK if report.ok else EXIT_BREACH


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
