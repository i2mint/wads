#!/usr/bin/env python3
"""Pin a repo's references to its own actions to the release tag, in the tagged commit.

A repo that hosts reusable workflows or actions (wads itself) refers to them as
``uses: <owner>/<repo>/...@<default branch>``. A caller that pins the workflow to a
release tag (``uv-ci.yml@0.2.15``) then still runs every action at the branch tip, so
the pin freezes the job graph but not the code (issue #170). ``uses:`` must be a
literal, so the fix is in the tag: the publish job tags a commit whose workflow and
action files say ``@<version>`` instead of ``@<default branch>``. That commit sits on
top of the built bump commit and is reachable only through the tag; the branch keeps
floating refs. A repo with no such self-references tags the built commit unchanged.

References to other repos (``i2mint/isee/...@master``) and ``uvx --from <package>``
installs are not rewritten: they are outside this repo's release.

Run from the action's checkout, stdlib only::

    python3 -I pin_self_refs.py --repo OWNER/REPO --branch master --version 1.2.3 \\
        --ref <commit> [--message MSG]

prints ``commit-sha=<sha>`` to ``$GITHUB_OUTPUT`` (or stdout): the pinned commit, or
``--ref`` itself when nothing referred to the branch.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

#: Files, relative to the repo root, whose ``uses:`` lines may name this repo.
SELF_REF_GLOBS = (
    ".github/workflows/*.yml",
    ".github/workflows/*.yaml",
    "actions/*/action.yml",
    "actions/*/action.yaml",
)
DFLT_MESSAGE = "Pin this repo's own action refs to {version} for the release tag"


def pin_self_refs(text: str, *, repo: str, branch: str, version: str) -> str:
    """``text`` with every ``uses: <repo>/...@<branch>`` pinned to ``@<version>``.

    The repo match ignores case (GitHub does); other repos, other refs and a ref that
    only starts with ``branch`` (``@master-old``) are left alone.

    >>> pin_self_refs(
    ...     "  uses: i2mint/wads/actions/x@master\\n"
    ...     "  uses: I2mint/Wads/.github/workflows/uv-ci.yml@master  # floats\\n"
    ...     "  uses: i2mint/isee/actions/bump@master\\n"
    ...     "  uses: i2mint/wads/actions/y@master-old\\n",
    ...     repo="i2mint/wads", branch="master", version="1.2.3",
    ... ).splitlines()  # doctest: +NORMALIZE_WHITESPACE
    ['  uses: i2mint/wads/actions/x@1.2.3',
     '  uses: I2mint/Wads/.github/workflows/uv-ci.yml@1.2.3  # floats',
     '  uses: i2mint/isee/actions/bump@master',
     '  uses: i2mint/wads/actions/y@master-old']
    """
    pattern = re.compile(
        rf"(\buses:\s*['\"]?{re.escape(repo)}/[^@\s'\"]+@){re.escape(branch)}"
        r"(?=['\"]?(\s|$))",
        re.IGNORECASE,
    )
    return pattern.sub(lambda m: m.group(1) + version, text)


def _git(*args: str, cwd) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def pinned_release_commit(
    *, repo: str, branch: str, version: str, ref: str, message: str, cwd="."
) -> str:
    """The commit to tag: ``ref`` itself, or a child of it with self-refs pinned.

    Works in a throwaway worktree, so the caller's checkout, index and branch are not
    touched; the new commit is reachable only once something (the tag) points at it.
    """
    with tempfile.TemporaryDirectory(prefix="wads-pin-") as tmp:
        tree = Path(tmp, "tree")
        _git("worktree", "add", "--detach", "--quiet", str(tree), ref, cwd=cwd)
        try:
            changed = []
            for pattern in SELF_REF_GLOBS:
                for path in sorted(tree.glob(pattern)):
                    text = path.read_text(encoding="utf-8")
                    pinned = pin_self_refs(
                        text, repo=repo, branch=branch, version=version
                    )
                    if pinned != text:
                        path.write_text(pinned, encoding="utf-8")
                        changed.append(str(path.relative_to(tree)))
            if not changed:
                return _git("rev-parse", ref, cwd=cwd)
            _git("add", "--", *changed, cwd=tree)
            _git("commit", "--quiet", "-m", message, cwd=tree)
            return _git("rev-parse", "HEAD", cwd=tree)
        finally:
            _git("worktree", "remove", "--force", str(tree), cwd=cwd)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", required=True, help="OWNER/REPO of this repository")
    parser.add_argument("--branch", required=True, help="the floating ref to replace")
    parser.add_argument("--version", required=True, help="the release tag")
    parser.add_argument("--ref", default="HEAD", help="the built commit to start from")
    parser.add_argument("--message", default=None, help="commit message")
    args = parser.parse_args(argv)
    message = args.message or DFLT_MESSAGE.format(version=args.version)
    sha = pinned_release_commit(
        repo=args.repo,
        branch=args.branch,
        version=args.version,
        ref=args.ref or "HEAD",
        message=message,
    )
    line = f"commit-sha={sha}\n"
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as f:
            f.write(line)
    sys.stdout.write(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
