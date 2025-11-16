"""
CI Migration - Diagnosis and migration tools for GitHub Actions workflows.

This module provides tools to analyze differences between old CI scripts and new
templates, helping to identify what needs to be carried over during migration.

Key Functions:
    diagnose_migration: Analyze what needs to change when migrating from old to new
    create_migration_report: Generate a human-readable migration report
    apply_migration_rules: Apply customizable rules to identify critical differences

Example:
    >>> from wads.ci_migration import diagnose_migration, create_migration_report
    >>> from wads import github_ci_publish_2025_path
    >>>
    >>> # Diagnose migration for a specific project
    >>> diagnosis = diagnose_migration(  # doctest: +SKIP
    ...     'old_ci.yml',
    ...     github_ci_publish_2025_path
    ... )
    >>>
    >>> # Generate a report
    >>> report = create_migration_report(diagnosis)  # doctest: +SKIP
    >>> print(report)  # doctest: +SKIP
"""

from pathlib import Path
from typing import Union, Optional, Mapping, Any, Callable
from dataclasses import dataclass, field

from wads.github_ci_ops import (
    GitHubWorkflow,
    compare_workflows,
    diff_nested,
    extract_job_names,
    extract_steps,
    get_workflow_env_vars,
    summarize_workflow,
)


# --------------------------------------------------------------------------------------
# Migration rules and configuration
# --------------------------------------------------------------------------------------


@dataclass
class MigrationRule:
    """
    A rule for identifying important differences during migration.

    Attributes:
        name: Human-readable name of the rule
        description: What this rule checks for
        check_func: Function that takes (old_workflow, new_workflow) and returns
            a dict with findings
        severity: 'critical', 'warning', or 'info'
    """

    name: str
    description: str
    check_func: Callable[[Mapping, Mapping], dict]
    severity: str = "info"


@dataclass
class MigrationDiagnosis:
    """
    Results of a migration diagnosis.

    Attributes:
        old_workflow: The old workflow being migrated from
        new_workflow: The new workflow/template being migrated to
        raw_diff: The raw diff from compare_workflows
        rule_findings: Dict of findings from each migration rule
        critical_issues: List of critical issues that must be addressed
        warnings: List of warnings to consider
        info: List of informational items
        summary: Dict summarizing the migration
    """

    old_workflow: GitHubWorkflow
    new_workflow: GitHubWorkflow
    raw_diff: dict
    rule_findings: dict = field(default_factory=dict)
    critical_issues: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    info: list = field(default_factory=list)
    summary: dict = field(default_factory=dict)


# --------------------------------------------------------------------------------------
# Built-in migration rules
# --------------------------------------------------------------------------------------


def rule_check_project_name(old: Mapping, new: Mapping) -> dict:
    """Check if PROJECT_NAME needs to be updated."""
    old_env = get_workflow_env_vars(old)
    new_env = get_workflow_env_vars(new)

    old_name = old_env.get("PROJECT_NAME", "")
    new_name = new_env.get("PROJECT_NAME", "")

    if "#PROJECT_NAME#" in str(new_name):
        return {
            "status": "action_required",
            "message": f"Need to set PROJECT_NAME (was: {old_name})",
            "old_value": old_name,
            "new_value": new_name,
        }
    elif old_name and new_name and old_name != new_name:
        return {
            "status": "changed",
            "message": f"PROJECT_NAME changed from {old_name} to {new_name}",
            "old_value": old_name,
            "new_value": new_name,
        }
    return {"status": "ok"}


def rule_check_python_versions(old: Mapping, new: Mapping) -> dict:
    """Check if Python versions changed."""
    findings = []

    old_jobs = old.get("jobs", {})
    new_jobs = new.get("jobs", {})

    for job_name in set(old_jobs.keys()) | set(new_jobs.keys()):
        old_job = old_jobs.get(job_name, {})
        new_job = new_jobs.get(job_name, {})

        old_matrix = old_job.get("strategy", {}).get("matrix", {})
        new_matrix = new_job.get("strategy", {}).get("matrix", {})

        old_versions = old_matrix.get("python-version", [])
        new_versions = new_matrix.get("python-version", [])

        if old_versions != new_versions:
            findings.append(
                {
                    "job": job_name,
                    "old_versions": old_versions,
                    "new_versions": new_versions,
                    "message": f"Python versions changed in {job_name}: {old_versions} → {new_versions}",
                }
            )

    return {
        "status": "changed" if findings else "ok",
        "findings": findings,
    }


def rule_check_custom_steps(old: Mapping, new: Mapping) -> dict:
    """
    Identify custom steps in old workflow that might need to be carried over.

    Custom steps are those that don't use standard actions from i2mint/wads.
    """
    old_jobs = old.get("jobs", {})
    custom_steps = []

    standard_action_prefixes = [
        "actions/",
        "i2mint/wads/actions/",
        "i2mint/isee/actions/",
        "i2mint/epythet/actions/",
    ]

    for job_name, job in old_jobs.items():
        steps = job.get("steps", [])
        for i, step in enumerate(steps):
            step_name = step.get("name", f"Step {i}")
            uses = step.get("uses", "")

            # Check if it's a custom action
            is_standard = any(
                uses.startswith(prefix) for prefix in standard_action_prefixes
            )

            if uses and not is_standard:
                custom_steps.append(
                    {
                        "job": job_name,
                        "step_name": step_name,
                        "uses": uses,
                        "message": f"Custom action in {job_name}: {step_name} ({uses})",
                    }
                )
            elif "run" in step:
                # Check for custom run commands
                run_cmd = step["run"]
                # Skip simple/standard commands
                if len(run_cmd) > 50 or "\n" in run_cmd:
                    custom_steps.append(
                        {
                            "job": job_name,
                            "step_name": step_name,
                            "run": (
                                run_cmd[:100] + "..." if len(run_cmd) > 100 else run_cmd
                            ),
                            "message": f"Custom run command in {job_name}: {step_name}",
                        }
                    )

    return {
        "status": "action_required" if custom_steps else "ok",
        "findings": custom_steps,
        "message": f"Found {len(custom_steps)} custom steps that may need review",
    }


def rule_check_dependencies(old: Mapping, new: Mapping) -> dict:
    """Check if dependency installation approach changed."""
    findings = []

    old_jobs = old.get("jobs", {})
    new_jobs = new.get("jobs", {})

    for job_name in old_jobs.keys():
        old_job = old_jobs.get(job_name, {})
        new_job = new_jobs.get(job_name, {})

        old_steps = old_job.get("steps", [])
        new_steps = new_job.get("steps", [])

        # Look for dependency installation steps
        old_dep_step = None
        new_dep_step = None

        for step in old_steps:
            if (
                "install" in step.get("name", "").lower()
                and "depend" in step.get("name", "").lower()
            ):
                old_dep_step = step
                break

        for step in new_steps:
            if (
                "install" in step.get("name", "").lower()
                and "depend" in step.get("name", "").lower()
            ):
                new_dep_step = step
                break

        if old_dep_step and new_dep_step:
            # Check if setup.cfg vs pyproject.toml
            old_uses_setup_cfg = "setup.cfg" in str(old_dep_step)
            new_uses_pyproject = "pyproject.toml" in str(new_dep_step)

            if old_uses_setup_cfg and new_uses_pyproject:
                findings.append(
                    {
                        "job": job_name,
                        "message": f"Migration from setup.cfg to pyproject.toml needed in {job_name}",
                        "old_approach": "setup.cfg",
                        "new_approach": "pyproject.toml",
                    }
                )

    return {
        "status": "warning" if findings else "ok",
        "findings": findings,
    }


def rule_check_formatting_linting(old: Mapping, new: Mapping) -> dict:
    """
    Check if formatting/linting approach changed.

    Common migration: Black + Pylint → Ruff (format + lint)
    """
    findings = []

    old_jobs = old.get("jobs", {})
    new_jobs = new.get("jobs", {})

    for job_name in old_jobs.keys():
        old_steps = extract_steps(old, job_name)
        new_steps = extract_steps(new, job_name)

        # Check old approach
        old_uses_black = any("black" in str(step).lower() for step in old_steps)
        old_uses_pylint = any("pylint" in str(step).lower() for step in old_steps)

        # Check new approach
        new_uses_ruff = any("ruff" in str(step).lower() for step in new_steps)

        if (old_uses_black or old_uses_pylint) and new_uses_ruff:
            old_tools = []
            if old_uses_black:
                old_tools.append("Black")
            if old_uses_pylint:
                old_tools.append("Pylint")

            findings.append(
                {
                    "job": job_name,
                    "message": f"Linting/formatting migration in {job_name}: {' + '.join(old_tools)} → Ruff",
                    "old_tools": old_tools,
                    "new_tool": "Ruff",
                }
            )

    return {
        "status": "info" if findings else "ok",
        "findings": findings,
        "message": "Ruff combines formatting and linting into one tool",
    }


def rule_check_secrets(old: Mapping, new: Mapping) -> dict:
    """Identify secrets that might need to be configured."""
    all_secrets = set()

    def extract_secrets(data: Any):
        """Recursively find all ${{ secrets.* }} references."""
        if isinstance(data, str):
            import re

            matches = re.findall(r"\$\{\{\s*secrets\.(\w+)\s*\}\}", data)
            all_secrets.update(matches)
        elif isinstance(data, dict):
            for value in data.values():
                extract_secrets(value)
        elif isinstance(data, list):
            for item in data:
                extract_secrets(item)

    extract_secrets(new)

    return {
        "status": "info",
        "secrets": sorted(all_secrets),
        "message": f"Secrets required: {', '.join(sorted(all_secrets))}",
    }


# Default migration rules
DEFAULT_MIGRATION_RULES = [
    MigrationRule(
        name="project_name",
        description="Check PROJECT_NAME configuration",
        check_func=rule_check_project_name,
        severity="critical",
    ),
    MigrationRule(
        name="python_versions",
        description="Check if Python versions changed",
        check_func=rule_check_python_versions,
        severity="info",
    ),
    MigrationRule(
        name="custom_steps",
        description="Identify custom steps that need review",
        check_func=rule_check_custom_steps,
        severity="warning",
    ),
    MigrationRule(
        name="dependencies",
        description="Check dependency installation approach",
        check_func=rule_check_dependencies,
        severity="warning",
    ),
    MigrationRule(
        name="formatting_linting",
        description="Check formatting/linting tool changes",
        check_func=rule_check_formatting_linting,
        severity="info",
    ),
    MigrationRule(
        name="secrets",
        description="Identify required secrets",
        check_func=rule_check_secrets,
        severity="info",
    ),
]


# --------------------------------------------------------------------------------------
# Main diagnosis function
# --------------------------------------------------------------------------------------


def diagnose_migration(
    old_ci: Union[str, Path, Mapping, GitHubWorkflow],
    new_template: Union[str, Path, Mapping, GitHubWorkflow],
    *,
    rules: Optional[list[MigrationRule]] = None,
    project_name: Optional[str] = None,
) -> MigrationDiagnosis:
    """
    Diagnose what needs to change when migrating from old CI to new template.

    This function performs a comprehensive analysis of differences between an old
    CI script and a new template, applying a set of migration rules to identify
    what needs to be carried over, what can be replaced, and what requires attention.

    Args:
        old_ci: Old CI workflow (path, YAML string, or GitHubWorkflow)
        new_template: New CI template (path, YAML string, or GitHubWorkflow)
        rules: Custom migration rules (defaults to DEFAULT_MIGRATION_RULES)
        project_name: Optional project name to substitute in new template

    Returns:
        MigrationDiagnosis object with detailed findings

    Example:
        >>> from wads import github_ci_publish_2025_path
        >>> old = '''
        ... name: CI
        ... env:
        ...   PROJECT_NAME: myproject
        ... on: [push]
        ... jobs:
        ...   test:
        ...     runs-on: ubuntu-latest
        ...     steps:
        ...       - uses: actions/checkout@v3
        ... '''
        >>> diagnosis = diagnose_migration(old, github_ci_publish_2025_path)
        >>> diagnosis.old_workflow['name']
        'CI'
    """
    if rules is None:
        rules = DEFAULT_MIGRATION_RULES

    # Parse workflows
    old_wf = old_ci if isinstance(old_ci, GitHubWorkflow) else GitHubWorkflow(old_ci)
    new_wf = (
        new_template
        if isinstance(new_template, GitHubWorkflow)
        else GitHubWorkflow(new_template)
    )

    # Substitute project name if provided
    if project_name:
        new_yaml = new_wf.to_yaml().replace("#PROJECT_NAME#", project_name)
        new_wf = GitHubWorkflow(new_yaml)

    # Perform basic comparison
    raw_diff = compare_workflows(old_wf, new_wf)

    # Initialize diagnosis
    diagnosis = MigrationDiagnosis(
        old_workflow=old_wf,
        new_workflow=new_wf,
        raw_diff=raw_diff,
    )

    # Apply migration rules
    for rule in rules:
        try:
            finding = rule.check_func(dict(old_wf), dict(new_wf))
            diagnosis.rule_findings[rule.name] = finding

            # Categorize by severity
            if finding.get("status") in ("action_required", "error"):
                diagnosis.critical_issues.append(
                    {
                        "rule": rule.name,
                        "description": rule.description,
                        "finding": finding,
                    }
                )
            elif (
                finding.get("status") in ("changed", "warning")
                or rule.severity == "warning"
            ):
                diagnosis.warnings.append(
                    {
                        "rule": rule.name,
                        "description": rule.description,
                        "finding": finding,
                    }
                )
            else:
                diagnosis.info.append(
                    {
                        "rule": rule.name,
                        "description": rule.description,
                        "finding": finding,
                    }
                )
        except Exception as e:
            # Don't let one rule failure stop the whole diagnosis
            diagnosis.warnings.append(
                {
                    "rule": rule.name,
                    "description": f"Rule failed: {e}",
                    "finding": {"status": "error", "error": str(e)},
                }
            )

    # Create summary
    diagnosis.summary = {
        "old_name": old_wf.get("name", "Unknown"),
        "new_name": new_wf.get("name", "Unknown"),
        "old_jobs": extract_job_names(old_wf),
        "new_jobs": extract_job_names(new_wf),
        "critical_count": len(diagnosis.critical_issues),
        "warning_count": len(diagnosis.warnings),
        "info_count": len(diagnosis.info),
    }

    return diagnosis


# --------------------------------------------------------------------------------------
# Reporting and output
# --------------------------------------------------------------------------------------


def create_migration_report(
    diagnosis: MigrationDiagnosis, *, verbose: bool = False
) -> str:
    """
    Generate a human-readable migration report from a diagnosis.

    Args:
        diagnosis: MigrationDiagnosis object
        verbose: If True, include detailed diff information

    Returns:
        Formatted report string

    Example:
        >>> from wads import github_ci_publish_2025_path
        >>> old = 'name: CI\\non: [push]\\njobs:\\n  test:\\n    runs-on: ubuntu-latest'
        >>> diag = diagnose_migration(old, github_ci_publish_2025_path)
        >>> report = create_migration_report(diag)
        >>> 'CI MIGRATION REPORT' in report
        True
    """
    lines = []
    lines.append("=" * 80)
    lines.append("CI MIGRATION REPORT")
    lines.append("=" * 80)
    lines.append("")

    # Summary
    lines.append(f"Old workflow: {diagnosis.summary['old_name']}")
    lines.append(f"New workflow: {diagnosis.summary['new_name']}")
    lines.append("")
    lines.append(f"Old jobs: {', '.join(diagnosis.summary['old_jobs'])}")
    lines.append(f"New jobs: {', '.join(diagnosis.summary['new_jobs'])}")
    lines.append("")

    # Critical issues
    if diagnosis.critical_issues:
        lines.append("CRITICAL ISSUES (must be addressed):")
        lines.append("-" * 80)
        for issue in diagnosis.critical_issues:
            lines.append(f"  • {issue['description']}")
            if "message" in issue["finding"]:
                lines.append(f"    {issue['finding']['message']}")
            if verbose and "findings" in issue["finding"]:
                for finding in issue["finding"]["findings"]:
                    lines.append(f"    - {finding.get('message', finding)}")
        lines.append("")

    # Warnings
    if diagnosis.warnings:
        lines.append("WARNINGS (should review):")
        lines.append("-" * 80)
        for warning in diagnosis.warnings:
            lines.append(f"  • {warning['description']}")
            if "message" in warning["finding"]:
                lines.append(f"    {warning['finding']['message']}")
            if verbose and "findings" in warning["finding"]:
                for finding in warning["finding"]["findings"]:
                    lines.append(f"    - {finding.get('message', finding)}")
        lines.append("")

    # Info
    if diagnosis.info:
        lines.append("INFORMATION:")
        lines.append("-" * 80)
        for info in diagnosis.info:
            if "message" in info["finding"] and info["finding"]["message"]:
                lines.append(f"  • {info['description']}")
                lines.append(f"    {info['finding']['message']}")
        lines.append("")

    # Detailed diff (if verbose)
    if verbose and diagnosis.raw_diff:
        lines.append("DETAILED DIFFERENCES:")
        lines.append("-" * 80)
        _format_diff(diagnosis.raw_diff, lines, indent=2)
        lines.append("")

    lines.append("=" * 80)
    return "\n".join(lines)


def _format_diff(diff: dict, lines: list, indent: int = 0):
    """Helper to format diff dict recursively."""
    prefix = " " * indent

    if "added" in diff and diff["added"]:
        lines.append(f"{prefix}Added:")
        _format_value(diff["added"], lines, indent + 2, symbol="+")

    if "removed" in diff and diff["removed"]:
        lines.append(f"{prefix}Removed:")
        _format_value(diff["removed"], lines, indent + 2, symbol="-")

    if "modified" in diff and diff["modified"]:
        lines.append(f"{prefix}Modified:")
        _format_value(diff["modified"], lines, indent + 2, symbol="~")


def _format_value(value: Any, lines: list, indent: int, symbol: str = " "):
    """Helper to format values with indentation."""
    prefix = " " * indent
    if isinstance(value, dict):
        for k, v in value.items():
            if isinstance(v, dict) and ("old" in v and "new" in v):
                lines.append(f"{prefix}{symbol} {k}: {v['old']} → {v['new']}")
            elif isinstance(v, dict):
                lines.append(f"{prefix}{symbol} {k}:")
                _format_value(v, lines, indent + 2, symbol)
            else:
                lines.append(f"{prefix}{symbol} {k}: {v}")
    elif isinstance(value, list):
        for item in value:
            lines.append(f"{prefix}{symbol} {item}")
    else:
        lines.append(f"{prefix}{symbol} {value}")


def get_migration_checklist(diagnosis: MigrationDiagnosis) -> list[str]:
    """
    Generate an actionable checklist for migration.

    Args:
        diagnosis: MigrationDiagnosis object

    Returns:
        List of action items

    Example:
        >>> from wads import github_ci_publish_2025_path
        >>> old = 'name: CI\\non: [push]\\njobs:\\n  test:\\n    runs-on: ubuntu-latest'
        >>> diag = diagnose_migration(old, github_ci_publish_2025_path)
        >>> checklist = get_migration_checklist(diag)
        >>> isinstance(checklist, list)
        True
    """
    checklist = []

    # Critical items first
    for issue in diagnosis.critical_issues:
        if "message" in issue["finding"]:
            checklist.append(f"[ ] CRITICAL: {issue['finding']['message']}")

    # Then warnings
    for warning in diagnosis.warnings:
        if "message" in warning["finding"]:
            checklist.append(f"[ ] Review: {warning['finding']['message']}")

    # General steps
    checklist.extend(
        [
            "[ ] Update workflow file with new template",
            "[ ] Test the new workflow in a branch",
            "[ ] Verify all required secrets are configured",
            "[ ] Check that all jobs complete successfully",
        ]
    )

    return checklist
