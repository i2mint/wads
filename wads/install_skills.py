"""Install wads Claude Code skills to ~/.claude/skills/ for global availability.

Skills shipped with wads:
- setup-py-project: AI-assisted Python project creation
- wads-migrate: Migration to modern wads/uv setup

Usage:
    wads-install-skills          # Install all skills (symlinks by default)
    wads-install-skills --list   # List available skills
    wads-install-skills --force  # Overwrite existing skills
    wads-install-skills --copy   # Copy files instead of symlinking
"""

import os
import shutil
import sys
from pathlib import Path

from wads import rjoin


SKILLS_SOURCE_DIR = rjoin("data", "skills")
CLAUDE_SKILLS_DIR = Path.home() / ".claude" / "skills"


def list_available_skills() -> list[str]:
    """List skill names bundled with wads."""
    source = Path(SKILLS_SOURCE_DIR)
    if not source.exists():
        return []
    return sorted(d.name for d in source.iterdir() if d.is_dir())


def _supports_symlinks() -> bool:
    """Check if the current platform/filesystem supports symlinks."""
    if sys.platform != "win32":
        return True
    # On Windows, symlinks require developer mode or admin privileges
    test_path = Path(CLAUDE_SKILLS_DIR) / ".symlink_test"
    try:
        test_path.parent.mkdir(parents=True, exist_ok=True)
        test_path.symlink_to(__file__)
        test_path.unlink()
        return True
    except OSError:
        return False


def install_skills(
    *,
    force: bool = False,
    copy: bool = False,
    verbose: bool = True,
) -> list[str]:
    """Install wads Claude Code skills to ~/.claude/skills/.

    By default, creates symlinks so skills stay in sync with the wads package.
    Use ``copy=True`` to copy files instead (not recommended — updates won't
    propagate, and the skills depend on wads being installed anyway).

    Args:
        force: If True, overwrite existing skill entries.
        copy: If True, copy files instead of creating symlinks.
        verbose: If True, print progress.

    Returns:
        List of installed skill names.
    """
    log = print if verbose else lambda *a, **kw: None
    source_dir = Path(SKILLS_SOURCE_DIR)
    installed = []

    if not source_dir.exists():
        log(f"No skills found in {source_dir}")
        return installed

    use_symlinks = not copy
    if use_symlinks and not _supports_symlinks():
        log("Symlinks not supported on this system, falling back to copy.")
        use_symlinks = False

    CLAUDE_SKILLS_DIR.mkdir(parents=True, exist_ok=True)

    for skill_dir in sorted(source_dir.iterdir()):
        if not skill_dir.is_dir():
            continue

        skill_name = skill_dir.name
        target = CLAUDE_SKILLS_DIR / skill_name

        if target.exists() or target.is_symlink():
            if not force:
                # Show whether current install is a symlink or copy
                kind = "symlink" if target.is_symlink() else "copy"
                log(f"  Skipping {skill_name} (already exists as {kind}, "
                    f"use --force to overwrite)")
                continue
            # Remove existing (symlink, dir, or file)
            if target.is_symlink() or target.is_file():
                target.unlink()
            else:
                shutil.rmtree(target)

        if use_symlinks:
            target.symlink_to(skill_dir.resolve())
            installed.append(skill_name)
            log(f"  Linked: /{skill_name} -> {skill_dir.resolve()}")
        else:
            shutil.copytree(skill_dir, target)
            installed.append(skill_name)
            log(f"  Copied: /{skill_name} -> {target}")

    if installed:
        log(f"\nInstalled {len(installed)} skill(s) via "
            f"{'symlink' if use_symlinks else 'copy'}.")
        log("Use /SKILL_NAME in Claude Code to invoke.")
    else:
        log("\nNo new skills to install.")

    return installed


def main():
    """CLI entry point for wads-install-skills."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Install wads Claude Code skills to ~/.claude/skills/"
    )
    parser.add_argument(
        "--list", action="store_true", dest="list_skills",
        help="List available skills without installing",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Overwrite existing skills",
    )
    parser.add_argument(
        "--copy", action="store_true",
        help="Copy files instead of creating symlinks (not recommended)",
    )

    args = parser.parse_args()

    if args.list_skills:
        skills = list_available_skills()
        if skills:
            print("Available wads skills:")
            for name in skills:
                print(f"  /{name}")
        else:
            print("No skills found.")
        return

    print("Installing wads Claude Code skills...")
    install_skills(force=args.force, copy=args.copy)


if __name__ == "__main__":
    main()
