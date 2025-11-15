"""
Example showing MANIFEST.in detection and migration guidance.

This demonstrates how `populate` automatically detects MANIFEST.in files
and provides migration guidance for Hatchling.
"""

from pathlib import Path
import tempfile
from wads.populate import populate_pkg_dir
from wads.migration import analyze_manifest_in


def show_manifest_analysis():
    """Analyze a MANIFEST.in file directly."""
    print("=" * 70)
    print("DIRECT MANIFEST.IN ANALYSIS")
    print("=" * 70)

    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = Path(tmpdir) / 'MANIFEST.in'

        # Create a typical setuptools MANIFEST.in
        manifest_content = """
# Include documentation and metadata
include README.md LICENSE CHANGELOG.md
recursive-include docs *.rst *.md

# Include package data
recursive-include mypackage/data *.json *.yaml *.csv
graft mypackage/templates

# Exclude development files
prune tests
prune .github
global-exclude *.pyc *.pyo __pycache__
"""
        manifest_path.write_text(manifest_content)

        # Analyze it
        result = analyze_manifest_in(manifest_path)

        print(f"\n✓ File exists: {result['exists']}")
        print(f"⚠️  Needs migration: {result['needs_migration']}")
        print(f"📋 Found {len(result['directives'])} directives")

        print("\n📝 Recommendations:")
        for i, rec in enumerate(result['recommendations'], 1):
            print(f"\n{i}. {rec}")

        if result['hatchling_config']:
            print("\n" + "=" * 70)
            print("SUGGESTED PYPROJECT.TOML CONFIGURATION")
            print("=" * 70)
            print(result['hatchling_config'])
            print("=" * 70)


def show_populate_with_manifest():
    """Show how populate handles projects with MANIFEST.in."""
    print("\n\n" + "=" * 70)
    print("POPULATE WITH MANIFEST.IN DETECTION")
    print("=" * 70)

    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir) / "old_project"
        project_dir.mkdir()

        # Create package structure
        (project_dir / "old_project").mkdir()
        (project_dir / "old_project" / "__init__.py").touch()

        # Create MANIFEST.in (as in old setuptools projects)
        (project_dir / "MANIFEST.in").write_text(
            """
include README.md LICENSE
recursive-include old_project/data *.json
graft docs
"""
        )

        print("\n📦 Running populate on project with MANIFEST.in...")
        print("-" * 70)

        # Run populate - it will detect and warn about MANIFEST.in
        populate_pkg_dir(
            str(project_dir),
            description="An old project with MANIFEST.in",
            author="Test Author",
            root_url="https://github.com/test",
            verbose=True,
            skip_ci_def_gen=True,
        )

        print("\n💡 TIP: When you see the MANIFEST.in warning above,")
        print("   copy the suggested [tool.hatch.build.targets.wheel] config")
        print("   into your pyproject.toml to migrate package data inclusion.")


if __name__ == '__main__':
    show_manifest_analysis()
    show_populate_with_manifest()

    print("\n\n" + "=" * 70)
    print("✅ MANIFEST.in migration guidance complete!")
    print("=" * 70)
    print("\nKey takeaways:")
    print("  • MANIFEST.in is setuptools-specific (not used by Hatchling)")
    print("  • Use [tool.hatch.build.targets.wheel] instead")
    print("  • Hatchling includes all package files by default")
    print("  • Only add explicit include/exclude if needed")
    print("=" * 70)
