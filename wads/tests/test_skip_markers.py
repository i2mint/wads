"""The ``[skip publish]`` / ``[skip github-pages]`` markers (i2mint/wads#62).

The setup job of both uv workflows decides the skip markers once, in a bash step
("Decide skip markers"), and the publish and github-pages jobs gate on its
``skip-publish`` / ``skip-pages`` outputs. These tests run that shipped step under
bash with fake subjects and marker outputs, then feed its verdict into each job's
real ``if:`` through the expression evaluator of ``test_ci_trigger``, so what is
asserted is what GitHub would decide, not a re-implementation of it.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import pytest
import yaml

from wads.ci_config import (
    DFLT_SKIP_PAGES_MARKER,
    DFLT_SKIP_PUBLISH_MARKER,
    CIConfig,
)
from wads.tests.test_workflow_gates import _run_extraction, bash_required

REPO_ROOT = Path(__file__).resolve().parents[2]
UV_CI = REPO_ROOT / ".github" / "workflows" / "uv-ci.yml"
INLINE = REPO_ROOT / "wads" / "data" / "github_ci_uv.yml"
WORKFLOWS = pytest.mark.parametrize("workflow", (UV_CI, INLINE), ids=lambda p: p.name)
STEP_NAME = "Decide skip markers"


def _gates_step(workflow: Path) -> dict:
    steps = yaml.safe_load(workflow.read_text())["jobs"]["setup"]["steps"]
    (step,) = [s for s in steps if s.get("name") == STEP_NAME]
    return step


def run_gates(
    workflow: Path,
    subject: str,
    *,
    skip_ci: str = "[skip ci]",
    skip_publish: str = DFLT_SKIP_PUBLISH_MARKER,
    skip_pages: str = DFLT_SKIP_PAGES_MARKER,
) -> dict[str, str]:
    """Run the workflow's own gates step; return its outputs."""
    step = _gates_step(workflow)
    with tempfile.TemporaryDirectory() as tmp:
        github_output = os.path.join(tmp, "github_output")
        open(github_output, "w").close()
        env = dict(
            os.environ,
            SUBJECT=subject,
            SKIP_CI_MARKER=skip_ci,
            SKIP_PUBLISH_MARKER=skip_publish,
            SKIP_PAGES_MARKER=skip_pages,
            GITHUB_OUTPUT=github_output,
        )
        result = subprocess.run(
            ["bash", "-e", "-c", step["run"]], env=env, capture_output=True, text=True
        )
        assert result.returncode == 0, result.stderr
        lines = open(github_output).read().splitlines()
    return dict(line.split("=", 1) for line in lines)


# --- wiring ----------------------------------------------------------------------


@WORKFLOWS
def test_the_step_takes_everything_through_env_and_is_wired_to_setup(workflow):
    step = _gates_step(workflow)
    assert step.get("id") == "gates"
    assert "${{" not in step["run"], "values must reach bash via env:, not spliced"
    assert set(step["env"]) == {
        "SUBJECT", "SKIP_CI_MARKER", "SKIP_PUBLISH_MARKER", "SKIP_PAGES_MARKER"
    }
    outputs = yaml.safe_load(workflow.read_text())["jobs"]["setup"]["outputs"]
    assert outputs["skip-publish"] == "${{ steps.gates.outputs.skip-publish }}"
    assert outputs["skip-pages"] == "${{ steps.gates.outputs.skip-pages }}"


def test_both_workflows_ship_the_same_step():
    assert _gates_step(UV_CI) == _gates_step(INLINE)


@WORKFLOWS
def test_publish_and_pages_gate_on_the_verdict_failing_closed(workflow):
    jobs = yaml.safe_load(workflow.read_text())["jobs"]
    assert "needs.setup.outputs.skip-publish == 'false'" in jobs["publish"]["if"]
    assert "needs.setup.outputs.skip-pages == 'false'" in jobs["github-pages"]["if"]
    # the old literal / per-job marker clauses are gone, so the jobs cannot disagree
    assert "'[skip ci]'" not in jobs["github-pages"]["if"]
    assert "skip-ci-marker" not in jobs["publish"]["if"]


# --- the step's verdicts -------------------------------------------------------------


@bash_required
@WORKFLOWS
@pytest.mark.parametrize(
    "subject, publish, pages",
    [
        ("Fix the parser (#12)", "false", "false"),
        ("Chore [skip ci]", "true", "true"),
        ("Docs only [skip publish] (#12)", "true", "false"),
        ("Bump [skip github-pages] (#12)", "false", "true"),
        ("Both [skip publish] [skip github-pages]", "true", "true"),
        ("Case-blind like contains() [Skip Publish]", "true", "false"),
        ("[skip publishing] is not the marker", "false", "false"),
        ("[skip pages] is not the marker", "false", "false"),
        ("", "false", "false"),
    ],
)
def test_verdicts(workflow, subject, publish, pages):
    assert run_gates(workflow, subject) == {"skip-publish": publish, "skip-pages": pages}


@bash_required
@WORKFLOWS
def test_an_empty_marker_output_falls_back_to_the_default_never_to_match_all(workflow):
    """The version-skew trap: an old wads on PyPI emits no new output, so it is ''."""
    plain = run_gates(workflow, "Fix (#3)", skip_ci="", skip_publish="", skip_pages="")
    assert plain == {"skip-publish": "false", "skip-pages": "false"}
    marked = run_gates(
        workflow, "Docs [skip publish]", skip_ci="", skip_publish="", skip_pages=""
    )
    assert marked == {"skip-publish": "true", "skip-pages": "false"}


@bash_required
@WORKFLOWS
def test_renamed_markers_are_honoured_and_globs_are_literal(workflow):
    custom = dict(skip_ci="[no ci]", skip_publish="[no*rel]", skip_pages="?docs?")
    assert run_gates(workflow, "x [no ci]", **custom) == {
        "skip-publish": "true", "skip-pages": "true"
    }
    assert run_gates(workflow, "x [no*rel]", **custom)["skip-publish"] == "true"
    assert run_gates(workflow, "x [no release]", **custom)["skip-publish"] == "false"
    assert run_gates(workflow, "x ?docs?", **custom)["skip-pages"] == "true"
    assert run_gates(workflow, "x adocsb", **custom)["skip-pages"] == "false"


@bash_required
@WORKFLOWS
def test_a_hostile_subject_is_data(workflow, tmp_path):
    canary = tmp_path / "pwned"
    subject = f'$(touch {canary}) `touch {canary}` "; touch {canary}; " [skip publish]'
    assert run_gates(workflow, subject)["skip-publish"] == "true"
    assert not canary.exists()


# --- end to end: the shipped extraction + gates feed the real job conditions ---------


def _verdicts(workflow, message, *, ref="refs/heads/main", publish_enabled="true"):
    from wads.tests.test_ci_trigger import evaluate

    subject = _run_extraction(workflow, message)
    context = {
        "github.event_name": "push",
        "github.event.head_commit.message": message,
        "github.ref": ref,
        "github.event.repository.default_branch": "main",
        "needs.setup.outputs.commit-subject": subject,
        "needs.setup.outputs.trigger-mode": "auto",
        "needs.setup.outputs.run-ci-marker": "[run ci]",
        "needs.setup.outputs.skip-ci-marker": "[skip ci]",
        "needs.setup.outputs.publish-enabled": publish_enabled,
        "needs.setup.outputs.publish-marker": "[publish]",
        "needs.setup.outputs.test-on-windows": "true",
        "needs.setup.outputs.tests-enabled": "true",
        "needs.setup.outputs.docs-enabled": "true",
        **{f"needs.setup.outputs.{k}": v for k, v in run_gates(workflow, subject).items()},
    }
    jobs = yaml.safe_load(workflow.read_text())["jobs"]
    return {
        name: evaluate(jobs[name]["if"], context)
        for name in ("validation", "publish", "github-pages")
    }


@bash_required
@WORKFLOWS
@pytest.mark.parametrize(
    "message, expected",
    [
        ("Fix the parser (#12)\n\nbody", (True, True, True)),
        ("Docs only [skip publish] (#12)\n\nbody", (True, False, True)),
        ("Docs build [skip github-pages] (#12)", (True, True, False)),
        ("Chore [skip ci]", (False, False, False)),
        # a marker quoted only in a squash-merged PR body does not count
        ("Explain markers (#62)\n\nUse [skip publish] to keep tests.", (True, True, True)),
    ],
)
def test_jobs_on_the_default_branch(workflow, message, expected):
    got = _verdicts(workflow, message)
    assert (got["validation"], got["publish"], got["github-pages"]) == expected


@bash_required
@WORKFLOWS
def test_skip_publish_wins_over_the_publish_marker(workflow):
    got = _verdicts(workflow, "Docs [publish] [skip publish]", publish_enabled="false")
    assert got["validation"] and not got["publish"]
    assert _verdicts(workflow, "Ship it [publish]", publish_enabled="false")["publish"]


# --- configuration -------------------------------------------------------------------


def test_config_defaults_and_overrides():
    default = CIConfig({"project": {"name": "x"}, "tool": {"wads": {"ci": {}}}})
    assert default.publish_skip_publish_marker == "[skip publish]"
    assert default.docs_skip_marker == "[skip github-pages]"
    custom = CIConfig(
        {
            "project": {"name": "x"},
            "tool": {
                "wads": {
                    "ci": {
                        "publish": {"skip_publish_marker": "[no release]"},
                        "docs": {"skip_marker": "[no docs]"},
                    }
                }
            },
        }
    )
    assert custom.publish_skip_publish_marker == "[no release]"
    assert custom.docs_skip_marker == "[no docs]"
