"""``wads npm-trust``: find a repo's npm publishers and attach Trusted Publishers.

npm trusted publishing (OIDC, see the ``npm-publishing`` skill) needs, per package,
one ``npm trust github <pkg> --file <caller workflow> --repo <owner>/<repo> [--env E]
--allow-publish -y`` (npm >= 11.15, an owner login with 2FA) and the package must already
exist on npm. Doing that by hand across a fleet means finding, for every package, the
workflow that publishes it. This module does the finding, reports it, and optionally
runs the commands:

1. **Discover** (:func:`discover`): the workflows under ``.github/workflows`` that publish
   (``npm publish``, ``pnpm publish``, ``pnpm -r publish``, ``changeset publish``,
   ``changesets/action`` with a ``publish:`` command, a script such as ``pnpm release``
   that runs one of those, or a caller of a wads ``npm-ci*.yml`` reusable workflow), and
   the non-private packages each publishes (the package in the working directory, every
   workspace member for ``-r`` / ``--workspaces`` / changesets, or the ``--filter``ed
   ones), with the job's ``environment``. A ``--dry-run``, a commented or ``echo``ed
   line, or ``npm run publish:docs`` is not a publish. For a reusable workflow npm checks
   the *caller's* filename, which is the file found here.
2. **Report** (:func:`npm_trust`, the default): one row per (package, workflow,
   environment), saying whether the package is on npm or needs a first manual publish;
   a row whose name or environment cannot be resolved (``${{ ... }}``) or is unsafe to
   pass to npm says so and is never run.
3. **Apply** (``apply=True``): run ``npm trust github`` for each package that is on npm,
   continue past per-package failures, and verify with ``npm trust list``.

Everything that touches the world (``npm``, ``git``) goes through one injectable
``run`` callable, so the discovery and the plan are testable without a network.

>>> trust_command(Publisher("@x/a", "o/r", "release.yml", "npm"))
['npm', 'trust', 'github', '@x/a', '--file', 'release.yml', '--repo', 'o/r', '--env', 'npm', '--allow-publish', '-y']
"""

from __future__ import annotations

import fnmatch
import json
import posixpath
import re
import shlex
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence

import yaml

WORKFLOWS_DIR = ".github/workflows"
FORMATS = ("table", "tsv", "json")
#: Seconds one npm/git call may take (npm may wait on an OTP or a web login).
CALL_TIMEOUT = 60
#: What wads' reusable npm workflows publish when the caller passes no ``package-dir``.
WADS_REUSABLE_DEFAULT_DIR = {"npm-ci.yml": "js", "npm-ci-monorepo.yml": "."}
_WADS_REUSABLE_RE = re.compile(r"i2mint/wads/\.github/workflows/(npm-ci[\w-]*\.yml)")
_GITHUB_REMOTE_RE = re.compile(r"github\.com[:/]([^/\s]+)/([^/\s]+?)(?:\.git)?\s*$")
_SPLIT_RE = re.compile(r"\s*(?:&&|\|\||;|\|)\s*")
_NPM_NAME_RE = re.compile(r"^(@[a-z0-9~][a-z0-9._~-]*/)?[a-z0-9~][a-z0-9._~-]*$")
_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_WORKFLOW_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*\.ya?ml$")
_VALUE_FLAGS = {"--filter", "-F", "--dir", "-C", "--prefix", "--workspace", "-w"}
_FILTER_FLAGS = {"--filter", "-F", "--workspace", "-w"}
_DIR_FLAGS = {"--dir", "-C", "--prefix"}
_SHELL_KEYWORDS = {"if", "then", "else", "elif", "do", "while", "until", "!", "time"}
_RECURSIVE_FLAGS = {"-r", "--recursive", "--workspaces", "-ws"}
_MAX_SCRIPT_DEPTH = 5


@dataclass(frozen=True)
class Publisher:
    """One package that one workflow job publishes: what ``npm trust github`` needs.

    ``problem`` is set when the row cannot be acted on (unresolved expression, name
    npm would read as an option); such rows are reported, never run.
    """

    package: str
    repo: str
    workflow: str
    environment: str = ""
    problem: str = ""


@dataclass(frozen=True)
class Row:
    """A :class:`Publisher` plus what npm says about it (``on_npm`` None = unknown)."""

    publisher: Publisher
    on_npm: Optional[bool] = None
    trusted: Optional[bool] = None

    @property
    def status(self) -> str:
        if self.publisher.problem:
            return f"skipped ({self.publisher.problem})"
        if self.on_npm is None:
            return "unknown"
        if not self.on_npm:
            return "first-publish-needed"
        return "trusted" if self.trusted else "on-npm"

    @property
    def actionable(self) -> bool:
        """Whether ``--apply`` would run ``npm trust github`` for this row."""
        return not self.publisher.problem and self.on_npm is True and not self.trusted


@dataclass
class Outcome:
    """What :func:`apply_trust` did for one row."""

    row: Row
    action: str  # "attached" | "already-trusted" | "skipped" | "failed"
    detail: str = ""
    verified: Optional[bool] = None


Run = Callable[[Sequence[str]], "subprocess.CompletedProcess"]


def subprocess_run(argv: Sequence[str]) -> "subprocess.CompletedProcess":
    """The default ``run``: captured, no stdin, time-limited; a missing tool is rc 127."""
    try:
        return subprocess.run(
            list(argv),
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=CALL_TIMEOUT,
        )
    except FileNotFoundError:
        return subprocess.CompletedProcess(
            argv, 127, "", f"{argv[0]!r} not found on PATH"
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(
            argv, 124, "", f"timed out after {CALL_TIMEOUT}s"
        )


# --------------------------------------------------------------------------------------
# Reading publish commands


@dataclass(frozen=True)
class PublishCall:
    """One publish command: where it runs and which workspace members it covers."""

    directory: str = "."
    everything: bool = False  # -r / --workspaces / changesets: every workspace member
    filters: tuple = ()  # --filter / --workspace selectors


def _tokens(segment: str) -> list[str]:
    try:
        return shlex.split(segment)
    except ValueError:
        return segment.split()


def _npm_call(
    tokens: list[str], cwd: str, scripts: dict, depth: int
) -> list[PublishCall]:
    """``npm|pnpm|yarn [flags] <sub> ...``: a publish, or a script that may run one."""
    flags, positional, filters, index, where = set(), [], [], 1, cwd
    while index < len(tokens):
        token = tokens[index]
        name, _, inline = token.partition("=")
        if token.startswith("-"):
            flags.add(name)
            if name in _VALUE_FLAGS and not inline and index + 1 < len(tokens):
                index += 1
                inline = tokens[index]
            if name in _FILTER_FLAGS and inline:
                filters.append(inline)
            if name in _DIR_FLAGS and inline:
                where = posixpath.normpath(posixpath.join(cwd, inline))
        else:
            positional.append(token)
        index += 1
    if "--dry-run" in flags or not positional:
        return []
    sub = positional[0]
    if sub == "publish":
        target = positional[1] if len(positional) > 1 else ""
        if target and not target.endswith((".tgz", ".tar.gz")) and "/" in target:
            where = posixpath.normpath(
                posixpath.join(where, target)
            )  # `npm publish ./dir`
        return [PublishCall(where, bool(flags & _RECURSIVE_FLAGS), tuple(filters))]
    script = (
        positional[1] if sub in ("run", "run-script") and len(positional) > 1 else sub
    )
    if depth < _MAX_SCRIPT_DEPTH and isinstance(scripts.get(script), str):
        return publish_calls(scripts[script], scripts, directory=cwd, _depth=depth + 1)
    return []


def publish_calls(
    text: str, scripts: Optional[dict] = None, *, directory: str = ".", _depth: int = 0
) -> list[PublishCall]:
    """The publish commands in a shell script text, following ``cd`` and package scripts.

    >>> publish_calls("pnpm -r publish --access public")
    [PublishCall(directory='.', everything=True, filters=())]
    >>> publish_calls("cd packages/a && npm publish")[0].directory
    'packages/a'
    >>> publish_calls("npm publish --dry-run\\n# npm publish\\necho npm publish")
    []
    >>> publish_calls("pnpm release", {"release": "changeset publish"})[0].everything
    True
    """
    scripts = scripts or {}
    calls, cwd = [], directory
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        for segment in _SPLIT_RE.split(line):
            tokens = _tokens(segment)
            while tokens and (
                tokens[0] in _SHELL_KEYWORDS
                or re.fullmatch(r"[A-Za-z_]\w*=.*", tokens[0])
            ):
                tokens = tokens[1:]  # leading `if`/`then`/... and VAR=value assignments
            if tokens and tokens[0] in ("npx", "pnpx", "bunx"):
                tokens = tokens[1:]
            if not tokens:
                continue
            command = tokens[0]
            if command == "cd" and len(tokens) > 1:
                cwd = posixpath.normpath(posixpath.join(cwd, tokens[1]))
            elif command in ("changeset", "changesets") and tokens[1:2] == ["publish"]:
                if "--dry-run" not in tokens:
                    calls.append(PublishCall(cwd, everything=True))
            elif command in ("npm", "pnpm", "yarn"):
                calls += _npm_call(tokens, cwd, scripts, _depth)
    return calls


# --------------------------------------------------------------------------------------
# Packages


def _load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def workspace_globs(root: Path) -> list[str]:
    """The workspace patterns of the package at ``root`` (npm/yarn ``workspaces`` or pnpm)."""
    workspaces = _load_json(root / "package.json").get("workspaces")
    if isinstance(workspaces, dict):
        workspaces = workspaces.get("packages")
    patterns = list(workspaces) if isinstance(workspaces, list) else []
    pnpm = root / "pnpm-workspace.yaml"
    if pnpm.is_file():
        try:
            doc = yaml.safe_load(pnpm.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            doc = {}
        patterns += [p for p in (doc.get("packages") or []) if isinstance(p, str)]
    return patterns


def workspace_manifests(root: Path) -> list[dict]:
    """``package.json`` contents of ``root`` itself and its workspace members."""
    patterns = workspace_globs(root)
    skipped = {d for p in patterns if p.startswith("!") for d in root.glob(p[1:])}
    directories = [root]
    for pattern in (p for p in patterns if not p.startswith("!")):
        directories += sorted(
            d for d in root.glob(pattern) if d.is_dir() and d not in skipped
        )
    return [
        _load_json(d / "package.json")
        for d in directories
        if "node_modules" not in d.parts
    ]


def packages_of(root: Path, call: PublishCall) -> list[str]:
    """Names of the non-private packages ``call`` publishes from ``root``.

    >>> import tempfile
    >>> with tempfile.TemporaryDirectory() as d:
    ...     _ = Path(d, "package.json").write_text('{"name": "solo"}')
    ...     packages_of(Path(d), PublishCall())
    ['solo']
    """
    manifests = workspace_manifests(root)
    if call.filters:
        patterns = [f.removeprefix("...").removesuffix("...") for f in call.filters]
        chosen = [
            m
            for m in manifests
            if any(fnmatch.fnmatch(str(m.get("name")), p) for p in patterns)
        ]
    elif call.everything:
        chosen = manifests
    else:
        chosen = manifests[:1]
    names = []
    for manifest in chosen:
        name = manifest.get("name")
        if name and not manifest.get("private") and name not in names:
            names.append(name)
    return names


# --------------------------------------------------------------------------------------
# Discovery


def _environment(job: dict) -> str:
    environment = job.get("environment")
    if isinstance(environment, dict):
        environment = environment.get("name")
    return str(environment) if environment else ""


def job_calls(job: dict, scripts: dict) -> list[PublishCall]:
    """The publish calls of a workflow job: its ``run`` steps, changesets, a wads caller."""
    match = _WADS_REUSABLE_RE.search(str(job.get("uses", "")))
    if match:
        workflow = match.group(1)
        inputs = job.get("with") or {}
        directory = str(
            inputs.get("package-dir") or WADS_REUSABLE_DEFAULT_DIR.get(workflow, ".")
        )
        return [PublishCall(directory, everything="monorepo" in workflow)]
    defaults = (job.get("defaults") or {}).get("run") or {}
    calls = []
    for step in job.get("steps") or []:
        directory = str(
            step.get("working-directory") or defaults.get("working-directory") or "."
        )
        if step.get("run"):
            calls += publish_calls(str(step["run"]), scripts, directory=directory)
        elif str(step.get("uses", "")).startswith("changesets/action"):
            command = (step.get("with") or {}).get("publish")
            if command:
                calls += publish_calls(str(command), scripts, directory=directory)
    return calls


def check_publisher(publisher: Publisher) -> Publisher:
    """``publisher`` with ``problem`` set if it must not be passed to ``npm trust``."""
    fields = {
        "package": (publisher.package, _NPM_NAME_RE),
        "workflow": (publisher.workflow, _WORKFLOW_RE),
    }
    for label, (value, pattern) in fields.items():
        if "${{" in value:
            problem = f"unresolved {label}"
        elif not pattern.match(value):
            problem = f"unsafe {label} name"
        else:
            continue
        return Publisher(**{**asdict(publisher), "problem": problem})
    if not _REPO_RE.match(publisher.repo):
        return Publisher(
            **{
                **asdict(publisher),
                "problem": "unknown GitHub repo (pass --github-repo)",
            }
        )
    environment = publisher.environment
    if "${{" in environment or environment.startswith("-"):
        problem = (
            "unresolved environment" if "${{" in environment else "unsafe environment"
        )
        return Publisher(**{**asdict(publisher), "problem": problem})
    return publisher


def discover(
    repo_dir=".", *, repo: Optional[str] = None, run: Run = subprocess_run
) -> list[Publisher]:
    """Every (package, workflow, environment) the repo's workflows publish to npm.

    ``repo`` is the ``owner/name`` slug; ``None`` reads it from the ``origin`` remote
    (see :func:`github_slug`), falling back to ``'?/?'``.
    """
    root = Path(repo_dir)
    slug = repo or github_slug(root, run=run) or "?/?"
    scripts = _load_json(root / "package.json").get("scripts") or {}
    found: dict[tuple, Publisher] = {}
    workflows = sorted(
        [*(root / WORKFLOWS_DIR).glob("*.yml"), *(root / WORKFLOWS_DIR).glob("*.yaml")]
    )
    for workflow in workflows:
        try:
            doc = yaml.safe_load(workflow.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            continue
        for job in (doc.get("jobs") or {}).values():
            if not isinstance(job, dict):
                continue
            for call in job_calls(job, scripts):
                if "${{" in call.directory:
                    names = [f"<{call.directory}>"]
                else:
                    names = packages_of(root / call.directory, call)
                for name in names:
                    publisher = check_publisher(
                        Publisher(name, slug, workflow.name, _environment(job))
                    )
                    key = (publisher.package, publisher.workflow, publisher.environment)
                    found.setdefault(key, publisher)
    return list(found.values())


def github_slug(repo_dir=".", *, run: Run = subprocess_run) -> Optional[str]:
    """``owner/name`` of the ``origin`` remote of ``repo_dir``, if it is a GitHub one.

    >>> fake = lambda argv: subprocess.CompletedProcess(argv, 0, "git@github.com:i2mint/wads.git\\n", "")
    >>> github_slug(".", run=fake)
    'i2mint/wads'
    """
    result = run(["git", "-C", str(repo_dir), "remote", "get-url", "origin"])
    match = (
        _GITHUB_REMOTE_RE.search(result.stdout or "")
        if result.returncode == 0
        else None
    )
    return f"{match.group(1)}/{match.group(2)}" if match else None


# --------------------------------------------------------------------------------------
# What npm knows


def is_on_npm(package: str, *, run: Run = subprocess_run) -> Optional[bool]:
    """Whether ``package`` is published (``None``: could not tell, e.g. offline)."""
    result = run(["npm", "view", package, "version"])
    if result.returncode == 0:
        return True
    return False if "E404" in (result.stderr or "") + (result.stdout or "") else None


def trust_listing(package: str, *, run: Run = subprocess_run) -> Optional[str]:
    """The text of ``npm trust list <package>``, or ``None`` when it cannot be read."""
    result = run(["npm", "trust", "list", package])
    return result.stdout if result.returncode == 0 else None


_TOKEN_SPLIT = re.compile(r"""[\s,"'\[\]{}:=()]+""")


def _listing_entries(listing: str) -> list[set]:
    """One set of exact tokens per entry of an ``npm trust list`` text (JSON or lines)."""

    def strings(value) -> set:
        if isinstance(value, dict):
            return set().union(*map(strings, value.values())) if value else set()
        if isinstance(value, list):
            return set().union(*map(strings, value)) if value else set()
        return {value} if isinstance(value, str) else set()

    try:
        data = json.loads(listing)
    except ValueError:
        return [
            set(_TOKEN_SPLIT.split(line))
            for line in listing.splitlines()
            if line.strip()
        ]
    entries = (
        data
        if isinstance(data, list)
        else next((v for v in data.values() if isinstance(v, list)), [data])
        if isinstance(data, dict)
        else [data]
    )
    return [strings(entry) for entry in entries]


def has_trust(listing: Optional[str], publisher: Publisher) -> bool:
    """Whether an ``npm trust list`` text has an entry naming exactly this repo and workflow.

    Whole tokens only, so ``o/rr`` or ``release.yml.bak`` never stand in for ``o/r`` or
    ``release.yml``.

    >>> p = Publisher("pkg", "o/r", "release.yml")
    >>> has_trust("github  o/r  release.yml", p)
    True
    >>> has_trust("github  o/rr  release.yml.bak", p)
    False
    """
    if not listing:
        return False
    return any(
        publisher.repo in entry
        and publisher.workflow in entry
        and (not publisher.environment or publisher.environment in entry)
        for entry in _listing_entries(listing)
    )


def survey(
    publishers: Sequence[Publisher],
    *,
    run: Run = subprocess_run,
    check_npm: bool = True,
) -> list[Row]:
    """:class:`Row` per publisher, asking npm once per package unless ``check_npm=False``."""
    if not check_npm:
        return [Row(p) for p in publishers]
    askable = {p.package for p in publishers if not p.problem}
    on_npm = {name: is_on_npm(name, run=run) for name in askable}
    listings = {name: trust_listing(name, run=run) for name in askable if on_npm[name]}
    return [
        Row(
            p,
            on_npm.get(p.package),
            has_trust(listings.get(p.package), p) if on_npm.get(p.package) else None,
        )
        for p in publishers
    ]


# --------------------------------------------------------------------------------------
# Attaching


def trust_command(publisher: Publisher) -> list[str]:
    """The ``npm trust github`` call that attaches this publisher."""
    argv = [
        "npm",
        "trust",
        "github",
        publisher.package,
        "--file",
        publisher.workflow,
        "--repo",
        publisher.repo,
    ]
    if publisher.environment:
        argv += ["--env", publisher.environment]
    return argv + ["--allow-publish", "-y"]


def apply_trust(rows: Sequence[Row], *, run: Run = subprocess_run) -> list[Outcome]:
    """Attach each row's publisher; a failure on one package never stops the others.

    Rows with a problem, not on npm, or of unknown state are skipped with the reason,
    rows that already carry the trust are left alone, and a successful attach is
    verified with ``npm trust list``.
    """
    outcomes = []
    for row in rows:
        publisher = row.publisher
        if publisher.problem:
            outcomes.append(Outcome(row, "skipped", publisher.problem))
        elif row.on_npm is not True:
            reason = (
                "not on npm: publish the first version by hand"
                if row.on_npm is False
                else "npm state unknown"
            )
            outcomes.append(Outcome(row, "skipped", reason))
        elif row.trusted:
            outcomes.append(Outcome(row, "already-trusted"))
        else:
            result = run(trust_command(publisher))
            if result.returncode != 0:
                detail = (
                    (result.stderr or result.stdout or "").strip().splitlines() or [""]
                )[-1]
                outcomes.append(Outcome(row, "failed", detail))
                continue
            verified = has_trust(trust_listing(publisher.package, run=run), publisher)
            outcomes.append(Outcome(row, "attached", verified=verified))
    return outcomes


def preflight(*, run: Run = subprocess_run) -> list[str]:
    """Problems that would make every attach fail: no npm, not logged in."""
    result = run(["npm", "whoami"])
    if result.returncode == 127:
        return ["npm is not on PATH (needs npm >= 11.15)"]
    if result.returncode != 0:
        return ["not logged in to npm: run `npm login` as the package owner (2FA)"]
    return []


# --------------------------------------------------------------------------------------
# Rendering and the command


_COLUMNS = ("package", "repo", "workflow", "environment", "status")


def row_fields(row: Row) -> tuple:
    p = row.publisher
    return (p.package, p.repo, p.workflow, p.environment or "-", row.status)


def render_rows(rows: Sequence[Row], fmt: str = "table") -> str:
    """Rows as an aligned ``table``, ``tsv`` (the fleet rollout's format) or ``json``."""
    if fmt not in FORMATS:
        raise ValueError(f"fmt must be one of {FORMATS}, got {fmt!r}")
    if fmt == "json":
        return json.dumps(
            [{**asdict(r.publisher), "status": r.status} for r in rows], indent=2
        )
    table = [_COLUMNS, *(row_fields(r) for r in rows)]
    if fmt == "tsv":
        return "\n".join("\t".join(line) for line in table)
    widths = [max(len(line[i]) for line in table) for i in range(len(_COLUMNS))]
    return "\n".join(
        "  ".join(cell.ljust(width) for cell, width in zip(line, widths)).rstrip()
        for line in table
    )


def run_npm_trust(
    repo: str = ".",
    *,
    apply: bool = False,
    dry_run: bool = False,
    github_repo: Optional[str] = None,
    offline: bool = False,
    fmt: str = "table",
    run: Run = subprocess_run,
    out: Callable[[str], None] = print,
):
    """:func:`npm_trust` with injectable ``run`` (npm/git) and ``out`` (printing)."""
    if apply and dry_run:
        raise SystemExit("--apply and --dry-run contradict each other")
    if fmt not in FORMATS:
        raise SystemExit(f"--fmt must be one of {FORMATS}, got {fmt!r}")
    publishers = discover(repo, repo=github_repo, run=run)
    if not publishers:
        out(f"No npm publishing workflow found under {Path(repo) / WORKFLOWS_DIR}")
        return None
    rows = survey(publishers, run=run, check_npm=not offline)
    out(render_rows(rows, fmt))
    if not apply:
        todo = [
            r for r in rows if r.actionable or (offline and not r.publisher.problem)
        ]
        out(f"\nWould run for {len(todo)} of {len(rows)} (use --apply to run):")
        out("\n".join("  " + " ".join(trust_command(r.publisher)) for r in todo))
        return None
    problems = preflight(run=run)
    if problems:
        raise SystemExit("; ".join(problems))
    failed = False
    for outcome in apply_trust(rows, run=run):
        failed |= outcome.action == "failed" or outcome.verified is False
        verified = {True: " (verified)", False: " (NOT verified)", None: ""}[
            outcome.verified
        ]
        out(
            f"{outcome.row.publisher.package}: {outcome.action}{verified} {outcome.detail}".rstrip()
        )
    if failed:
        raise SystemExit(1)
    return None


def npm_trust(
    repo: str = ".",
    *,
    apply: bool = False,
    dry_run: bool = False,
    github_repo: Optional[str] = None,
    offline: bool = False,
    fmt: str = "table",
):
    """Find the npm packages ``repo`` publishes and attach Trusted Publishers (dry run by default).

    Prints one row per (package, workflow, environment) with whether the package is on npm
    or needs a first manual publish, and the ``npm trust github`` call for each package
    ``--apply`` would act on. Nothing changes unless ``--apply`` (``--dry-run`` is the
    explicit spelling of the default): then each package that is on npm gets its Trusted
    Publisher (needs npm >= 11.15 and an owner login with 2FA), failures are reported per
    package, and every attach is verified with ``npm trust list``. ``--offline`` skips the
    npm lookups; ``--github-repo owner/name`` overrides the origin remote.
    """
    return run_npm_trust(
        repo,
        apply=apply,
        dry_run=dry_run,
        github_repo=github_repo,
        offline=offline,
        fmt=fmt,
    )
