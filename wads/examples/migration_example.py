"""
Example usage of the migration module.

This demonstrates how to use the migration tools to convert old setup.cfg
files to modern pyproject.toml format and migrate old CI scripts.
"""

from wads.migration import migrate_setuptools_to_hatching, migrate_github_ci_old_to_new


def example_migrate_setup_cfg():
    """Example: Migrate setup.cfg to pyproject.toml."""

    # Example 1: From a dictionary
    setup_cfg_dict = {
        "metadata": {
            "name": "example-project",
            "version": "1.0.0",
            "description": "An example project",
            "url": "https://github.com/example/example-project",
            "license": "MIT",
            "author": "Example Author",
            "author_email": "author@example.com",
            "keywords": "example\nproject\nmigration",
        },
        "options": {
            "packages": "find:",
            "install_requires": "requests\nclick>=7.0",
        },
    }

    pyproject_content = migrate_setuptools_to_hatching(setup_cfg_dict)
    print("Generated pyproject.toml:")
    print(pyproject_content)
    print("\n" + "=" * 70 + "\n")

    # Example 2: From a file
    # pyproject_content = migrate_setuptools_to_hatching('path/to/setup.cfg')

    # Example 3: With defaults for missing fields
    minimal_cfg = {
        "metadata": {
            "name": "minimal-project",
            "version": "0.1.0",
        }
    }

    defaults = {
        "description": "A minimal example project",
        "url": "https://github.com/example/minimal",
        "license": "Apache-2.0",
    }

    pyproject_content = migrate_setuptools_to_hatching(minimal_cfg, defaults=defaults)
    print("Generated pyproject.toml with defaults:")
    print(pyproject_content)
    print("\n" + "=" * 70 + "\n")


def example_migrate_ci():
    """Example: Migrate old CI to new format."""

    old_ci = """
name: Continuous Integration
on: [push, pull_request]
env:
  PROJECT_NAME: example_project

jobs:
  validation:
    name: Validation
    steps:
      - uses: actions/checkout@v3
      - name: Install setuptools
        run: python -m pip install setuptools
"""

    new_ci = migrate_github_ci_old_to_new(old_ci)
    print("Migrated CI script:")
    print(new_ci)


if __name__ == "__main__":
    print("=" * 70)
    print("EXAMPLE: Migrating setup.cfg to pyproject.toml")
    print("=" * 70 + "\n")
    example_migrate_setup_cfg()

    print("\n" + "=" * 70)
    print("EXAMPLE: Migrating CI scripts")
    print("=" * 70 + "\n")
    example_migrate_ci()
