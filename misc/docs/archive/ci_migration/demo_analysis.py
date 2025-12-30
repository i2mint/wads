"""
Demo script to show the agent's analysis capabilities without requiring API calls.

Usage:
    python demo_analysis.py /path/to/project [--analyze-code]
"""

from pathlib import Path
import sys
import argparse
from wads_ci_migration_agent import analyze_project, generate_migration_prompt


def demo_analysis(project_root: Path, *, analyze_code: bool = False) -> None:
    """
    Demonstrate the agent's analysis capabilities.

    This runs the analysis phase without calling the Anthropic API,
    showing what information would be extracted and sent to Claude.
    """
    print(f"\n{'=' * 70}")
    print(f"CI Migration Agent - Analysis Demo")
    print(f"{'=' * 70}\n")
    print(f"Project: {project_root.absolute()}")
    print(f"Code analysis: {'enabled' if analyze_code else 'disabled'}")
    print(f"\n{'-' * 70}\n")

    # Run analysis
    print("📋 Analyzing project files...\n")
    analysis = analyze_project(project_root, analyze_code=analyze_code)

    # Display detailed analysis results
    print(f"\n{'-' * 70}\n")
    print("📊 Analysis Results\n")
    print(f"{'=' * 70}\n")

    # Configuration file
    if analysis["current_config"]:
        print(f"✓ Configuration File: {analysis['config_file_name']}")
        print(f"  Length: {len(analysis['current_config'])} characters")
    else:
        print("✗ No configuration file found")
    print()

    # CI file
    if analysis["ci_config"]:
        print(f"✓ CI Workflow: {analysis['ci_file_name']}")
        print(f"  Length: {len(analysis['ci_config'])} characters")
    else:
        print("✗ No CI workflow found")
    print()

    # System packages
    print("📦 System Packages:")
    for platform, packages in analysis["system_packages"].items():
        if packages:
            print(f"  {platform.title()}:")
            for pkg in packages:
                print(f"    • {pkg}")
    if not any(analysis["system_packages"].values()):
        print("  (none detected)")
    print()

    # Environment variables
    print("🌍 Environment Variables:")
    if analysis["env_vars"]:
        for key, value in analysis["env_vars"].items():
            print(f"  {key} = {value}")
    else:
        print("  (none detected)")
    print()

    # Python versions
    print(f"🐍 Python Versions: {', '.join(analysis['python_versions'])}")
    print()

    # Inferred dependencies
    if analyze_code:
        print("🔍 Inferred Dependencies (from code):")
        if analysis["inferred_deps"]:
            for dep in sorted(analysis["inferred_deps"]):
                print(f"  • {dep}")
        else:
            print("  (none detected)")
        print()

    # Generate the prompt
    print(f"\n{'-' * 70}\n")
    print("📝 Generated Prompt for Claude\n")
    print(f"{'=' * 70}\n")

    prompt = generate_migration_prompt(analysis)
    print(prompt)

    print(f"\n{'=' * 70}\n")
    print("\n💡 Next Steps:")
    print("   To complete the migration, run:")
    print(f"   python wads_ci_migration_agent.py {project_root}")
    print()


def main():
    """Main entry point for demo."""
    parser = argparse.ArgumentParser(
        description="Demo the CI migration agent's analysis (no API calls)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
This script runs the analysis phase only, showing what information
would be extracted and sent to Claude, without actually calling the API.

Examples:
  python demo_analysis.py /path/to/project
  python demo_analysis.py . --analyze-code
        """,
    )

    parser.add_argument("project_root", type=Path, help="Path to the project directory")

    parser.add_argument(
        "--analyze-code",
        action="store_true",
        help="Analyze Python code to infer system dependencies",
    )

    args = parser.parse_args()

    # Validate project root
    if not args.project_root.exists():
        print(f"Error: Project directory not found: {args.project_root}")
        sys.exit(1)

    if not args.project_root.is_dir():
        print(f"Error: Not a directory: {args.project_root}")
        sys.exit(1)

    # Run demo
    demo_analysis(args.project_root, analyze_code=args.analyze_code)


if __name__ == "__main__":
    main()
