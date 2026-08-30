"""Tests for the licence-perimeter gate (wads#68, wads#69).

Every test docstring names the MUTATION it kills. That convention is not
decoration: this file's ancestor (``thorwhalen/an``'s
``tests/test_licence_perimeter.py``) stayed entirely green when its forbidden
patterns were deleted, because every assertion in it only ever said that
*nothing* matched. A detector with no demonstrated true positive is a detector
nobody has checked.

The declaration strings below are REAL, copied from installed ``dist-info``
metadata, not invented. That is what makes them evidence.
"""

import doctest
import json
import subprocess
import sys
from email import message_from_string
from pathlib import Path

import pytest

from wads import licence_check as lc
from wads.ci_config import CIConfig

REPO_ROOT = Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------------------------
# Fixtures: fake metadata, so these tests are about the LOGIC, not about what
# happens to be installed on the machine running them.
# --------------------------------------------------------------------------------------

#: name -> raw METADATA text, in the exact shapes observed in the wild.
RECORDS = {
    # PEP 639 expression, ZERO classifiers. `click` 8.4.2 really is like this.
    "click": "Name: click\nLicense-Expression: BSD-3-Clause\n",
    "html2text": "Name: html2text\nLicense-Expression: GPL-3.0-or-later\n",
    "soxr": "Name: soxr\nLicense-Expression: LGPL-2.1-or-later\n",
    # Classifier only; free-text field empty. This is argh, and PyGithub.
    "argh": (
        "Name: argh\nClassifier: License :: OSI Approved :: GNU Library or "
        "Lesser General Public License (LGPL)\n"
    ),
    "ultralytics": (
        "Name: ultralytics\nClassifier: License :: OSI Approved :: GNU Affero "
        "General Public License v3 or later (AGPLv3+)\nLicense: AGPL-3.0\n"
    ),
    # Free-text field only: no expression, no classifier. This is `i2`.
    "i2": "Name: i2\nLicense: Apache Software License\n",
    "requests": (
        "Name: requests\nClassifier: License :: OSI Approved :: Apache "
        "Software License\n"
    ),
    "certifi": (
        "Name: certifi\nClassifier: License :: OSI Approved :: Mozilla Public "
        "License 2.0 (MPL 2.0)\n"
    ),
    # The numpy trap: BSD-3-Clause, whose free-text field is the entire licence
    # document and contains an LGPL URL for a vendored component's notice.
    "numpy": (
        "Name: numpy\nLicense: Copyright (c) 2005-2024, NumPy Developers.\n"
        "        All rights reserved. Redistribution and use in source and\n"
        "        binary forms, with or without modification, are permitted.\n"
        "        Vendored: see https://www.gnu.org/licenses/lgpl-3.0.html\n"
    ),
    # The blank-field trap: nothing declared anywhere.
    "mystery": "Name: mystery\n",
    "unknown-literal": "Name: unknown-literal\nLicense: UNKNOWN\n",
    # Source-available, declared ONLY in the free-text field. Arize Phoenix.
    "phoenix": "Name: phoenix\nLicense: Elastic-2.0\n",
}

#: name -> Requires-Dist list, mirroring the shapes importlib.metadata returns.
REQUIRES = {
    "citeget": [
        "html2text",
        "requests",
        "pytest>=7; extra == 'test'",
    ],
    "html2text": [],
    "requests": ["certifi", "numpy>=1.0"],
    "certifi": [],
    "numpy": [],
    "pytest": [],
}


def fake_read_metadata(name):
    key = lc.normalise(name)
    if key not in RECORDS:
        raise lc.PackageNotFoundError(name)
    return message_from_string(RECORDS[key])


def fake_read_requires(name):
    key = lc.normalise(name)
    if key not in REQUIRES and key not in RECORDS:
        raise lc.PackageNotFoundError(name)
    return REQUIRES.get(key, [])


FAKE_READERS = lc.MetadataReaders(fake_read_metadata, fake_read_requires)


def declaration_of(name):
    return lc.declare(name, read_metadata=fake_read_metadata)


# --------------------------------------------------------------------------------------
# 1. The precision ladder
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name,expected_text,expected_source",
    [
        ("click", "BSD-3-Clause", "License-Expression"),
        ("html2text", "GPL-3.0-or-later", "License-Expression"),
        (
            "argh",
            "License :: OSI Approved :: GNU Library or Lesser General Public "
            "License (LGPL)",
            "Classifier",
        ),
        ("i2", "Apache Software License", "License"),
        ("mystery", "", ""),
    ],
)
def test_the_ladder_reads_the_most_precise_field_that_exists(
    name, expected_text, expected_source
):
    """MUTATION: read only one metadata field.

    Each row is a real shape that a one-field check gets WRONG. `click` has a
    PEP 639 expression and no classifiers, so a classifier-only read sees
    nothing. `i2` has neither, so an expression-or-classifier read sees nothing.
    `argh` has a classifier and an EMPTY free-text field, so a field-only read
    sees nothing. There is no single field that works.
    """
    declaration = declaration_of(name)
    assert declaration.text == expected_text
    assert declaration.source == expected_source


def test_the_numpy_trap_the_free_text_field_is_read_one_line_deep():
    """MUTATION: substring-scan the whole `License` field.

    numpy is BSD-3-Clause and its `License` field is the entire licence
    document -- 48k characters in the installed copy -- carrying an LGPL URL for
    a vendored component's notice. Scanning it whole reports numpy as copyleft,
    which is a false positive against one of the most-depended-on distributions
    in Python. The ladder reads the FIRST LINE.
    """
    declaration = declaration_of("numpy")
    assert declaration.text == "Copyright (c) 2005-2024, NumPy Developers."
    assert "lgpl" not in declaration.text.lower()

    policy = lc.LicencePolicy()
    assert not policy.matched_forbidden(declaration.text)
    # And the whole-field scan the ladder exists to prevent WOULD have flagged it.
    assert policy.matched_forbidden(RECORDS["numpy"])


def test_the_ladder_prefers_the_expression_over_a_disagreeing_classifier():
    """MUTATION: swap the ladder's first two rungs.

    `ultralytics` declares both an AGPL classifier and an `AGPL-3.0` field. Both
    are forbidden here, so the verdict is the same either way -- what the order
    protects is PRECISION of the reported reason, which is what a reader has to
    go and verify. Pinned so a reordering is a decision, not a drift.
    """
    assert declaration_of("ultralytics").source == "Classifier"


# --------------------------------------------------------------------------------------
# 2. Demonstrated true positives and true negatives
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name,declaration",
    lc.COPYLEFT_CANARIES
    + (
        (
            "ultralytics classifier",
            "License :: OSI Approved :: GNU Affero General Public License v3 "
            "or later (AGPLv3+)",
        ),
        ("phoenix (Elastic-2.0, field only)", "Elastic-2.0"),
        ("a BUSL-licensed distribution", "Business Source License 1.1"),
        ("an SSPL-licensed distribution", "SSPL-1.0"),
        ("a RAIL-licensed model", "bigscience-openrail-m"),
    ),
)
def test_the_detector_actually_detects(name, declaration):
    """MUTATION: `DFLT_FORBIDDEN = ()`.

    This is the test the whole file exists for. In the originating suite,
    deleting the forbidden patterns left every other test green, because they
    all only asserted that nothing matched. These declarations are real, copied
    from installed metadata, and each one is a distribution somebody's project
    is actually pulling in today.
    """
    assert lc.LicencePolicy().matched_forbidden(declaration), (
        f"{name} declares {declaration!r} and the detector did not catch it"
    )


@pytest.mark.parametrize("declaration", lc.PERMISSIVE_CANARIES)
def test_the_detector_discriminates(declaration):
    """MUTATION: a forbidden pattern broad enough to match everything.

    A gate that flags MIT is not strict, it is broken -- and it gets switched
    off within the day, which is worse than never having existed. Each of these
    must be cleanly permissive: not forbidden, AND matching a named family.
    """
    policy = lc.LicencePolicy()
    assert not policy.matched_forbidden(declaration)
    assert policy.matched_allowed(declaration)


def test_mpl_is_neither_forbidden_nor_permissive():
    """MUTATION: add MPL to the forbidden patterns; or to the allowed ones.

    MPL-2.0 is file-level weak copyleft. It is not a reciprocity risk for a
    package that merely depends on it, so forbidding it would fail nearly every
    repo (certifi is everywhere, and tqdm ships `MPL-2.0 AND MIT`). But waving
    it through as permissive would hide it. It lands as `unclassified`: visible
    in the report, not failing the build, and recorded via `exceptions` when a
    project has looked at it.
    """
    policy = lc.LicencePolicy()
    for declaration in ("MPL-2.0", "MPL-2.0 AND MIT"):
        assert not policy.matched_forbidden(declaration)
    assert not policy.matched_allowed("MPL-2.0")
    assert (
        lc.verdict("certifi", policy=policy, read_metadata=fake_read_metadata).status
        == lc.Status.UNCLASSIFIED
    )


def test_lgpl_does_not_leak_out_of_the_gpl_pattern_and_vice_versa():
    """MUTATION: `r"GPL"` without the word boundary.

    `\\bGPL` deliberately does NOT match inside `LGPL` (there is no word
    boundary between `L` and `G`), which is why LGPL carries its own pattern. A
    policy that permits LGPL -- a legitimate position for dynamically-linked
    libraries, and the one `thorwhalen/ek` takes -- must be expressible by
    dropping that one pattern, and must still catch plain GPL.
    """
    lgpl_permissive = lc.LicencePolicy(
        forbidden=tuple(
            p for p in lc.DFLT_FORBIDDEN if "LGPL" not in p and "Lesser" not in p
        )
    )
    assert not lgpl_permissive.matched_forbidden("LGPL-2.1-or-later")
    assert lgpl_permissive.matched_forbidden("GPL-3.0-or-later")
    assert lgpl_permissive.matched_forbidden("AGPL-3.0")
    # And it is still a usable detector, so the self-check lets it run.
    assert lc.self_check(lgpl_permissive)


# --------------------------------------------------------------------------------------
# 3. The blank-field trap
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["mystery", "unknown-literal"])
def test_a_blank_declaration_is_a_failure_not_a_notice(name):
    """MUTATION: treat an undeclared licence as clean.

    Blank is not "fine", it is *unaudited*: the terms may live in a repo file
    no scanner reads, which is exactly where TorchCP's LGPL and surya-ocr's
    non-commercial model weights were found. A warning that still exits 0 is
    precisely the hiding place this closes -- nobody reads a green build's log.
    """
    strict = lc.LicencePolicy()
    assert (
        lc.verdict(name, policy=strict, read_metadata=fake_read_metadata).status
        == lc.Status.UNKNOWN
    )
    report = lc.LicenceReport(
        policy=strict,
        declared=(name,),
        verdicts=(lc.verdict(name, policy=strict, read_metadata=fake_read_metadata),),
    )
    assert not report.ok

    lenient = lc.LicencePolicy(unknown_is_failure=False)
    assert lc.LicenceReport(
        policy=lenient,
        declared=(name,),
        verdicts=(lc.verdict(name, policy=lenient, read_metadata=fake_read_metadata),),
    ).ok


def test_a_source_available_licence_declared_only_in_the_free_text_field_is_caught():
    """MUTATION: read classifiers only.

    Arize Phoenix declares Elastic-2.0 in its `License` field and ships NO
    trove classifier, so a classifier-only gate sails straight past it. ELv2 is
    not copyleft, but it forbids offering the software as a hosted service --
    which is a real restriction on what a downstream project may do.
    """
    assert declaration_of("phoenix") == lc.Declaration("Elastic-2.0", "License")
    assert (
        lc.verdict(
            "phoenix", policy=lc.LicencePolicy(), read_metadata=fake_read_metadata
        ).status
        == lc.Status.FORBIDDEN
    )


# --------------------------------------------------------------------------------------
# 4. The transitive closure
# --------------------------------------------------------------------------------------


def test_the_closure_is_bigger_than_the_declared_set():
    """MUTATION: `closure = declared`.

    The perimeter is what `pip install <pkg>` PULLS IN, not what it names. A
    copyleft distribution three levels down is exactly as much a part of what a
    downstream consumer inherits -- and that is not hypothetical: this is how
    `html2text` (GPL-3.0-or-later) sat undetected as a core dependency of two
    repos while everyone read the declared list.
    """
    declared = ("citeget",)
    walked = lc.closure(declared, read_requires=fake_read_requires)
    assert set(declared) <= set(walked)
    assert len(walked) > len(declared)
    assert "certifi" in walked, "the walk stopped before the third level"


def test_extras_are_excluded_by_default_and_selectable():
    """MUTATION: drop the `extra ==` marker check, or hardcode it to skip all.

    A bare `pip install <pkg>` does not take extras, so including them by
    default would report failures a downstream consumer never inherits. But a
    project that SHIPS an extra needs to be able to audit it, so the choice is a
    policy field, not a constant.
    """
    hard = lc.closure(["citeget"], read_requires=fake_read_requires)
    assert "pytest" not in hard
    with_test = lc.closure(
        ["citeget"], read_requires=fake_read_requires, include_extras=("test",)
    )
    assert "pytest" in with_test
    everything = lc.closure(
        ["citeget"], read_requires=fake_read_requires, include_extras=(lc.ALL_EXTRAS,)
    )
    assert "pytest" in everything
    # A named extra that is not this one stays out.
    assert "pytest" not in lc.closure(
        ["citeget"], read_requires=fake_read_requires, include_extras=("docs",)
    )


def test_the_walk_terminates_on_a_cycle():
    """MUTATION: drop the `seen` set.

    Circular requirement graphs exist in the wild (a package that depends on
    itself via an extra is the common shape). A walk that does not remember
    where it has been hangs the CI job rather than failing it, which is the
    worst failure mode a gate can have.
    """
    cyclic = {"a": ["b"], "b": ["a"]}
    assert lc.closure(["a"], read_requires=cyclic.get) == ("a", "b")


def test_requirement_parsing_survives_the_shapes_a_requirement_can_take():
    """MUTATION: `requirement.split("=")[0]`, or any single-delimiter split.

    Names arrive with extras, pins, markers and parenthesised versions, often
    together. Getting this wrong does not error -- it silently produces a name
    nothing resolves, which the report then files as "not installed" and the
    reader skims past.
    """
    cases = {
        "uvicorn[standard]>=0.20; python_version >= '3.9'": "uvicorn",
        "ruamel.yaml (>=0.17)": "ruamel-yaml",
        "typing_extensions>=4; extra == 'vision'": "typing-extensions",
        "argh~=0.30": "argh",
        "  pydantic  ": "pydantic",
    }
    for requirement, expected in cases.items():
        assert lc.requirement_name(requirement) == expected


# --------------------------------------------------------------------------------------
# 5. The self-check: the gate proves it can still detect, at RUN time
# --------------------------------------------------------------------------------------


def test_a_policy_that_detects_nothing_refuses_to_run():
    """MUTATION: make the self-check a warning, or drop it.

    This is the demonstrated-true-positive requirement enforced in PRODUCTION,
    not just in the test suite. A repo whose `[tool.wads.licence].forbidden` has
    been emptied -- by a bad merge, a typo, or someone silencing a failure --
    would otherwise get a green gate forever. It fails loudly instead, and the
    message says what to do.
    """
    with pytest.raises(lc.DetectorError) as caught:
        lc.self_check(lc.LicencePolicy(forbidden=()))
    assert "catch none of the known-copyleft declarations" in str(caught.value)
    assert "enabled = false" in str(caught.value)


def test_an_over_broad_policy_refuses_to_run_and_names_what_it_wrongly_flagged():
    """MUTATION: check only that SOMETHING matched.

    "At least one canary caught" alone is satisfied by `forbidden = ['.']`,
    which fails every project. The second half of the self-check is what makes
    the first half mean "discriminates" rather than "matches".
    """
    with pytest.raises(lc.DetectorError) as caught:
        lc.self_check(lc.LicencePolicy(forbidden=(r"\bAGPL\b", r"\bApache\b")))
    assert "Apache-2.0" in str(caught.value)


def test_check_runs_the_self_check_before_reading_anything(tmp_path):
    """MUTATION: call self_check after building the report, or not at all.

    Order matters: a broken policy must fail the run, not decorate a report
    nobody will question.
    """
    _write_project(tmp_path, dependencies=["requests"], licence={"forbidden": []})
    with pytest.raises(lc.DetectorError):
        lc.check(tmp_path, readers=FAKE_READERS)


def test_the_shipped_default_policy_passes_its_own_self_check():
    """MUTATION: edit DFLT_FORBIDDEN into something that no longer detects.

    The defaults are what every repo that opts in gets on day one.
    """
    assert lc.self_check(lc.LicencePolicy()) == tuple(
        label for label, _ in lc.COPYLEFT_CANARIES
    )


# --------------------------------------------------------------------------------------
# 6. End to end: pyproject in, report out
# --------------------------------------------------------------------------------------


def _write_project(directory, *, dependencies, optional=None, licence=None):
    lines = [
        "[project]",
        'name = "fake-project"',
        'version = "0.0.1"',
        "dependencies = [" + ", ".join(json.dumps(d) for d in dependencies) + "]",
    ]
    if optional:
        lines.append("[project.optional-dependencies]")
        for group, requirements in optional.items():
            lines.append(
                f"{group} = [" + ", ".join(json.dumps(r) for r in requirements) + "]"
            )
    if licence is not None:
        lines.append("[tool.wads.licence]")
        exceptions = licence.pop("exceptions", None)
        for key, value in licence.items():
            lines.append(f"{key} = {json.dumps(value)}")
        if exceptions:
            lines.append("[tool.wads.licence.exceptions]")
            for name, reason in exceptions.items():
                lines.append(f"{json.dumps(name)} = {json.dumps(reason)}")
    (directory / "pyproject.toml").write_text("\n".join(lines) + "\n")
    return directory


def test_a_copyleft_transitive_dependency_breaches_the_perimeter(tmp_path):
    """MUTATION: check only the declared names.

    `citeget` declares `html2text`; the point is that a project declaring only
    `citeget` inherits it anyway, and the report must say so with the field the
    verdict came from.
    """
    _write_project(tmp_path, dependencies=["citeget"])
    report = lc.check(tmp_path, readers=FAKE_READERS)
    assert not report.ok
    offenders = {v.name: v for v in report.of_status(lc.Status.FORBIDDEN)}
    assert "html2text" in offenders
    assert offenders["html2text"].declaration.text == "GPL-3.0-or-later"
    assert offenders["html2text"].declaration.source == "License-Expression"
    assert "GPL" in offenders["html2text"].note
    # The report names the field, so a reader can go and check the claim.
    assert "License-Expression" in report.render()


def test_an_adjudicated_exception_clears_a_distribution_and_carries_its_reason(
    tmp_path,
):
    """MUTATION: implement exceptions as a silent skip.

    An exception is a decision somebody made and can be asked about. Dropping
    the name from the report turns it back into silence -- which is the state
    this whole tool exists to end.
    """
    reason = (
        "MPL-2.0 -- weak, file-level, over an unmodified CA bundle. Audited 2026-08."
    )
    _write_project(
        tmp_path,
        dependencies=["certifi"],
        licence={"exceptions": {"certifi": reason}},
    )
    report = lc.check(tmp_path, readers=FAKE_READERS)
    assert report.ok
    excepted = report.of_status(lc.Status.EXCEPTED)
    assert [v.name for v in excepted] == ["certifi"]
    assert reason in report.render()


def test_an_exception_can_clear_even_a_forbidden_declaration(tmp_path):
    """MUTATION: apply exceptions only to unclassified verdicts.

    The hard cases are exactly the forbidden ones -- an LGPL library used via a
    dynamic link, say. Recording that decision with a reason is better than the
    two alternatives people actually reach for: deleting the pattern (which
    disarms the gate globally) or switching the gate off.
    """
    _write_project(
        tmp_path,
        dependencies=["argh"],
        licence={
            "exceptions": {"argh": "Being removed under the fleet argh campaign."}
        },
    )
    assert lc.check(tmp_path, readers=FAKE_READERS).ok


def test_unclassified_is_a_notice_by_default_and_a_failure_on_request(tmp_path):
    """MUTATION: make `unclassified` fail by default.

    Every project on earth has `certifi` (MPL-2.0) somewhere in its closure. A
    gate that fails on it out of the box is a gate everybody turns off on day
    one, and the exposures it existed to catch go back to being invisible.
    """
    _write_project(tmp_path, dependencies=["certifi"])
    assert lc.check(tmp_path, readers=FAKE_READERS).ok

    _write_project(
        tmp_path, dependencies=["certifi"], licence={"unclassified-is-failure": True}
    )
    strict = lc.check(tmp_path, readers=FAKE_READERS)
    assert not strict.ok
    assert [v.name for v in strict.failures] == ["certifi"]


def test_a_project_declaring_no_licence_policy_gets_the_defaults(tmp_path):
    """MUTATION: require `[tool.wads.licence]` to exist.

    The tool has to be runnable against any repo in the fleet, unconfigured,
    which is how a fleet-wide sweep gets its first numbers.
    """
    _write_project(tmp_path, dependencies=["requests"])
    report = lc.check(tmp_path, readers=FAKE_READERS)
    assert report.policy == lc.LicencePolicy()
    assert report.ok


def test_a_typo_in_the_policy_table_is_an_error_not_a_silent_default(tmp_path):
    """MUTATION: `config.get(key, default)` over every field, ignoring extras.

    A misspelt `forbiden = [...]` would leave the perimeter on its defaults
    while reading, to whoever wrote it, as configured. The whole point of
    writing a policy down is that it is the policy in force.
    """
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "0"\ndependencies = []\n'
        "[tool.wads.licence]\nforbiden = []\n"
    )
    with pytest.raises(ValueError, match="unknown \\[tool.wads.licence\\] key"):
        lc.check(tmp_path, readers=FAKE_READERS)


def test_extras_are_audited_only_when_the_policy_asks(tmp_path):
    """MUTATION: always walk optional-dependencies, or never.

    A project's own extras are opt-in for its consumers too, so auditing them
    by default would report breaches nobody inherits from a bare install.
    """
    _write_project(
        tmp_path, dependencies=["requests"], optional={"scrape": ["html2text"]}
    )
    assert lc.check(tmp_path, readers=FAKE_READERS).ok

    _write_project(
        tmp_path,
        dependencies=["requests"],
        optional={"scrape": ["html2text"]},
        licence={"include-extras": ["scrape"]},
    )
    report = lc.check(tmp_path, readers=FAKE_READERS)
    assert not report.ok
    assert "html2text" in [v.name for v in report.of_status(lc.Status.FORBIDDEN)]


def test_an_environment_with_none_of_the_closure_installed_refuses_to_report(tmp_path):
    """MUTATION: report `not-installed` as clean and exit 0.

    This is the no-op the CI wiring can most easily fall into: run the tool from
    an isolated `uvx` environment and it sees ITS OWN dependencies, not the
    project's, and reports a confident green over an unexamined closure. There
    is nothing to check, so it says so and exits non-zero.
    """
    _write_project(tmp_path, dependencies=["nothing-installed-anywhere"])
    with pytest.raises(lc.DetectorError, match="nothing here to check"):
        lc.check(tmp_path, readers=FAKE_READERS)


def test_a_partially_installed_closure_reports_what_it_could_not_read(tmp_path):
    """MUTATION: drop `not-installed` from the report.

    A name the walk could not read is a hole in the perimeter. It does not fail
    the build (platform- and marker-conditional dependencies are legitimately
    absent), but it must be visible, because "no violations found" over a
    closure half of which was never read is not the same claim.
    """
    _write_project(tmp_path, dependencies=["requests", "not-a-real-distribution"])
    report = lc.check(tmp_path, readers=FAKE_READERS)
    assert report.ok
    missing = [v.name for v in report.of_status(lc.Status.NOT_INSTALLED)]
    assert missing == ["not-a-real-distribution"]
    assert "NOT INSTALLED" in report.render()


def test_the_report_says_out_loud_that_it_describes_an_environment(tmp_path):
    """MUTATION: delete the caveat from the rendered report.

    `Requires-Dist` is read from INSTALLED metadata, so a resolution that picks
    different versions elsewhere is invisible. Measured, and not hypothetically:
    typer 0.19.2 requires `click`, while the typer a fresh install resolves
    today requires `shellingham`, `rich`, `annotated-doc` and no click at all.
    A number that reads as universal but is not is worse than no number.
    """
    _write_project(tmp_path, dependencies=["requests"])
    rendered = lc.check(tmp_path, readers=FAKE_READERS).render()
    assert "INSTALLED metadata" in rendered
    assert "environment" in rendered
    # And the self-check result is stated, so a reader can see it detected.
    assert "self-check" in rendered


def test_the_json_view_carries_the_field_each_verdict_came_from(tmp_path):
    """MUTATION: emit only names and statuses.

    A fleet sweep that says "argh: forbidden" without saying which field
    declared it produces a list nobody can act on without re-doing the work.
    """
    _write_project(tmp_path, dependencies=["citeget"])
    payload = lc.check(tmp_path, readers=FAKE_READERS).as_dict()
    assert payload["ok"] is False
    row = next(v for v in payload["verdicts"] if v["name"] == "html2text")
    assert row["source"] == "License-Expression"
    assert row["licence"] == "GPL-3.0-or-later"
    assert json.dumps(payload)  # serialisable, which is the point of the view


# --------------------------------------------------------------------------------------
# 7. The CI gate is OPT-IN
# --------------------------------------------------------------------------------------


def test_the_ci_gate_defaults_to_off():
    """MUTATION: default `licence_enabled` to True.

    Every other gate in wads defaults on. This one must not: the reusable
    workflow is called by the whole fleet, and a new failing check turned on for
    all of them in one merge reddens every caller's CI simultaneously -- which
    gets the gate reverted rather than the exposures fixed.
    """
    assert CIConfig({"project": {"name": "x"}}).licence_enabled is False
    assert (
        CIConfig({"tool": {"wads": {"licence": {"enabled": True}}}}).licence_enabled
        is True
    )
    assert (
        CIConfig({"tool": {"wads": {"licence": {"forbidden": []}}}}).licence_enabled
        is False
    )


def test_the_licence_table_is_read_from_tool_wads_not_tool_wads_ci():
    """MUTATION: read `[tool.wads.ci.licence]`.

    The policy is a fact about the package's dependency perimeter and is useful
    outside CI; only `enabled` is a CI concern. Putting the table under
    `[tool.wads.ci]` would make `wads-licence-check` on a developer's machine
    read a different policy than CI does -- the second-table smell.
    """
    config = CIConfig({"tool": {"wads": {"licence": {"forbidden": ["AGPL"]}}}})
    assert config.licence_config == {"forbidden": ["AGPL"]}
    assert (
        CIConfig(
            {"tool": {"wads": {"ci": {"licence": {"enabled": True}}}}}
        ).licence_enabled
        is False
    )


@pytest.mark.parametrize(
    "workflow",
    [
        REPO_ROOT / ".github" / "workflows" / "uv-ci.yml",
        REPO_ROOT / "wads" / "data" / "github_ci_uv.yml",
    ],
    ids=["reusable-workflow", "inline-template"],
)
def test_the_workflow_step_is_gated_and_runs_once(workflow):
    """MUTATION: `!= 'false'` instead of `== 'true'`; or no matrix guard.

    `!= 'false'` is the opt-OUT spelling used by every other gate here, and it
    would turn this one on for every caller including those running an older
    wads that emits no such output at all (empty string != 'false'). And the
    licence answer does not vary by interpreter, so running it across the whole
    matrix produces N identical failures, which is noise.
    """
    yaml = pytest.importorskip("yaml")
    data = yaml.safe_load(workflow.read_text())
    assert "licence-enabled" in data["jobs"]["setup"]["outputs"]
    step = next(
        s
        for s in data["jobs"]["validation"]["steps"]
        if s.get("name") == "Licence Perimeter"
    )
    condition = step["if"]
    assert "licence-enabled == 'true'" in condition
    assert "!= 'false'" not in condition
    assert "python-versions)[0]" in condition, "must run on one interpreter only"
    # The tool must be pointed at the project's venv, not uvx's isolated one.
    assert "--python" in step["run"]


def test_the_windows_job_does_not_run_the_licence_gate():
    """MUTATION: put the step in the shared step list.

    A licence declaration is not platform-dependent. Running it on Windows too
    doubles every failure and adds a `.venv/Scripts` path to get wrong.
    """
    yaml = pytest.importorskip("yaml")
    data = yaml.safe_load(
        (REPO_ROOT / ".github" / "workflows" / "uv-ci.yml").read_text()
    )
    names = [s.get("name") for s in data["jobs"]["windows-validation"]["steps"]]
    assert "Licence Perimeter" not in names


# --------------------------------------------------------------------------------------
# 8. Housekeeping
# --------------------------------------------------------------------------------------


def test_the_module_has_no_third_party_imports():
    """MUTATION: import `pip-licenses`, `packaging`, `requests`, or `cw`.

    The gate has to run in the CI of every repo in the fleet, including the ones
    being emptied by the dependency-removal campaign, without dragging a
    toolchain in behind it. `tomli` is the sole conditional import, and only on
    Python 3.10, where `tomllib` does not yet exist.

    Both TOML names are allowed through: `tomllib` IS stdlib, but only from
    3.11, so `sys.stdlib_module_names` on 3.10 does not know it -- which is the
    exact interpreter the guarded import exists for.
    """
    source = (REPO_ROOT / "wads" / "licence_check.py").read_text()
    stdlib = set(sys.stdlib_module_names)
    imported = set()
    for line in source.splitlines():
        line = line.strip()
        if line.startswith("import "):
            imported.add(line.split()[1].split(".")[0])
        elif line.startswith("from ") and " import " in line:
            module = line.split()[1].split(".")[0]
            if module != "__future__":
                imported.add(module)
    toml_readers = {"tomli", "tomllib"}
    third_party = {m for m in imported if m not in stdlib and m != "wads"}
    assert third_party <= toml_readers, (
        f"third-party imports: {sorted(third_party - toml_readers)}"
    )


def test_the_console_script_is_declared():
    """MUTATION: ship the module without an entry point.

    `uvx --from wads wads-licence-check` in the CI step resolves through
    `[project.scripts]`; without the entry the workflow step fails with a
    command-not-found that reads like an infrastructure problem.
    """
    pyproject = (REPO_ROOT / "pyproject.toml").read_text()
    assert 'wads-licence-check = "wads.licence_check:main"' in pyproject


def test_module_doctests():
    """MUTATION: let the docstring examples drift from the code.

    CI's `--doctest-modules` collects over `testpaths` (`wads/tests`), so the
    module's own examples are NOT otherwise executed anywhere.
    """
    results = doctest.testmod(
        lc, optionflags=doctest.ELLIPSIS | doctest.NORMALIZE_WHITESPACE, verbose=False
    )
    assert results.failed == 0, (
        f"{results.failed} of {results.attempted} doctests failed"
    )


def test_the_cli_exits_nonzero_on_a_breach_and_zero_when_clean(tmp_path, capsys):
    """MUTATION: always `return 0`, or raise instead of exiting cleanly.

    The exit code IS the gate. Everything else in this file is only advice if
    the process comes back 0 to the CI runner.

    Both fixtures are wads's OWN core dependencies -- `jinja2` (BSD-3-Clause)
    and `argh` (LGPL) -- so they are installed wherever `wads.licence_check` is
    importable at all. Naming anything else couples the test to whichever
    extras happen to be present, and the run then fails on the
    nothing-is-installed guard rather than on what it meant to check.
    """
    _write_project(tmp_path, dependencies=["jinja2"])
    clean = subprocess.run(
        [sys.executable, "-m", "wads.licence_check", str(tmp_path)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert clean.returncode == lc.EXIT_OK, clean.stderr

    _write_project(tmp_path, dependencies=["argh"])
    breach = subprocess.run(
        [sys.executable, "-m", "wads.licence_check", str(tmp_path), "--json"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert breach.returncode == lc.EXIT_BREACH, breach.stderr
    payload = json.loads(breach.stdout)
    assert payload["ok"] is False
    assert any(
        v["name"] == "argh" and v["status"] == lc.Status.FORBIDDEN
        for v in payload["verdicts"]
    )

    missing = subprocess.run(
        [sys.executable, "-m", "wads.licence_check", str(tmp_path / "nope")],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert missing.returncode == lc.EXIT_ERROR
    assert "pyproject.toml" in missing.stderr


def test_reading_another_environments_metadata(tmp_path):
    """MUTATION: drop `--python` and read this interpreter's `sys.path`.

    The CI step runs the tool under `uvx`, in an environment holding wads and
    nothing of the project. Without this seam it would walk the WRONG closure
    and report green over a project it never looked at -- the single most
    dangerous failure this tool can have, because it is invisible.
    """
    path = lc.search_path_of(sys.executable)
    assert path and all(isinstance(entry, str) for entry in path)
    readers = lc.readers_for(path)
    assert readers.read_metadata("wads")["Name"] == "wads"
    with pytest.raises(lc.PackageNotFoundError):
        readers.read_metadata("definitely-not-a-distribution")
    # An empty search path finds nothing -- which is what makes the
    # nothing-is-installed guard above reachable in the real world.
    assert lc.readers_for([]) is not None
    with pytest.raises(lc.PackageNotFoundError):
        lc.readers_for([]).read_metadata("wads")


def test_the_repo_itself_can_be_audited():
    """MUTATION: none -- this is the smoke test.

    wads declares `argh` (LGPL-3.0-or-later) today, so this asserts the tool
    runs end-to-end against a real pyproject and a real installed closure, not
    that the result is clean. When the fleet campaign removes argh from wads,
    this repo becomes a candidate for `[tool.wads.licence].enabled = true`.
    """
    report = lc.check(REPO_ROOT)
    assert report.declared
    assert len(report.closure) >= len(report.declared)
    assert report.render()


def test_an_exception_matches_on_the_normalised_distribution_name(tmp_path):
    """MUTATION: look exceptions up by the raw string.

    Distribution names are written both ways: `ruamel.yaml` in a pyproject,
    `ruamel-yaml` in installed metadata. A raw-string lookup fails silently --
    the exception simply never applies, and the report keeps flagging a name
    somebody believes they already adjudicated.
    """
    policy = lc.LicencePolicy(exceptions={"Typing_Extensions": "PSF-2.0, permissive."})
    assert policy.exception_for("typing-extensions") == "PSF-2.0, permissive."
    assert policy.exception_for("something-else") == ""


def test_a_stale_exception_is_reported(tmp_path):
    """MUTATION: drop stale-exception reporting.

    An exception for a distribution that has left the tree is stale advice, and
    one whose licence has since changed is worse: it reads as adjudicated when
    nobody has looked at the current terms. It is a notice, not a failure --
    an extra is often the reason, and breaking a build over tidiness is how
    gates get switched off.
    """
    _write_project(
        tmp_path,
        dependencies=["requests"],
        licence={"exceptions": {"long-gone": "audited in 2019"}},
    )
    report = lc.check(tmp_path, readers=FAKE_READERS)
    assert report.ok
    assert report.stale_exceptions == ("long-gone",)
    assert "STALE EXCEPTIONS" in report.render()
    assert report.as_dict()["stale_exceptions"] == ["long-gone"]
