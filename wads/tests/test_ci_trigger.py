"""On-demand CI (`[tool.wads.ci.trigger]`, i2mint/wads#85).

Three things are pinned here:

1. **Rendering.** `auto` renders the stub byte-identical to the template (so every
   existing repo and `populate` are untouched); `on-demand` renders a stub that says,
   in words, that nothing runs unless asked.
2. **The gates' verdicts.** Not "the YAML mentions the right output" but "this job runs
   / does not run" for a given push, evaluated over the REAL `if:` strings shipped in
   `uv-ci.yml`, the inline template and a rendered stub, with subjects produced by the
   workflows' own extraction script. The expression evaluator below covers exactly the
   subset of the GitHub expression language those conditions use, and fails loudly on
   anything else (including a context name the conditions reference but the test did
   not provide, which is how a typo'd output name would show up).
3. **The flip.** One command, idempotent, dry-run safe, keeps a stub's pin and secrets
   transport, and refuses workflows that would ignore the setting.
"""

import re
import subprocess
from pathlib import Path

import pytest
import yaml

from wads import github_ci_uv_stub_path
from wads.ci_config import CIConfig
from wads.ci_trigger import (
    AUTO_ON_LINE,
    CI_JOB_ANCHOR,
    DFLT_FLIP_COMMIT_MESSAGE,
    classify_ci_workflow,
    flip_to_on_demand,
    render_stub_trigger,
    run_ci_on_demand,
    stub_if_expression,
)
from wads.migration import migrate_ci_to_stub
from wads.tests.test_workflow_gates import _run_extraction, bash_required

REPO_ROOT = Path(__file__).resolve().parents[2]
UV_CI = REPO_ROOT / ".github" / "workflows" / "uv-ci.yml"
INLINE = REPO_ROOT / "wads" / "data" / "github_ci_uv.yml"
READ_CI_CONFIG_ACTION = REPO_ROOT / "actions" / "read-ci-config" / "action.yml"
STUB_TEMPLATE = Path(github_ci_uv_stub_path).read_text()
MARKER = "[run ci]"
GATED_JOBS = ("validation", "windows-validation", "publish", "github-pages")


# --------------------------------------------------------------------------------------
# A small evaluator for the GitHub expression subset the job conditions use


_TOKEN = re.compile(
    r"\s*(?:(?P<string>'(?:[^']|'')*')|(?P<op>&&|\|\||==|!=|!|\(|\)|,)"
    r"|(?P<name>[A-Za-z_][\w.\-]*))"
)


def _tokenize(expr):
    expr = expr.strip()
    if expr.startswith("${{") and expr.endswith("}}"):
        expr = expr[3:-2]
    tokens, pos = [], 0
    while expr[pos:].strip():
        match = _TOKEN.match(expr, pos)
        if not match or match.end() == pos:
            raise ValueError(f"cannot tokenize {expr[pos:]!r}")
        tokens.append((match.lastgroup, match.group(match.lastgroup)))
        pos = match.end()
    return tokens


def _truthy(value):
    return bool(value)


def _as_text(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _format(fmt, *args):
    return re.sub(r"\{(\d+)\}", lambda m: _as_text(args[int(m.group(1))]), fmt)


_FUNCTIONS = {
    # GitHub's contains() on strings is a case-insensitive substring test.
    "contains": lambda haystack, needle: _as_text(needle).lower()
    in _as_text(haystack).lower(),
    "format": _format,
}


class _Evaluator:
    def __init__(self, tokens, context):
        self.tokens, self.pos, self.context = tokens, 0, context

    def _peek(self):
        return self.tokens[self.pos][1] if self.pos < len(self.tokens) else None

    def _take(self, expected=None):
        kind, value = self.tokens[self.pos]
        if expected is not None and value != expected:
            raise ValueError(f"expected {expected!r}, got {value!r}")
        self.pos += 1
        return kind, value

    def parse(self):
        value = self._or()
        if self.pos != len(self.tokens):
            raise ValueError(f"trailing tokens: {self.tokens[self.pos:]}")
        return value

    def _or(self):
        value = self._and()
        while self._peek() == "||":
            self._take()
            right = self._and()
            value = value if _truthy(value) else right
        return value

    def _and(self):
        value = self._compare()
        while self._peek() == "&&":
            self._take()
            right = self._compare()
            value = right if _truthy(value) else value
        return value

    def _compare(self):
        left = self._unary()
        if self._peek() in ("==", "!="):
            op = self._take()[1]
            equal = _as_text(left).lower() == _as_text(self._unary()).lower()
            return equal if op == "==" else not equal
        return left

    def _unary(self):
        if self._peek() == "!":
            self._take()
            return not _truthy(self._unary())
        return self._primary()

    def _primary(self):
        kind, value = self._take()
        if value == "(":
            inner = self._or()
            self._take(")")
            return inner
        if kind == "string":
            return value[1:-1].replace("''", "'")
        if kind == "name" and self._peek() == "(":
            self._take("(")
            args = []
            if self._peek() != ")":
                args.append(self._or())
                while self._peek() == ",":
                    self._take()
                    args.append(self._or())
            self._take(")")
            return _FUNCTIONS[value.lower()](*args)
        if kind == "name":
            if value in ("true", "false"):
                return value == "true"
            if value not in self.context:
                raise KeyError(f"condition references {value!r}, absent from the context")
            return self.context[value]
        raise ValueError(f"unexpected token {value!r}")


def evaluate(expr, context):
    return _truthy(_Evaluator(_tokenize(expr), context).parse())


def test_the_evaluator_itself():
    assert evaluate("contains('Fix [RUN CI]', '[run ci]')", {})
    assert evaluate("!('a' == 'b') && ('x' != 'y' || false)", {})
    assert evaluate("format('refs/heads/{0}', 'main') == 'refs/heads/main'", {})
    assert not evaluate("contains('it''s', 'its')", {})
    with pytest.raises(KeyError):
        evaluate("needs.setup.outputs.nope == 'x'", {})


# --------------------------------------------------------------------------------------
# Scenarios


def _context(
    message,
    *,
    event="push",
    mode="on-demand",
    marker=MARKER,
    ref="refs/heads/master",
    default_branch="master",
):
    head_commit = message if event == "push" else ""
    return {
        "github.event_name": event,
        "github.event.head_commit.message": head_commit,
        "github.ref": ref,
        "github.event.repository.default_branch": default_branch,
        "needs.setup.outputs.commit-subject": _run_extraction(UV_CI, head_commit),
        "needs.setup.outputs.trigger-mode": mode,
        "needs.setup.outputs.run-ci-marker": marker,
        "needs.setup.outputs.skip-ci-marker": "[skip ci]",
        "needs.setup.outputs.publish-enabled": "true",
        "needs.setup.outputs.publish-marker": "[publish]",
        "needs.setup.outputs.test-on-windows": "true",
        "needs.setup.outputs.tests-enabled": "true",
        "needs.setup.outputs.docs-enabled": "true",
    }


def _job_verdicts(workflow, context):
    jobs = yaml.safe_load(workflow.read_text())["jobs"]
    return {name: evaluate(jobs[name]["if"], context) for name in GATED_JOBS}


def _on_demand_stub(marker=MARKER):
    return yaml.safe_load(
        render_stub_trigger(STUB_TEMPLATE, mode="on-demand", run_ci_marker=marker)
    )


def _stub_runs(context, *, marker=MARKER):
    """Does the on-demand stub schedule its ci job at all (the zero-cost pre-filter)?"""
    stub = _on_demand_stub(marker)
    triggers = stub[True]  # PyYAML reads the bare `on:` key as True
    return context["github.event_name"] in triggers and evaluate(
        stub["jobs"]["ci"]["if"], context
    )


WORKFLOWS = pytest.mark.parametrize("workflow", (UV_CI, INLINE), ids=lambda p: p.name)


@bash_required
@WORKFLOWS
def test_on_demand_plain_push_runs_nothing(workflow):
    context = _context("Fix the parser (#12)\n\nbody\n")
    assert not _stub_runs(context), "an ordinary push must not schedule a runner"
    assert not any(_job_verdicts(workflow, context).values())


@bash_required
@WORKFLOWS
def test_on_demand_marker_in_subject_runs_everything(workflow):
    context = _context(f"Fix the parser {MARKER} (#12)\n\nbody\n")
    assert _stub_runs(context)
    assert all(_job_verdicts(workflow, context).values())


@bash_required
@WORKFLOWS
def test_on_demand_marker_only_in_a_squashed_pr_body_runs_nothing(workflow):
    """THE trap: a squash commit whose body merely mentions the marker.

    The stub's pre-filter cannot see lines, so it lets the run start (one setup job);
    the subject gate behind it must then refuse every real job.
    """
    context = _context(
        "Document on-demand CI (#85)\n"
        "\n"
        f"Commits whose subject carries {MARKER} run the CI.\n"
    )
    assert _stub_runs(context), "documents the accepted cost: the setup job starts"
    assert _job_verdicts(workflow, context) == dict.fromkeys(GATED_JOBS, False)


@bash_required
@WORKFLOWS
def test_workflow_dispatch_is_always_allowed(workflow):
    context = _context("", event="workflow_dispatch")
    assert _stub_runs(context)
    assert all(_job_verdicts(workflow, context).values())


@bash_required
@WORKFLOWS
def test_publish_still_requires_the_default_branch(workflow):
    context = _context(f"Try it {MARKER}", ref="refs/heads/feature")
    verdicts = _job_verdicts(workflow, context)
    assert verdicts["validation"] and not verdicts["publish"]
    assert not verdicts["github-pages"]


@bash_required
@WORKFLOWS
def test_skip_ci_still_wins_over_the_run_marker(workflow):
    context = _context(f"Chore {MARKER} [skip ci]")
    assert not _job_verdicts(workflow, context)["validation"]


@bash_required
@WORKFLOWS
def test_auto_mode_behaves_as_before(workflow):
    context = _context("Fix the parser (#12)", mode="auto")
    assert all(_job_verdicts(workflow, context).values())


@bash_required
@WORKFLOWS
def test_a_wads_too_old_to_emit_the_output_fails_open_to_auto(workflow):
    context = _context("Fix the parser (#12)", mode="")
    assert all(_job_verdicts(workflow, context).values())


@bash_required
def test_the_run_marker_matches_case_insensitively_like_github():
    context = _context("Fix the parser [RUN CI]")
    assert _stub_runs(context)
    assert _job_verdicts(UV_CI, context)["validation"]


@WORKFLOWS
def test_setup_job_exports_the_trigger_outputs(workflow):
    outputs = yaml.safe_load(workflow.read_text())["jobs"]["setup"]["outputs"]
    assert outputs["trigger-mode"] == "${{ steps.config.outputs.trigger-mode }}"
    assert outputs["run-ci-marker"] == "${{ steps.config.outputs.run-ci-marker }}"
    action_outputs = yaml.safe_load(READ_CI_CONFIG_ACTION.read_text())["outputs"]
    assert {"trigger-mode", "run-ci-marker"} <= set(action_outputs)


def test_read_ci_config_writes_the_trigger_outputs(tmp_path, monkeypatch):
    from wads.scripts.read_ci_config import read_and_export_ci_config

    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\n\n[tool.wads.ci.trigger]\nmode = "on-demand"\n'
    )
    output = tmp_path / "out"
    output.touch()
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    assert read_and_export_ci_config(tmp_path) == 0
    lines = output.read_text().splitlines()
    assert "trigger-mode=on-demand" in lines
    assert f"run-ci-marker={MARKER}" in lines


# --------------------------------------------------------------------------------------
# Rendering


def test_the_stub_template_carries_each_anchor_once():
    assert STUB_TEMPLATE.count(AUTO_ON_LINE) == 1
    assert STUB_TEMPLATE.count(CI_JOB_ANCHOR) == 1


def test_auto_renders_the_template_byte_for_byte():
    assert render_stub_trigger(STUB_TEMPLATE) == STUB_TEMPLATE
    assert migrate_ci_to_stub() == STUB_TEMPLATE


def test_on_demand_stub_says_nothing_runs_unless_asked():
    text = render_stub_trigger(STUB_TEMPLATE, mode="on-demand")
    assert "NOTHING RUNS UNLESS ASKED" in text
    assert "wads ci-local" in text and "gh workflow run ci.yml" in text
    stub = yaml.safe_load(text)
    assert set(stub[True]) == {"push", "workflow_dispatch"}, "no pull_request trigger"
    assert stub["jobs"]["ci"]["if"] == stub_if_expression(MARKER)
    assert stub["jobs"]["ci"]["uses"] == "i2mint/wads/.github/workflows/uv-ci.yml@master"
    assert "WADS_CI_SECRETS_JSON" in stub["jobs"]["ci"]["secrets"]


@bash_required
def test_a_marker_with_a_quote_is_escaped_and_still_matches():
    marker = "it's time"
    stub = _on_demand_stub(marker)
    assert "'it''s time'" in stub["jobs"]["ci"]["if"]
    assert _stub_runs(_context(f"Go, {marker}", marker=marker), marker=marker)
    assert not _stub_runs(_context("Go, its time", marker=marker), marker=marker)


@pytest.mark.parametrize(
    "trigger, message",
    [
        ({"mode": "sometimes"}, "mode must be one of"),
        ({"run_ci_marker": ""}, "non-empty"),
        ({"run_ci_marker": "a\nb"}, "single-line"),
    ],
)
def test_invalid_trigger_config_fails_loudly(trigger, message):
    config = CIConfig({"tool": {"wads": {"ci": {"trigger": trigger}}}})
    with pytest.raises(ValueError, match=message):
        (config.trigger_mode, config.run_ci_marker)


def _write_repo(root, *, pyproject, ci=None):
    (root / ".git").mkdir(exist_ok=True)
    (root / "pyproject.toml").write_text(pyproject)
    if ci is not None:
        path = root / ".github" / "workflows" / "ci.yml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(ci)
    return root / ".github" / "workflows" / "ci.yml"


ON_DEMAND_PYPROJECT = '[project]\nname = "x"\n\n[tool.wads.ci.trigger]\nmode = "on-demand"\n'


def test_rerendering_an_on_demand_repo_keeps_it_on_demand(tmp_path):
    """A `ci-to-stub` / `fleet-stub` refresh must never silently revert to auto."""
    ci = _write_repo(tmp_path, pyproject=ON_DEMAND_PYPROJECT, ci=STUB_TEMPLATE)
    assert migrate_ci_to_stub(str(ci)) == render_stub_trigger(
        STUB_TEMPLATE, mode="on-demand"
    )


def test_on_demand_composes_with_pin_and_named_transport(tmp_path, capsys):
    ci = _write_repo(tmp_path, pyproject=ON_DEMAND_PYPROJECT, ci=STUB_TEMPLATE)
    stub = yaml.safe_load(migrate_ci_to_stub(str(ci), pin="@0.2.30", transport="named"))
    job = stub["jobs"]["ci"]
    assert job["uses"].endswith("uv-ci.yml@0.2.30")
    assert job["secrets"] == {"PYPI_PASSWORD": "${{ secrets.PYPI_PASSWORD }}"}
    assert job["if"] == stub_if_expression(MARKER)


# --------------------------------------------------------------------------------------
# The flip

COMMENTED_PYPROJECT = """\
[project]
name = "demo"
version = "0.1.0"

# CI knobs, kept on purpose
[tool.wads.ci.testing]
python_versions = ["3.10", "3.12"]  # the matrix
pytest_args = ["-x"]
"""


def _stub_repo(root, **pyproject):
    return _write_repo(
        root, pyproject=pyproject.get("text", COMMENTED_PYPROJECT), ci=STUB_TEMPLATE
    )


def test_flip_sets_the_trigger_and_the_cheap_matrix_and_keeps_comments(tmp_path):
    ci = _stub_repo(tmp_path)
    result = flip_to_on_demand(tmp_path)
    assert result.status == "changed"
    assert set(result.changes) == {"pyproject.toml", ".github/workflows/ci.yml"}
    text = (tmp_path / "pyproject.toml").read_text()
    assert "# CI knobs, kept on purpose" in text and 'pytest_args = ["-x"]' in text
    config = CIConfig.from_file(tmp_path)
    assert config.trigger_mode == "on-demand"
    assert config.python_versions == ["3.12"]
    assert config.test_on_windows is False
    assert ci.read_text() == render_stub_trigger(STUB_TEMPLATE, mode="on-demand")


def test_flip_is_idempotent(tmp_path):
    _stub_repo(tmp_path)
    flip_to_on_demand(tmp_path)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    again = flip_to_on_demand(tmp_path)
    assert again.status == "unchanged" and again.changes == {}
    assert {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before


def test_flip_dry_run_writes_nothing_but_shows_the_diff(tmp_path):
    ci = _stub_repo(tmp_path)
    before = ((tmp_path / "pyproject.toml").read_text(), ci.read_text())
    result = flip_to_on_demand(tmp_path, dry_run=True)
    assert result.status == "changed"
    assert ((tmp_path / "pyproject.toml").read_text(), ci.read_text()) == before
    diff = result.diff()
    assert '+mode = "on-demand"' in diff and "+  workflow_dispatch:" in diff


def test_flip_keeps_a_stub_pin_and_named_transport(tmp_path, capsys):
    named = migrate_ci_to_stub(pin="@0.2.30", transport="named")
    _write_repo(tmp_path, pyproject=COMMENTED_PYPROJECT, ci=named)
    result = flip_to_on_demand(tmp_path)
    job = yaml.safe_load((tmp_path / ".github/workflows/ci.yml").read_text())["jobs"]["ci"]
    assert job["uses"].endswith("@0.2.30")
    assert "WADS_CI_SECRETS_JSON" not in job["secrets"]
    assert job["if"] == stub_if_expression(MARKER)
    assert any("pinned to @0.2.30" in note for note in result.notes)


def test_flip_turns_an_inline_uv_workflow_into_the_stub_and_carries_its_env(tmp_path):
    inline = (
        "name: Continuous Integration (uv)\n"
        "on: [push, pull_request]\n"
        "env:\n"
        "  OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}\n"
        "jobs:\n"
        "  validation:\n"
        "    steps:\n"
        "      - uses: i2mint/wads/actions/run-tests-uv@master\n"
    )
    ci = _write_repo(tmp_path, pyproject=COMMENTED_PYPROJECT, ci=inline)
    result = flip_to_on_demand(tmp_path)
    assert classify_ci_workflow(ci.read_text()) == "stub"
    assert CIConfig.from_file(tmp_path).env_vars_extra == ["OPENAI_API_KEY"]
    assert any("OPENAI_API_KEY" in note for note in result.notes)


def test_flip_refuses_a_workflow_that_would_ignore_the_setting(tmp_path):
    legacy = "name: CI\non: [push]\njobs:\n  t:\n    steps:\n      - uses: actions/setup-python@v5\n"
    ci = _write_repo(tmp_path, pyproject=COMMENTED_PYPROJECT, ci=legacy)
    result = flip_to_on_demand(tmp_path)
    assert result.status == "refused" and result.changes == {}
    assert ci.read_text() == legacy
    assert (tmp_path / "pyproject.toml").read_text() == COMMENTED_PYPROJECT
    assert "ci-to-uv" in result.notes[0]


def test_flip_without_a_workflow_changes_pyproject_only(tmp_path):
    _write_repo(tmp_path, pyproject=COMMENTED_PYPROJECT)
    result = flip_to_on_demand(tmp_path)
    assert set(result.changes) == {"pyproject.toml"}
    assert not (tmp_path / ".github").exists()


def test_flip_names_other_workflows_that_still_run_unasked(tmp_path):
    _stub_repo(tmp_path)
    workflows = tmp_path / ".github" / "workflows"
    (workflows / "nightly.yml").write_text("on:\n  schedule:\n    - cron: '0 0 * * *'\njobs: {}\n")
    (workflows / "manual.yml").write_text("on: workflow_dispatch\njobs: {}\n")
    notes = flip_to_on_demand(tmp_path, dry_run=True).notes
    assert any("nightly.yml (schedule)" in note for note in notes)
    assert not any("manual.yml" in note for note in notes)


def _git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.fixture
def git_stub_repo(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "test")
    _stub_repo(tmp_path)
    (tmp_path / ".git" / "info").mkdir(parents=True, exist_ok=True)
    _git(tmp_path, "add", "pyproject.toml", ".github")
    _git(tmp_path, "commit", "-q", "-m", "init")
    return tmp_path


def test_cli_commit_commits_exactly_the_flip(git_stub_repo, capsys):
    assert run_ci_on_demand(git_stub_repo, commit=True) == 0
    assert _git(git_stub_repo, "log", "-1", "--format=%s") == DFLT_FLIP_COMMIT_MESSAGE
    assert MARKER not in DFLT_FLIP_COMMIT_MESSAGE, "the flip commit must not run CI"
    assert _git(git_stub_repo, "status", "--porcelain") == ""
    assert run_ci_on_demand(git_stub_repo, commit=True) == 0
    assert "already on-demand" in capsys.readouterr().out


def test_cli_commit_refuses_to_sweep_in_existing_edits(git_stub_repo, capsys):
    pyproject = git_stub_repo / "pyproject.toml"
    pyproject.write_text(pyproject.read_text() + "\n# local edit\n")
    assert run_ci_on_demand(git_stub_repo, commit=True) == 2
    assert "already have uncommitted changes" in capsys.readouterr().err
    assert _git(git_stub_repo, "log", "-1", "--format=%s") == "init"


def test_wads_migrate_ci_on_demand_command_line(tmp_path, monkeypatch, capsys):
    from wads.migration import main

    _stub_repo(tmp_path)
    monkeypatch.setattr(
        "sys.argv", ["wads-migrate", "ci-on-demand", str(tmp_path), "--dry-run"]
    )
    with pytest.raises(SystemExit) as exit_info:
        main()
    assert exit_info.value.code == 0
    out = capsys.readouterr().out
    assert "would change" in out and '+mode = "on-demand"' in out
    assert CIConfig.from_file(tmp_path).trigger_mode == "auto", "dry run wrote nothing"


# --- review follow-ups ---------------------------------------------------------------


def test_flip_keeps_the_inputs_a_stub_passes(tmp_path):
    from wads.ci_trigger import render_stub_inputs

    ci = _write_repo(
        tmp_path,
        pyproject=COMMENTED_PYPROJECT,
        ci=render_stub_inputs(STUB_TEMPLATE, {"project-name": "my_pkg"}),
    )
    assert flip_to_on_demand(tmp_path).status == "changed"
    job = yaml.safe_load(ci.read_text())["jobs"]["ci"]
    assert job["with"] == {"project-name": "my_pkg"}
    assert job["if"] == stub_if_expression(MARKER)
    assert flip_to_on_demand(tmp_path).status == "unchanged"


def test_flip_refuses_a_stub_a_rerender_would_strip(tmp_path):
    customized = (
        STUB_TEMPLATE
        + "  lint:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo hi\n"
    )
    ci = _write_repo(tmp_path, pyproject=COMMENTED_PYPROJECT, ci=customized)
    result = flip_to_on_demand(tmp_path)
    assert result.status == "refused" and result.changes == {}
    assert ci.read_text() == customized
    assert (tmp_path / "pyproject.toml").read_text() == COMMENTED_PYPROJECT
    assert "job `lint`" in result.notes[0] and "by hand" in result.notes[0]


def test_ci_to_stub_keeps_the_existing_pin_transport_and_inputs(
    tmp_path, monkeypatch, capsys
):
    from wads.ci_trigger import render_stub_inputs
    from wads.migration import main

    named = render_stub_inputs(
        migrate_ci_to_stub(pin="@0.2.30", transport="named"),
        {"project-name": "my_pkg"},
    )
    ci = _write_repo(tmp_path, pyproject=ON_DEMAND_PYPROJECT, ci=named)
    monkeypatch.setattr("sys.argv", ["wads-migrate", "ci-to-stub", str(ci)])
    main()
    job = yaml.safe_load(ci.read_text())["jobs"]["ci"]
    assert job["uses"].endswith("@0.2.30")
    assert "WADS_CI_SECRETS_JSON" not in job["secrets"]
    assert job["with"] == {"project-name": "my_pkg"}
    assert job["if"] == stub_if_expression(MARKER)


@pytest.mark.parametrize(
    "layout",
    [
        '[project]\nname = "x"\n\n[tool.wads]\nci = {testing = {python_versions = ["3.10"]}}\n',
        '[project]\nname = "x"\n\n[tool]\nwads.ci.testing.python_versions = ["3.10"]\n',
    ],
    ids=["inline-table", "dotted-keys"],
)
def test_flip_refuses_a_pyproject_layout_it_cannot_edit(tmp_path, layout):
    _write_repo(tmp_path, pyproject=layout, ci=STUB_TEMPLATE)
    result = flip_to_on_demand(tmp_path)
    assert result.status == "refused" and result.changes == {}
    assert (tmp_path / "pyproject.toml").read_text() == layout
    assert "by hand" in result.notes[-1]


def test_cli_commit_refuses_a_marker_its_own_commit_message_carries(
    git_stub_repo, capsys
):
    assert run_ci_on_demand(git_stub_repo, commit=True, run_ci_marker="on-demand") == 2
    assert "would run CI" in capsys.readouterr().err
    assert _git(git_stub_repo, "log", "-1", "--format=%s") == "init"
    assert CIConfig.from_file(git_stub_repo).trigger_mode == "auto"


def test_every_event_nobody_asks_for_is_reported(tmp_path):
    _stub_repo(tmp_path)
    workflows = tmp_path / ".github" / "workflows"
    (workflows / "after.yml").write_text(
        "on:\n  workflow_run:\n    workflows: [CI]\njobs: {}\n"
    )
    (workflows / "manual.yml").write_text(
        "on: [workflow_dispatch, repository_dispatch]\njobs: {}\n"
    )
    notes = flip_to_on_demand(tmp_path, dry_run=True).notes
    assert any("after.yml (workflow_run)" in note for note in notes)
    assert not any("manual.yml" in note for note in notes)


def test_the_on_demand_header_warns_that_a_manual_default_branch_run_releases():
    text = render_stub_trigger(STUB_TEMPLATE, mode="on-demand")
    assert "a manual run on the DEFAULT branch releases" in text
    assert "only the pushed HEAD commit's subject" in text
