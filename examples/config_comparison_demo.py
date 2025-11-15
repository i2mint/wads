"""
Example demonstrating the new config comparison and populate summary features.

This example shows:
1. How to use config_comparison to check project alignment with templates
2. How populate now provides emoji-based summaries
"""

from pathlib import Path
import tempfile
from wads.populate import populate_pkg_dir
from wads.config_comparison import (
    compare_pyproject_toml,
    compare_setup_cfg,
    summarize_config_status,
)


def demo_config_comparison():
    """Demonstrate config comparison tools."""
    print("=" * 60)
    print("CONFIG COMPARISON DEMO")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a minimal project
        project_dir = Path(tmpdir) / "demo_project"
        project_dir.mkdir()
        (project_dir / "demo_project").mkdir()
        (project_dir / "demo_project" / "__init__.py").touch()

        # Create an outdated setup.cfg
        (project_dir / "setup.cfg").write_text(
            """
[metadata]
name = demo_project
version = 0.1.0
description = An old project
"""
        )

        print("\n1. Checking setup.cfg status...")
        setup_status = compare_setup_cfg(project_dir / "setup.cfg")
        print(f"   Should migrate: {setup_status['should_migrate']}")
        for rec in setup_status.get('recommendations', []):
            print(f"   • {rec}")

        print("\n2. Overall project status...")
        status = summarize_config_status(project_dir, check_ci=False)
        print(f"   Has pyproject.toml: {status['has_pyproject']}")
        print(f"   Has setup.cfg: {status['has_setup_cfg']}")
        if status['needs_attention']:
            print("   ⚠️  Files needing attention:")
            for file in status['needs_attention']:
                print(f"      - {file}")


def demo_populate_with_summary():
    """Demonstrate new populate summary feature."""
    print("\n" + "=" * 60)
    print("POPULATE WITH SUMMARY DEMO")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a basic project structure
        project_dir = Path(tmpdir) / "test_project"
        project_dir.mkdir()
        (project_dir / "test_project").mkdir()
        (project_dir / "test_project" / "__init__.py").touch()

        # Pre-create some files so we see "skipped" in summary
        (project_dir / "README.md").write_text("# Existing README\n")

        print("\nRunning populate...")
        print("-" * 60)

        # Run populate - it will now show emoji summary at the end!
        populate_pkg_dir(
            str(project_dir),
            description="A test project",
            author="Test Author",
            root_url="https://github.com/test",
            verbose=True,
            skip_ci_def_gen=True,  # Skip CI for this demo
        )


def demo_comparison_on_existing_project():
    """Show comparison on a project with existing pyproject.toml."""
    print("\n" + "=" * 60)
    print("COMPARISON ON EXISTING PROJECT")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir) / "existing_project"
        project_dir.mkdir()

        # Create minimal pyproject.toml (missing some modern sections)
        (project_dir / "pyproject.toml").write_text(
            """
[project]
name = "existing_project"
version = "0.1.0"
description = "An existing project"

[build-system]
requires = ["setuptools"]
build-backend = "setuptools.build_meta"
"""
        )

        print("\nComparing with template...")
        comparison = compare_pyproject_toml(project_dir / "pyproject.toml")

        if comparison['needs_attention']:
            print("⚠️  Issues found:")
            for rec in comparison.get('recommendations', []):
                print(f"   • {rec}")

            if comparison.get('missing_sections'):
                print(f"\n   Missing sections:")
                for section in comparison['missing_sections'][:5]:
                    print(f"   - {section}")


if __name__ == '__main__':
    # Run all demos
    demo_config_comparison()
    demo_populate_with_summary()
    demo_comparison_on_existing_project()

    print("\n" + "=" * 60)
    print("✅ All demos completed!")
    print("=" * 60)
