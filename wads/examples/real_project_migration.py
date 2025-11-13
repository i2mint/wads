"""
Real-world migration example: Migrate a project from the workspace.

This script demonstrates how to use the migration tools on a real project
from the i2mint ecosystem.
"""

import os
from pathlib import Path
from wads.migration import (
    migrate_setuptools_to_hatching,
    migrate_github_ci_old_to_new,
    MigrationError,
)


def find_projects_with_setup_cfg(base_dir: str, limit: int = 5):
    """Find projects that have setup.cfg files."""
    base_path = Path(base_dir)
    projects = []

    for setup_cfg in base_path.rglob("setup.cfg"):
        # Skip if it's in a hidden directory or a venv
        if any(part.startswith(".") or part == "venv" for part in setup_cfg.parts):
            continue

        project_root = setup_cfg.parent
        projects.append(project_root)

        if len(projects) >= limit:
            break

    return projects


def migrate_project(project_root: Path, dry_run: bool = True):
    """
    Migrate a project from setup.cfg to pyproject.toml.

    Args:
        project_root: Path to the project root
        dry_run: If True, just show what would be done without writing files
    """
    print(f"\n{'='*70}")
    print(f"Migrating project: {project_root.name}")
    print(f"Location: {project_root}")
    print(f"{'='*70}\n")

    setup_cfg = project_root / "setup.cfg"
    pyproject_toml = project_root / "pyproject.toml"

    if not setup_cfg.exists():
        print("❌ No setup.cfg found")
        return False

    if pyproject_toml.exists():
        print("⚠️  pyproject.toml already exists. Skipping...")
        return False

    # Try to migrate setup.cfg
    try:
        print("📝 Migrating setup.cfg to pyproject.toml...")
        pyproject_content = migrate_setuptools_to_hatching(str(setup_cfg))

        if dry_run:
            print("\n✅ Migration successful (dry run)!")
            print("\nGenerated pyproject.toml preview (first 500 chars):")
            print("-" * 70)
            print(pyproject_content[:500])
            print("...")
            print("-" * 70)
        else:
            pyproject_toml.write_text(pyproject_content)
            print(f"\n✅ Created {pyproject_toml}")

        # Try to migrate CI if it exists
        ci_dir = project_root / ".github" / "workflows"
        if ci_dir.exists():
            old_ci_files = list(ci_dir.glob("*.yml")) + list(ci_dir.glob("*.yaml"))

            for old_ci in old_ci_files:
                if "ci" in old_ci.name.lower():
                    print(f"\n📝 Found CI file: {old_ci.name}")
                    try:
                        new_ci_content = migrate_github_ci_old_to_new(str(old_ci))

                        if dry_run:
                            print("✅ CI migration successful (dry run)!")
                        else:
                            new_ci_path = ci_dir / f"{old_ci.stem}_new{old_ci.suffix}"
                            new_ci_path.write_text(new_ci_content)
                            print(f"✅ Created {new_ci_path}")
                    except MigrationError as e:
                        print(f"⚠️  CI migration needs attention: {e}")
                    break

        return True

    except MigrationError as e:
        print(f"❌ Migration failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False


def main():
    """Main function demonstrating migration workflow."""

    # Example 1: Direct migration with inline config
    print("=" * 70)
    print("EXAMPLE 1: Direct migration from dictionary")
    print("=" * 70)

    example_cfg = {
        "metadata": {
            "name": "example-lib",
            "version": "2.3.4",
            "description": "An example library for demonstration",
            "url": "https://github.com/i2mint/example-lib",
            "license": "MIT",
            "author": "i2mint",
            "keywords": "example\nlibrary\nmigration",
        },
        "options": {
            "packages": "find:",
            "install_requires": "requests>=2.28.0\nclick>=8.0",
        },
    }

    try:
        result = migrate_setuptools_to_hatching(example_cfg)
        print("\n✅ Migration successful!")
        print("\nGenerated content (first 800 chars):")
        print(result[:800])
        print("...\n")
    except MigrationError as e:
        print(f"❌ Error: {e}")

    # Example 2: Find real projects and show what would be migrated
    print("\n" + "=" * 70)
    print("EXAMPLE 2: Finding projects that could be migrated")
    print("=" * 70)

    # Look for projects in the workspace
    workspace_root = Path(__file__).parent.parent.parent.parent  # Go up to proj/i

    if workspace_root.exists():
        print(f"\nSearching for projects with setup.cfg in: {workspace_root}")
        projects = find_projects_with_setup_cfg(str(workspace_root), limit=3)

        print(f"\nFound {len(projects)} project(s) with setup.cfg:\n")
        for i, project in enumerate(projects, 1):
            print(f"{i}. {project.name} ({project})")

        # Try to migrate the first one (dry run)
        if projects:
            print("\n" + "=" * 70)
            print("EXAMPLE 3: Dry-run migration of first project")
            print("=" * 70)
            migrate_project(projects[0], dry_run=True)
    else:
        print("Workspace root not found, skipping real project search")

    print("\n" + "=" * 70)
    print("Examples complete!")
    print("=" * 70)
    print("\nTo actually migrate a project, use:")
    print("  migrate_project(Path('/path/to/project'), dry_run=False)")


if __name__ == "__main__":
    main()
