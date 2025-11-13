"""
Quick Reference Guide for wads.migration
=========================================

BASIC SETUP.CFG MIGRATION
--------------------------

From file:
    >>> from wads.migration import migrate_setuptools_to_hatching  # doctest: +SKIP
    >>> pyproject = migrate_setuptools_to_hatching('setup.cfg')  # doctest: +SKIP
    >>> with open('pyproject.toml', 'w') as f:  # doctest: +SKIP
    ...     f.write(pyproject)

From string:
    >>> setup_cfg_text = "[metadata]\\nname=myproj\\nversion=1.0.0"  # doctest: +SKIP
    >>> pyproject = migrate_setuptools_to_hatching(setup_cfg_text)  # doctest: +SKIP

From dict:
    >>> cfg = {'metadata': {'name': 'myproj', 'version': '1.0.0'}}  # doctest: +SKIP
    >>> pyproject = migrate_setuptools_to_hatching(cfg)  # doctest: +SKIP


WITH DEFAULTS FOR MISSING FIELDS
---------------------------------

    >>> pyproject = migrate_setuptools_to_hatching(  # doctest: +SKIP
    ...     'setup.cfg',
    ...     defaults={
    ...         'description': 'My awesome project',
    ...         'url': 'https://github.com/user/project',
    ...         'license': 'MIT'
    ...     }
    ... )


CUSTOM TRANSFORMATION RULES
----------------------------

    >>> custom_rules = {  # doctest: +SKIP
    ...     'project.name': lambda cfg: cfg['metadata']['name'].upper(),
    ...     'project.version': lambda cfg: cfg['metadata']['version'],
    ...     'project.description': lambda cfg: "Custom description",
    ... }
    >>> pyproject = migrate_setuptools_to_hatching('setup.cfg', rules=custom_rules)  # doctest: +SKIP


ERROR HANDLING
--------------

    >>> from wads.migration import MigrationError  # doctest: +SKIP
    >>> try:  # doctest: +SKIP
    ...     pyproject = migrate_setuptools_to_hatching(incomplete_cfg)
    ... except MigrationError as e:
    ...     print(f"Missing: {e}")
    ...     # Provide defaults and retry


CI MIGRATION
------------

From file:
    >>> from wads.migration import migrate_github_ci_old_to_new
    >>> new_ci = migrate_github_ci_old_to_new('.github/workflows/ci.yml')
    >>> with open('.github/workflows/ci_new.yml', 'w') as f:  # doctest: +SKIP
    ...     f.write(new_ci)

With defaults:
    >>> new_ci = migrate_github_ci_old_to_new(  # doctest: +SKIP
    ...     'ci.yml',
    ...     defaults={'project_name': 'myproject'}
    ... )


COMPLETE MIGRATION WORKFLOW
----------------------------

Migrate setup.cfg and CI files:

    >>> from pathlib import Path  # doctest: +SKIP
    >>> from wads.migration import (  # doctest: +SKIP
    ...     migrate_setuptools_to_hatching,
    ...     migrate_github_ci_old_to_new
    ... )
    >>> project = Path('/path/to/project')  # doctest: +SKIP
    >>> pyproject = migrate_setuptools_to_hatching(str(project / 'setup.cfg'))  # doctest: +SKIP
    >>> (project / 'pyproject.toml').write_text(pyproject)  # doctest: +SKIP
    >>> old_ci = project / '.github/workflows/ci.yml'  # doctest: +SKIP
    >>> if old_ci.exists():  # doctest: +SKIP
    ...     new_ci = migrate_github_ci_old_to_new(str(old_ci))
    ...     (project / '.github/workflows/ci_new.yml').write_text(new_ci)


AVAILABLE TRANSFORMATION RULES
-------------------------------

The following fields are automatically extracted from setup.cfg:

    project.name                     - Project name
    project.version                  - Version number
    project.description              - Description
    project.url                      - Homepage URL
    project.license                  - License identifier
    project.keywords                 - Keywords list
    project.authors                  - Author information
    project.dependencies             - install_requires → dependencies
    project.optional-dependencies    - extras_require
    project.scripts                  - console_scripts entry points


ADDING NEW RULES
----------------

    >>> from wads.migration import setup_cfg_to_pyproject_toml_rules
    >>>
    >>> def _rule_custom_field(cfg: dict) -> str:
    ...     return cfg.get('metadata', {}).get('custom', 'default')
    >>>
    >>> setup_cfg_to_pyproject_toml_rules['project.custom'] = _rule_custom_field


COMMON PATTERNS
---------------

Check if migration needed:
    >>> from pathlib import Path  # doctest: +SKIP
    >>> project = Path('/path/to/project')  # doctest: +SKIP
    >>> needs_migration = (  # doctest: +SKIP
    ...     (project / 'setup.cfg').exists() and
    ...     not (project / 'pyproject.toml').exists()
    ... )

Batch migration:
    >>> projects = [Path(p) for p in ['proj1', 'proj2', 'proj3']]  # doctest: +SKIP
    >>> for proj in projects:  # doctest: +SKIP
    ...     if (proj / 'setup.cfg').exists():
    ...         pyproject = migrate_setuptools_to_hatching(str(proj / 'setup.cfg'))
    ...         (proj / 'pyproject.toml').write_text(pyproject)

Dry-run (show what would be done):
    >>> from wads.migration import migrate_setuptools_to_hatching
    >>> pyproject = migrate_setuptools_to_hatching('setup.cfg')
    >>> print(pyproject[:500])  # doctest: +ELLIPSIS
    [build-system]
    requires = [
        "hatchling",
    ]
    ...


For complete documentation, see MIGRATION.md
"""
