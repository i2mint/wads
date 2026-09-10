"""On-demand CI: render a repo's caller stub from ``[tool.wads.ci.trigger]``, and flip
a repo to on-demand in one idempotent command.

``[tool.wads.ci.trigger].mode`` decides whether CI runs at all:

- ``"auto"`` (the default): every push and pull request, as wads always has. The stub
  renders byte-identical to ``wads/data/github_ci_uv_stub.yml``.
- ``"on-demand"``: **nothing runs unless asked** -- the commit subject carries
  ``run_ci_marker`` (default ``"[run ci]"``), or someone starts a ``workflow_dispatch``.

Two gates, because workflow expressions cannot split a string:

1. The stub's job-level ``if:`` is a zero-cost pre-filter. An ordinary push schedules
   no runner at all, but the pre-filter can only ask whether the marker is *anywhere*
   in the commit message.
2. The reusable workflow's setup job extracts the subject line, and every other job
   gates on the marker being in *that* (the TRIGGER GATE note in
   ``.github/workflows/uv-ci.yml``). A marker quoted only in a squash-merged PR body
   passes gate 1, costs one setup job, and runs nothing else.

The flip (:func:`flip_to_on_demand`, CLI ``wads-migrate ci-on-demand``) sets the mode
plus a cheap test matrix and re-renders the stub. Everything is computed in a shadow
copy of the repo first, so a dry run and a real run take the same path.
"""

from __future__ import annotations

import difflib
import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Optional, Sequence

from wads.ci_config import (
    CIConfig,
    DFLT_RUN_CI_MARKER,
    DFLT_TRIGGER_MODE,
    tomllib,
)

DFLT_CI_WORKFLOW = ".github/workflows/ci.yml"
DFLT_ON_DEMAND_PYTHON_VERSIONS = ("3.12",)
DFLT_FLIP_COMMIT_MESSAGE = "ci: switch to on-demand CI ([tool.wads.ci.trigger])"

# The two lines of wads/data/github_ci_uv_stub.yml that the on-demand render rewrites.
# A test pins that the template still carries each exactly once.
AUTO_ON_LINE = "on: [push, pull_request]\n"
CI_JOB_ANCHOR = "  ci:\n    uses: "

# Events someone has to ask for. Every other event in a workflow's `on:` (push, PR,
# cron, workflow_run, ...) makes it run unasked, and the flip reports it.
ASKED_EVENTS = frozenset({"workflow_dispatch", "workflow_call", "repository_dispatch"})

# What a stub may hold that a re-render reproduces (anything else would be dropped).
_TEMPLATE_TRIGGERS = (
    ["push", "pull_request"],
    {"push": None, "workflow_dispatch": None},
)
_STUB_JOB_KEYS = ("uses", "permissions", "secrets", "if", "with")
_STUB_IF_PREFIX = (
    "github.event_name == 'workflow_dispatch' || "
    "contains(github.event.head_commit.message, '"
)
_USES_LINE = re.compile(
    r"^    uses: i2mint/wads/\.github/workflows/uv-ci\.yml@\S+\n", re.MULTILINE
)

_PIN_RE = re.compile(r"uv-ci\.yml(@\S+)")


# --------------------------------------------------------------------------------------
# Rendering


def stub_if_expression(run_ci_marker: str = DFLT_RUN_CI_MARKER) -> str:
    """The on-demand stub's job-level pre-filter, as a workflow expression.

    >>> stub_if_expression("[run ci]")
    "github.event_name == 'workflow_dispatch' || contains(github.event.head_commit.message, '[run ci]')"

    A quote in the marker is doubled, which is how workflow expressions escape it:

    >>> stub_if_expression("it's")
    "github.event_name == 'workflow_dispatch' || contains(github.event.head_commit.message, 'it''s')"
    """
    literal = run_ci_marker.replace("'", "''")
    return (
        "github.event_name == 'workflow_dispatch' || "
        f"contains(github.event.head_commit.message, '{literal}')"
    )


def _on_demand_header(run_ci_marker: str) -> str:
    return f"""\
# --- ON-DEMAND CI: NOTHING RUNS UNLESS ASKED ---------------------------------
# pyproject.toml sets [tool.wads.ci.trigger] mode = "on-demand". A push does
# NOT run tests, build, publish or docs. CI runs only when:
#   - the commit SUBJECT (its first line) contains {run_ci_marker}
#       git commit -m "Fix the parser {run_ci_marker}"
#   - or it is started by hand, which is always allowed:
#       gh workflow run ci.yml --ref <branch>    (or Actions tab > Run workflow)
# Publishing obeys the same gate, so a manual run on the DEFAULT branch releases
# (when publishing is enabled), exactly like a {run_ci_marker} push: to only test,
# run it on another branch, or run `wads ci-local`. The publish marker needs
# {run_ci_marker} in the same subject, and only the pushed HEAD commit's subject
# counts. To do locally what CI would have done:
#   wads ci-local              # lint, tests, build
#   wads ci-local --publish    # + version bump, PyPI upload, tag, push
#
# The job-level `if:` below is a zero-cost pre-filter: an ordinary push
# schedules no runner at all. Workflow expressions cannot split out the first
# line, so it matches the marker anywhere in the message, and the reusable
# workflow re-checks the extracted SUBJECT before any job runs. A marker quoted
# only in a squash-merged PR body therefore costs one short setup job, nothing
# else. This file is rendered from pyproject.toml: after changing
# [tool.wads.ci.trigger], re-render it with `wads-migrate ci-to-stub` (which
# keeps this stub's pin, secrets transport and `with:` inputs).
on:
  push:
  workflow_dispatch:
"""


def validate_trigger(mode: str, run_ci_marker: str) -> tuple[str, str]:
    """Validate a (mode, marker) pair with the same rules the CI setup job applies.

    >>> validate_trigger("on-demand", "[run ci]")
    ('on-demand', '[run ci]')
    >>> validate_trigger("sometimes", "[run ci]")
    Traceback (most recent call last):
      ...
    ValueError: [tool.wads.ci.trigger].mode must be one of ('auto', 'on-demand'), got 'sometimes'
    """
    trigger = {"mode": mode, "run_ci_marker": run_ci_marker}
    config = CIConfig({"tool": {"wads": {"ci": {"trigger": trigger}}}})
    return config.trigger_mode, config.run_ci_marker


def render_stub_trigger(
    stub: str,
    *,
    mode: str = DFLT_TRIGGER_MODE,
    run_ci_marker: str = DFLT_RUN_CI_MARKER,
) -> str:
    """Render the caller stub for a trigger mode.

    ``"auto"`` returns ``stub`` unchanged. ``"on-demand"`` replaces the push/PR trigger
    with push + ``workflow_dispatch``, puts the plain-language explanation above it, and
    adds the pre-filter ``if:`` to the ``ci`` job.
    """
    mode, run_ci_marker = validate_trigger(mode, run_ci_marker)
    if mode == "auto":
        return stub
    for anchor in (AUTO_ON_LINE, CI_JOB_ANCHOR):
        if stub.count(anchor) != 1:
            raise ValueError(
                f"stub template changed shape: expected exactly one {anchor!r}"
            )
    gated_job = (
        f"  ci:\n    if: {json.dumps(stub_if_expression(run_ci_marker))}\n    uses: "
    )
    return stub.replace(AUTO_ON_LINE, _on_demand_header(run_ci_marker)).replace(
        CI_JOB_ANCHOR, gated_job
    )


def repo_pyproject_for(ci_path) -> Optional[Path]:
    """The ``pyproject.toml`` of the repo holding workflow file ``ci_path``, if any.

    Walks up from the workflow, stopping at the first directory that holds a ``.git``
    so an enclosing project's pyproject is never mistaken for this repo's.
    """
    if not ci_path or not os.path.isfile(str(ci_path)):
        return None
    path = Path(ci_path)
    for parent in path.resolve().parents:
        candidate = parent / "pyproject.toml"
        if candidate.is_file():
            return candidate
        if (parent / ".git").exists():
            return None
    return None


def trigger_for_workflow(ci_path) -> tuple[str, str]:
    """The ``(mode, run_ci_marker)`` declared by the repo holding ``ci_path``.

    Defaults when there is no such file or no pyproject. An invalid trigger table
    raises: a stub must never silently render ``auto`` for a repo that asked for
    ``on-demand``.
    """
    pyproject = repo_pyproject_for(ci_path)
    if pyproject is None:
        return DFLT_TRIGGER_MODE, DFLT_RUN_CI_MARKER
    config = CIConfig.from_file(pyproject)
    return config.trigger_mode, config.run_ci_marker


# --------------------------------------------------------------------------------------
# The flip


def classify_ci_workflow(text: Optional[str]) -> str:
    """Classify a ``ci.yml``: ``'missing'``, ``'stub'``, ``'inline-uv'`` or ``'other'``.

    >>> classify_ci_workflow(None)
    'missing'
    >>> classify_ci_workflow("uses: i2mint/wads/.github/workflows/uv-ci.yml@master")
    'stub'
    >>> classify_ci_workflow("uses: i2mint/wads/actions/run-tests-uv@master")
    'inline-uv'
    >>> classify_ci_workflow("uses: actions/setup-python@v5")
    'other'
    """
    if text is None:
        return "missing"
    if "i2mint/wads/.github/workflows/uv-ci.yml" in text:
        return "stub"
    if (
        "Continuous Integration (uv)" in text
        or "i2mint/wads/actions/run-tests-uv" in text
    ):
        return "inline-uv"
    return "other"


@dataclass
class FlipResult:
    """What :func:`flip_to_on_demand` changed or, on a dry run, would change.

    ``status`` is ``"changed"``, ``"unchanged"`` (already on-demand) or ``"refused"``
    (nothing written; ``notes`` says why). ``changes`` maps a repo-relative path to its
    ``(old, new)`` text.
    """

    repo: Path
    status: str = "unchanged"
    changes: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)

    def diff(self) -> str:
        """Unified diff of every change."""
        return "".join(
            "".join(
                difflib.unified_diff(
                    old.splitlines(keepends=True),
                    new.splitlines(keepends=True),
                    fromfile=f"a/{path}",
                    tofile=f"b/{path}",
                )
            )
            for path, (old, new) in self.changes.items()
        )


def _import_tomlkit():
    try:
        import tomlkit
    except ImportError as exc:  # pragma: no cover - depends on the install
        raise ImportError(
            "flipping a repo to on-demand edits pyproject.toml without losing its "
            "comments, which needs `tomlkit`: `pip install tomlkit` or "
            "`pip install wads[create]`"
        ) from exc
    return tomlkit


def set_on_demand_in_pyproject(
    text: str,
    *,
    python_versions: Sequence[str] = DFLT_ON_DEMAND_PYTHON_VERSIONS,
    test_on_windows: bool = False,
    run_ci_marker: Optional[str] = None,
) -> str:
    """Return pyproject.toml ``text`` with the on-demand settings applied.

    Sets ``[tool.wads.ci.trigger].mode = "on-demand"`` (and ``run_ci_marker`` when
    given), ``[tool.wads.ci.testing].python_versions`` and ``test_on_windows``.
    Comments and layout survive (tomlkit), and a key already holding its target value
    is not touched, so applying this twice returns the first result unchanged.
    """
    if run_ci_marker is not None:
        validate_trigger("on-demand", run_ci_marker)
    tomlkit = _import_tomlkit()
    try:
        doc = tomlkit.parse(text)
        ci_path = ("tool", "wads", "ci")
        trigger = _table_at(tomlkit, doc, (*ci_path, "trigger"))
        _assign(trigger, "mode", "on-demand")
        if run_ci_marker is not None:
            _assign(trigger, "run_ci_marker", run_ci_marker)
        testing = _table_at(tomlkit, doc, (*ci_path, "testing"))
        _assign(testing, "python_versions", list(python_versions))
        _assign(testing, "test_on_windows", bool(test_on_windows))
        new_text = tomlkit.dumps(doc)
        config = CIConfig(tomllib.loads(new_text))
    except (
        Exception
    ) as exc:  # tomlkit cannot safely edit inline-table or dotted layouts
        raise ValueError(
            f"could not edit its [tool.wads.ci] layout ({type(exc).__name__}: {exc}); "
            "set the on-demand values by hand"
        ) from exc
    applied = (config.trigger_mode, config.python_versions, config.test_on_windows)
    wanted = ("on-demand", list(python_versions), bool(test_on_windows))
    if applied != wanted:
        raise ValueError(
            f"its [tool.wads.ci] layout took the edit as {applied}, not {wanted}; "
            "set the on-demand values by hand"
        )
    return new_text


def _table_at(tomlkit, container, keys):
    """The table at ``keys``, creating it (intermediates as header-less super tables)."""
    for depth, key in enumerate(keys):
        if key not in container:
            is_leaf = depth == len(keys) - 1
            container[key] = tomlkit.table(is_super_table=not is_leaf)
        container = container[key]
    return container


def _assign(table, key, value):
    current = table.get(key)
    if hasattr(current, "unwrap"):
        current = current.unwrap()
    if current != value:
        table[key] = value


def stub_shape(ci_text: Optional[str]) -> dict:
    """The ``pin`` and secrets ``transport`` of a stub, which a re-render must keep.

    Defaults (``@master``, ``json``) for anything that is not a stub.

    >>> stub_shape("uses: i2mint/wads/.github/workflows/uv-ci.yml@0.2.30")
    {'pin': '@0.2.30', 'transport': 'named'}
    >>> stub_shape(None)
    {'pin': '@master', 'transport': 'json'}
    """
    if classify_ci_workflow(ci_text) != "stub":
        return {"pin": "@master", "transport": "json"}
    from wads.ci_secrets import render_stub_json_transport

    match = _PIN_RE.search(ci_text)
    return {
        "pin": match.group(1) if match else "@master",
        "transport": "json" if render_stub_json_transport() in ci_text else "named",
    }


def stub_customizations(text: str) -> tuple[dict, list]:
    r"""Split what a stub holds beyond the template into ``(with_inputs, dropped)``.

    ``with_inputs`` (a flat ``with:`` mapping, e.g. ``project-name``) survives a
    re-render; ``dropped`` names everything else a re-render would silently lose.
    Raises ``yaml.YAMLError`` when the text does not parse.

    >>> stub_customizations(
    ...     "on: [push, pull_request]\njobs:\n  ci:\n    uses: x\n"
    ...     "    with:\n      project-name: my_pkg\n"
    ... )
    ({'project-name': 'my_pkg'}, [])
    >>> stub_customizations("on: [push]\njobs:\n  ci:\n    uses: x\n  lint:\n    runs-on: y\n")[1]
    ['`on: ["push"]`', 'job `lint`']
    """
    import yaml

    doc = yaml.safe_load(text) or {}
    dropped = [
        f"top-level `{key}`" for key in doc if key not in ("name", "on", True, "jobs")
    ]
    triggers = doc.get("on", doc.get(True))  # PyYAML reads a bare `on:` as True
    if triggers not in _TEMPLATE_TRIGGERS:
        dropped.append(f"`on: {json.dumps(triggers)}`")
    jobs = doc.get("jobs") or {}
    dropped += [f"job `{name}`" for name in jobs if name != "ci"]
    job = jobs.get("ci") or {}
    dropped += [f"`jobs.ci.{key}`" for key in job if key not in _STUB_JOB_KEYS]
    condition = job.get("if")
    if condition is not None and not str(condition).startswith(_STUB_IF_PREFIX):
        dropped.append("`jobs.ci.if`")
    inputs = job.get("with") or {}
    if not isinstance(inputs, dict) or any(
        isinstance(value, (dict, list)) for value in inputs.values()
    ):
        dropped.append("`jobs.ci.with` (not a flat mapping)")
        inputs = {}
    return dict(inputs), dropped


def stub_inputs_of(ci_path) -> dict:
    """The ``with:`` inputs an existing stub file passes; ``{}`` if none or not a stub."""
    import yaml

    if not ci_path or not os.path.isfile(str(ci_path)):
        return {}
    text = Path(ci_path).read_text()
    if classify_ci_workflow(text) != "stub":
        return {}
    try:
        return stub_customizations(text)[0]
    except yaml.YAMLError:
        return {}


def render_stub_inputs(stub: str, inputs: Mapping) -> str:
    """Add a ``with:`` block (the reusable workflow's inputs) under the stub's ``uses:``."""
    if not inputs:
        return stub
    import yaml

    block = yaml.safe_dump(
        {"with": dict(inputs)}, default_flow_style=False, sort_keys=False
    )
    indented = "".join(f"    {line}\n" for line in block.splitlines())
    match = _USES_LINE.search(stub)
    if match is None:
        raise ValueError("stub template changed shape: no `uses: ...uv-ci.yml@` line")
    return stub[: match.end()] + indented + stub[match.end() :]


def unasked_workflows(repo, *, workflow: str = DFLT_CI_WORKFLOW) -> list[str]:
    """Other workflow files in ``repo`` that run without anyone asking (push, PR, cron).

    The flip only governs ``workflow``; these keep running and are worth knowing about.
    """
    import yaml

    repo = Path(repo)
    governed = (repo / workflow).resolve()
    found = []
    for path in sorted((repo / ".github" / "workflows").glob("*.y*ml")):
        if path.resolve() == governed:
            continue
        try:
            doc = yaml.safe_load(path.read_text())
        except (yaml.YAMLError, OSError):
            continue
        if not isinstance(doc, dict):
            continue
        triggers = doc.get("on", doc.get(True))  # PyYAML reads a bare `on:` as True
        if isinstance(triggers, str):
            events = {triggers}
        elif isinstance(triggers, (list, dict)):
            events = set(triggers)
        else:
            events = set()
        hits = sorted(str(event) for event in events - ASKED_EVENTS)
        if hits:
            found.append(f"{path.relative_to(repo)} ({', '.join(hits)})")
    return found


def flip_to_on_demand(
    repo=".",
    *,
    python_versions: Sequence[str] = DFLT_ON_DEMAND_PYTHON_VERSIONS,
    test_on_windows: bool = False,
    run_ci_marker: Optional[str] = None,
    workflow: str = DFLT_CI_WORKFLOW,
    dry_run: bool = False,
) -> FlipResult:
    """Flip a repo to on-demand CI: pyproject settings plus a re-rendered stub.

    - a **stub** ``ci.yml`` is re-rendered keeping its pin, secrets transport and
      ``with:`` inputs, or **refused** if it holds anything else a re-render would drop
      (extra jobs, custom triggers);
    - an **inline uv** workflow becomes the stub, carrying its secret-backed env vars
      into ``[tool.wads.ci.env]`` first (as ``wads-migrate ci-to-stub`` does);
    - **no** ``ci.yml``: only pyproject changes (nothing runs on push anyway);
    - anything else (2025/legacy/custom workflow) is **refused** and nothing is
      written, because it would ignore the setting and keep running on every push.

    Idempotent: a second run reports ``"unchanged"`` and writes nothing.
    """
    from wads.migration import carry_ci_env_into_pyproject, migrate_ci_to_stub

    repo = Path(repo)
    pyproject = repo / "pyproject.toml"
    if not pyproject.is_file():
        raise FileNotFoundError(f"no pyproject.toml in {repo}: not a wads-managed repo")
    ci_path = repo / workflow
    old_py = pyproject.read_text()
    old_ci = ci_path.read_text() if ci_path.is_file() else None
    kind = classify_ci_workflow(old_ci)
    result = FlipResult(repo=repo)

    if kind == "other":
        result.status = "refused"
        result.notes.append(
            f"{workflow} is not a wads uv workflow (2025, legacy or custom), so it would "
            "ignore [tool.wads.ci.trigger] and keep running on every push. Move it to uv "
            f"first -- `wads-migrate ci-to-uv {workflow} -o {workflow}` -- then re-run "
            "`wads-migrate ci-on-demand`."
        )
        return result

    if kind == "stub":
        import yaml

        try:
            _, dropped = stub_customizations(old_ci)
        except yaml.YAMLError as exc:
            dropped = [f"YAML that does not parse ({type(exc).__name__})"]
        if dropped:
            marker = run_ci_marker or DFLT_RUN_CI_MARKER
            result.status = "refused"
            result.notes.append(
                f"{workflow} has customizations a re-render would drop: "
                f"{', '.join(dropped)}. Flip it by hand: in pyproject.toml set "
                '[tool.wads.ci.trigger] mode = "on-demand" (and the test matrix); in the '
                "workflow use `on: [push, workflow_dispatch]` and give the job that calls "
                f"uv-ci.yml `if: {json.dumps(stub_if_expression(marker))}`."
            )
            return result

    with tempfile.TemporaryDirectory(prefix="wads-flip-") as tmp:
        shadow = Path(tmp)
        (shadow / ".git").mkdir()  # bounds the pyproject lookup to the shadow repo
        shadow_py = shadow / "pyproject.toml"
        shadow_py.write_text(old_py)
        if kind == "inline-uv":
            carried = carry_ci_env_into_pyproject(old_ci, shadow_py)
            if carried:
                result.notes.append(
                    "carried env var(s) from the inline workflow into "
                    f"[tool.wads.ci.env].extra_envvars: {', '.join(carried)}"
                )
        try:
            on_demand_py = set_on_demand_in_pyproject(
                shadow_py.read_text(),
                python_versions=python_versions,
                test_on_windows=test_on_windows,
                run_ci_marker=run_ci_marker,
            )
        except ValueError as exc:
            result.status = "refused"
            result.changes = {}
            result.notes.append(f"pyproject.toml left unchanged: {exc}")
            return result
        shadow_py.write_text(on_demand_py)
        new_py = shadow_py.read_text()
        new_ci = old_ci
        if kind in ("stub", "inline-uv"):
            shadow_ci = shadow / workflow
            shadow_ci.parent.mkdir(parents=True, exist_ok=True)
            shadow_ci.write_text(old_ci)
            shape = stub_shape(old_ci)
            new_ci = migrate_ci_to_stub(str(shadow_ci), **shape)
            if shape["pin"] != "@master":
                result.notes.append(
                    f"the stub stays pinned to {shape['pin']}. Its pre-filter works on "
                    "any pin, but only a uv-ci.yml with the on-demand job gates "
                    "(i2mint/wads#85) keeps a marker quoted in a PR body from running "
                    "the whole CI."
                )

    if kind == "missing":
        result.notes.append(
            f"no {workflow}: nothing runs on push. pyproject now says on-demand, so a "
            "stub rendered later (`wads-migrate ci-to-stub`) will be on-demand too."
        )
    result.notes += [
        f"still runs unasked, not governed by this flip: {name}"
        for name in unasked_workflows(repo, workflow=workflow)
    ]

    if new_py != old_py:
        result.changes["pyproject.toml"] = (old_py, new_py)
    if new_ci is not None and new_ci != old_ci:
        result.changes[workflow] = (old_ci or "", new_ci)
    result.status = "changed" if result.changes else "unchanged"
    if result.changes and not dry_run:
        for relpath, (_, new) in result.changes.items():
            (repo / relpath).write_text(new)
    return result


# --------------------------------------------------------------------------------------
# Git helpers for the CLI's --commit


def _git(repo, *args) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True
    )


def uncommitted(repo, paths: Sequence[str]) -> list[str]:
    """Which of ``paths`` have uncommitted changes (``git status --porcelain`` lines)."""
    proc = _git(repo, "status", "--porcelain", "--", *paths)
    if proc.returncode != 0:
        raise RuntimeError(f"git status failed in {repo}: {proc.stderr.strip()}")
    return [line for line in proc.stdout.splitlines() if line.strip()]


def commit_paths(repo, paths: Sequence[str], *, message: str) -> str:
    """Commit exactly ``paths`` and return the new commit's short sha."""
    for args in (
        ("add", "--", *paths),
        ("commit", "--quiet", "-m", message, "--", *paths),
    ):
        proc = _git(repo, *args)
        if proc.returncode != 0:
            raise RuntimeError(f"git {args[0]} failed: {proc.stderr.strip()}")
    return _git(repo, "rev-parse", "--short", "HEAD").stdout.strip()


def run_ci_on_demand(
    repo=".",
    *,
    dry_run: bool = False,
    python_versions: Sequence[str] = DFLT_ON_DEMAND_PYTHON_VERSIONS,
    test_on_windows: bool = False,
    run_ci_marker: Optional[str] = None,
    workflow: str = DFLT_CI_WORKFLOW,
    commit: bool = False,
    out=None,
    err=None,
) -> int:
    """``wads-migrate ci-on-demand``: flip, report, optionally commit. Returns an exit code.

    ``0`` changed or already on-demand, ``2`` refused (nothing written).
    """
    import sys

    out = out or sys.stdout
    err = err or sys.stderr
    repo = Path(repo)
    governed = ["pyproject.toml", workflow]
    if commit and not dry_run:
        marker = run_ci_marker
        if marker is None and (repo / "pyproject.toml").is_file():
            marker = CIConfig.from_file(repo).run_ci_marker
        if marker and marker.lower() in DFLT_FLIP_COMMIT_MESSAGE.lower():
            print(
                f"Refusing --commit: the run-ci marker {marker!r} occurs in the flip's "
                f"commit message ({DFLT_FLIP_COMMIT_MESSAGE!r}), so pushing it would run "
                "CI. Flip without --commit and commit with your own message.",
                file=err,
            )
            return 2
        dirty = uncommitted(repo, governed)
        if dirty:
            print(
                "Refusing --commit: these files already have uncommitted changes, which "
                "the flip commit would sweep in:\n  " + "\n  ".join(dirty),
                file=err,
            )
            return 2
    result = flip_to_on_demand(
        repo,
        python_versions=python_versions,
        test_on_windows=test_on_windows,
        run_ci_marker=run_ci_marker,
        workflow=workflow,
        dry_run=dry_run,
    )
    verb = "would change" if dry_run else "changed"
    if result.status == "refused":
        print(f"✗ refused: {repo}", file=out)
    elif result.status == "unchanged":
        print(f"✓ already on-demand, nothing to do: {repo}", file=out)
    else:
        print(f"✓ {verb}: {', '.join(result.changes)}  ({repo})", file=out)
        if dry_run:
            print(result.diff(), file=out, end="")
    for note in result.notes:
        print(f"  note: {note}", file=err)
    if result.status == "refused":
        return 2
    if commit and not dry_run and result.changes:
        sha = commit_paths(repo, list(result.changes), message=DFLT_FLIP_COMMIT_MESSAGE)
        print(
            f"✓ committed {sha}: {DFLT_FLIP_COMMIT_MESSAGE}\n"
            "  push it: the pushed commit carries the on-demand stub, so the push "
            "itself runs nothing.",
            file=out,
        )
    return 0
