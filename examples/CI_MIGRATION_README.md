# GitHub CI Migration Tools

This document describes the new GitHub CI analysis and migration tools added to wads.

## Overview

Two new modules have been added to help with analyzing and migrating GitHub Actions workflows:

1. **`wads.github_ci_ops`** - Core operations for parsing, comparing, and manipulating GitHub Actions YAML files
2. **`wads.ci_migration`** - Migration diagnosis and reporting tools

## Key Features

### Comment Preservation
Uses `ruamel.yaml` to preserve comments and formatting when parsing and modifying YAML files.

### Flexible Parsing
Parse workflows from:
- File paths
- YAML strings
- Python dicts

### Nested Structure Comparison
Deep comparison of nested dictionaries with configurable equivalence functions.

### Migration Rules
Extensible rule system to identify what needs attention during migration.

## Installation

The new modules require `ruamel.yaml`:

```bash
pip install ruamel.yaml
```

## Quick Start

### 1. Parse a Workflow

```python
from wads.github_ci_ops import GitHubWorkflow

# From file
wf = GitHubWorkflow('path/to/ci.yml')

# From YAML string
yaml_str = """
name: CI
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
"""
wf = GitHubWorkflow(yaml_str)

# Access as a dict
print(wf['name'])  # CI
print(wf['jobs'].keys())  # dict_keys(['test'])

# Convert back to YAML (preserves comments!)
print(wf.to_yaml())
```

### 2. Compare Workflows

```python
from wads.github_ci_ops import compare_workflows

old = GitHubWorkflow('old_ci.yml')
new = GitHubWorkflow('new_ci.yml')

diff = compare_workflows(old, new)

print(diff['added'])     # Keys present in new but not old
print(diff['removed'])   # Keys present in old but not new
print(diff['modified'])  # Keys present in both but different
```

### 3. Diagnose Migration

```python
from wads.ci_migration import diagnose_migration, create_migration_report
from wads import github_ci_publish_2025_path

# Diagnose what needs to change
diagnosis = diagnose_migration(
    'old_ci.yml',
    github_ci_publish_2025_path,
    project_name='myproject'
)

# Generate a human-readable report
report = create_migration_report(diagnosis)
print(report)

# Get an actionable checklist
from wads.ci_migration import get_migration_checklist
checklist = get_migration_checklist(diagnosis)
for item in checklist:
    print(item)
```

## Module Reference

### `wads.github_ci_ops`

#### Classes

- **`GitHubWorkflow`**: Mapping view of a GitHub Actions workflow with comment preservation
  - `__init__(src)`: Parse from file path, YAML string, or dict
  - `to_yaml()`: Convert back to YAML string
  - `to_dict()`: Convert to plain dict (loses comments)
  - `save(path)`: Save to file

#### Functions

- **`compare_workflows(old, new, **options)`**: Compare two workflows
  - `focus_keys`: Only compare these top-level keys
  - `ignore_keys`: Ignore these top-level keys
  - `equivalence_func`: Custom equivalence function

- **`diff_nested(old, new, **options)`**: General nested structure comparison

- **`summarize_workflow(workflow)`**: High-level summary of a workflow

- **`extract_job_names(workflow)`**: Get list of job names

- **`extract_steps(workflow, job_name)`**: Get steps from a job

- **`find_step_by_name(workflow, job_name, step_name)`**: Find specific step

- **`get_workflow_env_vars(workflow)`**: Extract environment variables

### `wads.ci_migration`

#### Classes

- **`MigrationRule`**: Defines a migration rule
  - `name`: Rule identifier
  - `description`: What it checks
  - `check_func`: Function that performs the check
  - `severity`: 'critical', 'warning', or 'info'

- **`MigrationDiagnosis`**: Results of migration analysis
  - `old_workflow`: Old workflow object
  - `new_workflow`: New workflow/template
  - `raw_diff`: Raw comparison diff
  - `rule_findings`: Results from each rule
  - `critical_issues`: Critical items
  - `warnings`: Warning items
  - `info`: Informational items
  - `summary`: High-level summary

#### Functions

- **`diagnose_migration(old_ci, new_template, **options)`**: Analyze migration
  - `rules`: Custom migration rules
  - `project_name`: Project name to substitute

- **`create_migration_report(diagnosis, verbose=False)`**: Generate report

- **`get_migration_checklist(diagnosis)`**: Get actionable checklist

#### Built-in Migration Rules

1. **project_name** (critical): Check PROJECT_NAME configuration
2. **python_versions** (info): Check Python version changes
3. **custom_steps** (warning): Identify custom steps to review
4. **dependencies** (warning): Check dependency approach (setup.cfg vs pyproject.toml)
5. **formatting_linting** (info): Check tool changes (Black/Pylint → Ruff)
6. **secrets** (info): Identify required secrets

## Examples

See the `examples/` directory:

- **`ci_migration_demo.py`**: Basic demonstrations of all features
- **`analyze_real_ci_files.py`**: Analyze actual CI files from GitHub repositories

Run them:

```bash
python examples/ci_migration_demo.py
python examples/analyze_real_ci_files.py
```

## Advanced Usage

### Custom Migration Rules

```python
from wads.ci_migration import MigrationRule, diagnose_migration

def check_custom_feature(old, new):
    """Check for custom feature usage."""
    has_feature = 'my-custom-action' in str(old)
    return {
        'status': 'warning' if has_feature else 'ok',
        'message': 'Custom action found' if has_feature else 'OK'
    }

custom_rule = MigrationRule(
    name='custom_feature',
    description='Check for custom feature',
    check_func=check_custom_feature,
    severity='warning'
)

diagnosis = diagnose_migration(
    'old.yml',
    'new.yml',
    rules=[custom_rule]
)
```

### Custom Equivalence Functions

```python
from wads.github_ci_ops import compare_workflows

def ignore_version_changes(a, b):
    """Consider versions equivalent if they're both valid."""
    if isinstance(a, str) and isinstance(b, str):
        # Treat all version strings as equivalent
        if a.startswith('v') and b.startswith('v'):
            return True
    return a == b

diff = compare_workflows(
    old,
    new,
    equivalence_func=ignore_version_changes
)
```

### Working with Comments

```python
from wads.github_ci_ops import GitHubWorkflow

yaml_with_comments = """
# Important workflow
name: CI

env:
  # Project name - update this!
  PROJECT_NAME: myproject
"""

wf = GitHubWorkflow(yaml_with_comments)

# Modify
wf['env']['PROJECT_NAME'] = 'newproject'

# Comments are preserved!
print(wf.to_yaml())
# Output includes original comments
```

## Use Cases

### 1. Batch Migration Analysis

Analyze all your projects' CIs against a new template:

```python
from wads.ci_migration import diagnose_migration, create_migration_report
from wads import github_ci_publish_2025_path

repos = ['repo1', 'repo2', 'repo3']

for repo in repos:
    ci_path = f'../{repo}/.github/workflows/ci.yml'
    diagnosis = diagnose_migration(ci_path, github_ci_publish_2025_path)

    print(f"\n{'='*80}")
    print(f"REPO: {repo}")
    print('='*80)
    print(create_migration_report(diagnosis))
```

### 2. Extract Custom Configuration

Find all custom environment variables across your CIs:

```python
from wads.github_ci_ops import GitHubWorkflow, get_workflow_env_vars

workflows = [GitHubWorkflow(f) for f in ci_files]
all_env_vars = {}

for wf in workflows:
    env_vars = get_workflow_env_vars(wf)
    for key, value in env_vars.items():
        if key not in all_env_vars:
            all_env_vars[key] = []
        all_env_vars[key].append(value)

print("All environment variables used:")
for key, values in all_env_vars.items():
    print(f"  {key}: {set(values)}")
```

### 3. Progressive Migration

Incrementally migrate by focusing on specific sections:

```python
from wads.github_ci_ops import compare_workflows

# First, just migrate the validation job
diff = compare_workflows(
    old,
    new,
    focus_keys=['jobs']
)

validation_diff = diff['modified']['jobs']['modified']['validation']
print("Changes needed in validation job:", validation_diff)
```

## Migration Workflow

Recommended workflow for migrating CIs:

1. **Analyze**: Run diagnosis on all projects
2. **Review**: Examine reports and identify patterns
3. **Customize**: Add custom rules for project-specific needs
4. **Test**: Migrate one project, test thoroughly
5. **Iterate**: Refine rules based on lessons learned
6. **Batch**: Apply to remaining projects

## Tips

- Always test migrations in a branch first
- Use `verbose=True` in reports for detailed diffs
- Create custom rules for project-specific patterns
- Keep the old CI for reference during transition
- Document any manual steps required

## Future Enhancements

Potential additions:

- Automatic migration (not just analysis)
- Visual diff output (HTML reports)
- Integration with GitHub API to analyze entire organizations
- More sophisticated list/array comparison (LCS algorithm)
- Template inheritance and composition
- Migration rollback support
