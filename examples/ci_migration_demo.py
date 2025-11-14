"""
Demo script showing how to use the CI migration tools.

This script demonstrates:
1. Parsing GitHub Actions workflows
2. Comparing old and new CI scripts
3. Diagnosing migration needs
4. Generating migration reports
"""

from wads.github_ci_ops import GitHubWorkflow, compare_workflows, summarize_workflow
from wads.ci_migration import (
    diagnose_migration,
    create_migration_report,
    get_migration_checklist,
)
from wads import github_ci_publish_2025_path

# Example 1: Parse a workflow
print("=" * 80)
print("Example 1: Parsing a workflow")
print("=" * 80)

old_ci_yaml = """
name: CI
on: [push, pull_request]

env:
  PROJECT_NAME: myproject

jobs:
  validation:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.8", "3.10"]

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install dependencies
        run: |
          pip install -e .[test]

      - name: Format with Black
        run: |
          pip install black
          black --line-length 88 .

      - name: Lint with Pylint
        run: |
          pip install pylint
          pylint myproject

      - name: Test with pytest
        run: |
          pytest
"""

workflow = GitHubWorkflow(old_ci_yaml)
print(f"Workflow name: {workflow['name']}")
print(f"Jobs: {list(workflow['jobs'].keys())}")
print()

# Example 2: Summarize a workflow
print("=" * 80)
print("Example 2: Workflow summary")
print("=" * 80)

summary = summarize_workflow(workflow)
print(f"Name: {summary['name']}")
print(f"Triggers: {summary['triggers']}")
print(f"Jobs: {summary['jobs']}")
print()

# Example 3: Compare two workflows
print("=" * 80)
print("Example 3: Compare workflows")
print("=" * 80)

new_template = GitHubWorkflow(github_ci_publish_2025_path)
diff = compare_workflows(workflow, new_template)

print("Added keys:", list(diff.get("added", {}).keys()))
print("Removed keys:", list(diff.get("removed", {}).keys()))
print("Modified keys:", list(diff.get("modified", {}).keys()))
print()

# Example 4: Diagnose migration
print("=" * 80)
print("Example 4: Migration diagnosis")
print("=" * 80)

diagnosis = diagnose_migration(
    old_ci_yaml, github_ci_publish_2025_path, project_name="myproject"
)

print(f"Critical issues: {len(diagnosis.critical_issues)}")
print(f"Warnings: {len(diagnosis.warnings)}")
print(f"Info items: {len(diagnosis.info)}")
print()

# Example 5: Generate migration report
print("=" * 80)
print("Example 5: Migration report")
print("=" * 80)

report = create_migration_report(diagnosis, verbose=False)
print(report)
print()

# Example 6: Get migration checklist
print("=" * 80)
print("Example 6: Migration checklist")
print("=" * 80)

checklist = get_migration_checklist(diagnosis)
for item in checklist:
    print(item)
print()

# Example 7: Test with comment preservation
print("=" * 80)
print("Example 7: Comment preservation")
print("=" * 80)

yaml_with_comments = """
# Main CI workflow
name: CI

# Run on all pushes and PRs
on: [push, pull_request]

env:
  # Project name - IMPORTANT: update this!
  PROJECT_NAME: myproject

jobs:
  validation:
    # This job validates the code
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
"""

wf = GitHubWorkflow(yaml_with_comments)
# Modify it
wf["env"]["PROJECT_NAME"] = "newproject"
# Convert back to YAML - comments should be preserved
output = wf.to_yaml()
print("Output YAML (comments preserved):")
print(output)
print()

print("=" * 80)
print("Demo complete!")
print("=" * 80)
