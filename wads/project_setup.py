"""Project setup utilities: name checking, GitHub operations, and orchestration.

This module provides the building blocks for AI-assisted project creation.
Each function is independently useful — they can be called from Python, CLI, or
a Claude skill.

Key capabilities:
- Check package name availability on PyPI and GitHub
- Manage name candidate files (pools of potential names)
- Create GitHub repositories via the gh CLI
- Orchestrate full project creation (repo → populate → commit/push)
"""

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Iterable

from wads.pack import http_get_json, validate_package_name, PYPI_PACKAGE_JSON_URL
from wads.user_dirs import (
    name_candidates_dir,
    read_user_preferences,
    write_user_preferences,
)


# ---------------------------------------------------------------------------
# Name availability checking
# ---------------------------------------------------------------------------

PYPI_PROJECT_URL = "https://pypi.org/project/{name}/"
GITHUB_REPO_URL = "https://github.com/{org}/{name}"


def is_available_on_pypi(name: str) -> bool:
    """Check if a package name is unclaimed on PyPI.

    Returns True if the name is available (no package exists with that name).

    >>> is_available_on_pypi("wads")  # doctest: +SKIP
    False
    >>> is_available_on_pypi("zzz_nonexistent_pkg_12345")  # doctest: +SKIP
    True
    """
    url = PYPI_PACKAGE_JSON_URL.format(package=name)
    try:
        result = http_get_json(url)
        # urllib path returns None on HTTPError (404) → available
        return result is None
    except ValueError as e:
        # requests path raises ValueError("response code was 404") → available
        if "404" in str(e):
            return True
        # Other status codes (500, etc.) → unknown, treat as unavailable
        return False
    except Exception:
        return False


def pypi_project_url(name: str) -> str:
    """Return the PyPI project page URL for a package name."""
    return PYPI_PROJECT_URL.format(name=name)


def github_repo_url(name: str, *, org: str | None = None) -> str:
    """Return the GitHub repository URL for org/name."""
    org = org or _resolve_org()
    return GITHUB_REPO_URL.format(org=org, name=name)


def is_available_on_github(name: str, *, org: str | None = None) -> bool:
    """Check if a repository name is available on GitHub.

    Requires the ``gh`` CLI to be installed and authenticated.
    Returns True if no repo exists at org/name.
    """
    org = org or _resolve_org()
    _require_gh()
    result = subprocess.run(
        ["gh", "repo", "view", f"{org}/{name}"],
        capture_output=True,
    )
    return result.returncode != 0


def check_name_availability(name: str, *, org: str | None = None) -> dict:
    """Check a package name's validity and availability on PyPI and GitHub.

    Returns a dict with keys:
        name, valid_pep508, pypi_available, pypi_url,
        github_available, github_url

    >>> result = check_name_availability("wads")  # doctest: +SKIP
    >>> result["valid_pep508"]  # doctest: +SKIP
    True
    """
    valid = validate_package_name(name, raise_error=False)

    pypi_avail = is_available_on_pypi(name) if valid else None
    pypi_url = pypi_project_url(name) if not pypi_avail and valid else None

    try:
        github_avail = is_available_on_github(name, org=org) if valid else None
        gh_url = github_repo_url(name, org=org) if not github_avail and valid else None
    except EnvironmentError:
        github_avail = None
        gh_url = None

    return {
        "name": name,
        "valid_pep508": valid,
        "pypi_available": pypi_avail,
        "pypi_url": pypi_url,
        "github_available": github_avail,
        "github_url": gh_url,
    }


def check_names(names: Iterable[str], *, org: str | None = None) -> list[dict]:
    """Check multiple names for availability. Returns a list of result dicts."""
    return [check_name_availability(name, org=org) for name in names]


# ---------------------------------------------------------------------------
# Name candidate files
# ---------------------------------------------------------------------------


def list_name_candidate_files() -> list[Path]:
    """List all name candidate files in the name_candidates directory.

    Name candidate files are plain text files (one name per line).
    Lines starting with # are comments; blank lines are ignored.
    """
    d = name_candidates_dir()
    if not d.exists():
        return []
    return sorted(p for p in d.iterdir() if p.is_file() and not p.name.startswith("."))


def load_name_candidates(filepath: Path | None = None) -> list[str]:
    """Load name candidates from a file or all files in the name_candidates directory.

    Args:
        filepath: Specific file to load from. If None, loads from all files
            in the name_candidates directory.

    Returns:
        List of candidate names (deduplicated, preserving order).
    """
    if filepath is not None:
        return _parse_name_file(Path(filepath))

    seen = set()
    names = []
    for f in list_name_candidate_files():
        for name in _parse_name_file(f):
            if name not in seen:
                seen.add(name)
                names.append(name)
    return names


def _parse_name_file(path: Path) -> list[str]:
    """Parse a name candidate file: one name per line, # comments, blank lines."""
    names = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            names.append(line)
    return names


# ---------------------------------------------------------------------------
# GitHub operations
# ---------------------------------------------------------------------------


def detect_github_username() -> str | None:
    """Detect the current GitHub username.

    Tries ``gh auth status`` first, then falls back to ``git config user.name``.
    Returns None if detection fails.
    """
    # Try gh CLI first
    if shutil.which("gh"):
        try:
            result = subprocess.run(
                ["gh", "auth", "status"],
                capture_output=True,
                text=True,
            )
            output = result.stdout + result.stderr
            # Look for "Logged in to github.com account <username>"
            match = re.search(r"Logged in to github\.com account (\S+)", output)
            if not match:
                # Alternative format: "account <username>"
                match = re.search(r"account\s+(\S+)", output)
            if match:
                return match.group(1).strip("()")
        except Exception:
            pass

    # Fall back to git config
    try:
        result = subprocess.run(
            ["git", "config", "--global", "user.name"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass

    return None


def _resolve_org(org: str | None = None) -> str:
    """Resolve the GitHub org/username to use.

    Priority: explicit arg > user preferences > detected username.
    """
    if org:
        return org
    prefs = read_user_preferences()
    if prefs.get("default_org"):
        return prefs["default_org"]
    username = prefs.get("github_username") or detect_github_username()
    if username:
        return username
    raise EnvironmentError(
        "Could not determine GitHub org/username. "
        "Set it via user preferences or ensure `gh` CLI is authenticated."
    )


def repo_exists(name: str, *, org: str | None = None) -> bool:
    """Check if a GitHub repository exists at org/name."""
    return not is_available_on_github(name, org=org)


def create_github_repo(
    name: str,
    *,
    org: str | None = None,
    description: str = "",
    public: bool = True,
    clone: bool = True,
    clone_dir: str | None = None,
) -> str:
    """Create a GitHub repository via the ``gh`` CLI.

    Args:
        name: Repository name.
        org: GitHub org or username. Detected if not provided.
        description: Repository description.
        public: If True, create a public repo. If False, private.
        clone: If True, clone the repo after creation.
        clone_dir: Directory to clone into. Defaults to current dir.

    Returns:
        The local path to the cloned/created repository.

    Raises:
        EnvironmentError: If ``gh`` CLI is not available.
        subprocess.CalledProcessError: If repo creation fails.
    """
    _require_gh()
    org = org or _resolve_org()
    full_name = f"{org}/{name}"
    visibility = "--public" if public else "--private"

    cmd = ["gh", "repo", "create", full_name, visibility]
    if description:
        cmd.extend(["--description", description])
    if clone:
        cmd.append("--clone")

    cwd = clone_dir or os.getcwd()
    subprocess.run(cmd, check=True, cwd=cwd)

    return os.path.join(cwd, name)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def setup_project(
    name: str,
    *,
    description: str = "",
    org: str | None = None,
    author: str | None = None,
    license: str = "mit",
    root_url: str | None = None,
    proj_rootdir: str | None = None,
    create_repo: bool = True,
    populate: bool = True,
    create_devdocs: bool = False,
    setup_opsward: bool = False,
    verbose: bool = True,
) -> dict:
    """Orchestrate full project creation.

    Steps (each independently skippable via keyword args):
    1. Validate name
    2. Create GitHub repo (if create_repo)
    3. Populate project files (if populate)
    4. Create misc/docs/ (if create_devdocs)
    5. Run opsward generate (if setup_opsward and opsward is available)

    Returns a summary dict with keys: path, steps_completed, warnings.
    """
    from wads.populate import populate_pkg_dir

    log = print if verbose else lambda *a, **kw: None
    steps = []
    warnings = []

    # 1. Validate name
    validate_package_name(name)
    steps.append("name_validated")
    log(f"Name '{name}' is valid (PEP 508)")

    # Resolve org and paths
    resolved_org = org or _resolve_org()
    if root_url is None:
        root_url = f"https://github.com/{resolved_org}"
    pkg_dir = proj_rootdir or os.path.join(os.getcwd(), name)

    # 2. Create GitHub repo
    if create_repo:
        if repo_exists(name, org=resolved_org):
            log(f"Repository {resolved_org}/{name} already exists, skipping creation")
            warnings.append(f"repo_already_exists:{resolved_org}/{name}")
        else:
            log(f"Creating GitHub repository: {resolved_org}/{name}")
            create_github_repo(
                name,
                org=resolved_org,
                description=description,
                public=True,
                clone=True,
                clone_dir=os.path.dirname(pkg_dir) or os.getcwd(),
            )
            steps.append("repo_created")
            log(f"Repository created at {github_repo_url(name, org=resolved_org)}")

    # Ensure local dir exists
    os.makedirs(pkg_dir, exist_ok=True)

    # 3. Populate project files
    if populate:
        log(f"Populating project files in {pkg_dir}")

        # Merge author from preferences if not provided
        if author is None:
            prefs = read_user_preferences()
            author = prefs.get("default_author")

        populate_pkg_dir(
            pkg_dir,
            description=description
            or "There is a bit of an air of mystery around this project...",
            root_url=root_url,
            author=author,
            license=license,
        )
        steps.append("populated")

    # 4. Create dev docs
    if create_devdocs:
        created = create_misc_docs(pkg_dir)
        steps.append("devdocs_created")
        log(f"Created dev docs: {', '.join(os.path.basename(p) for p in created)}")

    # 5. Set up opsward
    if setup_opsward:
        if setup_opsward_for_project(pkg_dir):
            steps.append("opsward_configured")
            log("Opsward AI agent setup configured")
        else:
            warnings.append("opsward_not_available")
            log("Opsward not available — skipping AI agent setup")

    return {
        "path": pkg_dir,
        "steps_completed": steps,
        "warnings": warnings,
    }


def create_misc_docs(
    pkg_dir: str,
    *,
    sections: list[str] | None = None,
) -> list[str]:
    """Create misc/docs/ directory with template markdown files.

    Args:
        pkg_dir: Project root directory.
        sections: List of section names to create. Defaults to
            ["research", "design", "roadmap"].

    Returns:
        List of created file paths.
    """
    if sections is None:
        sections = ["research", "design", "roadmap"]

    docs_dir = os.path.join(pkg_dir, "misc", "docs")
    os.makedirs(docs_dir, exist_ok=True)

    created = []
    for section in sections:
        filepath = os.path.join(docs_dir, f"{section}.md")
        if not os.path.exists(filepath):
            with open(filepath, "w") as f:
                title = section.replace("_", " ").title()
                f.write(f"# {title}\n\n")
                f.write(f"TODO: Add {section} notes here.\n")
            created.append(filepath)

    return created


def setup_opsward_for_project(pkg_dir: str) -> bool:
    """Set up AI agent configuration using opsward, if available.

    Returns True if opsward ran successfully, False if not available.
    """
    # Try Python import first
    try:
        import importlib

        opsward = importlib.import_module("opsward")
        # Use opsward's generate functionality if available
        if hasattr(opsward, "generate"):
            opsward.generate(pkg_dir, write=True)
            return True
    except ImportError:
        pass

    # Fall back to CLI
    if shutil.which("opsward"):
        try:
            subprocess.run(
                ["opsward", "generate", pkg_dir, "--write"],
                check=True,
                capture_output=True,
            )
            return True
        except subprocess.CalledProcessError:
            pass

    return False


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _require_gh():
    """Raise informative error if gh CLI is not installed."""
    if not shutil.which("gh"):
        raise EnvironmentError(
            "The GitHub CLI (gh) is required but not installed.\n"
            "Install it from: https://cli.github.com/\n"
            "  macOS: brew install gh\n"
            "  Linux: https://github.com/cli/cli/blob/trunk/docs/install_linux.md\n"
            "  Windows: winget install --id GitHub.cli\n"
            "After installing, run: gh auth login"
        )
