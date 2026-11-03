"""Do locally what the wads CI would have done: the same ``[tool.wads.ci]``, no Actions minutes.

``wads ci-local`` reads the repo's ``pyproject.toml`` through :class:`wads.ci_config.CIConfig`,
the object the reusable workflow's setup job reads, and runs in order:

1. **lint**: ``ruff format --check`` (reported, never fatal: CI reformats in place and moves
   on), then ``ruff check <project>``, both through ``uvx`` so the repo's own ``[tool.ruff]``
   applies exactly as in CI. Black and mypy too, when enabled.
2. **tests**: for each ``python_versions`` entry, a fresh ``uv`` venv in a temporary
   directory, ``uv pip install -e .[extras]``, then pytest with the arguments
   ``actions/run-tests-uv`` builds (coverage, ``--doctest-modules`` and its option flags,
   one ``--ignore`` per excluded path, then ``pytest_args``). Then one more such leg per
   ``[[tool.wads.ci.testing.pinned]]`` entry, the project and its pins installed in one
   resolve and checked with ``uv pip check``, as the validation job's pinned legs do.
3. **build**: ``uv build`` into the temporary directory, never the repo's ``dist/``, so a
   stale artifact can never be uploaded.

With ``publish=True`` it does what the publish job does in place of the plain build:
format in place, bump the version with ``isee`` (as CI does), build, ``uv publish``,
commit, tag and push. Before any of that it refuses on a dirty tree, a branch other than
the default, a branch behind its remote, or missing PyPI credentials.

Known differences from CI: the developer's environment passes through to the commands
(minus PyPI credentials, which only the upload step sees, and minus what the dev shell has
and hosted CI does not: install pins such as ``UV_CONSTRAINT``, and ``PYTHONSAFEPATH``,
``PYTHONPATH``, ``PYTHONHOME``, ``PYTHONOPTIMIZE``; each leg's tests run with its venv
activated, as CI's are), where CI exports only the
variables ``[tool.wads.ci.env]`` declares; ``[tool.wads.ops.*]`` system packages are not
installed; and lint runs on the tree as it is, where CI formats first.

Each run works in a fresh ``wads-ci-local-*`` temporary directory that records its owner's
PID (:mod:`wads.workdirs`), and gives pytest a private ``--basetemp`` inside it, so
concurrent runs never delete each other's basetemp and the workdir's removal takes the
basetemp with it. Before starting, a run removes the workdirs killed runs left behind
(older than a few hours, owner no longer running) and refuses, with a plain message, when
the temp filesystem lacks the space or the inodes for one venv per tested Python, rather
than failing partway with ``No space left on device`` (issue #159).

Every command goes through one ``runner`` seam. The default runs subprocesses; tests pass
a fake. The default also refuses upload and push steps while pytest is running, so no test
can ever spend or publish.

>>> steps = plan_ci_local(".", config=CIConfig({"project": {"name": "pkg"}}))
>>> [s.name for s in steps][:3]
['format check (ruff)', 'lint (ruff)', 'python 3.10: venv']
"""

from __future__ import annotations

import configparser
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping, Optional, Sequence

from wads.ci_config import TRIGGER_LEVELS, CIConfig
from wads.native_build import cargo_test_args, native_build_config
from wads.scripts.pytest_doctest_flags import doctest_optionflags_arg
from wads.workdirs import (
    BYTES_PER_GB,
    DFLT_STALE_AGE,
    HOUR,
    make_workdir,
    room_shortfall,
    sweep_stale_workdirs,
)

# Mirrors of values the CI actions hardcode. Tests pin each against its source
# (actions/run-tests-uv/action.yml, .github/workflows/uv-ci.yml) so they cannot drift.
RELEASE_COMMIT_MESSAGE = (
    "**CI** Formatted code + Updated version to <<version>> [skip ci]"
)
RELEASE_TAG_MESSAGE = "Release version <<version>>"
# What bump-version-number runs. `--with pip`: isee imports pip at module load, which
# CI's setup-python environment has and a bare uvx environment does not.
VERSION_TOOL = ("uvx", "--from", "isee", "--with", "pip", "isee")
VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")

# Run-time placeholders in a Step's argv/env, in the templating engine's << >> style
# (so they cannot collide with braces in a user's pytest_args).
WORKDIR = "<<workdir>>"
DIST_DIR = f"{WORKDIR}/dist"
# ci-local's own pytest --basetemp: private to the run (pytest prunes the shared default
# one on startup, deleting a concurrent run's live basetemp), and swept with the workdir.
PYTEST_BASETEMP = f"{WORKDIR}/pytest"
_PLACEHOLDER = re.compile(r"<<(\w+)>>")

# Side-effect classes. The default runner refuses the outward ones under pytest.
WRITES, UPLOADS, PUSHES = "writes", "uploads", "pushes"
OUTWARD_SIDE_EFFECTS = (UPLOADS, PUSHES)

# Kept out of every step's environment except the upload's, as CI keeps them out of
# lint, tests, the version bump and build hooks.
PUBLISH_CREDENTIAL_VARS = (
    "PYPI_PASSWORD",
    "UV_PUBLISH_TOKEN",
    "UV_PUBLISH_USERNAME",
    "UV_PUBLISH_PASSWORD",
)

# The dev machine's install pins. Hosted CI has none; inherited, they make ci-local test a
# different environment (and the fleet's constraint file, which pins every local package
# to its main checkout, breaks the install from a git worktree, issue #191).
HOST_INSTALL_PIN_VARS = (
    "UV_CONSTRAINT",
    "UV_BUILD_CONSTRAINT",
    "UV_OVERRIDE",
    "PIP_CONSTRAINT",
)
# The dev shell's interpreter path settings. CI's ``python -m pytest`` puts the cwd on
# ``sys.path``; an inherited ``PYTHONSAFEPATH=1`` keeps it off (3.11+), and a
# ``PYTHONPATH`` adds directories CI does not have (issue #194).
# Likewise PYTHONHOME (a venv's activation unsets it; inherited, it breaks every venv
# step) and PYTHONOPTIMIZE (strips asserts: a false green). Not every PYTHON*: CI sets
# PYTHONIOENCODING and PYTHONUTF8 itself.
HOST_INTERPRETER_VARS = ("PYTHONSAFEPATH", "PYTHONPATH", "PYTHONHOME", "PYTHONOPTIMIZE")
#: Everything of the dev shell hosted CI does not have; every step runs without it, by
#: default (``run_ci_local(host_only_vars=())`` keeps it all).
HOST_ONLY_VARS = HOST_INSTALL_PIN_VARS + HOST_INTERPRETER_VARS

PASSED, FAILED, SKIPPED = "ok", "FAIL", "skip"

#: Prefix of the temporary work directory each run makes (and sweeps when left behind).
WORKDIR_PREFIX = "wads-ci-local-"
#: Free space the temp filesystem needs per tested Python before a run starts: one venv
#: with the project's deps installed (0.5-0.7 GB for a mid-size package), plus headroom.
WORKDIR_BYTES_PER_PYTHON = 1_000_000_000
#: Free inodes it needs per tested Python: a workdir held ~22k and a pytest basetemp up
#: to ~82k on a real tmpfs that ran out of inodes, not bytes (issue #159).
WORKDIR_INODES_PER_PYTHON = 100_000

_INSTALL_HINTS = {
    "uv": "install uv: https://docs.astral.sh/uv/getting-started/installation/",
    "uvx": "install uv (it provides uvx): https://docs.astral.sh/uv/getting-started/installation/",
    "git": "install git: https://git-scm.com/downloads",
}


@dataclass(frozen=True)
class Step:
    """One thing CI would do: a command (``argv``) or an in-process ``check``.

    ``argv`` and ``env`` values may hold ``<<workdir>>``, ``<<version>>``,
    ``<<default_branch>>``, ``<<pypi_token>>`` or ``<<host_path_suffix>>`` (the run's PATH
    after a path separator, or nothing when it has none), filled in at run time. A non-``blocking``
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


def pytest_argv(
    config: CIConfig,
    *,
    repo=None,
    pytest_args: Optional[Sequence[str]] = None,
) -> list[str]:
    """The pytest arguments ``actions/run-tests-uv`` builds, in its order.

    The default ``doctest_optionflags`` are passed unless ``repo``'s own pytest config
    sets them (``repo=None``: not checked, defaults passed). ``pytest_args`` defaults
    to the config's (a pinned leg passes its own, issue #189).

    >>> pytest_argv(CIConfig({"project": {"name": "pkg"}}))  # doctest: +NORMALIZE_WHITESPACE
    ['--cov=pkg', '--cov-report=term-missing', '--doctest-modules',
     '-o', 'doctest_optionflags=ELLIPSIS IGNORE_EXCEPTION_DETAIL',
     '--ignore=examples', '--ignore=scrap', '-v', '--tb=short']
    """
    pytest_args = config.pytest_args if pytest_args is None else pytest_args
    argv = []
    if config.coverage_enabled:
        argv += [f"--cov={config.project_name}", "--cov-report=term-missing"]
    argv += ["--doctest-modules"]
    extra = " ".join(pytest_args)
    if flags_arg := doctest_optionflags_arg(
        None if repo is None else str(repo), pytest_args=extra
    ):
        argv += ["-o", flags_arg]
    argv += [f"--ignore={p.strip()}" for p in config.exclude_paths if p.strip()]
    # The action joins pytest_args with spaces and `eval`s the result.
    argv += shlex.split(extra)
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
    steps += _rust_steps(config, repo=repo)
    steps += _test_steps(config, platform=platform, repo=repo)
    steps += _pinned_steps(config, platform=platform, repo=repo)
    steps += _release_steps(config, repo=repo) if publish else _build_steps(config)
    return steps


def _venv_count(steps: Sequence[Step]) -> int:
    """How many venvs ``steps`` create (none when tests and the licence gate are off)."""
    return sum(step.argv[:2] == ("uv", "venv") for step in steps)


def _space_needed(n_venvs: int) -> str:
    """The temp space a run with ``n_venvs`` venvs needs, as the plan and check word it."""
    gb = n_venvs * WORKDIR_BYTES_PER_PYTHON / BYTES_PER_GB
    return f"{gb:.1f} GB / {n_venvs * WORKDIR_INODES_PER_PYTHON:,} inodes"


def _temp_space_step(n_venvs: int) -> Step:
    """Refuse up front when the temp filesystem cannot hold the run's venvs (issue #159).

    Not part of :func:`plan_ci_local`, which mirrors what CI does: it is a check on this
    machine, run first by :func:`run_ci_local`. Without it a full tmpfs fails the run
    partway, as test errors or a crashed pytest that read as red CI. Both bytes and
    inodes count: the outage behind #159 had bytes to spare and no inodes left.
    """
    needed_bytes = n_venvs * WORKDIR_BYTES_PER_PYTHON
    needed_inodes = n_venvs * WORKDIR_INODES_PER_PYTHON

    def check(ctx):
        shortfall = room_shortfall(
            ctx.values["workdir"], min_bytes=needed_bytes, min_inodes=needed_inodes
        )
        if shortfall:
            return (
                f"{shortfall} in the temp directory, need about "
                f"{_space_needed(n_venvs)} (one venv and pytest basetemp per tested "
                "Python): free some, or set TMPDIR to a bigger filesystem"
            )
        return None

    return Step(
        "temp space",
        check=check,
        description=f">= {_space_needed(n_venvs)} free for <<workdir>>",
    )


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


def _install_target(config: CIConfig) -> str:
    """What ``install-deps-uv`` installs: the project, with its CI extras."""
    return f".[{config.install_extras}]" if config.install_extras else "."


def _leg_steps(
    config: CIConfig,
    *,
    label: str,
    venv: str,
    version: str,
    platform: str,
    repo=None,
    pins: Sequence[str] = (),
    pytest_args: Optional[Sequence[str]] = None,
    licence: bool = False,
) -> list[Step]:
    """One validation leg: a venv on ``version``, the project installed (with ``pins``
    in the same resolve, then ``uv pip check``), optionally the licence gate, then
    pytest with ``pytest_args`` (default: the config's) when tests are on."""
    python = venv_python(venv, platform=platform)
    runner_deps = ("pytest", "pytest-cov") if config.coverage_enabled else ("pytest",)
    install = (
        "uv",
        "pip",
        "install",
        "--python",
        python,
        "-e",
        _install_target(config),
    )
    steps = [
        Step(f"{label}: venv", ("uv", "venv", venv, "--python", version)),
        # A pinned leg resolves pytest with the pins, so the later pytest install is a
        # no-op and cannot re-upgrade a pin in pytest's own closure (pluggy, ...).
        Step(f"{label}: install", (*install, *pins, *(runner_deps if pins else ()))),
    ]
    if pins:
        steps.append(
            Step(f"{label}: pip check", ("uv", "pip", "check", "--python", python))
        )
    if licence:
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
            Step(
                f"{label}: tests",
                (
                    python,
                    "-m",
                    "pytest",
                    # First, so a `--` in the user's pytest_args cannot turn it
                    # into a test path.
                    "--basetemp",
                    PYTEST_BASETEMP,
                    *pytest_argv(config, repo=repo, pytest_args=pytest_args),
                ),
                # The venv activated, as run-tests-uv does: a test that shells out to
                # `python` or `uv pip` reaches this venv, not the dev shell's (#194).
                env=_activated(venv, platform=platform),
            ),
        ]
    return steps


def _activated(venv: str, *, platform: str) -> tuple:
    """A Step's ``env`` for running inside ``venv``: its bin directory first on PATH.

    >>> _activated("/w/py3.12", platform="posix")
    (('VIRTUAL_ENV', '/w/py3.12'), ('PATH', '/w/py3.12/bin<<host_path_suffix>>'))
    >>> _activated("/w/py3.12", platform="nt")[1]
    ('PATH', '/w/py3.12/Scripts<<host_path_suffix>>')
    """
    bin_dir = venv_python(venv, platform=platform).rsplit("/", 1)[0]
    return (("VIRTUAL_ENV", venv), ("PATH", f"{bin_dir}<<host_path_suffix>>"))


def _rust_steps(config: CIConfig, *, repo: Path) -> list[Step]:
    """The validation job's Rust checks for a native (maturin) package (issue #166)."""
    native = native_build_config(config.data)
    if native is None:
        return []

    def cargo_test(ctx):
        args = native.cargo_test_args
        if args is None:
            meta = ctx.run(
                ["cargo", "metadata", *manifest, "--no-deps", "--format-version", "1"],
                capture=True,
            )
            if meta.returncode != 0:
                return f"cargo metadata failed (exit {meta.returncode})"
            args = cargo_test_args(
                json.loads(meta.stdout),
                binding_manifest=str(repo / native.manifest_path),
            )
        if not args:
            ctx.notes.append("no pure-Rust crate to cargo test")
            return None
        result = ctx.run(["cargo", "test", *manifest, *args])
        return f"exit {result.returncode}" if result.returncode else None

    manifest = ("--manifest-path", native.manifest_path)
    return [
        Step("rust: fmt", ("cargo", "fmt", "--all", "--check", *manifest)),
        Step(
            "rust: clippy",
            ("cargo", "clippy", *manifest, "--workspace", "--all-targets")
            + ("--", "-D", "warnings"),
        ),
        Step(
            "rust: test",
            check=cargo_test,
            description="cargo test on the pure-Rust crates (not the binding one)",
        ),
    ]


def _test_steps(config: CIConfig, *, platform: str, repo=None) -> list[Step]:
    if not (config.tests_enabled or config.licence_enabled):
        return []
    steps = []
    for index, version in enumerate(config.python_versions):
        steps += _leg_steps(
            config,
            label=f"python {version}",
            venv=f"{WORKDIR}/py{version}",
            version=version,
            platform=platform,
            repo=repo,
            licence=config.licence_enabled and index == 0,
        )
    return steps


def _pinned_steps(config: CIConfig, *, platform: str, repo=None) -> list[Step]:
    """The validation job's pinned legs (issue #189): per ``[[tool.wads.ci.testing.pinned]]``
    entry, a venv on its ``python_version``, the project and the pins in one resolve,
    ``uv pip check``, then pytest with the entry's ``pytest_args``."""
    runs = config.pinned_test_runs  # validated even when tests are off: fail closed
    if not config.tests_enabled:
        return []
    steps = []
    for run in runs:
        steps += _leg_steps(
            config,
            label=f"pinned {run.name}",
            venv=f"{WORKDIR}/pinned-{run.name}",
            version=run.python_version,
            platform=platform,
            repo=repo,
            pins=run.requirements,
            pytest_args=run.pytest_args,
        )
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
    token, source = resolve_pypi_token(environ=ctx.source_env)
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
    source_env: dict = field(default_factory=dict)  # unsanitized: credentials live here

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
        if not self.publish:
            return (
                f"Result: FAILED at {failure.name!r}. CI would have reported this run red, "
                "and publish would not have run."
            )
        return "\n".join(self._publish_failure_lines(failure))

    def _publish_failure_lines(self, failure: Step) -> list:
        """What a failed publish left behind, and how to recover, from the steps that passed."""
        steps = [step for step, _, _ in self.outcomes]
        passed = {id(step) for step, status, _ in self.outcomes if status == PASSED}
        upload = next((step for step in steps if step.side_effect == UPLOADS), None)
        version = self.values.get("version", "<version>")
        if upload is not None and id(upload) in passed:
            remaining = [
                step
                for step in steps[steps.index(upload) + 1 :]
                if id(step) not in passed
            ]
            lines = [
                f"Result: FAILED at {failure.name!r} AFTER the upload: PyPI has {version}. "
                "Finish by hand, in order:"
            ]
            lines += [
                "  " + shlex.join(_show(item, self.values) for item in step.argv)
                for step in remaining
            ]
            if any(step.side_effect == PUSHES for step in remaining):
                lines.append(
                    "  (if a push is rejected because origin moved: `git pull --rebase`, "
                    "then push again)"
                )
            return lines
        lines = [
            f"Result: FAILED at {failure.name!r}. CI would have reported this run red."
        ]
        if failure is upload:
            lines.append(
                "The upload failed and may be PARTIAL (one file up, another not): check "
                f"https://pypi.org/project/{self.project}/{version}/ before retrying."
            )
        else:
            lines.append("Nothing was uploaded.")
        wrote = [
            step.name
            for step in steps
            if step.side_effect == WRITES and id(step) in passed
        ]
        if wrote:
            lines.append(
                f"The working tree was changed by: {', '.join(wrote)}. Undo with "
                "`git checkout -- .` before re-running (--publish refuses a dirty tree)."
            )
        return lines

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


def steps_env(
    source_env: Mapping[str, str],
    *,
    defaults: Mapping[str, object] = (),
    withheld: Sequence[str] = PUBLISH_CREDENTIAL_VARS + HOST_ONLY_VARS,
) -> tuple[dict, list[str]]:
    """The environment the steps run in, and the names of ``source_env`` it left out.

    ``source_env`` minus ``withheld``, then the committed ``defaults``, which are
    authoritative as in CI's export-ci-env (so a withheld name a default sets is back,
    and is not reported as left out).

    >>> steps_env({"HOME": "/h", "UV_CONSTRAINT": "/c.txt", "PYPI_PASSWORD": "t"})
    ({'HOME': '/h'}, ['PYPI_PASSWORD', 'UV_CONSTRAINT'])
    >>> steps_env({"UV_CONSTRAINT": "/c.txt"}, defaults={"UV_CONSTRAINT": "/repo.txt"})
    ({'UV_CONSTRAINT': '/repo.txt'}, [])
    """
    env = {k: v for k, v in source_env.items() if k not in withheld}
    env.update({key: str(value) for key, value in dict(defaults).items()})
    return env, sorted(k for k in source_env if k not in env)


def run_ci_local(
    repo=".",
    *,
    publish: bool = False,
    config: Optional[CIConfig] = None,
    runner: Runner = subprocess_runner,
    environ: Optional[Mapping[str, str]] = None,
    out=None,
    keep_workdir: bool = False,
    workdir_root: Optional[str] = None,
    host_only_vars: Sequence[str] = HOST_ONLY_VARS,
) -> CILocalReport:
    """Run :func:`plan_ci_local`'s steps, stop at the first blocking failure, and report.

    The steps run in a fresh work directory under ``workdir_root`` (default: the system
    temp directory), after removing the stale ones killed runs left there and checking
    that the filesystem has room for this run (issue #159).

    ``environ`` (default ``os.environ``) reaches every step minus the PyPI credentials
    (only the upload sees them) and minus ``host_only_vars``, what the dev shell has and
    hosted CI does not: install constraints (#191), ``PYTHONSAFEPATH`` / ``PYTHONPATH``
    (#194). Each leg's tests run with its venv activated (``VIRTUAL_ENV``, its ``bin``
    first on ``PATH``), as in CI.
    """
    repo = Path(repo).resolve()
    out = out or sys.stdout
    config = config if config is not None else CIConfig.from_file(repo)
    steps = plan_ci_local(repo, publish=publish, config=config)
    if n_venvs := _venv_count(steps):
        steps.insert(0, _temp_space_step(n_venvs))
    source_env = dict(os.environ if environ is None else environ)
    env, dropped_host = steps_env(
        source_env,
        defaults=config.env_vars_defaults,
        withheld=(*PUBLISH_CREDENTIAL_VARS, *host_only_vars),
    )
    dropped_host = [name for name in dropped_host if name in host_only_vars]
    # A killed run never reaches the cleanup below; remove what earlier ones left.
    # Best effort: a sweep that fails must not stop the run it was clearing room for.
    try:
        swept = sweep_stale_workdirs(WORKDIR_PREFIX, root=workdir_root)
    except OSError as exc:
        swept = []
        print(f"Note: skipped the stale workdir sweep ({exc})", file=out)
    if swept:
        print(f"Removed {len(swept)} stale {WORKDIR_PREFIX}* workdir(s)", file=out)
    workdir = make_workdir(WORKDIR_PREFIX, root=workdir_root)
    ctx = _Context(
        repo=repo,
        runner=runner,
        env=env,
        # No trailing separator for an empty PATH: on POSIX an empty entry is the cwd.
        values={
            "workdir": workdir,
            "host_path_suffix": os.pathsep + env["PATH"] if env.get("PATH") else "",
        },
        source_env=source_env,
    )
    if dropped_host:
        ctx.notes.append(f"ran without {', '.join(dropped_host)} (hosted CI has none)")
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
    """The plan as numbered lines, flagging non-blocking and side-effecting steps.

    The header also says what :func:`run_ci_local` does before the plan: sweep stale
    workdirs and check the temp filesystem has room.
    """
    n_venvs = _venv_count(steps)
    room = f", and requires about {_space_needed(n_venvs)} free" if n_venvs else ""
    lines = [
        "wads ci-local plan (<<workdir>> is a fresh temporary directory; "
        "<<version>> comes from the bump step):",
        f"  A real run first removes stale {WORKDIR_PREFIX}* workdirs older than "
        f"{DFLT_STALE_AGE / HOUR:g} h whose owner is gone{room}.",
    ]
    for number, step in enumerate(steps, 1):
        tags = ([] if step.blocking else ["non-blocking"]) + (
            [step.side_effect] if step.side_effect else []
        )
        suffix = f"  [{', '.join(tags)}]" if tags else ""
        lines.append(f"  {number:>2}. {step.name}: {step.display()}{suffix}")
    return "\n".join(lines)


def ci_local(
    repo: str = ".",
    *,
    publish: bool = False,
    dry_run: bool = False,
    level: Optional[str] = None,
):
    """Do locally what wads CI would have done, from the repo's [tool.wads.ci] config.

    Lint, tests (a fresh uv venv per configured Python) and build. With --publish, the
    publish job instead: format, bump version, build, upload to PyPI, commit, tag and push,
    refusing on a dirty tree, off the default branch, or without PyPI credentials. With
    --dry-run, print the plan and run nothing. ``--level validate|deploy`` names the same
    choice as CI's on-demand ladder (``deploy`` is ``--publish``).
    """
    if level is not None:
        if level not in TRIGGER_LEVELS:
            raise SystemExit(f"--level must be one of {TRIGGER_LEVELS}, got {level!r}")
        if publish and level != "deploy":
            raise SystemExit(
                "--publish is --level deploy; it contradicts --level validate"
            )
        publish = level == "deploy"
    if dry_run:
        print(render_plan(plan_ci_local(repo, publish=publish)))
        return None
    if not run_ci_local(repo, publish=publish).ok:
        raise SystemExit(1)
    return None
