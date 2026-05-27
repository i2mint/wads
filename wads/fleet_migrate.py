"""Batch migration helpers across the user's local Python ecosystem.

Single entry point: ``fleet_stub`` (also exposed as ``wads-migrate fleet-stub``)
which converts a batch of repos to the SSOT stub CI workflow in one call.

Reads the candidate list from the wads-ci-sweep state file
(``~/Downloads/wads_ci_diagnosis.json``), selects by category, orders by
last-commit recency, and applies ``migrate_ci_to_stub`` to each. Per-repo
failures are isolated — the batch never aborts midway.

See: wads-ci-sweep skill at ``~/.claude/skills/wads-ci-sweep/`` for the
ecosystem inventory + state-tracking it relies on.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Optional

from wads.migration import migrate_ci_to_stub


DEFAULT_STATE_FILE = Path.home() / "Downloads" / "wads_ci_diagnosis.json"
DEFAULT_COMMIT_MESSAGE = "ci: switch to wads reusable workflow stub"


@dataclass
class RepoResult:
    """Outcome of attempting to stub-migrate one repo."""

    name: str
    path: str
    status: str  # one of: ok, noop, skip, fail
    detail: str = ""

    def __str__(self) -> str:
        if self.detail:
            return f"{self.name:18s}  {self.status:5s}  {self.detail}"
        return f"{self.name:18s}  {self.status}"


def read_sweep_state(path: Path | str = DEFAULT_STATE_FILE) -> dict:
    """Load the wads-ci-sweep state file.

    Raises:
        FileNotFoundError: if the state file does not exist (the caller likely
            needs to run ``python ~/.claude/skills/wads-ci-sweep/sweep.py
            diagnose`` to create it).
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(
            f"Sweep state file not found at {p}. Run "
            f"`python ~/.claude/skills/wads-ci-sweep/sweep.py diagnose` first."
        )
    return json.loads(p.read_text())


def _git_last_commit_ts(repo_path: str) -> Optional[int]:
    """Return the unix-ts of the repo's current-branch HEAD commit, or None."""
    try:
        r = subprocess.run(
            ["git", "-C", repo_path, "log", "-1", "--format=%ct"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            return int(r.stdout.strip())
    except (subprocess.TimeoutExpired, ValueError):
        pass
    return None


def select_candidates(
    state: dict,
    *,
    category: str = "uv_current",
    limit: int = 20,
    order_by: str = "git_recency",
) -> list[dict]:
    """Pick which packages to migrate, in priority order.

    Args:
        state: Sweep state dict (from :func:`read_sweep_state`).
        category: Only consider packages with this ``category``. Default
            ``"uv_current"`` — repos already on inline uv-CI that can safely
            move to the stub. Other useful values: ``"uv_stub"`` (already
            done; useful for refresh sweeps after a stub-template change).
        limit: Max number of repos to return.
        order_by: ``"git_recency"`` (default) sorts most-recently-committed
            first. ``"name"`` sorts alphabetically.

    Returns:
        List of package records (subset of ``state['packages']``), in the
        chosen order.
    """
    candidates = [p for p in state.get("packages", []) if p.get("category") == category]
    if order_by == "git_recency":
        candidates.sort(
            key=lambda p: _git_last_commit_ts(p["path"]) or 0,
            reverse=True,
        )
    elif order_by == "name":
        candidates.sort(key=lambda p: p["name"])
    else:
        raise ValueError(f"Unknown order_by: {order_by!r}")
    return candidates[:limit]


def _sync_default_branch(repo_path: str) -> Optional[str]:
    """Switch to and fast-forward the repo's default branch. Returns its name
    on success, ``None`` on failure (caller should mark the repo as ``fail``).
    """
    # Determine default branch from origin/HEAD.
    r = subprocess.run(
        ["git", "-C", repo_path, "symbolic-ref", "refs/remotes/origin/HEAD"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if r.returncode != 0:
        return None
    default = r.stdout.strip().rsplit("/", 1)[-1]
    if not default:
        return None

    # Checkout if not already there.
    current = subprocess.run(
        ["git", "-C", repo_path, "branch", "--show-current"],
        capture_output=True,
        text=True,
        timeout=5,
    ).stdout.strip()
    if current != default:
        co = subprocess.run(
            ["git", "-C", repo_path, "checkout", default, "--quiet"],
            capture_output=True,
            timeout=10,
        )
        if co.returncode != 0:
            return None

    # Fetch + ff-only; fall back to rebase if divergent.
    if (
        subprocess.run(
            ["git", "-C", repo_path, "fetch", "--quiet"], timeout=30
        ).returncode
        != 0
    ):
        return None
    ffm = subprocess.run(
        ["git", "-C", repo_path, "merge", "--ff-only", "@{u}"],
        capture_output=True,
        timeout=10,
    )
    if ffm.returncode != 0:
        # Diverged — try rebase.
        rb = subprocess.run(
            ["git", "-C", repo_path, "pull", "--rebase", "--quiet"],
            capture_output=True,
            timeout=30,
        )
        if rb.returncode != 0:
            return None
    return default


def _has_tracked_changes(repo_path: str) -> bool:
    """True if there are uncommitted, tracked changes. Untracked files don't count."""
    return any(
        subprocess.run(
            ["git", "-C", repo_path] + cmd, capture_output=True, timeout=5
        ).stdout
        for cmd in (
            ["diff", "--name-only"],
            ["diff", "--cached", "--name-only"],
        )
    )


def migrate_one_to_stub(
    repo_path: str,
    *,
    pin: str = "@master",
    commit_message: str = DEFAULT_COMMIT_MESSAGE,
    workflow_path: str = ".github/workflows/ci.yml",
) -> RepoResult:
    """Stub-migrate one repo end-to-end: sync, rewrite, commit, push.

    Idempotent: if the workflow is already on the latest stub template, returns
    ``status="noop"``.
    """
    name = os.path.basename(repo_path.rstrip("/"))
    if not Path(repo_path, ".git").is_dir():
        return RepoResult(name, repo_path, "skip", "not a git repo")

    # Check tracked-changes BEFORE attempting sync — `git pull --rebase`
    # refuses to run with a dirty working tree, and previously surfaced as
    # the less-informative "could not sync default branch".
    if _has_tracked_changes(repo_path):
        return RepoResult(name, repo_path, "skip", "uncommitted tracked changes")

    default_branch = _sync_default_branch(repo_path)
    if default_branch is None:
        return RepoResult(name, repo_path, "fail", "could not sync default branch")

    ci_path = Path(repo_path) / workflow_path
    if not ci_path.exists():
        return RepoResult(name, repo_path, "skip", f"no {workflow_path}")

    try:
        new_content = migrate_ci_to_stub(str(ci_path), pin=pin)
    except Exception as e:
        return RepoResult(name, repo_path, "fail", f"ci-to-stub: {e}")

    if ci_path.read_text() == new_content:
        return RepoResult(name, repo_path, "noop", "already on this stub")
    ci_path.write_text(new_content)

    for cmd, label in (
        (["git", "-C", repo_path, "add", workflow_path], "git add"),
        (
            ["git", "-C", repo_path, "commit", "-m", commit_message, "--quiet"],
            "git commit",
        ),
        (
            ["git", "-C", repo_path, "push", "--quiet", "origin", default_branch],
            "git push",
        ),
    ):
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            return RepoResult(
                name, repo_path, "fail", f"{label}: {r.stderr.strip()[:80]}"
            )

    return RepoResult(name, repo_path, "ok", f"pushed to {default_branch}")


def fleet_stub(
    *,
    limit: int = 20,
    select_category: str = "uv_current",
    state_file: Path | str = DEFAULT_STATE_FILE,
    dry_run: bool = False,
    pin: str = "@master",
    commit_message: str = DEFAULT_COMMIT_MESSAGE,
    order_by: str = "git_recency",
) -> list[RepoResult]:
    """Stub-migrate up to ``limit`` repos, picked from the sweep state file.

    Args:
        limit: Max repos to migrate this run.
        select_category: Only consider packages with this ``category`` in the
            sweep state file (default ``"uv_current"``).
        state_file: Path to the wads-ci-sweep JSON. Default
            ``~/Downloads/wads_ci_diagnosis.json``.
        dry_run: If True, print candidates and exit without touching anything.
        pin: Wads ref the stub points at (passed to ``migrate_ci_to_stub``).
        commit_message: Commit message for the per-repo stub-conversion commit.
        order_by: Candidate ordering — ``"git_recency"`` or ``"name"``.

    Returns:
        List of :class:`RepoResult`, one per attempted repo (empty for dry-run).
    """
    state = read_sweep_state(state_file)
    candidates = select_candidates(
        state, category=select_category, limit=limit, order_by=order_by
    )

    if not candidates:
        print(f"No candidates in category={select_category!r}.")
        return []

    print(
        f"=== {len(candidates)} candidates (category={select_category}, order={order_by}) ==="
    )
    for p in candidates:
        print(f"  {p['name']:18s}  {p['path']}")
    print()
    if dry_run:
        print("(dry-run; no changes made)")
        return []

    results: list[RepoResult] = []
    for p in candidates:
        result = migrate_one_to_stub(p["path"], pin=pin, commit_message=commit_message)
        results.append(result)
        print(result)

    print()
    summary = _summarize(results)
    print(f"=== summary: {summary} ===")
    print(
        "Hint: run `python ~/.claude/skills/wads-ci-sweep/sweep.py diagnose --no-refresh` "
        "to refresh the sweep state."
    )
    return results


def _summarize(results: Iterable[RepoResult]) -> str:
    counts: dict[str, int] = {}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
    return "  ".join(f"{s}={n}" for s, n in sorted(counts.items()))
