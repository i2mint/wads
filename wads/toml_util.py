"""Utilities for reading and writing pyproject.toml files."""

import sys
import os
from typing import Any, Optional

# Use tomllib for Python 3.11+, tomli for earlier versions
if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None

try:
    import tomli_w
except ImportError:
    tomli_w = None


def pep639_license(license_name: str):
    """The ``[project].license`` value for ``license_name``, PEP 639 when possible.

    A name that canonicalizes to a valid SPDX expression becomes that string
    (``license = "MIT"``). Anything else keeps the deprecated
    ``{"text": ...}`` table, because Hatchling rejects a ``license`` string
    that is not valid SPDX -- so this never produces an unbuildable project.
    Needs ``packaging>=24.2`` for SPDX support and falls back to the table
    without it.

    >>> pep639_license("mit")
    'MIT'
    >>> pep639_license("Apache Software License")
    'Apache-2.0'
    >>> pep639_license("Proprietary")
    {'text': 'Proprietary'}
    """
    if isinstance(license_name, dict):
        return license_name  # already a table
    if not isinstance(license_name, str):
        return {"text": license_name}
    try:
        from packaging.licenses import (
            InvalidLicenseExpression,
            canonicalize_license_expression,
        )
    except ImportError:
        return {"text": license_name}
    aliases = {
        "apache software license": "Apache-2.0",
        "apache license 2.0": "Apache-2.0",
        "apache 2.0": "Apache-2.0",
        "mit license": "MIT",
        "bsd license": "BSD-3-Clause",
    }
    candidate = aliases.get(str(license_name).strip().lower(), license_name)
    try:
        return canonicalize_license_expression(candidate)
    except (InvalidLicenseExpression, TypeError):
        return {"text": license_name}


def read_pyproject_toml(pkg_dir: str) -> dict[str, Any]:
    """
    Read pyproject.toml from the specified package directory.

    Args:
        pkg_dir: Path to the package directory

    Returns:
        Dictionary containing the parsed TOML data

    Raises:
        ImportError: If tomli/tomllib is not available
        FileNotFoundError: If pyproject.toml doesn't exist
    """
    if tomllib is None:
        raise ImportError(
            "tomli is required for Python < 3.11. Install with: pip install tomli"
        )

    pyproject_path = os.path.join(pkg_dir, "pyproject.toml")

    if not os.path.isfile(pyproject_path):
        return {}

    with open(pyproject_path, "rb") as f:
        return tomllib.load(f)


def write_pyproject_toml(pkg_dir: str, data: dict[str, Any]) -> None:
    """
    Write data to pyproject.toml in the specified package directory.

    Args:
        pkg_dir: Path to the package directory
        data: Dictionary to write as TOML

    Raises:
        ImportError: If tomli_w is not available
    """
    if tomli_w is None:
        raise ImportError(
            "tomli_w is required for writing TOML. Install with: pip install tomli_w"
        )

    pyproject_path = os.path.join(pkg_dir, "pyproject.toml")

    with open(pyproject_path, "wb") as f:
        tomli_w.dump(data, f)


def get_project_metadata(pkg_dir: str) -> dict[str, Any]:
    """
    Get the [project] section from pyproject.toml.

    Args:
        pkg_dir: Path to the package directory

    Returns:
        Dictionary containing project metadata
    """
    data = read_pyproject_toml(pkg_dir)
    return data.get("project", {})


def get_project_version(pkg_dir: str) -> Optional[str]:
    """
    Get the version from pyproject.toml.

    Args:
        pkg_dir: Path to the package directory

    Returns:
        Version string or None if not found
    """
    metadata = get_project_metadata(pkg_dir)
    return metadata.get("version")


def set_project_version(pkg_dir: str, version: str) -> None:
    """
    Set the version in pyproject.toml.

    Args:
        pkg_dir: Path to the package directory
        version: New version string
    """
    data = read_pyproject_toml(pkg_dir)

    if "project" not in data:
        data["project"] = {}

    data["project"]["version"] = version
    write_pyproject_toml(pkg_dir, data)


def get_project_name(pkg_dir: str) -> Optional[str]:
    """
    Get the project name from pyproject.toml.

    Args:
        pkg_dir: Path to the package directory

    Returns:
        Project name or None if not found
    """
    metadata = get_project_metadata(pkg_dir)
    return metadata.get("name")


def update_project_metadata(pkg_dir: str, **kwargs) -> None:
    """
    Update project metadata in pyproject.toml.

    Args:
        pkg_dir: Path to the package directory
        **kwargs: Metadata fields to update
    """
    data = read_pyproject_toml(pkg_dir)

    if "project" not in data:
        data["project"] = {}

    data["project"].update(kwargs)
    write_pyproject_toml(pkg_dir, data)


def update_project_url(pkg_dir: str, url: str, url_key: str = "Homepage") -> None:
    """
    Update or add a URL in the [project.urls] section of pyproject.toml.

    Args:
        pkg_dir: Path to the package directory
        url: The URL to set
        url_key: The key to use in the urls dict (default: "Homepage")
    """
    data = read_pyproject_toml(pkg_dir)

    if "project" not in data:
        data["project"] = {}

    if "urls" not in data["project"]:
        data["project"]["urls"] = {}

    data["project"]["urls"][url_key] = url
    write_pyproject_toml(pkg_dir, data)
