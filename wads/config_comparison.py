"""
Compare project configuration files (pyproject.toml, setup.cfg, MANIFEST.in) against templates.

This module provides tools to analyze project configurations and identify
differences from standard templates, helping users maintain up-to-date
project structures.

Key Functions:
    compare_pyproject_toml: Compare actual pyproject.toml against template
    compare_setup_cfg: Analyze setup.cfg and recommend migration
    compare_manifest_in: Analyze MANIFEST.in and recommend Hatchling migration
    summarize_config_status: Overall project config health check
    compare_ci_workflow: Compare CI workflow against template

Example:
    >>> from wads.config_comparison import summarize_config_status  # doctest: +SKIP
    >>> status = summarize_config_status('/path/to/project')  # doctest: +SKIP
    >>> if status['needs_attention']:  # doctest: +SKIP
    ...     print(status['recommendations'])  # doctest: +SKIP
"""

import sys
from typing import Dict, Any, List, Tuple, Optional, Set
from pathlib import Path
from contextlib import suppress

# Import TOML handling
if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None

from wads import pyproject_toml_tpl_path, github_ci_publish_2025_path
from wads.toml_util import read_pyproject_toml


# --------------------------------------------------------------------------------------
# pyproject.toml comparison
# --------------------------------------------------------------------------------------


def _nested_get(d: dict, path: str, default=None):
    """
    Get value from nested dict using dot-separated path.

    >>> d = {'a': {'b': {'c': 1}}}
    >>> _nested_get(d, 'a.b.c')
    1
    >>> _nested_get(d, 'a.b.x', 'missing')
    'missing'
    """
    parts = path.split(".")
    current = d
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
            if current is None:
                return default
        else:
            return default
    return current


def _flatten_dict(d: dict, parent_key: str = "", sep: str = ".") -> dict:
    """
    Flatten nested dict into dot-separated keys.

    >>> d = {'a': {'b': 1, 'c': 2}, 'd': 3}
    >>> sorted(_flatten_dict(d).items())
    [('a.b', 1), ('a.c', 2), ('d', 3)]
    """
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict) and v:
            items.extend(_flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


def _find_missing_sections(
    actual: dict, template: dict, ignore_keys: Set[str]
) -> List[str]:
    """Find top-level and nested sections in template missing from actual."""
    flat_template = _flatten_dict(template)
    flat_actual = _flatten_dict(actual)

    missing = []
    for key in flat_template:
        # Skip ignored keys
        if any(ignored in key for ignored in ignore_keys):
            continue

        if key not in flat_actual:
            # Only report if it's a meaningful section (not empty placeholders)
            template_val = flat_template[key]
            if template_val and template_val not in ("", [], {}):
                missing.append(key)

    return missing


def _find_outdated_sections(
    actual: dict, template: dict, ignore_keys: Set[str]
) -> List[str]:
    """Find sections in actual that might be outdated or unnecessary."""
    flat_template = _flatten_dict(template)
    flat_actual = _flatten_dict(actual)

    outdated = []
    for key in flat_actual:
        # Skip ignored keys
        if any(ignored in key for ignored in ignore_keys):
            continue

        # Check for common outdated patterns
        if key not in flat_template:
            # Check if it's a known legacy field
            if any(
                legacy in key.lower()
                for legacy in ["setup.py", "setup.cfg", "manifest"]
            ):
                outdated.append(key)

    return outdated


def _generate_recommendations(
    actual: dict, template: dict, missing: List[str], project_name: str = None
) -> List[str]:
    """Generate actionable recommendations."""
    recommendations = []

    if missing:
        recommendations.append(
            "Some template sections are missing from your pyproject.toml."
        )

        # Check for specific important missing sections
        critical_missing = [
            m
            for m in missing
            if any(crit in m for crit in ["tool.ruff", "tool.pytest", "build-system"])
        ]

        if critical_missing:
            recommendations.append(
                f"Critical sections missing: {', '.join(critical_missing)}"
            )
            recommendations.append("Consider running: wads migrate pyproject.toml")

    # Check if using outdated build backend
    build_backend = actual.get("build-system", {}).get("build-backend", "")
    template_backend = template.get("build-system", {}).get("build-backend", "")

    if build_backend != template_backend and "setuptools" in build_backend.lower():
        recommendations.append(
            f"Consider upgrading build backend from '{build_backend}' to '{template_backend}'"
        )

    return recommendations


def compare_pyproject_toml(
    actual_path: str | Path,
    template_path: str | Path = pyproject_toml_tpl_path,
    *,
    ignore_keys: Set[str] | None = None,
    project_name: str = None,
) -> Dict[str, Any]:
    """
    Compare actual pyproject.toml against template.

    Args:
        actual_path: Path to the project's pyproject.toml
        template_path: Path to template pyproject.toml
        ignore_keys: Keys to ignore in comparison (project-specific values)
        project_name: Optional project name for contextual recommendations

    Returns:
        Dictionary with:
        - 'missing_sections': sections in template but not in actual
        - 'outdated_sections': sections in actual that might be outdated
        - 'recommendations': suggested updates
        - 'needs_attention': boolean flag

    Example:
        >>> diff = compare_pyproject_toml('my_project/pyproject.toml')  # doctest: +SKIP
        >>> if diff['needs_attention']:  # doctest: +SKIP
        ...     for rec in diff['recommendations']:  # doctest: +SKIP
        ...         print(f"  - {rec}")  # doctest: +SKIP
    """
    ignore_keys = ignore_keys or {
        "project.name",
        "project.version",
        "project.description",
        "project.authors",
        "project.urls",
        "project.keywords",
        "project.dependencies",
        "project.optional-dependencies",
        "project.scripts",
    }

    try:
        actual = read_pyproject_toml(actual_path)
        template = read_pyproject_toml(template_path)
    except Exception as e:
        return {
            "error": str(e),
            "needs_attention": True,
            "recommendations": [f"Could not read pyproject.toml: {e}"],
        }

    missing = _find_missing_sections(actual, template, ignore_keys)
    outdated = _find_outdated_sections(actual, template, ignore_keys)
    recommendations = _generate_recommendations(actual, template, missing, project_name)

    return {
        "missing_sections": missing,
        "outdated_sections": outdated,
        "recommendations": recommendations,
        "needs_attention": bool(missing or outdated or recommendations),
    }


# --------------------------------------------------------------------------------------
# setup.cfg comparison
# --------------------------------------------------------------------------------------


def compare_setup_cfg(
    actual_path: str | Path,
    *,
    warn_about_deprecation: bool = True,
) -> Dict[str, Any]:
    """
    Analyze setup.cfg and recommend migration to pyproject.toml.

    Args:
        actual_path: Path to setup.cfg file
        warn_about_deprecation: Whether to warn about using deprecated format

    Returns:
        Dictionary with migration recommendations

    Example:
        >>> analysis = compare_setup_cfg('old_project/setup.cfg')  # doctest: +SKIP
        >>> if analysis['should_migrate']:  # doctest: +SKIP
        ...     print(analysis['recommendations'])  # doctest: +SKIP
    """
    from configparser import ConfigParser

    if not Path(actual_path).exists():
        return {
            "exists": False,
            "should_migrate": False,
        }

    config = ConfigParser()
    try:
        config.read(actual_path)
    except Exception as e:
        return {
            "exists": True,
            "error": str(e),
            "needs_attention": True,
        }

    sections = list(config.sections())

    recommendations = []
    if warn_about_deprecation:
        recommendations.append(
            "setup.cfg is deprecated in favor of pyproject.toml (PEP 621)"
        )
        recommendations.append("To migrate, run: populate . --migrate")
        recommendations.append(
            "Or use: from wads.migration import migrate_setuptools_to_hatching"
        )

    return {
        "exists": True,
        "sections": sections,
        "should_migrate": warn_about_deprecation,
        "recommendations": recommendations,
        "needs_attention": warn_about_deprecation,
    }


def compare_manifest_in(
    actual_path: str | Path,
) -> Dict[str, Any]:
    """
    Analyze MANIFEST.in and recommend migration to Hatchling configuration.

    Args:
        actual_path: Path to MANIFEST.in file

    Returns:
        Dictionary with migration recommendations

    Example:
        >>> analysis = compare_manifest_in('MANIFEST.in')  # doctest: +SKIP
        >>> if analysis['needs_migration']:  # doctest: +SKIP
        ...     print(analysis['hatchling_config'])  # doctest: +SKIP
    """
    from wads.migration import analyze_manifest_in

    result = analyze_manifest_in(actual_path)

    if not result["exists"]:
        return {
            "exists": False,
            "needs_migration": False,
        }

    return {
        "exists": True,
        "needs_migration": result["needs_migration"],
        "directives": result["directives"],
        "recommendations": result["recommendations"],
        "hatchling_config": result["hatchling_config"],
        "needs_attention": result["needs_migration"],
    }


# --------------------------------------------------------------------------------------
# CI workflow comparison
# --------------------------------------------------------------------------------------


def compare_ci_workflow(
    actual_path: str | Path,
    template_path: str | Path = github_ci_publish_2025_path,
    *,
    project_name: str = None,
) -> Dict[str, Any]:
    """
    Compare CI workflow against modern template.

    Args:
        actual_path: Path to .github/workflows/ci.yml
        template_path: Path to template CI workflow
        project_name: Optional project name for placeholder replacement

    Returns:
        Dictionary with comparison results and recommendations

    Example:
        >>> diff = compare_ci_workflow('.github/workflows/ci.yml')  # doctest: +SKIP
        >>> if diff['needs_attention']:  # doctest: +SKIP
        ...     print("CI might be outdated")  # doctest: +SKIP
    """
    with suppress(ImportError):
        from wads.github_ci_ops import compare_workflows, GitHubWorkflow

        try:
            actual = GitHubWorkflow(actual_path)
            template = GitHubWorkflow(template_path)

            comparison = compare_workflows(actual, template)

            recommendations = []

            # Check for outdated action versions
            # Use _data attribute to access the workflow data
            workflow_data = actual._data if hasattr(actual, "_data") else actual
            if "jobs" in workflow_data:
                for job_name, job_data in workflow_data["jobs"].items():
                    if "steps" in job_data:
                        for step in job_data["steps"]:
                            if "uses" in step:
                                uses = step["uses"]
                                # Check for old action versions
                                if "@v3" in uses or "@v2" in uses:
                                    recommendations.append(
                                        f"Action '{uses}' might be outdated (consider @v4 or @v5)"
                                    )

            # Check for missing modern features
            if "tool.ruff" not in str(workflow_data).lower():
                recommendations.append(
                    "CI doesn't use ruff for linting - consider modern CI template"
                )

            if recommendations:
                recommendations.append(f"To update CI, run: populate . --migrate")

            return {
                "differences": comparison,
                "recommendations": recommendations,
                "needs_attention": bool(recommendations),
            }

        except Exception as e:
            return {
                "error": str(e),
                "needs_attention": True,
                "recommendations": [f"Could not compare CI workflows: {e}"],
            }

    return {
        "error": "github_ci_ops not available",
        "needs_attention": False,
    }


# --------------------------------------------------------------------------------------
# Overall project status
# --------------------------------------------------------------------------------------


def summarize_config_status(
    pkg_dir: str | Path,
    *,
    check_ci: bool = True,
    project_name: str = None,
) -> Dict[str, Any]:
    """
    Check overall config status of a project.

    Analyzes pyproject.toml, setup.cfg, CI workflows and returns a comprehensive
    summary of what needs attention.

    Args:
        pkg_dir: Path to project directory
        check_ci: Whether to check CI workflow
        project_name: Optional project name for contextual checks

    Returns:
        Dictionary with:
        - 'has_pyproject': bool
        - 'has_setup_cfg': bool
        - 'has_ci': bool
        - 'needs_attention': list of issues
        - 'recommendations': list of recommendations
        - Details for each file type

    Example:
        >>> status = summarize_config_status('/path/to/project')  # doctest: +SKIP
        >>> for issue in status['needs_attention']:  # doctest: +SKIP
        ...     print(f"⚠️  {issue}")  # doctest: +SKIP
    """
    pkg_dir = Path(pkg_dir)
    pyproject_path = pkg_dir / "pyproject.toml"
    setup_cfg_path = pkg_dir / "setup.cfg"
    manifest_path = pkg_dir / "MANIFEST.in"
    ci_path = pkg_dir / ".github" / "workflows" / "ci.yml"

    result = {
        "has_pyproject": pyproject_path.exists(),
        "has_setup_cfg": setup_cfg_path.exists(),
        "has_manifest_in": manifest_path.exists(),
        "has_ci": ci_path.exists(),
        "needs_attention": [],
        "recommendations": [],
    }

    # Check pyproject.toml
    if result["has_pyproject"]:
        pyproject_diff = compare_pyproject_toml(
            pyproject_path, project_name=project_name
        )
        result["pyproject_status"] = pyproject_diff

        if pyproject_diff.get("needs_attention"):
            result["needs_attention"].append("pyproject.toml")
            result["recommendations"].extend(pyproject_diff.get("recommendations", []))

    # Check setup.cfg
    if result["has_setup_cfg"]:
        setup_cfg_status = compare_setup_cfg(setup_cfg_path)
        result["setup_cfg_status"] = setup_cfg_status

        if setup_cfg_status.get("needs_attention"):
            result["needs_attention"].append("setup.cfg")
            result["recommendations"].extend(
                setup_cfg_status.get("recommendations", [])
            )

    # Check MANIFEST.in
    if result["has_manifest_in"]:
        manifest_status = compare_manifest_in(manifest_path)
        result["manifest_status"] = manifest_status

        if manifest_status.get("needs_attention"):
            result["needs_attention"].append("MANIFEST.in")
            result["recommendations"].extend(manifest_status.get("recommendations", []))

    # Check CI
    if check_ci and result["has_ci"]:
        ci_diff = compare_ci_workflow(ci_path, project_name=project_name)
        result["ci_status"] = ci_diff

        if ci_diff.get("needs_attention"):
            result["needs_attention"].append(".github/workflows/ci.yml")
            result["recommendations"].extend(ci_diff.get("recommendations", []))

    return result
