"""Regression guards for two CI wiring bugs (see issue #45 follow-up).

1. A GitHub *expression* (``${{ ... }}``) written literally inside an action
   manifest's input ``description``/``default`` is evaluated at manifest-load
   time. Referencing the ``secrets`` context there crashes the whole action
   ("Unrecognized named-value: 'secrets'"), which took down the validation job.

2. The reusable workflow's ``publish`` job must be gated on the Linux
   ``validation`` matrix — a failing test must block publication. This pins
   that the gate has no status-function escape hatch (``!cancelled()`` /
   ``always()``) and that ``validation`` is a dependency.
"""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
ACTIONS_DIR = REPO_ROOT / "actions"
UV_CI = REPO_ROOT / ".github" / "workflows" / "uv-ci.yml"


def test_no_action_input_embeds_github_expression():
    """No action.yml input description/default may contain a `${{ }}` expression."""
    offenders = []
    for action_yml in ACTIONS_DIR.glob("*/action.yml"):
        data = yaml.safe_load(action_yml.read_text())
        for name, spec in (data.get("inputs") or {}).items():
            for field in ("description", "default"):
                val = spec.get(field)
                if isinstance(val, str) and "${{" in val:
                    offenders.append(f"{action_yml.parent.name}:{name}.{field}")
    assert not offenders, (
        "GitHub expressions in action input description/default are evaluated at "
        f"manifest load and can crash the action: {offenders}"
    )


def _jobs(path: Path):
    data = yaml.safe_load(path.read_text())
    return data["jobs"]


def test_publish_is_gated_on_validation():
    publish = _jobs(UV_CI)["publish"]
    needs = publish["needs"]
    assert "validation" in needs and "setup" in needs
    cond = publish["if"]
    # No status function -> implicit success() requires all `needs` to pass,
    # so a failing validation blocks publish. Reject the escape hatches.
    assert "cancelled(" not in cond, (
        "publish must not bypass validation via !cancelled()"
    )
    assert "always(" not in cond, "publish must not run via always()"


def test_publish_gates_on_actual_default_branch():
    """Publish must key off the repo's real default branch, not a literal master/main.

    Keeps publish and github-pages consistent and correct for repos whose
    default branch is neither 'master' nor 'main'.
    """
    cond = _jobs(UV_CI)["publish"]["if"]
    assert "github.event.repository.default_branch" in cond
    assert "refs/heads/master" not in cond and "refs/heads/main" not in cond


def test_windows_validation_is_optional_and_separate():
    jobs = _jobs(UV_CI)
    win = jobs["windows-validation"]
    # Windows is continue-on-error and is NOT a publish dependency, so it never
    # blocks publication.
    assert win.get("continue-on-error") is True
    assert "windows-validation" not in jobs["publish"]["needs"]


# ---------------------------------------------------------------------------
# Marker gates match the commit SUBJECT, never the whole commit message.
#
# A squash-merge folds the ENTIRE PR BODY into the squash commit message. A
# gate written as `contains(github.event.head_commit.message, '<marker>')`
# therefore fires on a PR that merely WRITES ABOUT a marker — which is how a
# PR body quoting the publish marker forced a publish on a repo that had
# publishing disabled and reddened a default branch that had just gone green
# for the first time in a year.
#
# The gates now read a `commit-subject` output that the setup job computes as
# the first line of the message. `startsWith()` is NOT an acceptable
# substitute and these tests reject it: this house's marker convention is
# TRAILING and GitHub appends " (#N)" to every squash subject, so a prefix
# match would convert a gate that fires too often into one that silently
# never fires.
#
# Nothing here was covered before: the old assertions only checked that the
# gate *referenced* the marker outputs, so a refactor could have swapped the
# matching function back with the whole suite green.
# ---------------------------------------------------------------------------

import os
import re
import shutil
import subprocess
import tempfile

import pytest

DATA_DIR = REPO_ROOT / "wads" / "data"
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

# Every workflow that carries a marker gate AND a setup job to hang the
# subject output on. Keep in sync with the templates; a new gated template
# belongs here.
GATED_WORKFLOWS = (
    UV_CI,
    DATA_DIR / "github_ci_uv.yml",
    DATA_DIR / "github_ci_publish_2025.yml",
)

SUBJECT_OUTPUT_REF = "needs.setup.outputs.commit-subject"
WHOLE_MESSAGE_REF = "github.event.head_commit.message"

# The uv side names job outputs with hyphens, the npm side with underscores.
SUBJECT_OUTPUT_NAMES = ("commit-subject", "commit_subject")


def _workflow(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def _subject_output_name(setup_job: dict) -> str | None:
    outputs = setup_job.get("outputs") or {}
    return next((n for n in SUBJECT_OUTPUT_NAMES if n in outputs), None)


def _discover_extracting_workflows():
    """Every workflow that computes a commit subject — found, not listed.

    Deliberately DISCOVERED rather than enumerated. A hardcoded list is what
    let the two npm reusable workflows keep gating publication on the full
    message while the uv side was being fixed: "the files I was looking at"
    is not a population. Anything that grows a subject output is covered by
    the behavioural tests below the day it appears.
    """
    found = []
    for path in sorted(WORKFLOWS_DIR.glob("*.yml")) + sorted(DATA_DIR.glob("*.yml")):
        try:
            doc = yaml.safe_load(path.read_text())
        except yaml.YAMLError:
            continue
        if not isinstance(doc, dict):
            continue
        setup = (doc.get("jobs") or {}).get("setup")
        if isinstance(setup, dict) and _subject_output_name(setup):
            found.append(path)
    return tuple(found)


EXTRACTING_WORKFLOWS = _discover_extracting_workflows()


def _job_conditions(path: Path):
    """Yield (job_name, if_condition) for every job that declares one."""
    for name, job in _workflow(path)["jobs"].items():
        cond = job.get("if")
        if cond:
            yield name, cond


def _contains_haystacks(condition: str):
    """First argument of every `contains(...)` call in a job condition."""
    return [m.strip() for m in re.findall(r"contains\(\s*([^,]+?)\s*,", condition)]


@pytest.mark.parametrize("path", GATED_WORKFLOWS, ids=lambda p: p.name)
def test_marker_gates_match_the_subject_not_the_whole_message(path):
    """Every `contains()` gate reads the subject output, not the raw message.

    This is the assertion that was missing: the pre-existing tests checked
    only that the marker OUTPUTS were referenced, never WHICH haystack the
    matching function was handed.
    """
    offenders = []
    for job, cond in _job_conditions(path):
        if WHOLE_MESSAGE_REF in cond:
            offenders.append(f"{job}: reads the whole commit message")
        for haystack in _contains_haystacks(cond):
            if haystack != SUBJECT_OUTPUT_REF:
                offenders.append(f"{job}: contains() over {haystack!r}")
    assert not offenders, (
        f"{path.name}: marker gates must match the commit subject "
        f"({SUBJECT_OUTPUT_REF}); a PR body is folded into the squash commit "
        f"message and would otherwise trip the gate: {offenders}"
    )


@pytest.mark.parametrize("path", GATED_WORKFLOWS, ids=lambda p: p.name)
def test_no_gate_uses_startswith(path):
    """`startsWith()` is the wrong fix and must not appear in a gate.

    Markers are written at the END of a subject and GitHub appends " (#N)"
    to every squash subject, so a prefix match never fires — the same defect
    as the body trap, in the direction nobody notices.
    """
    offenders = [job for job, cond in _job_conditions(path) if "startsWith(" in cond]
    assert not offenders, (
        f"{path.name}: startsWith() cannot match this house's TRAILING marker "
        f"convention and would silently disable the gate: {offenders}"
    )


@pytest.mark.parametrize("path", GATED_WORKFLOWS, ids=lambda p: p.name)
def test_setup_job_publishes_the_commit_subject_output(path):
    """The subject output exists and is wired to the extraction step's id."""
    setup = _workflow(path)["jobs"]["setup"]
    outputs = setup["outputs"]
    assert "commit-subject" in outputs, "setup job must expose commit-subject"
    step_ids = {s.get("id") for s in setup["steps"]}
    referenced = re.search(r"steps\.([\w-]+)\.outputs", outputs["commit-subject"])
    assert referenced, (
        f"commit-subject output must read a step output: {outputs['commit-subject']!r}"
    )
    assert referenced.group(1) in step_ids, (
        f"commit-subject reads step id {referenced.group(1)!r}, which no step declares"
    )


@pytest.mark.parametrize("path", GATED_WORKFLOWS, ids=lambda p: p.name)
def test_every_gated_job_depends_on_setup(path):
    """A job reading `needs.setup.*` must actually declare `setup` in needs."""
    jobs = _workflow(path)["jobs"]
    for name, job in jobs.items():
        cond = job.get("if", "")
        if "needs.setup." not in cond:
            continue
        needs = job.get("needs")
        needs = [needs] if isinstance(needs, str) else (needs or [])
        assert "setup" in needs, (
            f"{path.name}:{name} reads needs.setup but does not need it"
        )


@pytest.mark.parametrize("path", GATED_WORKFLOWS, ids=lambda p: p.name)
def test_commit_message_reaches_the_shell_only_through_the_environment(path):
    """The untrusted message is never spliced into the run script.

    Interpolating `${{ github.event.head_commit.message }}` into `run:` would
    let a crafted commit message inject shell syntax into the setup job.
    """
    step = _extraction_step(path)
    assert "${{" not in step["run"], (
        "the commit message must not be interpolated into the run script; "
        "pass it via env: so quotes/newlines cannot become shell syntax"
    )
    env_values = " ".join(str(v) for v in (step.get("env") or {}).values())
    assert WHOLE_MESSAGE_REF in env_values, (
        "the extraction step must receive the message through env:"
    )


def _extraction_step(path: Path) -> dict:
    setup = _workflow(path)["jobs"]["setup"]
    name = _subject_output_name(setup)
    assert name, f"{path.name}: setup job exposes no commit-subject output"
    step_id = re.search(r"steps\.([\w-]+)\.outputs", setup["outputs"][name]).group(1)
    return next(s for s in setup["steps"] if s.get("id") == step_id)


def test_every_extracting_workflow_ships_the_same_script():
    """One extraction script, copied across workflows; it must not drift.

    Covers the npm reusable workflows too, whose copies would otherwise be
    verified by nothing executable.
    """
    scripts = {p.name: _extraction_step(p)["run"] for p in EXTRACTING_WORKFLOWS}
    assert len(scripts) >= len(GATED_WORKFLOWS), (
        f"discovery found fewer extracting workflows than are known to exist: "
        f"{sorted(scripts)}"
    )
    assert len(set(scripts.values())) == 1, (
        f"extraction scripts diverged across workflows: {sorted(scripts)}"
    )


# --- behavioural: run the shipped script, then evaluate the real gate ------


def _run_extraction(path: Path, message: str) -> str:
    """Execute the workflow's own extraction script and return the subject.

    This runs the shipped shell, not a re-implementation of it, so a change
    to the script is a change to what this test observes.
    """
    step = _extraction_step(path)
    with tempfile.TemporaryDirectory() as tmp:
        github_output = os.path.join(tmp, "github_output")
        open(github_output, "w").close()
        env = dict(
            os.environ,
            HEAD_COMMIT_MESSAGE=message,
            GITHUB_OUTPUT=github_output,
        )
        result = subprocess.run(
            ["bash", "-e", "-c", step["run"]],
            env=env,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        raw = open(github_output).read()
    # $GITHUB_OUTPUT heredoc form: `name<<DELIM\n<value>\nDELIM\n`
    lines = raw.splitlines()
    assert lines[0].startswith("subject<<"), raw
    delimiter = lines[0].split("<<", 1)[1]
    assert lines[-1] == delimiter, raw
    return "\n".join(lines[1:-1])


def _gh_contains(haystack: str, needle: str) -> bool:
    """GitHub's `contains()` for strings: case-insensitive substring."""
    return needle.lower() in haystack.lower()


def _bash_is_usable() -> bool:
    """Is there a POSIX bash here that can actually run a script?

    Probes the capability rather than the platform, because `which("bash")`
    is not evidence of one: on a GitHub windows-latest runner it resolves to
    `C:\\Windows\\System32\\bash.exe`, the WSL launcher, which exits 1 with no
    distro installed. The production shell for these workflows is the Linux
    runner's bash; the blocking Linux legs run these tests, and a box without
    a working bash reports them as SKIPPED rather than as failures nobody can
    act on.
    """
    if shutil.which("bash") is None:
        return False
    try:
        probe = subprocess.run(
            ["bash", "-c", "printf ok"], capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return probe.returncode == 0 and probe.stdout.strip() == "ok"


bash_required = pytest.mark.skipif(
    not _bash_is_usable(),
    reason="needs a working POSIX bash to run the workflow's own script",
)


@bash_required
@pytest.mark.parametrize("path", EXTRACTING_WORKFLOWS, ids=lambda p: p.name)
def test_extraction_keeps_only_the_first_line(path):
    message = "Land the thing (#41)\n\nSecond line\nThird line\n"
    assert _run_extraction(path, message) == "Land the thing (#41)"


@bash_required
@pytest.mark.parametrize("path", EXTRACTING_WORKFLOWS, ids=lambda p: p.name)
def test_a_marker_only_in_the_body_does_not_satisfy_the_gate(path):
    """THE regression this change exists to prevent.

    A squash commit whose body merely discusses a marker must not trip the
    gate. Asserted as the gate's VERDICT, not as the presence of a string.
    """
    marker = "[" + "publish" + "]"  # assembled so this file carries no literal marker
    message = (
        "Gate the publish job on the subject line (#41)\n"
        "\n"
        f"A PR body that writes {marker} used to force a publish, because the\n"
        "squash commit message contains the whole body.\n"
    )
    subject = _run_extraction(path, message)
    assert _gh_contains(message, marker), "precondition: the full message does match"
    assert not _gh_contains(subject, marker), (
        "a marker appearing only in a body line must not satisfy the gate"
    )


@bash_required
@pytest.mark.parametrize("path", EXTRACTING_WORKFLOWS, ids=lambda p: p.name)
def test_a_trailing_marker_in_the_subject_still_satisfies_the_gate(path):
    """The half `startsWith()` would have broken.

    Real squash subjects put the marker last, after which GitHub appends
    " (#N)". Both must still match.
    """
    marker = "[" + "bump minor" + "]"
    subject_line = (
        "cw v1: an MIT replacement for argh, bit-for-bit compatible "
        f"by default {marker} (#33)"
    )
    subject = _run_extraction(path, subject_line + "\n\nBody text.\n")
    assert subject == subject_line
    assert _gh_contains(subject, marker)
    assert not subject.startswith(marker), (
        "documents why startsWith() is rejected: the marker is trailing"
    )


@bash_required
@pytest.mark.parametrize("path", EXTRACTING_WORKFLOWS, ids=lambda p: p.name)
def test_extraction_survives_a_hostile_commit_message(path):
    """Shell metacharacters in the message are data, never syntax."""
    hostile = "fix `id` and \"q\" $(touch /tmp/wads_pwned) '; echo pwned' (#9)"
    assert _run_extraction(path, hostile + "\n\nbody\n") == hostile


@bash_required
@pytest.mark.parametrize("path", EXTRACTING_WORKFLOWS, ids=lambda p: p.name)
def test_extraction_handles_crlf_and_an_absent_head_commit(path):
    """CRLF leaves no stray carriage return; no head commit yields no subject.

    On a pull_request event `github.event.head_commit` is null, the
    expression renders empty, and every `contains()` gate is false — the
    same verdict the whole-message form gave.
    """
    assert _run_extraction(path, "Subject (#7)\r\nbody\r\n") == "Subject (#7)"
    assert _run_extraction(path, "") == ""


# ---------------------------------------------------------------------------
# The marker gates must read the commit SUBJECT, never the whole message.
#
# A squash-merge folds the entire PR BODY into the squash commit message, so a
# `contains()` over the full message fires on a PR that merely writes ABOUT a
# marker. That has already cost this fleet two real signals: a spurious publish
# on a publish-disabled repo (2026-08-17), and a run that was never created at
# all (2026-09-02).
#
# This sweeps EVERY reusable workflow rather than the one that was fixed,
# because the first pass at this change fixed uv-ci.yml and left both npm
# workflows still gating publication on the full message.
# ---------------------------------------------------------------------------


def _live_workflows():
    return sorted(WORKFLOWS_DIR.glob("*.yml"))


def test_no_live_workflow_gates_a_job_on_the_full_commit_message():
    offenders = []
    for path in _live_workflows():
        for number, line in enumerate(path.read_text().splitlines(), 1):
            if "head_commit.message" not in line:
                continue
            # The one legitimate use: handing the message to a step through the
            # environment, where it is data rather than a gate.
            if "HEAD_COMMIT_MESSAGE" in line:
                continue
            offenders.append(f"{path.name}:{number}: {line.strip()}")
    assert not offenders, (
        "these gate on the full commit message, which a squash-merge fills "
        "with the PR body:\n  " + "\n  ".join(offenders)
    )


def test_every_workflow_with_a_marker_gate_extracts_the_subject_safely():
    """The extraction must take the message through `env:`, never splice it
    into a command line — it is untrusted, attacker-influenced, multi-line text."""
    for path in _live_workflows():
        text = path.read_text()
        if "commit_subject" not in text and "commit-subject" not in text:
            continue
        doc = yaml.safe_load(text)
        steps = doc["jobs"]["setup"]["steps"]
        commit_step = next((s for s in steps if s.get("id") == "commit"), None)
        assert commit_step is not None, f"{path.name}: no subject-extraction step"
        assert "HEAD_COMMIT_MESSAGE" in (commit_step.get("env") or {}), (
            f"{path.name}: the message must reach bash through env:, not inline"
        )
        assert "${{ github.event.head_commit.message }}" not in commit_step["run"], (
            f"{path.name}: the message is spliced into the run script — a "
            "commit subject containing a quote could then become shell syntax"
        )


def test_the_subject_gate_is_used_wherever_a_marker_is_matched():
    """A workflow that names a marker must match it against the subject."""
    for path in _live_workflows():
        text = path.read_text()
        if "publish_marker" not in text and "publish-marker" not in text:
            continue
        assert "commit_subject" in text or "commit-subject" in text, (
            f"{path.name} matches a publish marker but has no subject output"
        )
