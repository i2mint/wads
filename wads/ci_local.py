"""Do locally what the wads CI would have done: the same ``[tool.wads.ci]``, no Actions minutes.

``wads ci-local`` reads the repo's ``pyproject.toml`` through :class:`wads.ci_config.CIConfig`,
the object the reusable workflow's setup job reads, and runs in order:

1. **lint**: ``ruff format --check`` (reported, never fatal: CI reformats in place and moves
   on), then ``ruff check <project>``, both through ``uvx`` so the repo's own ``[tool.ruff]``
   applies exactly as in CI. Black and mypy too, when enabled.
2. **tests**: for each ``python_versions`` entry, a fresh ``uv`` venv in a temporary
   directory, ``uv pip install -e .[extras]``, then pytest with the arguments
   ``actions/run-tests-uv`` builds (coverage, ``--doctest-modules`` and its option flags,
   one ``--ignore`` per excluded path, then ``pytest_args``).
3. **build**: ``uv build`` into the temporary directory, never the repo's ``dist/``, so a
   stale artifact can never be uploaded.

With ``publish=True`` it does what the publish job does in place of the plain build:
format in place, bump the version with ``isee`` (as CI does), build, ``uv publish``,
commit, tag and push. Before any of that it refuses on a dirty tree, a branch other than
the default, a branch behind its remote, or missing PyPI credentials.

Every command goes through one ``runner`` seam. The default runs subprocesses; tests pass
a fake. The default also refuses upload and push steps while pytest is running, so no test
can ever spend or publish.

>>> steps = plan_ci_local(".", config=CIConfig({"project": {"name": "pkg"}}))
>>> [s.name for s in steps][:3]
['format check (ruff)', 'lint (ruff)', 'python 3.10: venv']
"""

from __future__ import annotations

import configparser
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping, Optional, Sequence

from wads.ci_config import CIConfig

# Mirrors of values the CI actions hardcode. Tests pin each against its source
# (actions/run-tests-uv/action.yml, .github/workflows/uv-ci.yml) so they cannot drift.
DOCTEST_OPTIONFLAGS = "ELLIPSIS IGNORE_EXCEPTION_DETAIL"
RELEASE_COMMIT_MESSAGE = (
    "**CI** Formatted code + Updated version to <<version>> [skip ci]"
)
RELEASE_TAG_MESSAGE = "Release version <<version>>"
VERSION_TOOL = ("uvx", "--from", "isee", "isee")  # what bump-version-number runs
VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")

# Run-time placeholders in a Step's argv/env, in the templating engine's << >> style
# (so they cannot collide with braces in a user's pytest_args).
WORKDIR = "<<workdir>>"
DIST_DIR = f"{WORKDIR}/dist"
_PLACEHOLDER = re.compile(r"<<(\w+)>>")

# Side-effect classes. The default runner refuses the outward ones under pytest.
WRITES, UPLOADS, PUSHES = "writes", "uploads", "pushes"
OUTWARD_SIDE_EFFECTS = (UPLOADS, PUSHES)

PASSED, FAILED, SKIPPED = "ok", "FAIL", "skip"

_INSTALL_HINTS = {
    "uv": "install uv: https://docs.astral.sh/uv/getting-started/installation/",
    "uvx": "install uv (it provides uvx): https://docs.astral.sh/uv/getting-started/installation/",
    "git": "install git: https://git-scm.com/downloads",
}


@dataclass(frozen=True)
class Step:
    """One thing CI would do: a command (``argv``) or an in-process ``check``.

    ``argv`` and ``env`` values may hold ``<<workdir>>``, ``<<version>>``,
    ``<<default_branch>>`` or ``<<pypi_token>>``, filled in at run time. A non-``blocking``
    failure is reported without stopping the run. ``capture`` names the context value that
    receives the command's last stdout line. A ``check`` takes the run context and returns
    an error message, or ``None`` when it passes.
    """

    name: str
    argv: tuple = ()
    check: Optional[Callable] = None
    description: str = ""
    blocking: bool = True
    side_effect: str = ""
    capture: str = ""
    env: tuple = ()

    def display(self) -> str:
        if self.check is not None:
            return f"(check) {self.description}"
        return shlex.join(self.argv)


@dataclass(frozen=True)
class RunResult:
    """What a runner reports back: the exit code, and stdout when it was captured."""

    returncode: int
    stdout: str = ""


Runner = Callable[..., RunResult]


def subprocess_runner(
    argv: Sequence[str],
    *,
    cwd,
    env: Mapping[str, str],
    capture: bool = False,
    side_effect: str = "",
) -> RunResult:
    """The default runner: really run ``argv``, streaming its output.

    Refuses outward side effects (upload, push) while pytest is running.
    """
    if side_effect in OUTWARD_SIDE_EFFECTS and "PYTEST_CURRENT_TEST" in os.environ:
        raise RuntimeError(
            f"refusing a {side_effect!r} step under pytest: {shlex.join(argv)}"
        )
    try:
        proc = subprocess.run(
            list(argv), cwd=cwd, env=dict(env), text=True, capture_output=capture
        )
    except FileNotFoundError:
        tool = argv[0]
        return RunResult(127, _INSTALL_HINTS.get(tool, f"{tool!r} not found on PATH"))
    if capture and proc.stderr:
        print(proc.stderr, file=sys.stderr, end="")
    return RunResult(proc.returncode, proc.stdout if capture else "")


# --------------------------------------------------------------------------------------
# What CI runs, as data


def pytest_argv(config: CIConfig) -> list[str]:
    """The pytest arguments ``actions/run-tests-uv`` builds, in its order.

    >>> pytest_argv(CIConfig({"project": {"name": "pkg"}}))  # doctest: +NORMALIZE_WHITESPACE
    ['--cov=pkg', '--cov-report=term-missing', '--doctest-modules',
     '-o', 'doctest_optionflags=ELLIPSIS IGNORE_EXCEPTION_DETAIL',
     '--ignore=examples', '--ignore=scrap', '-v', '--tb=short']
    """
    argv = []
    if config.coverage_enabled:
        argv += [f"--cov={config.project_name}", "--cov-report=term-missing"]
    argv += ["--doctest-modules", "-o", f"doctest_optionflags={DOCTEST_OPTIONFLAGS}"]
    argv += [f"--ignore={p.strip()}" for p in config.exclude_paths if p.strip()]
    # The action joins pytest_args with spaces and `eval`s the result.
    argv += shlex.split(" ".join(config.pytest_args))
    return argv


def uv_build_args(*, sdist: bool = True, wheel: bool = True) -> list[str]:
    """``uv build`` selection flags for ``[tool.wads.ci.build]``.

    >>> uv_build_args()
    []
    >>> uv_build_args(sdist=False)
    ['--wheel']
    >>> uv_build_args(wheel=False)
    ['--sdist']
    """
    if not (sdist or wheel):
        raise ValueError(
            "[tool.wads.ci.build] disables both sdist and wheel: nothing to build"
        )
    if sdist and wheel:
        return []
    return ["--sdist"] if sdist else ["--wheel"]


def venv_python(venv: str, *, platform: str = os.name) -> str:
    """Path of the interpreter inside a venv directory.

    >>> venv_python("v", platform="posix")
    'v/bin/python'
    >>> venv_python("v", platform="nt")
    'v/Scripts/python.exe'
    """
    return f"{venv}/Scripts/python.exe" if platform == "nt" else f"{venv}/bin/python"


def plan_ci_local(
    repo=".",
    *,
    publish: bool = False,
    config: Optional[CIConfig] = None,
    platform: str = os.name,
) -> list[Step]:
    """Everything ``wads ci-local`` would run for ``repo``, in order, without running it."""
    repo = Path(repo)
    config = config if config is not None else CIConfig.from_file(repo)
    steps = _publish_preconditions() if publish else []
    if config.env_vars_required:
        steps.append(_required_env_step(config.env_vars_required))
    steps += _quality_steps(config)
    steps += _test_steps(config, platform=platform)
    steps += _release_steps(config, repo=repo) if publish else _build_steps(config)
    return steps


def _required_env_step(names) -> Step:
    def check(ctx):
        missing = [name for name in names if not ctx.env.get(name)]
        if missing:
            return (
                f"required env var(s) not set: {', '.join(missing)} "
                "(CI would fail at export-ci-env)"
            )
        return None

    return Step(
        "required env vars",
        check=check,
        description=f"set: {', '.join(names)} ([tool.wads.ci.env].required_envvars)",
    )


def _quality_steps(config: CIConfig) -> list[Step]:
    project = config.project_name
    steps = []
    if config.is_ruff_enabled():
        steps.append(
            Step(
                "format check (ruff)",
                ("uvx", "ruff", "format", "--check", "."),
                blocking=False,
            )
        )
    if config.is_black_enabled():
        steps.append(
            Step(
                "format check (black)", ("uvx", "black", "--check", "."), blocking=False
            )
        )
    if config.is_ruff_enabled():
        steps.append(Step("lint (ruff)", ("uvx", "ruff", "check", project)))
    if config.is_mypy_enabled():
        steps.append(Step("type check (mypy)", ("uvx", "mypy", project)))
    return steps


def _test_steps(config: CIConfig, *, platform: str) -> list[Step]:
    if not (config.tests_enabled or config.licence_enabled):
        return []
    target = f".[{config.install_extras}]" if config.install_extras else "."
    runner_deps = ("pytest", "pytest-cov") if config.coverage_enabled else ("pytest",)
    steps = []
    for index, version in enumerate(config.python_versions):
        venv = f"{WORKDIR}/py{version}"
        python = venv_python(venv, platform=platform)
        label = f"python {version}"
        steps += [
            Step(f"{label}: venv", ("uv", "venv", venv, "--python", version)),
            Step(
                f"{label}: install",
                ("uv", "pip", "install", "--python", python, "-e", target),
            ),
        ]
        if config.licence_enabled and index == 0:
            steps.append(
                Step(
                    f"{label}: licence perimeter",
                    (
                        "uvx",
                        "--from",
                        "wads",
                        "wads-licence-check",
                        ".",
                        "--python",
                        python,
                    ),
                )
            )
        if config.tests_enabled:
            steps += [
                Step(
                    f"{label}: install pytest",
                    ("uv", "pip", "install", "--python", python, *runner_deps),
                ),
                Step(f"{label}: tests", (python, "-m", "pytest", *pytest_argv(config))),
            ]
    return steps


def _build_steps(config: CIConfig) -> list[Step]:
    flags = uv_build_args(sdist=config.build_sdist, wheel=config.build_wheel)
    return [Step("build", ("uv", "build", "--out-dir", DIST_DIR, *flags))]


def _release_steps(config: CIConfig, *, repo: Path) -> list[Step]:
    steps = []
    if config.is_ruff_enabled():
        steps.append(
            Step("format (ruff)", ("uvx", "ruff", "format", "."), side_effect=WRITES)
        )
    if config.is_black_enabled():
        steps.append(Step("format (black)", ("uvx", "black", "."), side_effect=WRITES))
    steps.append(
        Step(
            "bump version",
            (*VERSION_TOOL, "gen-semver", "--output-mode=print"),
            capture="version",
        )
    )
    if (repo / "setup.cfg").is_file():
        steps.append(
            Step(
                "write version (setup.cfg)",
                (*VERSION_TOOL, "update-setup-cfg", "--version=<<version>>"),
                side_effect=WRITES,
            )
        )
    steps.append(
        Step(
            "write version (pyproject.toml)",
            (*VERSION_TOOL, "update-pyproject-toml", "--version=<<version>>"),
            side_effect=WRITES,
        )
    )
    steps += _build_steps(config)
    steps += [
        Step(
            "upload to PyPI",
            ("uv", "publish", f"{DIST_DIR}/*"),
            side_effect=UPLOADS,
            env=(("UV_PUBLISH_TOKEN", "<<pypi_token>>"),),
        ),
        Step(
            "commit release",
            ("git", "commit", "--all", "-m", RELEASE_COMMIT_MESSAGE),
            side_effect=WRITES,
        ),
        Step(
            "tag release",
            ("git", "tag", "-a", "<<version>>", "-m", RELEASE_TAG_MESSAGE),
            side_effect=WRITES,
        ),
        Step(
            "push branch",
            ("git", "push", "origin", "<<default_branch>>"),
            side_effect=PUSHES,
        ),
        Step("push tag", ("git", "push", "origin", "<<version>>"), side_effect=PUSHES),
    ]
    return steps


# --------------------------------------------------------------------------------------
# Publish preconditions


def resolve_pypi_token(
    *, environ: Optional[Mapping[str, str]] = None, pypirc=None
) -> tuple[Optional[str], str]:
    """Find a PyPI API token, most specific source first. Returns ``(token, source)``.

    1. ``$PYPI_PASSWORD``, the secret name CI reads;
    2. ``$UV_PUBLISH_TOKEN``, what ``uv publish`` itself reads;
    3. ``~/.pypirc``, section ``[pypi]``: ``password``, when ``username`` is ``__token__``
       (or absent) or the password is a ``pypi-`` token.

    Token-only, like CI. The token itself is never printed.

    >>> resolve_pypi_token(environ={"PYPI_PASSWORD": "pypi-x", "UV_PUBLISH_TOKEN": "pypi-y"})
    ('pypi-x', '$PYPI_PASSWORD')
    >>> resolve_pypi_token(environ={}, pypirc="/nonexistent/.pypirc")
    (None, '')
    """
    environ = os.environ if environ is None else environ
    for name in ("PYPI_PASSWORD", "UV_PUBLISH_TOKEN"):
        if environ.get(name):
            return environ[name], f"${name}"
    path = Path(pypirc) if pypirc is not None else Path.home() / ".pypirc"
    if path.is_file():
        parser = configparser.ConfigParser(interpolation=None)
        try:
            parser.read(path)
        except configparser.Error:
            return None, ""
        if parser.has_section("pypi"):
            password = parser.get("pypi", "password", fallback="").strip()
            username = parser.get("pypi", "username", fallback="__token__").strip()
            if password and (username == "__token__" or password.startswith("pypi-")):
                return password, f"{path} [pypi]"
    return None, ""


def _git_output(ctx, *args) -> tuple[int, str]:
    result = ctx.run(("git", *args), capture=True)
    return result.returncode, result.stdout.strip()


def _check_clean_tree(ctx) -> Optional[str]:
    code, status = _git_output(ctx, "status", "--porcelain")
    if code:
        return "`git status` failed: is this a git repository?"
    if status:
        return (
            "the working tree is dirty; commit or stash first:\n      "
            + status.replace("\n", "\n      ")
        )
    return None


def _check_default_branch(ctx) -> Optional[str]:
    code, ref = _git_output(ctx, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if code or not ref:
        return "cannot tell origin's default branch; run `git remote set-head origin --auto`"
    default = ref.split("/", 1)[-1]
    _, current = _git_output(ctx, "branch", "--show-current")
    if current != default:
        return (
            f"on {current or 'a detached HEAD'}, not the default branch {default!r}: "
            f"CI publishes only from {default!r}"
        )
    ctx.values["default_branch"] = default
    return None


def _check_not_behind(ctx) -> Optional[str]:
    default = ctx.values["default_branch"]
    code, _ = _git_output(ctx, "fetch", "--quiet", "origin", default)
    if code:
        return f"`git fetch origin {default}` failed"
    code, behind = _git_output(ctx, "rev-list", "--count", f"HEAD..origin/{default}")
    if code or not behind.isdigit():
        return f"could not compare HEAD with origin/{default}"
    if int(behind):
        return f"HEAD is {behind} commit(s) behind origin/{default}; pull first"
    return None


def _check_pypi_token(ctx) -> Optional[str]:
    token, source = resolve_pypi_token(environ=ctx.env)
    if not token:
        return (
            "no PyPI API token: set $PYPI_PASSWORD, or put `username = __token__` and "
            "`password = pypi-...` under [pypi] in ~/.pypirc"
        )
    ctx.values["pypi_token"] = token
    ctx.notes.append(f"PyPI token from {source}")
    return None


def _publish_preconditions() -> list[Step]:
    return [
        Step(
            "clean working tree",
            check=_check_clean_tree,
            description="`git status --porcelain` is empty",
        ),
        Step(
            "on the default branch",
            check=_check_default_branch,
            description="current branch is origin's default branch",
        ),
        Step(
            "up to date with origin",
            check=_check_not_behind,
            description="after `git fetch`, HEAD is not behind origin",
        ),
        Step(
            "PyPI credentials",
            check=_check_pypi_token,
            description="$PYPI_PASSWORD, else $UV_PUBLISH_TOKEN, else ~/.pypirc [pypi]",
        ),
    ]


# --------------------------------------------------------------------------------------
# Running and reporting


@dataclass
class _Context:
    repo: Path
    runner: Runner
    env: dict
    values: dict
    notes: list = field(default_factory=list)

    def run(self, argv, *, capture=False, side_effect=""):
        return self.runner(
            list(argv),
            cwd=self.repo,
            env=self.env,
            capture=capture,
            side_effect=side_effect,
        )


def _fill(template: str, values: Mapping[str, str]) -> str:
    def replace(match):
        key = match.group(1)
        if key not in values:
            raise KeyError(
                f"unresolved placeholder <<{key}>> (an earlier step did not set it)"
            )
        return values[key]

    return _PLACEHOLDER.sub(replace, template)


def _show(template: str, values: Mapping[str, str]) -> str:
    """Fill what is known, keep the rest, and never show the token."""
    safe = {k: v for k, v in values.items() if k != "pypi_token"}
    return _PLACEHOLDER.sub(lambda m: safe.get(m.group(1), m.group(0)), template)


def _last_line(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def _execute(step: Step, ctx: _Context) -> tuple[str, str]:
    if step.check is not None:
        error = step.check(ctx)
        return (FAILED, error) if error else (PASSED, "")
    argv = [_fill(item, ctx.values) for item in step.argv]
    env = dict(ctx.env)
    env.update({key: _fill(value, ctx.values) for key, value in step.env})
    result = ctx.runner(
        argv,
        cwd=ctx.repo,
        env=env,
        capture=bool(step.capture),
        side_effect=step.side_effect,
    )
    if result.returncode != 0:
        hint = f": {result.stdout.strip()}" if result.returncode == 127 else ""
        return FAILED, f"exit {result.returncode}{hint}"
    if step.capture:
        value = _last_line(result.stdout)
        if step.capture == "version" and not VERSION_PATTERN.match(value):
            return FAILED, f"not a version number: {value!r}"
        ctx.values[step.capture] = value
        return PASSED, value
    return PASSED, ""


@dataclass
class CILocalReport:
    """The outcome of a ``wads ci-local`` run, rendered the way CI would summarise it."""

    project: str
    publish: bool
    trigger_mode: str
    python_versions: list
    outcomes: list = field(default_factory=list)  # (Step, status, detail)
    notes: list = field(default_factory=list)
    values: dict = field(default_factory=dict)

    @property
    def failure(self) -> Optional[Step]:
        """The blocking step that failed, if any."""
        return next(
            (
                step
                for step, status, _ in self.outcomes
                if status == FAILED and step.blocking
            ),
            None,
        )

    @property
    def ok(self) -> bool:
        return self.failure is None

    def verdict(self) -> str:
        failure = self.failure
        if failure is None:
            if self.publish:
                return (
                    f"Result: PASSED. Released {self.values.get('version', '?')}, "
                    "as the CI publish job would have."
                )
            return "Result: PASSED. CI would have reported this run green."
        if failure.check is not None and self.publish:
            return f"Result: REFUSED to publish ({failure.name}). Nothing was changed."
        uploaded = any(
            step.side_effect == UPLOADS and status == PASSED
            for step, status, _ in self.outcomes
        )
        if uploaded:
            version = self.values.get("version", "<version>")
            branch = self.values.get("default_branch", "<branch>")
            return (
                f"Result: FAILED at {failure.name!r} AFTER the upload: PyPI has "
                f"{version}. Finish by hand: git push origin {branch} && "
                f"git push origin {version}"
            )
        tail = " Nothing was uploaded." if self.publish else ""
        return (
            f"Result: FAILED at {failure.name!r}. CI would have reported this run red, "
            f"and publish would not have run.{tail}"
        )

    def render(self) -> str:
        header = (
            f"wads ci-local: {self.project}  (trigger: {self.trigger_mode}; "
            f"python: {', '.join(self.python_versions)}; "
            f"publish: {'yes' if self.publish else 'no'})"
        )
        width = max((len(step.name) for step, _, _ in self.outcomes), default=0)
        lines = [header]
        for step, status, detail in self.outcomes:
            flag = "warn" if status == FAILED and not step.blocking else status
            first = detail.splitlines()[0] if detail else ""
            lines.append(f"  {flag:<4}  {step.name:<{width}}  {first}".rstrip())
        lines += [f"  note: {note}" for note in self.notes]
        failure = self.failure
        if failure is not None:
            detail = next(
                d for s, st, d in self.outcomes if s is failure and st == FAILED
            )
            if "\n" in detail:
                lines.append("  " + detail)
        lines.append(self.verdict())
        return "\n".join(lines)


def run_ci_local(
    repo=".",
    *,
    publish: bool = False,
    config: Optional[CIConfig] = None,
    runner: Runner = subprocess_runner,
    environ: Optional[Mapping[str, str]] = None,
    out=None,
    keep_workdir: bool = False,
) -> CILocalReport:
    """Run :func:`plan_ci_local`'s steps, stop at the first blocking failure, and report."""
    repo = Path(repo).resolve()
    out = out or sys.stdout
    config = config if config is not None else CIConfig.from_file(repo)
    steps = plan_ci_local(repo, publish=publish, config=config)
    env = dict(os.environ if environ is None else environ)
    # Committed defaults are authoritative, as in CI's export-ci-env.
    env.update({key: str(value) for key, value in config.env_vars_defaults.items()})
    workdir = tempfile.mkdtemp(prefix="wads-ci-local-")
    ctx = _Context(repo=repo, runner=runner, env=env, values={"workdir": workdir})
    report = CILocalReport(
        project=config.project_name,
        publish=publish,
        trigger_mode=config.trigger_mode,
        python_versions=list(config.python_versions),
    )
    try:
        stopped = False
        for step in steps:
            if stopped:
                report.outcomes.append((step, SKIPPED, "not reached"))
                continue
            # Flush: the command's own output goes straight to the terminal, and an
            # unflushed header would land after it.
            print(
                f"\n==> {step.name}: {_show(step.display(), ctx.values)}",
                file=out,
                flush=True,
            )
            try:
                status, detail = _execute(step, ctx)
            except KeyError as exc:
                status, detail = FAILED, str(exc)
            report.outcomes.append((step, status, detail))
            stopped = status == FAILED and step.blocking
    finally:
        if not keep_workdir:
            shutil.rmtree(workdir, ignore_errors=True)
    report.notes += ctx.notes
    report.values = {
        k: v for k, v in ctx.values.items() if k in ("version", "default_branch")
    }
    print("\n" + report.render(), file=out)
    return report


def render_plan(steps: Sequence[Step]) -> str:
    """The plan as numbered lines, flagging non-blocking and side-effecting steps."""
    lines = [
        "wads ci-local plan (<<workdir>> is a fresh temporary directory; "
        "<<version>> comes from the bump step):"
    ]
    for number, step in enumerate(steps, 1):
        tags = ([] if step.blocking else ["non-blocking"]) + (
            [step.side_effect] if step.side_effect else []
        )
        suffix = f"  [{', '.join(tags)}]" if tags else ""
        lines.append(f"  {number:>2}. {step.name}: {step.display()}{suffix}")
    return "\n".join(lines)


def ci_local(repo: str = ".", *, publish: bool = False, dry_run: bool = False):
    """Do locally what wads CI would have done, from the repo's [tool.wads.ci] config.

    Lint, tests (a fresh uv venv per configured Python) and build. With --publish, the
    publish job instead: format, bump version, build, upload to PyPI, commit, tag and push,
    refusing on a dirty tree, off the default branch, or without PyPI credentials. With
    --dry-run, print the plan and run nothing.
    """
    if dry_run:
        print(render_plan(plan_ci_local(repo, publish=publish)))
        return None
    if not run_ci_local(repo, publish=publish).ok:
        raise SystemExit(1)
    return None
