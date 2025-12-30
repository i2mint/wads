"""
Dependency Resolver Agent

Automatically analyzes import errors, missing dependencies, and suggests fixes.
Can scan local code, analyze error messages, and propose dependency additions.
"""

import re
import sys
import ast
from pathlib import Path
from typing import List, Set, Dict, Optional, Tuple
from dataclasses import dataclass
import subprocess

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None


@dataclass
class DependencyIssue:
    """Represents a missing or problematic dependency."""

    package_name: str
    import_statement: str
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    suggested_package: Optional[str] = None
    error_message: Optional[str] = None
    is_installed: bool = False


@dataclass
class DependencyReport:
    """Result of dependency analysis."""

    missing_packages: List[DependencyIssue]
    unused_packages: List[str]
    version_conflicts: List[Dict[str, str]]
    recommendations: List[str]


# Common import name to package name mappings
IMPORT_TO_PACKAGE = {
    "cv2": "opencv-python",
    "PIL": "Pillow",
    "yaml": "PyYAML",
    "sklearn": "scikit-learn",
    "bs4": "beautifulsoup4",
    "pytest": "pytest",
    "numpy": "numpy",
    "pandas": "pandas",
    "requests": "requests",
    "flask": "Flask",
    "django": "Django",
    "sqlalchemy": "SQLAlchemy",
}


def extract_imports_from_file(file_path: Path) -> Set[str]:
    """
    Extract all import statements from a Python file.

    Args:
        file_path: Path to Python file

    Returns:
        Set of imported module names
    """
    imports = set()

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=str(file_path))

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.add(node.module.split(".")[0])

    except (SyntaxError, UnicodeDecodeError):
        # Skip files with syntax errors or encoding issues
        pass

    return imports


def scan_project_imports(
    project_path: Path, exclude_patterns: List[str] = None
) -> Dict[str, Set[str]]:
    """
    Scan all Python files in a project for imports.

    Args:
        project_path: Root path of project
        exclude_patterns: Patterns to exclude (e.g., 'tests', 'venv')

    Returns:
        Dict mapping file paths to sets of imported modules
    """
    if exclude_patterns is None:
        exclude_patterns = [
            "venv",
            ".venv",
            "__pycache__",
            ".git",
            "build",
            "dist",
            ".eggs",
        ]

    imports_by_file = {}

    for py_file in project_path.rglob("*.py"):
        # Skip excluded directories
        if any(pattern in str(py_file) for pattern in exclude_patterns):
            continue

        imports = extract_imports_from_file(py_file)
        if imports:
            imports_by_file[str(py_file.relative_to(project_path))] = imports

    return imports_by_file


def get_installed_packages() -> Set[str]:
    """
    Get list of installed packages using pip.

    Returns:
        Set of installed package names (lowercase)
    """
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "list", "--format=freeze"],
            capture_output=True,
            text=True,
            check=True,
        )

        packages = set()
        for line in result.stdout.splitlines():
            if "==" in line:
                package_name = line.split("==")[0].lower()
                packages.add(package_name)

        return packages

    except subprocess.CalledProcessError:
        return set()


def resolve_package_name(import_name: str) -> str:
    """
    Resolve import name to package name.

    Args:
        import_name: Name used in import statement

    Returns:
        Likely package name for pip install
    """
    # Check known mappings first
    if import_name in IMPORT_TO_PACKAGE:
        return IMPORT_TO_PACKAGE[import_name]

    # Otherwise, assume import name is package name
    return import_name.lower()


def parse_error_message(error_msg: str) -> List[DependencyIssue]:
    """
    Parse error messages to extract missing dependencies.

    Args:
        error_msg: Error message from Python/pytest

    Returns:
        List of DependencyIssue objects
    """
    issues = []

    # Pattern: ModuleNotFoundError: No module named 'xxx'
    import_error_pattern = re.compile(
        r"ModuleNotFoundError: No module named '(.+?)'|"
        r"ImportError: No module named '?(.+?)'?|"
        r"cannot import name '(.+?)' from '(.+?)'"
    )

    # Pattern: File "path", line N
    file_pattern = re.compile(r'File "(.+?)", line (\d+)')

    for match in import_error_pattern.finditer(error_msg):
        module_name = match.group(1) or match.group(2) or match.group(3)
        if module_name:
            # Get file path and line number if available
            file_match = file_pattern.search(error_msg, pos=max(0, match.start() - 500))

            file_path = file_match.group(1) if file_match else None
            line_number = int(file_match.group(2)) if file_match else None

            # Resolve to package name
            top_level = module_name.split(".")[0]
            package_name = resolve_package_name(top_level)

            issues.append(
                DependencyIssue(
                    package_name=package_name,
                    import_statement=f"import {module_name}",
                    file_path=file_path,
                    line_number=line_number,
                    suggested_package=package_name,
                    error_message=match.group(0),
                )
            )

    return issues


def read_project_dependencies(pyproject_path: Path) -> Tuple[Set[str], Set[str]]:
    """
    Read declared dependencies from pyproject.toml.

    Args:
        pyproject_path: Path to pyproject.toml

    Returns:
        Tuple of (main_dependencies, dev_dependencies)
    """
    if not tomllib:
        return set(), set()

    try:
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)

        # Get main dependencies
        main_deps = set()
        project = data.get("project", {})
        for dep in project.get("dependencies", []):
            # Extract package name (before version specifiers)
            pkg = re.split(r"[<>=\[]", dep)[0].strip().lower()
            main_deps.add(pkg)

        # Get optional dependencies
        dev_deps = set()
        for group_deps in project.get("optional-dependencies", {}).values():
            for dep in group_deps:
                pkg = re.split(r"[<>=\[]", dep)[0].strip().lower()
                dev_deps.add(pkg)

        return main_deps, dev_deps

    except Exception:
        return set(), set()


def analyze_dependencies(
    project_path: str | Path,
    error_logs: Optional[str] = None,
    check_unused: bool = True,
) -> DependencyReport:
    """
    Analyze project dependencies and identify issues.

    Args:
        project_path: Path to project directory
        error_logs: Optional error logs to parse
        check_unused: Whether to check for unused dependencies

    Returns:
        DependencyReport with analysis results
    """
    project_path = Path(project_path)
    pyproject_path = project_path / "pyproject.toml"

    missing_packages = []
    unused_packages = []
    version_conflicts = []
    recommendations = []

    # Parse error logs if provided
    if error_logs:
        missing_from_errors = parse_error_message(error_logs)
        missing_packages.extend(missing_from_errors)

    # Scan project imports
    imports_by_file = scan_project_imports(project_path)
    all_imports = set()
    for imports in imports_by_file.values():
        all_imports.update(imports)

    # Get installed packages
    installed = get_installed_packages()

    # Read declared dependencies
    declared_main, declared_dev = read_project_dependencies(pyproject_path)
    all_declared = declared_main | declared_dev

    # Find missing dependencies (imported but not declared/installed)
    for import_name in all_imports:
        # Skip standard library modules
        if import_name in sys.stdlib_module_names:
            continue

        package_name = resolve_package_name(import_name).lower()

        # Check if installed
        is_installed = package_name in installed

        # Check if declared
        is_declared = package_name in all_declared

        if not is_declared:
            # Find which files use this import
            using_files = [
                f for f, imports in imports_by_file.items() if import_name in imports
            ]

            issue = DependencyIssue(
                package_name=package_name,
                import_statement=f"import {import_name}",
                file_path=using_files[0] if using_files else None,
                suggested_package=package_name,
                is_installed=is_installed,
            )

            if not any(m.package_name == package_name for m in missing_packages):
                missing_packages.append(issue)

    # Find unused dependencies
    if check_unused and pyproject_path.exists():
        for dep_pkg in all_declared:
            # Try to find if this package is imported
            # (This is approximate - package name != import name always)
            potential_imports = {dep_pkg, dep_pkg.replace("-", "_")}

            if not any(imp in all_imports for imp in potential_imports):
                # Double-check it's not a known mapping
                reverse_mapped = [
                    k for k, v in IMPORT_TO_PACKAGE.items() if v.lower() == dep_pkg
                ]
                if not any(imp in all_imports for imp in reverse_mapped):
                    unused_packages.append(dep_pkg)

    # Generate recommendations
    if missing_packages:
        recommendations.append(
            f"Add {len(missing_packages)} missing packages to pyproject.toml:"
        )
        for issue in missing_packages[:10]:  # Show first 10
            if issue.is_installed:
                recommendations.append(
                    f"  - {issue.package_name} (already installed, add to dependencies)"
                )
            else:
                recommendations.append(f"  - {issue.package_name} (needs installation)")

    if unused_packages:
        recommendations.append(
            f"\nConsider removing {len(unused_packages)} potentially unused packages:"
        )
        for pkg in unused_packages[:5]:  # Show first 5
            recommendations.append(f"  - {pkg}")

    return DependencyReport(
        missing_packages=missing_packages,
        unused_packages=unused_packages,
        version_conflicts=version_conflicts,
        recommendations=recommendations,
    )


def print_report(report: DependencyReport):
    """Print formatted dependency report."""
    print("\n" + "=" * 70)
    print("DEPENDENCY ANALYSIS REPORT")
    print("=" * 70)

    if report.missing_packages:
        print(f"\n📦 Missing Packages ({len(report.missing_packages)}):")
        for issue in report.missing_packages:
            status = "✓ installed" if issue.is_installed else "✗ not installed"
            print(f"\n  {issue.package_name} ({status})")
            print(f"    Import: {issue.import_statement}")
            if issue.file_path:
                location = (
                    f"{issue.file_path}:{issue.line_number}"
                    if issue.line_number
                    else issue.file_path
                )
                print(f"    Used in: {location}")

    if report.unused_packages:
        print(f"\n🗑️  Potentially Unused Packages ({len(report.unused_packages)}):")
        for pkg in report.unused_packages:
            print(f"  • {pkg}")

    if report.recommendations:
        print("\n💡 Recommendations:")
        for rec in report.recommendations:
            print(rec)

    print("\n" + "=" * 70)


def main():
    """CLI entry point for dependency resolver."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Analyze and resolve Python dependencies"
    )
    parser.add_argument(
        "project_path",
        nargs="?",
        default=".",
        help="Path to project directory (default: current directory)",
    )
    parser.add_argument("--error-log", help="Path to error log file to analyze")
    parser.add_argument(
        "--no-check-unused",
        action="store_true",
        help="Skip checking for unused dependencies",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Automatically add missing packages to pyproject.toml",
    )

    args = parser.parse_args()

    # Read error logs if provided
    error_logs = None
    if args.error_log:
        with open(args.error_log, "r") as f:
            error_logs = f.read()

    # Analyze dependencies
    report = analyze_dependencies(
        project_path=args.project_path,
        error_logs=error_logs,
        check_unused=not args.no_check_unused,
    )

    # Print report
    print_report(report)

    # Auto-fix if requested
    if args.fix and report.missing_packages:
        print("\n🔧 Auto-fix mode: Adding missing packages to pyproject.toml...")
        # TODO: Implement auto-fix
        print("(Auto-fix not yet implemented)")

    # Exit with error code if issues found
    sys.exit(1 if report.missing_packages else 0)


if __name__ == "__main__":
    main()
