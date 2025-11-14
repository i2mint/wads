"""
Analyze real GitHub Actions workflows from i2mint projects.

This script demonstrates analyzing actual CI files from GitHub repositories
to help with migration planning.
"""

import requests
from wads.github_ci_ops import GitHubWorkflow, compare_workflows
from wads.ci_migration import (
    diagnose_migration,
    create_migration_report,
    get_migration_checklist,
)
from wads import github_ci_publish_2025_path


def fetch_ci_from_url(url: str) -> str:
    """Fetch CI file content from a GitHub raw URL."""
    response = requests.get(url)
    response.raise_for_status()
    return response.text


# CI file URLs
ci_files = {
    "oldest (hum)": "https://raw.githubusercontent.com/i2mint/hum/refs/heads/master/.github/workflows/ci.yml",
    "old (extrude)": "https://raw.githubusercontent.com/i2mint/extrude/refs/heads/master/.github/workflows/ci.yml",
    "newish (dol)": "https://raw.githubusercontent.com/i2mint/dol/refs/heads/master/.github/workflows/ci.yml",
    "new (pyrompt)": "https://raw.githubusercontent.com/thorwhalen/pyrompt/refs/heads/main/.github/workflows/ci.yml",
}

print("=" * 80)
print("ANALYZING REAL CI FILES FROM GITHUB")
print("=" * 80)
print()

# Fetch all CI files
workflows = {}
for name, url in ci_files.items():
    print(f"Fetching {name}...")
    try:
        content = fetch_ci_from_url(url)
        workflows[name] = GitHubWorkflow(content)
        print(f"  ✓ Success - {len(content)} bytes")
    except Exception as e:
        print(f"  ✗ Error: {e}")
        continue

print()
print("=" * 80)
print("WORKFLOW SUMMARIES")
print("=" * 80)
print()

from wads.github_ci_ops import summarize_workflow

for name, wf in workflows.items():
    print(f"\n{name.upper()}:")
    print("-" * 40)
    summary = summarize_workflow(wf)
    print(f"  Name: {summary['name']}")
    print(f"  Triggers: {summary['triggers']}")
    print(f"  Env vars: {summary['env_vars']}")
    print(f"  Jobs: {list(summary['jobs'].keys())}")
    for job_name, job_info in summary["jobs"].items():
        print(
            f"    - {job_name}: {job_info['steps_count']} steps on {job_info['runs_on']}"
        )

print()
print("=" * 80)
print("MIGRATION ANALYSIS: Each project → 2025 template")
print("=" * 80)

# Analyze migration from each old CI to the new template
for name, wf in workflows.items():
    if name == "new (pyrompt)":
        # Skip the newest one - it's already similar to the template
        continue

    print()
    print("=" * 80)
    print(f"MIGRATION ANALYSIS: {name.upper()}")
    print("=" * 80)
    print()

    # Extract project name from env if available
    project_name = wf.get("env", {}).get("PROJECT_NAME", "unknown")
    if "#PROJECT_NAME#" in str(project_name):
        project_name = name.split("(")[1].strip(")")  # Extract from label

    # Diagnose migration
    diagnosis = diagnose_migration(
        wf, github_ci_publish_2025_path, project_name=project_name
    )

    # Generate report
    report = create_migration_report(diagnosis, verbose=False)
    print(report)

    # Show checklist
    print("\nMIGRATION CHECKLIST:")
    print("-" * 80)
    checklist = get_migration_checklist(diagnosis)
    for item in checklist[:7]:  # Show first 7 items
        print(item)
    print()

print("=" * 80)
print("COMPARISON: Oldest vs Newest")
print("=" * 80)
print()

if "oldest (hum)" in workflows and "new (pyrompt)" in workflows:
    oldest = workflows["oldest (hum)"]
    newest = workflows["new (pyrompt)"]

    diff = compare_workflows(oldest, newest)

    print("High-level differences between oldest and newest CI:")
    print()
    print(f"Added in new: {list(diff.get('added', {}).keys())}")
    print(f"Removed from old: {list(diff.get('removed', {}).keys())}")
    print(f"Modified: {list(diff.get('modified', {}).keys())}")
    print()

    # Show job differences
    if "jobs" in diff.get("modified", {}):
        jobs_diff = diff["modified"]["jobs"]
        print("Job changes:")
        print(f"  Jobs added: {list(jobs_diff.get('added', {}).keys())}")
        print(f"  Jobs removed: {list(jobs_diff.get('removed', {}).keys())}")
        print(f"  Jobs modified: {list(jobs_diff.get('modified', {}).keys())}")

print()
print("=" * 80)
print("ANALYSIS COMPLETE")
print("=" * 80)
print()
print("Next steps:")
print("1. Review the migration reports for each project")
print("2. Identify custom steps that need to be preserved")
print("3. Update CI files using the 2025 template")
print("4. Test in a branch before merging")
