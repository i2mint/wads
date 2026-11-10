"""A Python package and its npm twin: each CI runs on its own inputs (i2mint/wads#209).

The Python CI stub carries a ``paths:`` filter that leaves out each npm component
(its directory and its own workflow file), so a change only there runs the npm CI
alone and never cuts a PyPI release. The npm stub watches the inputs it shares with
the Python side (``fixtures/``, a Rust core). The filter is derived from the repo on
every render, so ``wads-migrate ci-to-stub`` and the on-demand flip keep it.

The "which workflow runs for this commit" tests evaluate GitHub's path-filter rules
(ordered patterns, ``!`` excludes, the last match wins) over the rendered files.
"""

import re
import subprocess

import pytest
import yaml

from wads.ci_config import CIConfig
from wads.ci_trigger import (
    flip_to_on_demand,
    python_ci_paths,
    render_stub_paths,
    render_stub_trigger,
    stub_customizations,
)
from wads.migration import migrate_ci_to_stub
from wads.populate import populate_pkg_dir
from wads.profiles import apply_frontend


def _matches(pattern: str, path: str) -> bool:
    """GitHub's glob: ``**`` crosses directories, ``*`` does not."""
    regex, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**", i):
            regex += ".*"
            i += 2
        elif pattern[i] == "*":
            regex += "[^/]*"
            i += 1
        else:
            regex += re.escape(pattern[i])
            i += 1
    return re.fullmatch(regex, path) is not None


def runs_on(paths: list, changed: list) -> bool:
    """Whether a push touching ``changed`` triggers a workflow filtered by ``paths``.

    GitHub: a file is included by the last pattern that matches it (``!`` excludes);
    the workflow runs when at least one changed file is included.
    """

    def included(path):
        verdict = False
        for pattern in paths:
            negated = pattern.startswith("!")
            if _matches(pattern.lstrip("!"), path):
                verdict = not negated
        return verdict

    return any(included(p) for p in changed)


def _triggers(text: str) -> dict:
    doc = yaml.safe_load(text)
    return doc.get("on", doc.get(True))


def _git_init(path, url):
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(
        ["git", "-C", str(path), "remote", "add", "origin", url], check=True
    )


@pytest.fixture
def polyglot(tmp_path):
    """A populated Python repo with a ``ts`` npm twin, as ``populate --frontend ts``."""
    pkg = tmp_path / "widget"
    pkg.mkdir()
    _git_init(pkg, "https://github.com/myorg/widget")
    populate_pkg_dir(
        str(pkg),
        description="Python package with a TypeScript twin",
        root_url="https://github.com/myorg",
        version="0.1.0",
        verbose=False,
        frontend="ts",
    )
    return pkg


# --- the scenario of the issue's "done when" -----------------------------------


@pytest.mark.parametrize(
    "changed, python_runs, npm_runs",
    [
        (["ts/src/index.ts"], False, True),  # TS only: no PyPI release
        (["fixtures/cases.json"], True, True),  # shared golden cases: both
        (["widget/__init__.py"], True, False),  # Python only
        ([".github/workflows/npm-ci-ts.yml"], False, True),
        ([".github/workflows/ci.yml"], True, False),
        (["README.md"], True, False),
    ],
)
def test_populate_frontend_ts_routes_each_change_to_its_ci(
    polyglot, changed, python_runs, npm_runs
):
    ci = _triggers((polyglot / ".github/workflows/ci.yml").read_text())
    npm = _triggers((polyglot / ".github/workflows/npm-ci-ts.yml").read_text())
    assert ci["push"]["paths"] == ci["pull_request"]["paths"]
    assert runs_on(ci["push"]["paths"], changed) is python_runs
    assert runs_on(npm["push"]["paths"], changed) is npm_runs
    # a PR that changes only the npm stub must still run some CI
    assert runs_on(npm["pull_request"]["paths"], changed) is npm_runs


def test_a_pure_python_repo_keeps_the_unfiltered_stub(tmp_path):
    pkg = tmp_path / "plain"
    pkg.mkdir()
    _git_init(pkg, "https://github.com/myorg/plain")
    populate_pkg_dir(
        str(pkg),
        description="no npm",
        root_url="https://github.com/myorg",
        version="0.1.0",
        verbose=False,
    )
    assert "on: [push, pull_request]\n" in (pkg / ".github/workflows/ci.yml").read_text()


def test_npm_stub_watches_the_rust_core_when_there_is_one(tmp_path):
    (tmp_path / "rust").mkdir()
    apply_frontend(str(tmp_path), profile="ts", project_name="widget")
    npm = _triggers((tmp_path / ".github/workflows/npm-ci-ts.yml").read_text())
    assert runs_on(npm["push"]["paths"], ["rust/core/src/lib.rs"])


def test_npm_stub_watch_paths_are_a_keyword(tmp_path):
    apply_frontend(
        str(tmp_path), profile="ts", project_name="widget", watch_paths=["data/**"]
    )
    npm = _triggers((tmp_path / ".github/workflows/npm-ci-ts.yml").read_text())
    assert npm["push"]["paths"] == ["ts/**", "data/**", ".github/workflows/npm-ci-ts.yml"]


# --- the filter is derived, so re-renders keep it --------------------------------


def test_ci_to_stub_re_render_keeps_the_filter(polyglot):
    ci_path = polyglot / ".github/workflows/ci.yml"
    rendered = migrate_ci_to_stub(str(ci_path))
    assert _triggers(rendered) == _triggers(ci_path.read_text())
    from wads.ci_trigger import stub_paths_for_workflow

    paths = stub_paths_for_workflow(ci_path)
    assert stub_customizations(rendered, paths=paths)[1] == []  # nothing dropped


def test_on_demand_render_carries_the_filter_on_push(polyglot):
    (polyglot / "pyproject.toml").write_text(
        (polyglot / "pyproject.toml").read_text()
        + '\n[tool.wads.ci.trigger]\nmode = "on-demand"\n'
    )
    ci_path = polyglot / ".github/workflows/ci.yml"
    rendered = migrate_ci_to_stub(str(ci_path))
    triggers = _triggers(rendered)
    assert set(triggers) == {"push", "workflow_dispatch"}
    assert not runs_on(triggers["push"]["paths"], ["ts/src/index.ts"])


def test_include_paths_re_add_a_generated_file(polyglot):
    """chordsym: the Python tests check a TS file the Python side generates."""
    (polyglot / "pyproject.toml").write_text(
        (polyglot / "pyproject.toml").read_text()
        + '\n[tool.wads.ci.trigger]\ninclude_paths = ["ts/src/grammar.generated.ts"]\n'
    )
    rendered = migrate_ci_to_stub(str(polyglot / ".github/workflows/ci.yml"))
    paths = _triggers(rendered)["push"]["paths"]
    assert runs_on(paths, ["ts/src/grammar.generated.ts"])
    assert not runs_on(paths, ["ts/src/index.ts"])


@pytest.mark.parametrize("bad", ["ts/x.ts", 3, {"a": 1}, [1]])
def test_include_paths_must_be_a_list_of_strings(bad):
    with pytest.raises(ValueError, match="include_paths"):
        CIConfig(
            {"tool": {"wads": {"ci": {"trigger": {"include_paths": bad}}}}}
        ).trigger_include_paths


def test_the_on_demand_flip_keeps_the_filter(polyglot):
    """The flip renders in a shadow copy; the components are read from the repo."""
    flip_to_on_demand(polyglot)
    triggers = _triggers((polyglot / ".github/workflows/ci.yml").read_text())
    assert set(triggers) == {"push", "workflow_dispatch"}
    assert not runs_on(triggers["push"]["paths"], ["ts/src/index.ts"])
    assert runs_on(triggers["push"]["paths"], ["widget/__init__.py"])


CHORDSYM_STYLE_ON = (
    'on:\n  push:\n    paths: ["**", "!ts/**", "ts/src/grammar.generated.ts", '
    '"!.github/workflows/npm-ci-ts.yml"]\n  pull_request:\n    paths: ["**", '
    '"!ts/**", "ts/src/grammar.generated.ts", "!.github/workflows/npm-ci-ts.yml"]\n'
)


def _with_on(stub_text: str, on_block: str) -> str:
    start = stub_text.index("on:")
    return stub_text[:start] + on_block + stub_text[stub_text.index("jobs:") :]


def test_a_hand_written_filter_is_reported_not_silently_replaced(polyglot):
    """chordsym's stub, before it declares include_paths: a re-render would drop
    its generated-file exception, so that must be reported."""
    ci_path = polyglot / ".github/workflows/ci.yml"
    ci_path.write_text(_with_on(ci_path.read_text(), CHORDSYM_STYLE_ON))
    derived = migrate_ci_to_stub(str(ci_path))
    from wads.ci_trigger import stub_paths_for_workflow

    dropped = stub_customizations(
        ci_path.read_text(), paths=stub_paths_for_workflow(ci_path)
    )[1]
    assert dropped and dropped[0].startswith("`on:")
    assert "grammar.generated.ts" not in derived


def test_include_paths_make_a_hand_written_filter_reproducible(polyglot):
    ci_path = polyglot / ".github/workflows/ci.yml"
    (polyglot / "pyproject.toml").write_text(
        (polyglot / "pyproject.toml").read_text()
        + '\n[tool.wads.ci.trigger]\ninclude_paths = ["ts/src/grammar.generated.ts"]\n'
    )
    rendered = migrate_ci_to_stub(str(ci_path))
    ci_path.write_text(rendered)
    from wads.ci_trigger import stub_paths_for_workflow

    assert stub_customizations(rendered, paths=stub_paths_for_workflow(ci_path))[1] == []
    assert migrate_ci_to_stub(str(ci_path)) == rendered  # stable


def test_an_existing_stub_is_flagged_not_rewritten(tmp_path, capsys):
    """populate --frontend on a repo whose stub predates it: report, do not touch."""
    pkg = tmp_path / "widget"
    pkg.mkdir()
    _git_init(pkg, "https://github.com/myorg/widget")
    kwargs = dict(
        description="x", root_url="https://github.com/myorg", version="0.1.0"
    )
    populate_pkg_dir(str(pkg), verbose=False, **kwargs)
    before = (pkg / ".github/workflows/ci.yml").read_text()
    populate_pkg_dir(str(pkg), verbose=True, frontend="ts", **kwargs)
    assert (pkg / ".github/workflows/ci.yml").read_text() == before
    assert "wads-migrate ci-to-stub" in capsys.readouterr().out


def test_a_stale_filter_is_flagged_when_a_component_is_added(polyglot, capsys):
    kwargs = dict(
        description="x", root_url="https://github.com/myorg", version="0.1.0"
    )
    before = (polyglot / ".github/workflows/ci.yml").read_text()
    populate_pkg_dir(str(polyglot), verbose=True, frontend="js", **kwargs)
    assert (polyglot / ".github/workflows/ci.yml").read_text() == before
    assert "does not match the repo's npm components" in capsys.readouterr().out
    rendered = migrate_ci_to_stub(str(polyglot / ".github/workflows/ci.yml"))
    assert not runs_on(_triggers(rendered)["push"]["paths"], ["js/index.js"])


# --- units -----------------------------------------------------------------------


def test_no_npm_component_means_no_filter(tmp_path):
    assert python_ci_paths(tmp_path) == []
    assert render_stub_paths("on: [push, pull_request]\n", []) == (
        "on: [push, pull_request]\n"
    )


def test_each_component_and_its_workflow_are_left_out(tmp_path):
    apply_frontend(str(tmp_path), profile="js", project_name="w")
    apply_frontend(str(tmp_path), profile="ts", project_name="w")
    assert python_ci_paths(tmp_path) == [
        "**",
        "!js/**",
        "!.github/workflows/npm-ci.yml",
        "!ts/**",
        "!.github/workflows/npm-ci-ts.yml",
    ]


def test_render_refuses_an_unknown_stub_shape():
    with pytest.raises(ValueError, match="changed shape"):
        render_stub_paths("on:\n  schedule: []\n", ["**", "!ts/**"])


def test_rendered_on_demand_stub_is_still_a_template_trigger():
    stub = render_stub_trigger(
        "on: [push, pull_request]\njobs:\n  ci:\n    uses: x\n", mode="on-demand"
    )
    stub = render_stub_paths(stub, ["**", "!ts/**"])
    assert stub_customizations(stub, paths=["**", "!ts/**"])[1] == []
    # without knowing the derived filter, a filter is never assumed reproducible
    assert stub_customizations(stub)[1] != []


def test_a_dir_called_by_two_stubs_is_excluded_once(tmp_path):
    apply_frontend(str(tmp_path), profile="ts", project_name="w")
    second = tmp_path / ".github/workflows/npm-ci-ts2.yml"
    second.write_text(
        (tmp_path / ".github/workflows/npm-ci-ts.yml").read_text()
    )
    paths = python_ci_paths(tmp_path)
    assert paths.count("!ts/**") == 1
    assert "!.github/workflows/npm-ci-ts2.yml" in paths
