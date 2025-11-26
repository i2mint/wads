"""
CI Debugging Agent for Wads

This agent analyzes failed CI runs, diagnoses issues, and proposes fixes.
It can:
- Fetch GitHub Actions logs via API
- Parse test failures and error messages
- Analyze code context
- Diagnose root causes (missing deps, config issues, code bugs)
- Propose fixes (install commands, code changes, config updates)

Usage:
    python -m wads.ci_debug_agent <repo> [--run-id RUN_ID] [--fix]
"""

import os
import sys
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import subprocess

try:
    import requests
except ImportError:
    requests = None

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None


@dataclass
class TestFailure:
    """Represents a single test failure."""

    test_name: str
    error_type: str
    error_message: str
    traceback: List[str]
    file_path: Optional[str] = None
    line_number: Optional[int] = None


@dataclass
class CIDiagnosis:
    """Result of CI failure diagnosis."""

    failures: List[TestFailure]
    missing_system_deps: List[str]
    missing_python_deps: List[str]
    config_issues: List[str]
    proposed_fixes: List[Dict[str, str]]
    confidence: str  # 'high', 'medium', 'low'


def get_github_token() -> Optional[str]:
    """Get GitHub token from environment."""
    return os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_TOKEN')


def fetch_workflow_runs(repo: str, limit: int = 5) -> List[Dict]:
    """
    Fetch recent workflow runs for a repository.

    Args:
        repo: Repository in format 'owner/name'
        limit: Number of runs to fetch

    Returns:
        List of workflow run dictionaries
    """
    if not requests:
        raise ImportError(
            "requests library required. Install with: pip install requests"
        )

    token = get_github_token()
    if not token:
        raise ValueError("GITHUB_TOKEN environment variable required")

    url = f"https://api.github.com/repos/{repo}/actions/runs"
    headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.v3+json',
    }

    response = requests.get(url, headers=headers, params={'per_page': limit})
    response.raise_for_status()

    return response.json()['workflow_runs']


def fetch_workflow_logs(repo: str, run_id: int) -> str:
    """
    Fetch logs for a specific workflow run.

    Args:
        repo: Repository in format 'owner/name'
        run_id: Workflow run ID

    Returns:
        Log content as string
    """
    if not requests:
        raise ImportError(
            "requests library required. Install with: pip install requests"
        )

    token = get_github_token()
    if not token:
        raise ValueError("GITHUB_TOKEN environment variable required")

    url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/logs"
    headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.v3+json',
    }

    response = requests.get(url, headers=headers)
    response.raise_for_status()

    return response.text


def parse_pytest_failures(logs: str) -> List[TestFailure]:
    """
    Parse pytest failures from CI logs.

    Args:
        logs: CI log content

    Returns:
        List of TestFailure objects
    """
    failures = []

    # Pattern for pytest failures (even broader: error_type can be anything, non-greedy)
    failure_pattern = re.compile(r'^FAILED\s+(.+?)\s+-\s+(.+?):\s+(.+)$', re.MULTILINE)

    # Fallback: match lines like 'FAILED <test> - <error>'
    fallback_pattern = re.compile(r'^FAILED\s+(.+?)\s+-\s+(.+)$', re.MULTILINE)

    # Pattern for tracebacks
    traceback_pattern = re.compile(r'File\s+"(.+?)",\s+line\s+(\d+)', re.MULTILINE)

    found = set()

    for match in failure_pattern.finditer(logs):
        test_name = match.group(1)
        error_type = match.group(2)
        error_message = match.group(3)
        found.add(test_name)

        # Try to extract traceback
        start = max(0, match.start() - 1000)
        end = min(len(logs), match.end() + 2000)
        context = logs[start:end]

        traceback = []
        file_path = None
        line_number = None

        for tb_match in traceback_pattern.finditer(context):
            file_path = tb_match.group(1)
            line_number = int(tb_match.group(2))
            traceback.append(f"  File \"{file_path}\", line {line_number}")

        failures.append(
            TestFailure(
                test_name=test_name,
                error_type=error_type,
                error_message=error_message,
                traceback=traceback,
                file_path=file_path,
                line_number=line_number,
            )
        )

    # Fallback: catch any other 'FAILED ... - ...' lines not already matched
    for match in fallback_pattern.finditer(logs):
        test_name = match.group(1)
        if test_name in found:
            continue
        error_info = match.group(2)
        # Try to split error_info into error_type and error_message
        if ': ' in error_info:
            error_type, error_message = error_info.split(': ', 1)
        else:
            error_type, error_message = error_info, ''

        # Try to extract traceback
        start = max(0, match.start() - 1000)
        end = min(len(logs), match.end() + 2000)
        context = logs[start:end]

        traceback = []
        file_path = None
        line_number = None

        for tb_match in traceback_pattern.finditer(context):
            file_path = tb_match.group(1)
            line_number = int(tb_match.group(2))
            traceback.append(f"  File \"{file_path}\", line {line_number}")

        failures.append(
            TestFailure(
                test_name=test_name,
                error_type=error_type,
                error_message=error_message,
                traceback=traceback,
                file_path=file_path,
                line_number=line_number,
            )
        )
    failures = []

    # Pattern for pytest failures (even broader: error_type can be anything, non-greedy)
    failure_pattern = re.compile(r'^FAILED\s+(.+?)\s+-\s+(.+?):\s+(.+)$', re.MULTILINE)

    # Fallback: match any line starting with 'FAILED'
    fallback_pattern = re.compile(r'^FAILED\s+(.+)$', re.MULTILINE)

    # Pattern for tracebacks
    traceback_pattern = re.compile(r'File\s+"(.+?)",\s+line\s+(\d+)', re.MULTILINE)

    found = set()

    # DEBUG: Print all lines starting with 'FAILED'
    failed_lines = [
        line for line in logs.splitlines() if line.strip().startswith('FAILED')
    ]
    if failed_lines:
        print("[DEBUG] Lines starting with 'FAILED':")
        for line in failed_lines:
            print("[DEBUG]", line)
    else:
        print("[DEBUG] No lines starting with 'FAILED' found in logs.")

    for match in failure_pattern.finditer(logs):
        test_name = match.group(1)
        error_type = match.group(2)
        error_message = match.group(3)
        found.add(test_name)

        # Try to extract traceback
        start = max(0, match.start() - 1000)
        end = min(len(logs), match.end() + 2000)
        context = logs[start:end]

        traceback = []
        file_path = None
        line_number = None

        for tb_match in traceback_pattern.finditer(context):
            file_path = tb_match.group(1)
            line_number = int(tb_match.group(2))
            traceback.append(f"  File \"{file_path}\", line {line_number}")

        failures.append(
            TestFailure(
                test_name=test_name,
                error_type=error_type,
                error_message=error_message,
                traceback=traceback,
                file_path=file_path,
                line_number=line_number,
            )
        )

    # Fallback: catch any other 'FAILED ...' lines not already matched
    for match in fallback_pattern.finditer(logs):
        line = match.group(1)
        # Try to parse as 'test_name - error_type: error_message'
        dash_idx = line.find(' - ')
        if dash_idx != -1:
            test_name = line[:dash_idx]
            error_info = line[dash_idx + 3 :]
            if test_name in found:
                continue
            if ': ' in error_info:
                error_type, error_message = error_info.split(': ', 1)
            else:
                error_type, error_message = error_info, ''
        else:
            # If no dash, treat the whole line as error_type
            test_name = ''
            error_type = line
            error_message = ''

        # Try to extract traceback
        # Use the match position if available, else search whole logs
        start = 0
        end = len(logs)
        context = logs[start:end]

        traceback = []
        file_path = None
        line_number = None

        for tb_match in traceback_pattern.finditer(context):
            file_path = tb_match.group(1)
            line_number = int(tb_match.group(2))
            traceback.append(f"  File \"{file_path}\", line {line_number}")

        failures.append(
            TestFailure(
                test_name=test_name,
                error_type=error_type,
                error_message=error_message,
                traceback=traceback,
                file_path=file_path,
                line_number=line_number,
            )
        )

    return failures


def print_diagnosis(diagnosis: CIDiagnosis):
    """Print formatted diagnosis report."""
    print("\n" + "=" * 70)
    print("CI FAILURE DIAGNOSIS")
    print("=" * 70)

    print(f"\nConfidence: {diagnosis.confidence.upper()}")

    if diagnosis.failures:
        print(f"\n❌ Test Failures ({len(diagnosis.failures)}):")
        for i, failure in enumerate(diagnosis.failures[:5], 1):  # Show first 5
            print(f"\n{i}. {failure.test_name}")
            print(f"   Error: {failure.error_type}")
            print(f"   Message: {failure.error_message[:200]}")
            if failure.file_path:
                print(f"   Location: {failure.file_path}:{failure.line_number}")

        if len(diagnosis.failures) > 5:
            print(f"\n   ... and {len(diagnosis.failures) - 5} more failures")

    if diagnosis.missing_system_deps:
        print(f"\n🔧 Missing System Dependencies:")
        for dep in diagnosis.missing_system_deps:
            print(f"  • {dep}")

    if diagnosis.missing_python_deps:
        print(f"\n📦 Missing Python Dependencies:")
        for dep in diagnosis.missing_python_deps:
            print(f"  • {dep}")

    if diagnosis.config_issues:
        print(f"\n⚠️  Configuration Issues:")
        for issue in diagnosis.config_issues:
            print(f"  • {issue}")

    if diagnosis.proposed_fixes:
        print(f"\n💡 Proposed Fixes:")
        for i, fix in enumerate(diagnosis.proposed_fixes, 1):
            print(f"\n{i}. {fix['description']}")
            print(f"   Type: {fix['type']}")
            print(f"   Action: {fix['action']}")
            if 'packages' in fix:
                print(f"   Packages: {', '.join(fix['packages'])}")

    print("\n" + "=" * 70)


# Restore diagnose_missing_system_deps and diagnose_missing_python_deps
def diagnose_missing_system_deps(failures: List[TestFailure], logs: str) -> List[str]:
    """
    Identify missing system dependencies from error messages.

    Args:
        failures: List of test failures
        logs: Full CI logs

    Returns:
        List of likely missing system dependencies
    """
    missing_deps = set()

    # Common patterns for missing system dependencies
    patterns = {
        'unixodbc': [
            r"Can't open lib.*ODBC.*Driver",
            r"libodbc.*not found",
            r"ODBC.*driver.*not found",
        ],
        'msodbcsql17': [r"ODBC Driver 17 for SQL Server.*not found"],
        'msodbcsql18': [r"ODBC Driver 18 for SQL Server.*not found"],
        'ffmpeg': [r"ffmpeg.*not found", r"libav.*not found"],
        'libsndfile': [r"libsndfile.*not found", r"sndfile.*not found"],
        'portaudio': [r"portaudio.*not found", r"libportaudio.*not found"],
    }

    # Check failures and logs
    all_text = logs + '\n' + '\n'.join(f.error_message for f in failures)

    for dep, patterns_list in patterns.items():
        for pattern in patterns_list:
            if re.search(pattern, all_text, re.IGNORECASE):
                missing_deps.add(dep)
                break

    return sorted(missing_deps)


def diagnose_missing_python_deps(failures: List[TestFailure]) -> List[str]:
    """
    Identify missing Python dependencies from import errors.

    Args:
        failures: List of test failures

    Returns:
        List of likely missing Python packages
    """
    missing_deps = set()

    import_pattern = re.compile(r"ModuleNotFoundError: No module named '(.+?)'")

    for failure in failures:
        match = import_pattern.search(failure.error_message)
        if match:
            module = match.group(1).split('.')[0]  # Get top-level package
            missing_deps.add(module)

    return sorted(missing_deps)


def generate_fix_instructions(diagnosis: CIDiagnosis, repo_path: Path) -> str:
    """
    Generate detailed fix instructions.

    Args:
        diagnosis: CIDiagnosis result
        repo_path: Local path to repository

    Returns:
        Formatted fix instructions
    """
    lines = []

    lines.append("=" * 70)
    lines.append("FIX INSTRUCTIONS")
    lines.append("=" * 70)
    lines.append("")

    if diagnosis.missing_system_deps:
        lines.append("## Fix System Dependencies")
        lines.append("")
        lines.append("### Option 1: Use PEP 725 format (recommended)")
        lines.append("")
        lines.append("Add to your `pyproject.toml`:")
        lines.append("")
        lines.append("[external]")
        lines.append("host-requires = [")
        for dep in diagnosis.missing_system_deps:
            lines.append(f'    "dep:generic/{dep}",')
        lines.append("]")
        lines.append("")

        lines.append("Then add operational metadata for each:")
        for dep in diagnosis.missing_system_deps:
            lines.append(f"")
            lines.append(f"[tool.wads.external.ops.{dep}]")
            lines.append(f'canonical_id = "dep:generic/{dep}"')
            lines.append(f'rationale = "Description of why {dep} is needed"')
            lines.append(f'install.linux = "sudo apt-get install -y {dep}"')

        lines.append("")
        lines.append("### Option 2: Manual CI fix")
        lines.append("")
        lines.append("Add this step to `.github/workflows/ci.yml`")
        lines.append("after 'Set up Python' step:")
        lines.append("")
        lines.append("```yaml")
        lines.append("      - name: Install System Dependencies")
        lines.append("        run: |")
        for dep in diagnosis.missing_system_deps:
            if dep == 'msodbcsql18':
                lines.append(
                    "          curl https://packages.microsoft.com/keys/microsoft.asc | sudo apt-key add -"
                )
                lines.append(
                    "          curl https://packages.microsoft.com/config/ubuntu/$(lsb_release -rs)/prod.list | sudo tee /etc/apt/sources.list.d/mssql-release.list"
                )
                lines.append("          sudo apt-get update")
                lines.append(
                    "          sudo ACCEPT_EULA=Y apt-get install -y msodbcsql18"
                )
            elif dep == 'unixodbc':
                lines.append("          sudo apt-get update")
                lines.append("          sudo apt-get install -y unixodbc unixodbc-dev")
            else:
                lines.append(f"          sudo apt-get install -y {dep}")
        lines.append("```")
        lines.append("")

    if diagnosis.missing_python_deps:
        lines.append("## Fix Python Dependencies")
        lines.append("")
        lines.append("Add to `[project.dependencies]` in `pyproject.toml`:")
        lines.append("")
        for dep in diagnosis.missing_python_deps:
            lines.append(f'    "{dep}",')
        lines.append("")

    lines.append("=" * 70)

    return '\n'.join(lines)


# Restore diagnose_ci_failure function
def diagnose_ci_failure(repo: str, run_id: Optional[int] = None) -> CIDiagnosis:
    """
    Diagnose a CI failure.

    Args:
        repo: Repository in format 'owner/name'
        run_id: Specific run ID, or None for latest failed run

    Returns:
        CIDiagnosis with analysis results
    """
    # Fetch run info
    if run_id is None:
        runs = fetch_workflow_runs(repo, limit=10)
        # Find first failed run
        failed_run = next((r for r in runs if r['conclusion'] == 'failure'), None)
        if not failed_run:
            raise ValueError("No failed runs found")
        run_id = failed_run['id']
        print(f"Analyzing failed run: {run_id} - {failed_run['name']}")

    # Fetch logs
    print(f"Fetching logs for run {run_id}...")
    logs = fetch_workflow_logs(repo, run_id)

    # Parse failures
    failures = parse_pytest_failures(logs)
    print(f"Found {len(failures)} test failures")

    # Diagnose issues
    missing_system_deps = diagnose_missing_system_deps(failures, logs)
    missing_python_deps = diagnose_missing_python_deps(failures)

    config_issues = []
    proposed_fixes = []

    # Generate fix proposals
    if missing_system_deps:
        config_issues.append(
            f"Missing system dependencies: {', '.join(missing_system_deps)}"
        )

        # Check if pyproject.toml needs updating
        proposed_fixes.append(
            {
                'type': 'config',
                'description': 'Add missing system dependencies to pyproject.toml',
                'action': 'Add [external] and [tool.wads.external.ops] sections',
                'packages': missing_system_deps,
            }
        )

        # Also propose CI workflow fix
        proposed_fixes.append(
            {
                'type': 'workflow',
                'description': 'Add system dependency installation to CI workflow',
                'action': 'Add installation step before tests',
                'packages': missing_system_deps,
            }
        )

    if missing_python_deps:
        config_issues.append(
            f"Missing Python dependencies: {', '.join(missing_python_deps)}"
        )

        proposed_fixes.append(
            {
                'type': 'dependencies',
                'description': 'Add missing Python packages to pyproject.toml',
                'action': 'Add to [project.dependencies] or [project.optional-dependencies]',
                'packages': missing_python_deps,
            }
        )

    # Determine confidence
    if missing_system_deps or missing_python_deps:
        confidence = 'high'
    elif failures:
        confidence = 'medium'
    else:
        confidence = 'low'

    return CIDiagnosis(
        failures=failures,
        missing_system_deps=missing_system_deps,
        missing_python_deps=missing_python_deps,
        config_issues=config_issues,
        proposed_fixes=proposed_fixes,
        confidence=confidence,
    )


# CLI interface
def main():
    """CLI entry point for wads CI debug agent."""
    import argparse

    parser = argparse.ArgumentParser(description='Diagnose and fix CI failures')
    parser.add_argument('repo', help='Repository in format owner/name')
    parser.add_argument('--run-id', type=int, help='Specific workflow run ID')
    parser.add_argument('--fix', action='store_true', help='Generate fix instructions')
    parser.add_argument('--local-repo', help='Path to local repository clone')

    args = parser.parse_args()

    try:
        # Diagnose
        diagnosis = diagnose_ci_failure(args.repo, args.run_id)
        print_diagnosis(diagnosis)

        # Generate fix instructions
        if args.fix:
            repo_path = Path(args.local_repo) if args.local_repo else Path.cwd()
            instructions = generate_fix_instructions(diagnosis, repo_path)
            print("\n")
            print(instructions)

            # Save to file
            fix_file = repo_path / 'CI_FIX_INSTRUCTIONS.md'
            with open(fix_file, 'w') as f:
                f.write(instructions)
            print(f"\n✓ Fix instructions saved to: {fix_file}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
