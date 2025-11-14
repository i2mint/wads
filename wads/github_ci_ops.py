"""
GitHub CI Operations - Tools for analyzing and comparing GitHub Actions workflows.

This module provides utilities for parsing, analyzing, and comparing GitHub Actions
CI/CD scripts, with a focus on migration from old to new CI templates.

Key Components:
    GitHubWorkflow: Parse and manipulate GitHub Actions YAML files while preserving comments
    compare_workflows: Compare two workflows and identify differences
    diff_nested: General-purpose nested structure comparison

Example:
    >>> from wads.github_ci_ops import GitHubWorkflow, compare_workflows
    >>>
    >>> # Parse a workflow from YAML string
    >>> yaml_str = 'name: CI\\non: [push]\\njobs:\\n  test:\\n    runs-on: ubuntu-latest'
    >>> workflow = GitHubWorkflow(yaml_str)
    >>>
    >>> # Access as a mapping
    >>> jobs = workflow['jobs']
    >>> jobs['test']['runs-on']
    'ubuntu-latest'
"""

import os
from pathlib import Path
from typing import Union, Any, Mapping, Optional, Callable, Tuple
from collections.abc import MutableMapping
from io import StringIO

try:
    from ruamel.yaml import YAML
    from ruamel.yaml.comments import CommentedMap, CommentedSeq
except ImportError:
    raise ImportError(
        "ruamel.yaml is required for GitHub CI operations. "
        "Install with: pip install ruamel.yaml"
    )


# --------------------------------------------------------------------------------------
# YAML parsing with comment preservation
# --------------------------------------------------------------------------------------


class GitHubWorkflow(MutableMapping):
    """
    A Mapping view of a GitHub Actions workflow file that preserves comments.

    This class parses GitHub Actions YAML files using ruamel.yaml to maintain
    comments and formatting. It provides a dict-like interface for accessing
    and modifying the workflow structure.

    Args:
        src: Either a file path (str/Path), YAML string content, or a dict/Mapping

    Attributes:
        _data: The parsed YAML data (CommentedMap from ruamel.yaml)
        _yaml: The YAML parser instance

    Example:
        >>> # From file path
        >>> wf = GitHubWorkflow('ci.yml')  # doctest: +SKIP
        >>>
        >>> # From YAML string
        >>> yaml_str = '''
        ... name: CI
        ... on: [push]
        ... jobs:
        ...   test:
        ...     runs-on: ubuntu-latest
        ... '''
        >>> wf = GitHubWorkflow(yaml_str)
        >>> wf['name']
        'CI'
        >>>
        >>> # Access nested values
        >>> wf['jobs']['test']['runs-on']
        'ubuntu-latest'
        >>>
        >>> # Convert back to YAML
        >>> yaml_output = wf.to_yaml()
    """

    def __init__(self, src: Union[str, Path, Mapping]):
        self._yaml = YAML()
        self._yaml.preserve_quotes = True
        self._yaml.default_flow_style = False
        self._yaml.width = 4096  # Prevent line wrapping

        if isinstance(src, Mapping):
            # Convert dict to CommentedMap
            self._data = self._yaml.load(self._yaml.dump(src))
        elif isinstance(src, (str, Path)):
            src_str = str(src)
            if os.path.isfile(src_str):
                # Load from file
                with open(src_str, "r") as f:
                    self._data = self._yaml.load(f)
            else:
                # Parse as YAML string
                self._data = self._yaml.load(src_str)
        else:
            raise TypeError(
                f"src must be a file path, YAML string, or Mapping, got {type(src)}"
            )

        if self._data is None:
            self._data = CommentedMap()

    def to_yaml(self) -> str:
        """
        Convert the workflow back to a YAML string.

        Preserves comments and formatting from the original file.

        Returns:
            YAML string representation of the workflow
        """
        output = StringIO()
        self._yaml.dump(self._data, output)
        return output.getvalue()

    def to_dict(self) -> dict:
        """
        Convert to a plain Python dictionary (loses comments).

        Returns:
            Plain dict representation
        """
        return dict(self._data)

    def save(self, path: Union[str, Path]) -> None:
        """
        Save the workflow to a file.

        Args:
            path: File path to save to
        """
        with open(path, "w") as f:
            self._yaml.dump(self._data, f)

    # MutableMapping interface implementation
    def __getitem__(self, key):
        return self._data[key]

    def __setitem__(self, key, value):
        self._data[key] = value

    def __delitem__(self, key):
        del self._data[key]

    def __iter__(self):
        return iter(self._data)

    def __len__(self):
        return len(self._data)

    def __repr__(self):
        return f"GitHubWorkflow({dict(self._data)})"

    def __str__(self):
        return self.to_yaml()


# --------------------------------------------------------------------------------------
# Nested structure comparison
# --------------------------------------------------------------------------------------


def diff_nested(
    old: Any,
    new: Any,
    *,
    path: str = "",
    equivalence_func: Optional[Callable[[Any, Any], bool]] = None,
) -> dict:
    """
    Recursively compare two nested structures and identify differences.

    This function compares two nested data structures (dicts, lists, etc.) and
    returns a detailed report of the differences. It's the foundation for
    comparing GitHub Actions workflows.

    Args:
        old: The old/source structure
        new: The new/target structure
        path: Internal use - tracks the current path in the structure
        equivalence_func: Optional custom function to determine if two values
            are equivalent. If None, uses standard equality (==).

    Returns:
        A dict with the following structure:
        {
            'added': {...},      # Keys/values present in new but not in old
            'removed': {...},    # Keys/values present in old but not in new
            'modified': {...},   # Keys present in both but with different values
            'unchanged': {...},  # Keys present in both with same values (optional)
        }

    Example:
        >>> old = {'a': 1, 'b': {'bb': 1}, 'c': 3}
        >>> new = {'a': 1, 'b': {'bb': 2}, 'd': 4}
        >>> diff = diff_nested(old, new)
        >>> diff['removed']
        {'c': 3}
        >>> diff['added']
        {'d': 4}
        >>> 'b' in diff['modified']
        True
    """
    if equivalence_func is None:
        equivalence_func = lambda x, y: x == y

    result = {
        "added": {},
        "removed": {},
        "modified": {},
    }

    # Handle the case where types differ
    if type(old) != type(new):
        return {
            "added": new,
            "removed": old,
            "modified": {},
        }

    # Handle dict/mapping comparison
    if isinstance(old, Mapping) and isinstance(new, Mapping):
        old_keys = set(old.keys())
        new_keys = set(new.keys())

        # Keys only in new (added)
        for key in new_keys - old_keys:
            result["added"][key] = new[key]

        # Keys only in old (removed)
        for key in old_keys - new_keys:
            result["removed"][key] = old[key]

        # Keys in both (potentially modified)
        for key in old_keys & new_keys:
            old_val = old[key]
            new_val = new[key]

            # If both are mappings or sequences, recurse
            if isinstance(old_val, (Mapping, list)) and isinstance(
                new_val, (Mapping, list)
            ):
                nested_diff = diff_nested(
                    old_val,
                    new_val,
                    path=f"{path}.{key}" if path else str(key),
                    equivalence_func=equivalence_func,
                )

                # Only include in modified if there are actual differences
                if (
                    nested_diff["added"]
                    or nested_diff["removed"]
                    or nested_diff["modified"]
                ):
                    result["modified"][key] = nested_diff
            elif not equivalence_func(old_val, new_val):
                result["modified"][key] = {
                    "old": old_val,
                    "new": new_val,
                }

    # Handle list/sequence comparison
    elif isinstance(old, list) and isinstance(new, list):
        if old != new:
            # For lists, we track added/removed items
            # This is simplified - could be enhanced with LCS algorithm
            old_set = set(str(x) for x in old)  # Convert to strings for comparison
            new_set = set(str(x) for x in new)

            added_items = [x for x in new if str(x) not in old_set]
            removed_items = [x for x in old if str(x) not in new_set]

            if added_items:
                result["added"] = added_items
            if removed_items:
                result["removed"] = removed_items

            # Also track if the order changed
            if old_set == new_set and old != new:
                result["modified"] = {
                    "note": "Order changed",
                    "old": old,
                    "new": new,
                }

    # For non-nested values
    else:
        if not equivalence_func(old, new):
            return {
                "added": new,
                "removed": old,
                "modified": {},
            }

    return result


def compare_workflows(
    old: Union[GitHubWorkflow, Mapping, str, Path],
    new: Union[GitHubWorkflow, Mapping, str, Path],
    *,
    focus_keys: Optional[list] = None,
    ignore_keys: Optional[list] = None,
    equivalence_func: Optional[Callable[[Any, Any], bool]] = None,
) -> dict:
    """
    Compare two GitHub Actions workflows and identify differences.

    This is a specialized comparison for GitHub Actions workflows, with support
    for focusing on specific keys or ignoring certain keys.

    Args:
        old: Old workflow (GitHubWorkflow, Mapping, file path, or YAML string)
        new: New workflow (GitHubWorkflow, Mapping, file path, or YAML string)
        focus_keys: If provided, only compare these top-level keys
        ignore_keys: If provided, ignore these top-level keys in comparison
        equivalence_func: Optional custom equivalence function

    Returns:
        Detailed diff dict with 'added', 'removed', 'modified' sections

    Example:
        >>> old_yaml = '''
        ... name: Old CI
        ... on: [push]
        ... jobs:
        ...   test:
        ...     runs-on: ubuntu-latest
        ... '''
        >>> new_yaml = '''
        ... name: New CI
        ... on: [push, pull_request]
        ... jobs:
        ...   test:
        ...     runs-on: ubuntu-latest
        ...   lint:
        ...     runs-on: ubuntu-latest
        ... '''
        >>> diff = compare_workflows(old_yaml, new_yaml)
        >>> 'lint' in diff['modified']['jobs']['added']
        True
    """
    # Ensure both are GitHubWorkflow instances
    if not isinstance(old, GitHubWorkflow):
        old = GitHubWorkflow(old)
    if not isinstance(new, GitHubWorkflow):
        new = GitHubWorkflow(new)

    # Apply focus/ignore filters
    old_data = dict(old)
    new_data = dict(new)

    if focus_keys:
        old_data = {k: v for k, v in old_data.items() if k in focus_keys}
        new_data = {k: v for k, v in new_data.items() if k in focus_keys}

    if ignore_keys:
        old_data = {k: v for k, v in old_data.items() if k not in ignore_keys}
        new_data = {k: v for k, v in new_data.items() if k not in ignore_keys}

    return diff_nested(old_data, new_data, equivalence_func=equivalence_func)


# --------------------------------------------------------------------------------------
# Workflow analysis utilities
# --------------------------------------------------------------------------------------


def extract_job_names(workflow: Union[GitHubWorkflow, Mapping]) -> list:
    """
    Extract all job names from a workflow.

    Args:
        workflow: GitHubWorkflow or dict

    Returns:
        List of job names
    """
    if isinstance(workflow, GitHubWorkflow):
        workflow = dict(workflow)

    jobs = workflow.get("jobs", {})
    return list(jobs.keys())


def extract_steps(workflow: Union[GitHubWorkflow, Mapping], job_name: str) -> list:
    """
    Extract all steps from a specific job.

    Args:
        workflow: GitHubWorkflow or dict
        job_name: Name of the job to extract steps from

    Returns:
        List of step dicts
    """
    if isinstance(workflow, GitHubWorkflow):
        workflow = dict(workflow)

    jobs = workflow.get("jobs", {})
    job = jobs.get(job_name, {})
    return job.get("steps", [])


def find_step_by_name(
    workflow: Union[GitHubWorkflow, Mapping], job_name: str, step_name: str
) -> Optional[dict]:
    """
    Find a specific step by name within a job.

    Args:
        workflow: GitHubWorkflow or dict
        job_name: Name of the job
        step_name: Name of the step to find

    Returns:
        Step dict if found, None otherwise
    """
    steps = extract_steps(workflow, job_name)
    for step in steps:
        if step.get("name") == step_name:
            return step
    return None


def get_workflow_env_vars(workflow: Union[GitHubWorkflow, Mapping]) -> dict:
    """
    Extract top-level environment variables from a workflow.

    Args:
        workflow: GitHubWorkflow or dict

    Returns:
        Dict of environment variables
    """
    if isinstance(workflow, GitHubWorkflow):
        workflow = dict(workflow)

    return workflow.get("env", {})


def summarize_workflow(workflow: Union[GitHubWorkflow, Mapping]) -> dict:
    """
    Create a high-level summary of a workflow.

    Args:
        workflow: GitHubWorkflow or dict

    Returns:
        Summary dict with name, triggers, jobs, and env vars
    """
    if isinstance(workflow, GitHubWorkflow):
        workflow = dict(workflow)

    return {
        "name": workflow.get("name", "Unnamed"),
        "triggers": workflow.get("on", []),
        "env_vars": get_workflow_env_vars(workflow),
        "jobs": {
            job_name: {
                "runs_on": job.get("runs-on", "unknown"),
                "steps_count": len(job.get("steps", [])),
                "needs": job.get("needs", []),
            }
            for job_name, job in workflow.get("jobs", {}).items()
        },
    }
