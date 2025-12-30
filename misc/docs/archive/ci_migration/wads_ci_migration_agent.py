"""
CI Migration Agent for Wads

This agent helps migrate projects from old CI formats to the new v3 format that
uses pyproject.toml as the single source of truth, aligning with PEP 725/804.

Usage:
    python wads_ci_migration_agent.py /path/to/project [--analyze-code]
"""

from pathlib import Path
from typing import Iterable, Optional
import json
import re
import sys
import argparse


# ============================================================================
# AGENT SYSTEM PROMPT
# ============================================================================

SYSTEM_PROMPT = """You are an expert CI migration assistant specializing in converting projects to use wads v3 CI configuration format. Your expertise includes:

1. **PEP 725/804 Alignment**: You understand how to declare external dependencies using DepURLs
2. **CI Pattern Recognition**: You can identify system dependencies, environment variables, and build configurations in various CI formats
3. **Intelligent Inference**: You can analyze code and documentation to infer missing dependencies
4. **Best Practices**: You follow Python packaging best practices and the user's architectural preferences

## Your Task

Analyze the provided project files and generate an updated `pyproject.toml` that:
- Declares external dependencies in `[external]` using DepURLs
- Provides operational metadata in `[tool.wads.external.ops]` for each external dependency
- Configures CI settings in `[tool.wads.ci]` based on the old CI workflow
- Preserves all existing project metadata and dependencies

## Analysis Process

1. **Read the Current Configuration**
   - Parse existing `pyproject.toml` and/or `setup.cfg`
   - Extract project metadata, Python dependencies, and tool configurations

2. **Analyze the CI Workflow**
   - Identify system package installations (apt-get, brew, choco)
   - Extract environment variables
   - Note Python versions being tested
   - Identify any custom test or build steps

3. **Convert to New Format**
   - Map system packages to DepURLs (e.g., "unixodbc" → "dep:generic/unixodbc")
   - Create operational metadata with install/check commands for each platform
   - Configure [tool.wads.ci] sections with appropriate settings
   - Ensure backward compatibility during transition

4. **Optional Code Analysis** (if --analyze-code flag is set)
   - Scan Python imports to infer missing system dependencies
   - Check documentation for dependency mentions
   - Look for common patterns (e.g., pyodbc → needs unixodbc)

## DepURL Mapping Rules

Use these patterns to convert system packages to DepURLs:

| Package Type | Example Package | DepURL |
|-------------|----------------|---------|
| Generic library | unixodbc, libffi | dep:generic/{name} |
| Compiler/tool | gcc, clang | dep:virtual/compiler/c |
| Build tool | make, cmake | dep:generic/{name} |
| Runtime tool | git, ffmpeg | dep:generic/{name} |

## Output Format

Provide a complete, valid `pyproject.toml` that:
1. Preserves all original project settings
2. Adds or updates `[external]` sections with DepURLs
3. Adds `[tool.wads.external.ops]` with platform-specific commands
4. Updates `[tool.wads.ci]` with comprehensive settings
5. Includes helpful comments explaining changes

## Response Style

- Be thorough but concise
- Explain your reasoning for non-obvious decisions
- Highlight any ambiguities or assumptions
- Suggest improvements beyond the migration
- Use the complete template structure for consistency
"""


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def _read_file(path: Path) -> Optional[str]:
    """
    Read file content safely.

    >>> path = Path('test.txt')
    >>> path.write_text('hello')
    5
    >>> _read_file(path)
    'hello'
    """
    try:
        return path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"Warning: Could not read {path}: {e}")
        return None


def _find_file(project_root: Path, *candidates: str) -> Optional[Path]:
    """
    Find the first existing file from candidates.

    >>> import tempfile
    >>> with tempfile.TemporaryDirectory() as td:
    ...     root = Path(td)
    ...     (root / 'setup.cfg').touch()
    ...     found = _find_file(root, 'pyproject.toml', 'setup.cfg')
    ...     found.name
    'setup.cfg'
    """
    for candidate in candidates:
        path = project_root / candidate
        if path.exists():
            return path
    return None


def _extract_apt_packages(ci_content: str) -> list[str]:
    """
    Extract packages from apt-get install commands.

    >>> ci = "sudo apt-get install -y unixodbc libffi-dev"
    >>> _extract_apt_packages(ci)
    ['unixodbc', 'libffi-dev']
    """
    packages = []
    # Match: apt-get install ... package1 package2
    apt_pattern = r"apt-get\s+install\s+(?:-[a-z]+\s+)*([^\n&|;]+)"
    for match in re.finditer(apt_pattern, ci_content, re.IGNORECASE):
        pkg_line = match.group(1).strip()
        # Remove flags and split by whitespace
        parts = [p.strip() for p in pkg_line.split() if p and not p.startswith("-")]
        packages.extend(parts)
    return [p for p in packages if p and not p.startswith("$")]


def _extract_brew_packages(ci_content: str) -> list[str]:
    """
    Extract packages from brew install commands.

    >>> ci = "brew install unixodbc ffmpeg"
    >>> _extract_brew_packages(ci)
    ['unixodbc', 'ffmpeg']
    """
    packages = []
    brew_pattern = r"brew\s+install\s+([^\n&|;]+)"
    for match in re.finditer(brew_pattern, ci_content, re.IGNORECASE):
        pkg_line = match.group(1).strip()
        parts = [p.strip() for p in pkg_line.split() if p and not p.startswith("-")]
        packages.extend(parts)
    return [p for p in packages if p and not p.startswith("$")]


def _extract_env_vars(ci_content: str) -> dict[str, str]:
    """
    Extract environment variables from CI file.

    >>> ci = '''env:
    ...   PROJECT_NAME: myproject
    ...   DEBUG: true'''
    >>> _extract_env_vars(ci)
    {'PROJECT_NAME': 'myproject', 'DEBUG': 'true'}
    """
    env_vars = {}

    # Match env: block in YAML
    env_block_pattern = r"^env:\s*\n((?:  \w+:.*\n?)+)"
    match = re.search(env_block_pattern, ci_content, re.MULTILINE)
    if match:
        block = match.group(1)
        # Extract key: value pairs
        for line in block.split("\n"):
            line = line.strip()
            if ":" in line:
                key, value = line.split(":", 1)
                env_vars[key.strip()] = value.strip()

    return env_vars


def _extract_python_versions(ci_content: str) -> list[str]:
    """
    Extract Python versions from CI matrix.

    >>> ci = 'python-version: ["3.10", "3.11", "3.12"]'
    >>> _extract_python_versions(ci)
    ['3.10', '3.11', '3.12']
    """
    versions = []
    # Match: python-version: ["3.10", "3.11"]
    pattern = r"python-version:\s*\[([^\]]+)\]"
    match = re.search(pattern, ci_content)
    if match:
        versions_str = match.group(1)
        # Extract quoted strings
        versions = re.findall(r'["\']([0-9.]+)["\']', versions_str)
    return versions


def _infer_depurl(package_name: str) -> str:
    """
    Infer DepURL from package name.

    >>> _infer_depurl('unixodbc')
    'dep:generic/unixodbc'
    >>> _infer_depurl('gcc')
    'dep:virtual/compiler/c'
    """
    # Special cases for virtual dependencies
    compiler_packages = {"gcc", "g++", "clang", "clang++", "cc", "c++"}
    if package_name.lower() in compiler_packages:
        return "dep:virtual/compiler/c"

    # Default to generic
    return f"dep:generic/{package_name}"


def _normalize_package_name(package_name: str) -> str:
    """
    Normalize package name for use as TOML key.

    >>> _normalize_package_name('libffi-dev')
    'libffi'
    >>> _normalize_package_name('unixODBC')
    'unixodbc'
    """
    # Remove common suffixes but be careful with 'lib' prefix
    name = package_name.lower()
    # First remove suffixes that are clearly suffixes
    for suffix in ["-dev", "-devel", "-headers"]:
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    # Remove lib prefix only if followed by another word
    if name.startswith("lib") and len(name) > 3:
        # Keep 'lib' if it's part of the actual package name like 'libffi'
        pass
    return name.strip("-_")


def _scan_python_imports(project_root: Path) -> set[str]:
    """
    Scan Python files for imports that might indicate system dependencies.

    Returns set of potential system dependency names.
    """
    dependencies = set()

    # Known import → system dependency mappings
    import_to_system = {
        "pyodbc": "unixodbc",
        "soundfile": "libsndfile",
        "cv2": "opencv",
        "PIL": "libjpeg",
        "pycurl": "libcurl",
    }

    # Scan all .py files
    for py_file in project_root.rglob("*.py"):
        if any(
            part in py_file.parts
            for part in ["venv", ".venv", "site-packages", "__pycache__"]
        ):
            continue

        content = _read_file(py_file)
        if not content:
            continue

        # Find imports
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("import ") or line.startswith("from "):
                for imp_name, sys_dep in import_to_system.items():
                    if imp_name in line:
                        dependencies.add(sys_dep)

    return dependencies


# ============================================================================
# ANALYSIS FUNCTIONS
# ============================================================================


def analyze_project(project_root: Path, *, analyze_code: bool = False) -> dict:
    """
    Analyze project files to extract migration information.

    Returns dict with:
        - current_config: existing pyproject.toml or setup.cfg content
        - ci_config: existing CI workflow content
        - system_packages: dict of {platform: [packages]}
        - env_vars: dict of environment variables
        - python_versions: list of Python versions
        - inferred_deps: set of dependencies inferred from code (if analyze_code=True)
    """
    result = {
        "current_config": None,
        "ci_config": None,
        "system_packages": {"linux": [], "macos": [], "windows": []},
        "env_vars": {},
        "python_versions": ["3.10", "3.12"],  # defaults
        "inferred_deps": set(),
    }

    # 1. Read current config
    config_file = _find_file(project_root, "pyproject.toml", "setup.cfg")
    if config_file:
        result["current_config"] = _read_file(config_file)
        result["config_file_name"] = config_file.name
        print(f"✓ Found configuration: {config_file.name}")
    else:
        print("⚠ No pyproject.toml or setup.cfg found")

    # 2. Read CI workflow
    ci_file = _find_file(
        project_root,
        ".github/workflows/ci.yml",
        ".github/workflows/publish.yml",
        ".github/workflows/main.yml",
    )
    if ci_file:
        result["ci_config"] = _read_file(ci_file)
        result["ci_file_name"] = ci_file.name
        print(f"✓ Found CI workflow: {ci_file.name}")

        # Extract info from CI
        ci_content = result["ci_config"]
        if ci_content:
            result["system_packages"]["linux"] = _extract_apt_packages(ci_content)
            result["system_packages"]["macos"] = _extract_brew_packages(ci_content)
            result["env_vars"] = _extract_env_vars(ci_content)
            result["python_versions"] = (
                _extract_python_versions(ci_content) or result["python_versions"]
            )

            print(f"  → Found {len(result['system_packages']['linux'])} Linux packages")
            print(f"  → Found {len(result['system_packages']['macos'])} macOS packages")
            print(f"  → Found {len(result['env_vars'])} environment variables")
            print(
                f"  → Testing Python versions: {', '.join(result['python_versions'])}"
            )
    else:
        print("⚠ No CI workflow found")

    # 3. Optional: Analyze code
    if analyze_code:
        print("\n🔍 Analyzing Python code for dependencies...")
        result["inferred_deps"] = _scan_python_imports(project_root)
        if result["inferred_deps"]:
            print(
                f"  → Inferred {len(result['inferred_deps'])} potential dependencies:"
            )
            for dep in result["inferred_deps"]:
                print(f"    • {dep}")

    return result


def generate_migration_prompt(analysis: dict) -> str:
    """
    Generate the user prompt for Claude based on analysis.
    """
    prompt_parts = [
        "# CI Migration Request",
        "",
        "Please help me migrate this project to wads v3 CI format.",
        "",
    ]

    # Add current config
    if analysis["current_config"]:
        prompt_parts.extend(
            [
                "## Current Configuration",
                "",
                f"**File:** `{analysis['config_file_name']}`",
                "",
                "```toml",
                analysis["current_config"],
                "```",
                "",
            ]
        )

    # Add CI config
    if analysis["ci_config"]:
        prompt_parts.extend(
            [
                "## Current CI Workflow",
                "",
                f"**File:** `.github/workflows/{analysis['ci_file_name']}`",
                "",
                "```yaml",
                analysis["ci_config"],
                "```",
                "",
            ]
        )

    # Add extracted information
    prompt_parts.extend(
        [
            "## Extracted Information",
            "",
        ]
    )

    if any(analysis["system_packages"].values()):
        prompt_parts.append("### System Packages")
        prompt_parts.append("")
        for platform, packages in analysis["system_packages"].items():
            if packages:
                prompt_parts.append(f"**{platform.title()}:** {', '.join(packages)}")
        prompt_parts.append("")

    if analysis["env_vars"]:
        prompt_parts.append("### Environment Variables")
        prompt_parts.append("")
        for key, value in analysis["env_vars"].items():
            prompt_parts.append(f"- `{key}`: {value}")
        prompt_parts.append("")

    if analysis["python_versions"]:
        prompt_parts.append(
            f"**Python Versions:** {', '.join(analysis['python_versions'])}"
        )
        prompt_parts.append("")

    if analysis["inferred_deps"]:
        prompt_parts.extend(
            [
                "### Inferred Dependencies (from code analysis)",
                "",
            ]
        )
        for dep in analysis["inferred_deps"]:
            prompt_parts.append(f"- {dep}")
        prompt_parts.append("")

    # Add instructions
    prompt_parts.extend(
        [
            "## Instructions",
            "",
            "1. Generate a complete, updated `pyproject.toml` that:",
            "   - Declares system dependencies in `[external]` using DepURLs",
            "   - Provides operational metadata in `[tool.wads.external.ops]`",
            "   - Configures `[tool.wads.ci]` sections appropriately",
            "   - Preserves all existing project metadata",
            "",
            "2. For each system dependency:",
            "   - Map it to the appropriate DepURL (dep:generic/{name} or dep:virtual/...)",
            "   - Provide check and install commands for relevant platforms",
            "   - Include rationale and URL where helpful",
            "",
            "3. Explain any decisions or assumptions you made",
            "",
            "4. Highlight any potential issues or improvements",
            "",
            "Please provide the complete updated `pyproject.toml` file.",
        ]
    )

    return "\n".join(prompt_parts)


# ============================================================================
# AGENT TOOLS
# ============================================================================


def _create_tools() -> list[dict]:
    """
    Create tool definitions for the agent.

    In a real implementation, these would be actual callable tools.
    For this example, we'll define them as specifications.
    """
    return [
        {
            "name": "read_file",
            "description": "Read the contents of a file from the project",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path to the file from project root",
                    }
                },
                "required": ["path"],
            },
        },
        {
            "name": "list_directory",
            "description": "List files in a directory",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path to directory from project root",
                    },
                    "pattern": {
                        "type": "string",
                        "description": "Optional glob pattern to filter files",
                    },
                },
                "required": ["path"],
            },
        },
        {
            "name": "validate_depurl",
            "description": "Validate if a string is a properly formatted DepURL",
            "input_schema": {
                "type": "object",
                "properties": {
                    "depurl": {
                        "type": "string",
                        "description": "The DepURL to validate",
                    }
                },
                "required": ["depurl"],
            },
        },
    ]


# ============================================================================
# MAIN AGENT FUNCTION
# ============================================================================


def run_migration_agent(
    project_root: Path, *, analyze_code: bool = False, api_key: Optional[str] = None
) -> None:
    """
    Run the CI migration agent on a project.

    Args:
        project_root: Path to the project directory
        analyze_code: Whether to analyze Python code for dependency inference
        api_key: Anthropic API key (uses ANTHROPIC_API_KEY env var if not provided)
    """
    try:
        from anthropic import Anthropic
    except ImportError:
        print("Error: anthropic package not installed")
        print("Install with: pip install anthropic")
        sys.exit(1)

    print(f"\n{'=' * 70}")
    print(f"CI Migration Agent - Wads v3")
    print(f"{'=' * 70}\n")
    print(f"Project: {project_root.absolute()}")
    print(f"Code analysis: {'enabled' if analyze_code else 'disabled'}")
    print(f"\n{'-' * 70}\n")

    # 1. Analyze project
    print("📋 Analyzing project files...\n")
    analysis = analyze_project(project_root, analyze_code=analyze_code)

    # 2. Generate prompt
    print(f"\n{'-' * 70}\n")
    print("📝 Generating migration prompt...\n")
    user_prompt = generate_migration_prompt(analysis)

    # 3. Call Claude
    print(f"\n{'-' * 70}\n")
    print("🤖 Consulting Claude for migration...\n")

    client = Anthropic(api_key=api_key)

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    # 4. Display results
    print(f"\n{'-' * 70}\n")
    print("✅ Migration Analysis Complete\n")
    print(f"{'=' * 70}\n")

    # Extract the response text
    response_text = response.content[0].text

    print(response_text)

    print(f"\n{'=' * 70}\n")

    # 5. Save results
    output_file = project_root / "pyproject.toml.migrated"

    # Extract code blocks from response
    code_blocks = re.findall(r"```(?:toml)?\n(.*?)```", response_text, re.DOTALL)

    if code_blocks:
        # Save the first/largest code block
        largest_block = max(code_blocks, key=len)
        output_file.write_text(largest_block, encoding="utf-8")
        print(f"📄 Migrated config saved to: {output_file}")
        print(f"\nNext steps:")
        print(f"1. Review the migrated configuration: {output_file}")
        print(f"2. Compare with your current pyproject.toml")
        print(f"3. When ready, replace: mv {output_file} {project_root}/pyproject.toml")
        print(f"4. Update your CI workflow to use the v3 template")
    else:
        print("⚠ No TOML code block found in response")
        print("Full response saved to: migration_response.txt")
        (project_root / "migration_response.txt").write_text(
            response_text, encoding="utf-8"
        )


# ============================================================================
# CLI
# ============================================================================


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Migrate a project to wads v3 CI format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic migration
  python wads_ci_migration_agent.py /path/to/project
  
  # With code analysis
  python wads_ci_migration_agent.py /path/to/project --analyze-code
  
  # Using current directory
  python wads_ci_migration_agent.py .
        """,
    )

    parser.add_argument("project_root", type=Path, help="Path to the project directory")

    parser.add_argument(
        "--analyze-code",
        action="store_true",
        help="Analyze Python code to infer system dependencies",
    )

    parser.add_argument(
        "--api-key",
        type=str,
        help="Anthropic API key (defaults to ANTHROPIC_API_KEY env var)",
    )

    args = parser.parse_args()

    # Validate project root
    if not args.project_root.exists():
        print(f"Error: Project directory not found: {args.project_root}")
        sys.exit(1)

    if not args.project_root.is_dir():
        print(f"Error: Not a directory: {args.project_root}")
        sys.exit(1)

    # Run agent
    run_migration_agent(
        args.project_root, analyze_code=args.analyze_code, api_key=args.api_key
    )


if __name__ == "__main__":
    main()
