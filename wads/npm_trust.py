"""``wads npm-trust``: find a repo's npm publishers and attach Trusted Publishers.

npm trusted publishing (OIDC, see the ``npm-publishing`` skill) needs, per package,
one ``npm trust github <pkg> --file <caller workflow> --repo <owner>/<repo> [--env E]
--allow-publish -y`` (npm >= 11.15, an owner login with 2FA) and the package must already
exist on npm. Doing that by hand across a fleet means finding, for every package, the
workflow that publishes it. This module does the finding, reports it, and optionally
runs the commands:

1. **Discover** (:func:`discover`): the workflows under ``.github/workflows`` that publish
   (``npm publish``, ``pnpm publish``, ``pnpm -r publish``, ``changeset publish``,
   ``changesets/action``, a script such as ``pnpm release`` that runs one of those, or a
   caller of a wads ``npm-ci*.yml`` reusable workflow), and the non-private packages each
   publishes (a single package or a ``workspaces`` / ``pnpm-workspace.yaml`` monorepo),
   with the job's ``environment``. For a reusable workflow npm checks the *caller's*
   filename, which is the file found here.
2. **Report** (:func:`npm_trust`, the default): one row per (package, workflow,
   environment), saying whether the package is on npm or needs a first manual publish.
3. **Apply** (``apply=True``): run ``npm trust github`` for each package that is on npm,
   continue past per-package failures, and verify with ``npm trust list``.

Everything that touches the world (``npm``, ``git``) goes through one injectable
``run`` callable, so the discovery and the plan are testable without a network.

>>> trust_command(Publisher("@x/a", "o/r", "release.yml", "npm"))
['npm', 'trust', 'github', '@x/a', '--file', 'release.yml', '--repo', 'o/r', '--env', 'npm', '--allow-publish', '-y']
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Optional, Sequence

import yaml

WORKFLOWS_DIR = ".github/workflows"
FORMATS = ("table", "tsv", "json")
#: A shell line that publishes to npm (npm/pnpm/yarn ... publish, changeset publish).
_PUBLISH_RE = re.compile(
    r"\b(?:(?:npm|pnpm|yarn)\b[^\n;&|]*?\bpublish\b|changesets?\s+publish\b)"
)
#: ``pnpm release`` / ``npm run release``: a script name, resolved against package.json.
_SCRIPT_RE = re.compile(r"\b(?:npm|pnpm|yarn)\s+(?:run\s+)?([\w:.-]+)")
#: wads' own reusable npm workflows; a job calling one publishes its ``package-dir``.
_WADS_REUSABLE_RE = re.compile(r"i2mint/wads/\.github/workflows/npm-ci[\w-]*\.yml")
_GITHUB_REMOTE_RE = re.compile(r"github\.com[:/]([^/\s]+)/([^/\s]+?)(?:\.git)?\s*$")


@dataclass(frozen=True)
class Publisher:
    """One package that one workflow job publishes: what ``npm trust github`` needs."""

    package: str
    repo: str
    workflow: str
    environment: str = ""


@dataclass(frozen=True)
class Row:
    """A :class:`Publisher` plus what npm says about it (``on_npm`` None = unknown)."""

    publisher: Publisher
    on_npm: Optional[bool] = None
    trusted: Optional[bool] = None

    @property
    def status(self) -> str:
        if self.on_npm is None:
            return "unknown"
        if not self.on_npm:
            return "first-publish-needed"
        return "trusted" if self.trusted else "on-npm"


@dataclass
class Outcome:
    """What :func:`apply_trust` did for one row."""

    row: Row
    action: str  # "attached" | "already-trusted" | "skipped" | "failed"
    detail: str = ""
    verified: Optional[bool] = None


Run = Callable[[Sequence[str]], "subprocess.CompletedProcess"]


def subprocess_run(argv: Sequence[str]) -> "subprocess.CompletedProcess":
    """The default ``run``: a captured subprocess that reports a missing tool as rc 127."""
    try:
        return subprocess.run(list(argv), capture_output=True, text=True)
    except FileNotFoundError:
        return subprocess.CompletedProcess(
            argv, 127, "", f"{argv[0]!r} not found on PATH"
        )


# --------------------------------------------------------------------------------------
# Discovery


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


def publishable_packages(root: Path) -> list[str]:
    """Names of the non-private packages at ``root``: itself and its workspace members.

    >>> import tempfile
    >>> with tempfile.TemporaryDirectory() as d:
    ...     _ = Path(d, "package.json").write_text('{"name": "solo"}')
    ...     publishable_packages(Path(d))
    ['solo']
    """
    candidates = [root]
    include = [p for p in workspace_globs(root) if not p.startswith("!")]
    exclude = [p[1:] for p in workspace_globs(root) if p.startswith("!")]
    skipped = {d for pattern in exclude for d in root.glob(pattern)}
    for pattern in include:
        candidates += sorted(
            d for d in root.glob(pattern) if d.is_dir() and d not in skipped
        )
    names, seen = [], set()
    for directory in candidates:
        if "node_modules" in directory.parts:
            continue
        manifest = _load_json(directory / "package.json")
        name = manifest.get("name")
        if name and not manifest.get("private") and name not in seen:
            seen.add(name)
            names.append(name)
    return names


def _run_texts(job: dict, scripts: dict) -> Iterable[str]:
    """The shell text a job runs, with ``pnpm <script>`` calls expanded via ``scripts``."""
    texts = [str(step["run"]) for step in job.get("steps") or [] if step.get("run")]
    for step in job.get("steps") or []:
        if str(step.get("uses", "")).startswith("changesets/action"):
            texts.append(
                f"changesets publish {(step.get('with') or {}).get('publish', '')}"
            )
    for text in list(texts):
        for name in _SCRIPT_RE.findall(text):
            if isinstance(scripts.get(name), str):
                texts.append(scripts[name])
    return texts


def _environment(job: dict) -> str:
    environment = job.get("environment")
    if isinstance(environment, dict):
        environment = environment.get("name")
    return str(environment) if environment else ""


def _job_directory(job: dict) -> str:
    """The directory a job publishes from: wads' ``package-dir``, or a ``working-directory``."""
    inputs = job.get("with") or {}
    if inputs.get("package-dir"):
        return str(inputs["package-dir"])
    defaults = (job.get("defaults") or {}).get("run") or {}
    directories = [defaults.get("working-directory")] + [
        step.get("working-directory")
        for step in job.get("steps") or []
        if step.get("run") and _PUBLISH_RE.search(str(step["run"]))
    ]
    return next((str(d) for d in directories if d), ".")


def job_publishes(job: dict, scripts: dict) -> bool:
    """Whether a workflow job publishes to npm (directly, via a script, or a wads caller)."""
    if _WADS_REUSABLE_RE.search(str(job.get("uses", ""))):
        return True
    return any(_PUBLISH_RE.search(text) for text in _run_texts(job, scripts))


def discover(repo_dir=".", *, repo: Optional[str] = None) -> list[Publisher]:
    """Every (package, workflow, environment) the repo's workflows publish to npm.

    ``repo`` is the ``owner/name`` slug; ``None`` reads it from the ``origin`` remote
    (see :func:`github_slug`), falling back to ``'?/?'``.
    """
    root = Path(repo_dir)
    slug = repo or github_slug(root) or "?/?"
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
            if not isinstance(job, dict) or not job_publishes(job, scripts):
                continue
            directory = root / _job_directory(job)
            for name in publishable_packages(directory):
                publisher = Publisher(name, slug, workflow.name, _environment(job))
                found.setdefault(
                    (publisher.package, publisher.workflow, publisher.environment),
                    publisher,
                )
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


def has_trust(listing: Optional[str], publisher: Publisher) -> bool:
    """Whether an ``npm trust list`` text already names this repo and workflow file."""
    return bool(listing) and publisher.repo in listing and publisher.workflow in listing


def survey(
    publishers: Sequence[Publisher],
    *,
    run: Run = subprocess_run,
    check_npm: bool = True,
) -> list[Row]:
    """:class:`Row` per publisher, asking npm (once per package) unless ``check_npm=False``."""
    if not check_npm:
        return [Row(p) for p in publishers]
    on_npm = {p.package: is_on_npm(p.package, run=run) for p in publishers}
    return [
        Row(
            p,
            on_npm[p.package],
            has_trust(trust_listing(p.package, run=run), p)
            if on_npm[p.package]
            else None,
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

    Rows not on npm (or whose state is unknown) are skipped with the reason, rows that
    already carry the trust are left alone, and a successful attach is verified with
    ``npm trust list``.
    """
    outcomes = []
    for row in rows:
        publisher = row.publisher
        if row.on_npm is not True:
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
    publishers = discover(repo, repo=github_repo)
    if not publishers:
        out(f"No npm publishing workflow found under {Path(repo) / WORKFLOWS_DIR}")
        return None
    rows = survey(publishers, run=run, check_npm=not offline)
    out(render_rows(rows, fmt))
    if not apply:
        out("\nWould run (use --apply to run):")
        out("\n".join("  " + " ".join(trust_command(r.publisher)) for r in rows))
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
    or needs a first manual publish, and the ``npm trust github`` call for each. Nothing
    changes unless ``--apply``: then each package that is on npm gets its Trusted
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
