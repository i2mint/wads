"""Pin the on-demand TRIGGER GATE in the npm reusable workflows.

Mirrors the Python side's uv-ci.yml gate (see wads/ci_trigger.py): the
`validate` job (and `publish`, ANDed with its own opt-in gate) must only run
when `trigger_mode != 'on-demand'`, OR it's a manual `workflow_dispatch`, OR
the extracted commit subject carries `run_ci_marker`. A silent regression here
(e.g. someone drops the clause while touching the publish `if:`) would make an
on-demand npm repo run CI on every push again.
"""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
NPM_CI = REPO_ROOT / ".github" / "workflows" / "npm-ci.yml"
NPM_CI_MONOREPO = REPO_ROOT / ".github" / "workflows" / "npm-ci-monorepo.yml"

GATE_CLAUSE = "needs.setup.outputs.trigger_mode != 'on-demand'"
DISPATCH_CLAUSE = "github.event_name == 'workflow_dispatch'"
SUBJECT_CLAUSE = (
    "contains(needs.setup.outputs.commit_subject, needs.setup.outputs.run_ci_marker)"
)


def _load(path):
    with open(path) as f:
        # `on:` parses as the boolean key True under default PyYAML; doesn't
        # matter here since we only inspect `jobs`.
        return yaml.safe_load(f)


def _assert_gated(doc, workflow_name):
    setup_outputs = doc["jobs"]["setup"]["outputs"]
    assert "trigger_mode" in setup_outputs, workflow_name
    assert "run_ci_marker" in setup_outputs, workflow_name

    validate_if = doc["jobs"]["validate"]["if"]
    assert GATE_CLAUSE in validate_if, workflow_name
    assert DISPATCH_CLAUSE in validate_if, workflow_name
    assert SUBJECT_CLAUSE in validate_if, workflow_name

    publish_if = doc["jobs"]["publish"]["if"]
    assert GATE_CLAUSE in publish_if, workflow_name
    assert SUBJECT_CLAUSE in publish_if, workflow_name


def test_npm_ci_validate_and_publish_are_gated():
    _assert_gated(_load(NPM_CI), "npm-ci.yml")


def test_npm_ci_monorepo_validate_and_publish_are_gated():
    _assert_gated(_load(NPM_CI_MONOREPO), "npm-ci-monorepo.yml")


def test_npm_ci_setup_step_validates_trigger_mode_in_js():
    text = NPM_CI.read_text()
    assert "wads.ci.trigger.mode must be" in text
    assert "wads.ci.trigger.runCiMarker must be" in text


def test_npm_ci_monorepo_setup_step_validates_trigger_mode_in_js():
    text = NPM_CI_MONOREPO.read_text()
    assert "wads.ci.trigger.mode must be" in text
    assert "wads.ci.trigger.runCiMarker must be" in text
