"""
Migration tools for converting old setuptools/CI configurations to modern formats.

This module provides functions to migrate:
- setup.cfg files to pyproject.toml (hatching format)
- Old GitHub CI workflows to modern 2025 format

Key Functions:
    migrate_setuptools_to_hatching: Convert setup.cfg to pyproject.toml
    migrate_github_ci_old_to_new: Convert old CI scripts to new format

Example:
    >>> from wads.migration import migrate_setuptools_to_hatching
    >>> # From a file (use actual file path)
    >>> pyproject = migrate_setuptools_to_hatching('setup.cfg')  # doctest: +SKIP
    >>>
    >>> # From a dict with complete metadata
    >>> cfg = {
    ...     'metadata': {
    ...         'name': 'myproject',
    ...         'version': '0.1.0',
    ...         'description': 'A sample project',
    ...         'url': 'https://github.com/user/myproject',
    ...         'license': 'MIT'
    ...     }
    ... }
    >>> result = migrate_setuptools_to_hatching(cfg)
    >>> 'name = "myproject"' in result
    True
"""

import os
import sys
from typing import Union, Mapping, Callable, Optional
from pathlib import Path
from configparser import ConfigParser
from io import StringIO

# Import toml reading/writing utilities
if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        raise ImportError(
            "tomli is required for Python < 3.11. Install with: pip install tomli"
        )

try:
    import tomli_w
except ImportError:
    raise ImportError(
        "tomli_w is required for writing TOML. Install with: pip install tomli_w"
    )

from wads import (
    pyproject_toml_tpl_path,
    github_ci_tpl_publish_path,
    github_ci_publish_2025_path,
)


# --------------------------------------------------------------------------------------
# MANIFEST.in parsing and migration
# --------------------------------------------------------------------------------------


def _parse_manifest_in(filepath: str) -> dict:
    """
    Parse MANIFEST.in file and extract directives.

    Returns a dict with:
        - directives: list of (command, patterns) tuples
        - needs_migration: bool
        - recommendations: list of strings
    """
    if not os.path.isfile(filepath):
        return {"directives": [], "needs_migration": False, "recommendations": []}

    directives = []
    with open(filepath, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(None, 1)
            if len(parts) >= 1:
                command = parts[0]
                pattern = parts[1] if len(parts) > 1 else ""
                directives.append((command, pattern))

    if not directives:
        return {"directives": [], "needs_migration": False, "recommendations": []}

    # Analyze directives and generate recommendations
    recommendations = []
    include_patterns = []
    exclude_patterns = []

    for command, pattern in directives:
        if command in ("include", "recursive-include", "graft"):
            include_patterns.append(pattern)
        elif command in ("exclude", "recursive-exclude", "prune", "global-exclude"):
            exclude_patterns.append(pattern)

    # Generate Hatchling configuration suggestions
    if include_patterns or exclude_patterns:
        recommendations.append(
            "MANIFEST.in detected. With Hatchling, package data is handled differently."
        )

        if include_patterns:
            example_includes = "\n  ".join(f'"{p}",' for p in include_patterns[:3])
            if len(include_patterns) > 3:
                example_includes += "\n  # ... and more"
            recommendations.append(
                f"To include extra files, add to pyproject.toml:\n"
                f"[tool.hatch.build.targets.wheel]\n"
                f"include = [\n  {example_includes}\n]"
            )

        if exclude_patterns:
            example_excludes = "\n  ".join(f'"{p}",' for p in exclude_patterns[:3])
            if len(exclude_patterns) > 3:
                example_excludes += "\n  # ... and more"
            recommendations.append(
                f"To exclude files, add to pyproject.toml:\n"
                f"[tool.hatch.build.targets.wheel]\n"
                f"exclude = [\n  {example_excludes}\n]"
            )

        recommendations.append(
            "Note: Hatchling includes all package files by default. "
            "Only use explicit include/exclude if you need non-default behavior."
        )

    return {
        "directives": directives,
        "needs_migration": len(directives) > 0,
        "recommendations": recommendations,
    }


def analyze_manifest_in(manifest_path: Union[str, Path]) -> dict:
    """
    Analyze MANIFEST.in file and provide migration guidance for Hatchling.

    Args:
        manifest_path: Path to MANIFEST.in file

    Returns:
        Dictionary with:
            - exists: bool - whether file exists
            - needs_migration: bool - whether migration is needed
            - directives: list of (command, pattern) tuples
            - recommendations: list of strings with migration guidance
            - hatchling_config: suggested pyproject.toml configuration

    Example:
        >>> # If MANIFEST.in doesn't exist
        >>> result = analyze_manifest_in('nonexistent/MANIFEST.in')
        >>> result['exists']
        False
        >>> result['needs_migration']
        False
    """
    manifest_path = str(manifest_path)

    if not os.path.isfile(manifest_path):
        return {
            "exists": False,
            "needs_migration": False,
            "directives": [],
            "recommendations": [],
            "hatchling_config": None,
        }

    parsed = _parse_manifest_in(manifest_path)

    # Build suggested hatchling config
    hatchling_config = None
    if parsed["needs_migration"]:
        include_patterns = []
        exclude_patterns = []

        for command, pattern in parsed["directives"]:
            if command in ("include", "recursive-include", "graft"):
                # Convert MANIFEST.in patterns to hatchling patterns
                if command == "graft":
                    # graft dir -> include dir/**/*
                    include_patterns.append(f"{pattern}/**/*")
                elif command == "recursive-include":
                    # recursive-include dir pattern -> dir/**/pattern
                    parts = pattern.split(None, 1)
                    if len(parts) == 2:
                        dir_path, file_pattern = parts
                        include_patterns.append(f"{dir_path}/**/{file_pattern}")
                    else:
                        include_patterns.append(pattern)
                else:
                    include_patterns.append(pattern)
            elif command in ("exclude", "recursive-exclude", "prune", "global-exclude"):
                if command == "prune":
                    exclude_patterns.append(f"{pattern}/")
                elif command == "global-exclude":
                    exclude_patterns.append(f"**/{pattern}")
                elif command == "recursive-exclude":
                    parts = pattern.split(None, 1)
                    if len(parts) == 2:
                        dir_path, file_pattern = parts
                        exclude_patterns.append(f"{dir_path}/**/{file_pattern}")
                    else:
                        exclude_patterns.append(pattern)
                else:
                    exclude_patterns.append(pattern)

        config_parts = []
        if include_patterns:
            includes = ",\n  ".join(f'"{p}"' for p in include_patterns)
            config_parts.append(f"include = [\n  {includes}\n]")
        if exclude_patterns:
            excludes = ",\n  ".join(f'"{p}"' for p in exclude_patterns)
            config_parts.append(f"exclude = [\n  {excludes}\n]")

        if config_parts:
            hatchling_config = "[tool.hatch.build.targets.wheel]\n" + "\n".join(
                config_parts
            )

    return {
        "exists": True,
        "needs_migration": parsed["needs_migration"],
        "directives": parsed["directives"],
        "recommendations": parsed["recommendations"],
        "hatchling_config": hatchling_config,
    }


# --------------------------------------------------------------------------------------
# Setup.cfg to pyproject.toml migration
# --------------------------------------------------------------------------------------


class MigrationError(ValueError):
    """Raised when migration cannot be completed due to missing or unmapped data."""

    pass


def _parse_setup_cfg_string(content: str) -> dict:
    """Parse setup.cfg content string into a dictionary."""
    parser = ConfigParser()
    parser.read_string(content)

    result = {}
    for section in parser.sections():
        result[section] = dict(parser.items(section))
    return result


def _read_setup_cfg_file(filepath: str) -> dict:
    """Read and parse a setup.cfg file."""
    parser = ConfigParser()
    parser.read(filepath)

    result = {}
    for section in parser.sections():
        result[section] = dict(parser.items(section))
    return result


def _normalize_setup_cfg_input(setup_cfg: Union[str, Mapping]) -> dict:
    """
    Normalize setup_cfg input to a dictionary.

    Args:
        setup_cfg: Either a file path, file content string, or dict

    Returns:
        Dictionary representation of setup.cfg contents

    >>> cfg = _normalize_setup_cfg_input({'metadata': {'name': 'test'}})
    >>> cfg['metadata']['name']
    'test'
    """
    if isinstance(setup_cfg, Mapping):
        return dict(setup_cfg)

    # It's a string - either path or content
    if os.path.isfile(setup_cfg):
        return _read_setup_cfg_file(setup_cfg)
    else:
        # Assume it's the content itself
        return _parse_setup_cfg_string(setup_cfg)


def _extract_metadata_value(cfg: dict, *keys, default=None):
    """
    Extract value from setup.cfg dict trying multiple possible keys.

    >>> cfg = {'metadata': {'name': 'myproject'}}
    >>> _extract_metadata_value(cfg, 'name')
    'myproject'
    """
    metadata = cfg.get("metadata", {})
    for key in keys:
        if key in metadata:
            return metadata[key]
    return default


def _extract_options_value(cfg: dict, *keys, default=None):
    """Extract value from [options] section trying multiple possible keys."""
    options = cfg.get("options", {})
    for key in keys:
        if key in options:
            value = options[key]
            # Handle multi-line values (common in install_requires, keywords, etc.)
            if isinstance(value, str) and "\n" in value:
                # Split and clean
                items = [
                    line.strip() for line in value.strip().split("\n") if line.strip()
                ]
                return items if items else default
            return value
    return default


def _parse_list_field(value: Optional[str]) -> list:
    """Parse a multi-line or comma-separated string field into a list."""
    if not value:
        return []

    if isinstance(value, list):
        return value

    # Handle multi-line format (common in setup.cfg)
    if "\n" in value:
        return [line.strip() for line in value.strip().split("\n") if line.strip()]

    # Handle comma-separated format
    if "," in value:
        return [item.strip() for item in value.split(",") if item.strip()]

    # Single value
    return [value.strip()] if value.strip() else []


# Transformation rules: each rule takes the setup.cfg dict and returns the value for that field
def _rule_project_name(cfg: dict) -> str:
    """Extract project name."""
    return _extract_metadata_value(cfg, "name")


def _rule_project_version(cfg: dict) -> str:
    """Extract project version."""
    return _extract_metadata_value(cfg, "version")


def _rule_project_description(cfg: dict) -> str:
    """Extract project description."""
    return _extract_metadata_value(cfg, "description", default="")


def _rule_project_url(cfg: dict) -> str:
    """Extract project URL."""
    return _extract_metadata_value(cfg, "url", "home_page")


def _rule_project_license(cfg: dict) -> str:
    """Extract license identifier."""
    license_value = _extract_metadata_value(cfg, "license")
    if license_value:
        # Normalize common license names
        license_map = {
            "mit": "MIT",
            "apache-2.0": "Apache-2.0",
            "apache software license": "Apache-2.0",
            "bsd": "BSD",
            "gpl": "GPL",
        }
        return license_map.get(license_value.lower(), license_value)
    return license_value


def _rule_project_keywords(cfg: dict) -> list:
    """Extract keywords as list."""
    keywords = _extract_metadata_value(cfg, "keywords", default="")
    return _parse_list_field(keywords)


def _rule_project_authors(cfg: dict) -> list:
    """Extract authors list."""
    author = _extract_metadata_value(cfg, "author")
    author_email = _extract_metadata_value(cfg, "author_email", "author-email")

    if author or author_email:
        author_dict = {}
        if author:
            author_dict["name"] = author
        if author_email:
            author_dict["email"] = author_email
        return [author_dict]
    return []


def _rule_project_dependencies(cfg: dict) -> list:
    """Extract install_requires as dependencies."""
    deps = _extract_options_value(cfg, "install_requires", default="")
    parsed = _parse_list_field(deps)
    # Filter out placeholder/invalid dependencies
    return [d for d in parsed if d and not d.startswith("this_does_not_exist")]


def _rule_project_optional_dependencies(cfg: dict) -> dict:
    """Extract extras_require as optional-dependencies."""
    extras = cfg.get("options.extras_require", {})
    if not extras:
        return {}

    result = {}
    for key, value in extras.items():
        result[key] = _parse_list_field(value)
    return result


def _rule_project_entry_points(cfg: dict) -> dict:
    """Extract console_scripts from entry_points."""
    entry_points = cfg.get("options.entry_points", {})
    if not entry_points:
        return {}

    console_scripts = entry_points.get("console_scripts", "")
    if not console_scripts:
        return {}

    scripts = _parse_list_field(console_scripts)
    if scripts:
        return {"console_scripts": scripts}
    return {}


# Global rules dictionary mapping field paths to extraction functions
setup_cfg_to_pyproject_toml_rules = {
    "project.name": _rule_project_name,
    "project.version": _rule_project_version,
    "project.description": _rule_project_description,
    "project.url": _rule_project_url,
    "project.license": _rule_project_license,
    "project.keywords": _rule_project_keywords,
    "project.authors": _rule_project_authors,
    "project.dependencies": _rule_project_dependencies,
    "project.optional-dependencies": _rule_project_optional_dependencies,
    "project.scripts": _rule_project_entry_points,
}


def _load_pyproject_template() -> str:
    """Load the pyproject.toml template."""
    with open(pyproject_toml_tpl_path, "r") as f:
        return f.read()


def _apply_rules_to_extract_values(cfg: dict, rules: dict) -> dict:
    """
    Apply extraction rules to setup.cfg dict to get pyproject.toml values.

    Returns a nested dictionary structure matching pyproject.toml layout.
    """
    result = {}

    for field_path, rule_func in rules.items():
        value = rule_func(cfg)
        if value is not None and value != [] and value != {}:
            # Build nested dict structure from dot-separated path
            parts = field_path.split(".")
            current = result
            for part in parts[:-1]:
                if part not in current:
                    current[part] = {}
                current = current[part]
            current[parts[-1]] = value

    return result


def migrate_setuptools_to_hatching(
    setup_cfg: Union[str, Mapping],
    defaults: Optional[dict] = None,
    *,
    rules: Optional[dict] = None,
) -> str:
    """
    Migrate setup.cfg to pyproject.toml format using hatching.

    Args:
        setup_cfg: Either a file path, file content string, or dict of setup.cfg
        defaults: Default values to use for missing required fields
        rules: Custom transformation rules (defaults to setup_cfg_to_pyproject_toml_rules)

    Returns:
        String content of the generated pyproject.toml

    Raises:
        MigrationError: If required fields are missing or unmapped data exists

    Example:
        >>> # From file path
        >>> pyproject = migrate_setuptools_to_hatching('setup.cfg')  # doctest: +SKIP
        >>>
        >>> # From dict with all required fields
        >>> cfg = {
        ...     'metadata': {
        ...         'name': 'myproj',
        ...         'version': '0.1.0',
        ...         'description': 'My project',
        ...         'url': 'https://github.com/user/myproj',
        ...         'license': 'MIT'
        ...     }
        ... }
        >>> result = migrate_setuptools_to_hatching(cfg)
        >>> 'name = "myproj"' in result
        True
        >>>
        >>> # With defaults for missing fields
        >>> minimal = {'metadata': {'name': 'test', 'version': '1.0'}}
        >>> result = migrate_setuptools_to_hatching(
        ...     minimal,
        ...     defaults={
        ...         'description': 'Test project',
        ...         'url': 'https://test.com',
        ...         'license': 'MIT'
        ...     }
        ... )
        >>> 'name = "test"' in result
        True
    """
    if defaults is None:
        defaults = {}

    if rules is None:
        rules = setup_cfg_to_pyproject_toml_rules

    # Normalize input to dict
    cfg = _normalize_setup_cfg_input(setup_cfg)

    # Load template
    template = _load_pyproject_template()

    # Apply rules to extract values
    extracted = _apply_rules_to_extract_values(cfg, rules)

    # Required placeholders in template
    required_fields = {
        "name": extracted.get("project", {}).get("name") or defaults.get("name"),
        "version": extracted.get("project", {}).get("version")
        or defaults.get("version"),
        "description": extracted.get("project", {}).get("description")
        or defaults.get("description", ""),
        "url": extracted.get("project", {}).get("url") or defaults.get("url", ""),
        "license": extracted.get("project", {}).get("license")
        or defaults.get("license", "MIT"),
    }

    # Check for missing required fields
    missing = [k for k, v in required_fields.items() if not v]
    if missing:
        raise MigrationError(
            f"Missing required fields: {missing}. "
            f"Provide them in setup.cfg or via the defaults parameter."
        )

    # Parse the template as TOML (it has placeholders but is valid TOML structure)
    pyproject_dict = tomllib.loads(template)

    # Replace placeholder values with actual values
    if "project" not in pyproject_dict:
        pyproject_dict["project"] = {}

    pyproject_dict["project"]["name"] = required_fields["name"]
    pyproject_dict["project"]["version"] = required_fields["version"]
    pyproject_dict["project"]["description"] = required_fields["description"]
    pyproject_dict["project"]["license"] = {"text": required_fields["license"]}

    if "urls" not in pyproject_dict["project"]:
        pyproject_dict["project"]["urls"] = {}
    pyproject_dict["project"]["urls"]["Homepage"] = required_fields["url"]

    # Merge extracted values
    project_section = extracted.get("project", {})

    # Add keywords if present
    if "keywords" in project_section and project_section["keywords"]:
        pyproject_dict["project"]["keywords"] = project_section["keywords"]

    # Add authors if present
    if "authors" in project_section and project_section["authors"]:
        pyproject_dict["project"]["authors"] = project_section["authors"]

    # Add dependencies if present
    if "dependencies" in project_section and project_section["dependencies"]:
        pyproject_dict["project"]["dependencies"] = project_section["dependencies"]

    # Add optional dependencies if present
    if (
        "optional-dependencies" in project_section
        and project_section["optional-dependencies"]
    ):
        pyproject_dict["project"]["optional-dependencies"] = project_section[
            "optional-dependencies"
        ]

    # Add scripts/entry points if present
    if "scripts" in project_section and project_section["scripts"]:
        if "console_scripts" in project_section["scripts"]:
            pyproject_dict["project"]["scripts"] = {}
            for script in project_section["scripts"]["console_scripts"]:
                if "=" in script:
                    name, target = script.split("=", 1)
                    pyproject_dict["project"]["scripts"][name.strip()] = target.strip()

    # Convert back to TOML string
    from io import BytesIO

    output = BytesIO()
    # Write with tomli_w for consistent formatting
    tomli_w.dump(pyproject_dict, output)

    return output.getvalue().decode("utf-8")


# --------------------------------------------------------------------------------------
# GitHub CI migration
# --------------------------------------------------------------------------------------


def _load_ci_template(filepath: str) -> str:
    """Load CI template file."""
    with open(filepath, "r") as f:
        return f.read()


def _extract_project_name_from_ci(old_ci_content: str) -> Optional[str]:
    """Extract PROJECT_NAME from old CI script."""
    for line in old_ci_content.split("\n"):
        if "PROJECT_NAME:" in line and "#PROJECT_NAME#" in line:
            return None  # Placeholder not filled
        elif "PROJECT_NAME:" in line:
            parts = line.split(":", 1)
            if len(parts) == 2:
                name = parts[1].strip()
                # Remove comments
                if "#" in name:
                    name = name.split("#")[0].strip()
                return name
    return None


def migrate_github_ci_old_to_new(
    old_ci: Union[str, Path],
    defaults: Optional[dict] = None,
) -> str:
    """
    Migrate old GitHub CI script to new 2025 format.

    Args:
        old_ci: Path to old CI file or its content as string
        defaults: Default values for missing fields (e.g., {'project_name': 'myproject'})

    Returns:
        String content of the new CI script

    Raises:
        MigrationError: If unmapped elements exist or required fields are missing

    Note:
        The 2025 CI template is fully config-driven via pyproject.toml.
        Migration now primarily involves setting up proper [tool.wads.ci] configuration
        rather than doing template substitution. For new projects, use populate_pkg_dir()
        to generate proper configuration.

    Example:
        >>> # Migration is now about configuration, not template substitution
        >>> # For new projects, use populate_pkg_dir() instead
        >>> # Old migration approach with placeholders is deprecated
        >>> pass  # doctest: +SKIP
    """
    if defaults is None:
        defaults = {}

    # Read old CI content
    if isinstance(old_ci, Path):
        old_ci = str(old_ci)

    if os.path.isfile(old_ci):
        with open(old_ci, "r") as f:
            old_content = f.read()
    else:
        old_content = old_ci

    # Load new template
    new_template = _load_ci_template(github_ci_publish_2025_path)

    # Extract project name
    project_name = _extract_project_name_from_ci(old_content)
    if not project_name:
        project_name = defaults.get("project_name")

    if not project_name:
        raise MigrationError(
            "Could not extract PROJECT_NAME from old CI script. "
            "Provide it via defaults={'project_name': 'yourproject'}"
        )

    # Check for elements in old CI that might not be in new template
    # This is a basic check - you can expand this based on specific needs
    old_has_setuptools = "setuptools" in old_content.lower()
    old_has_pylint = "pylint" in old_content.lower()

    warnings = []
    if old_has_setuptools:
        warnings.append("Old CI uses setuptools - ensure pyproject.toml is ready")
    if old_has_pylint:
        warnings.append("Old CI uses pylint - new CI uses ruff for linting")

    # Replace project name placeholder
    result = new_template.replace("#PROJECT_NAME#", project_name)

    # Add warnings as comments if any
    if warnings:
        warning_text = "\n".join(f"# MIGRATION NOTE: {w}" for w in warnings)
        # Insert after the first line (name: ...)
        lines = result.split("\n")
        lines.insert(1, warning_text)
        result = "\n".join(lines)

    return result


def main():
    """CLI entry point for wads migration tools."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Migrate old setuptools/CI configurations to modern formats"
    )
    subparsers = parser.add_subparsers(dest="command", help="Migration command")

    # setup.cfg -> pyproject.toml
    setup_parser = subparsers.add_parser(
        "setup-to-pyproject", help="Convert setup.cfg to pyproject.toml"
    )
    setup_parser.add_argument(
        "input", help="Path to setup.cfg file or directory containing it"
    )
    setup_parser.add_argument(
        "-o",
        "--output",
        default="pyproject.toml",
        help="Output file path (default: pyproject.toml)",
    )

    # Old CI -> New CI
    ci_parser = subparsers.add_parser(
        "ci-old-to-new", help="Convert old GitHub CI workflow to new format"
    )
    ci_parser.add_argument("input", help="Path to old CI workflow file")
    ci_parser.add_argument(
        "-o", "--output", help="Output file path (default: print to stdout)"
    )
    ci_parser.add_argument(
        "--project-name", help="Project name (if not in old CI file)"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    try:
        if args.command == "setup-to-pyproject":
            # Handle input path
            input_path = Path(args.input)
            if input_path.is_dir():
                input_path = input_path / "setup.cfg"

            if not input_path.exists():
                print(f"Error: {input_path} not found", file=sys.stderr)
                sys.exit(1)

            # Perform migration
            result = migrate_setuptools_to_hatching(str(input_path))

            # Write output
            output_path = Path(args.output)
            with open(output_path, "w") as f:
                f.write(result)

            print(f"✓ Migrated {input_path} -> {output_path}")

        elif args.command == "ci-old-to-new":
            # Handle input path
            input_path = Path(args.input)
            if not input_path.exists():
                print(f"Error: {input_path} not found", file=sys.stderr)
                sys.exit(1)

            # Prepare defaults
            defaults = {}
            if args.project_name:
                defaults["project_name"] = args.project_name

            # Perform migration
            result = migrate_github_ci_old_to_new(str(input_path), defaults)

            # Write output
            if args.output:
                output_path = Path(args.output)
                with open(output_path, "w") as f:
                    f.write(result)
                print(f"✓ Migrated {input_path} -> {output_path}")
            else:
                print(result)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
