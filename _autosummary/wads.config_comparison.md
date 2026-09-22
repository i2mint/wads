# wads.config_comparison

Compare project configuration files (pyproject.toml, setup.cfg, MANIFEST.in) against templates.

This module provides tools to analyze project configurations and identify
differences from standard templates, helping users maintain up-to-date
project structures.

Key Functions:
: compare_pyproject_toml: Compare actual pyproject.toml against template
  compare_setup_cfg: Analyze setup.cfg and recommend migration
  compare_manifest_in: Analyze MANIFEST.in and recommend Hatchling migration
  summarize_config_status: Overall project config health check
  compare_ci_workflow: Compare CI workflow against template

### Example

```pycon
>>> from wads.config_comparison import summarize_config_status
>>> status = summarize_config_status('/path/to/project')
>>> if status['needs_attention']:
...     print(status['recommendations'])
```

### Functions

| [`compare_ci_workflow`](#wads.config_comparison.compare_ci_workflow)(actual_path[, ...])     | Compare CI workflow against modern template.                            |
|----------------------------------------------------------------------------------------------|-------------------------------------------------------------------------|
| [`compare_manifest_in`](#wads.config_comparison.compare_manifest_in)(actual_path)            | Analyze MANIFEST.in and recommend migration to Hatchling configuration. |
| [`compare_pyproject_toml`](#wads.config_comparison.compare_pyproject_toml)(actual_path[, ...])  | Compare actual pyproject.toml against template.                         |
| [`compare_setup_cfg`](#wads.config_comparison.compare_setup_cfg)(actual_path, \*[, ...])   | Analyze setup.cfg and recommend migration to pyproject.toml.            |
| [`summarize_config_status`](#wads.config_comparison.summarize_config_status)(pkg_dir, \*[, ...]) | Check overall config status of a project.                               |

### wads.config_comparison.compare_ci_workflow(actual_path, template_path='/home/runner/work/wads/wads/wads/data/github_ci_publish_2025.yml', , project_name=None)

Compare CI workflow against modern template.

* **Parameters:**
  * **actual_path** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)) – Path to .github/workflows/ci.yml
  * **template_path** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)) – Path to template CI workflow
  * **project_name** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Optional project name for placeholder replacement
* **Return type:**
  [`Dict`](https://docs.python.org/3/library/typing.html#typing.Dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]
* **Returns:**
  Dictionary with comparison results and recommendations

### Example

```pycon
>>> diff = compare_ci_workflow('.github/workflows/ci.yml')
>>> if diff['needs_attention']:
...     print("CI might be outdated")
```

### wads.config_comparison.compare_manifest_in(actual_path)

Analyze MANIFEST.in and recommend migration to Hatchling configuration.

* **Parameters:**
  **actual_path** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)) – Path to MANIFEST.in file
* **Return type:**
  [`Dict`](https://docs.python.org/3/library/typing.html#typing.Dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]
* **Returns:**
  Dictionary with migration recommendations

### Example

```pycon
>>> analysis = compare_manifest_in('MANIFEST.in')
>>> if analysis['needs_migration']:
...     print(analysis['hatchling_config'])
```

### wads.config_comparison.compare_pyproject_toml(actual_path, template_path='/home/runner/work/wads/wads/wads/data/pyproject_toml_tpl.toml', , ignore_keys=None, project_name=None)

Compare actual pyproject.toml against template.

* **Parameters:**
  * **actual_path** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)) – Path to the project’s pyproject.toml
  * **template_path** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)) – Path to template pyproject.toml
  * **ignore_keys** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`Set`](https://docs.python.org/3/library/typing.html#typing.Set)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]) – Keys to ignore in comparison (project-specific values)
  * **project_name** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Optional project name for contextual recommendations
* **Returns:**
  - ‘missing_sections’: sections in template but not in actual
  - ’outdated_sections’: sections in actual that might be outdated
  - ’recommendations’: suggested updates
  - ’needs_attention’: boolean flag
* **Return type:**
  [`Dict`](https://docs.python.org/3/library/typing.html#typing.Dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### Example

```pycon
>>> diff = compare_pyproject_toml('my_project/pyproject.toml')
>>> if diff['needs_attention']:
...     for rec in diff['recommendations']:
...         print(f"  - {rec}")
```

### wads.config_comparison.compare_setup_cfg(actual_path, , warn_about_deprecation=True)

Analyze setup.cfg and recommend migration to pyproject.toml.

* **Parameters:**
  * **actual_path** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)) – Path to setup.cfg file
  * **warn_about_deprecation** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Whether to warn about using deprecated format
* **Return type:**
  [`Dict`](https://docs.python.org/3/library/typing.html#typing.Dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]
* **Returns:**
  Dictionary with migration recommendations

### Example

```pycon
>>> analysis = compare_setup_cfg('old_project/setup.cfg')
>>> if analysis['should_migrate']:
...     print(analysis['recommendations'])
```

### wads.config_comparison.summarize_config_status(pkg_dir, , check_ci=True, project_name=None)

Check overall config status of a project.

Analyzes pyproject.toml, setup.cfg, CI workflows and returns a comprehensive
summary of what needs attention.

* **Parameters:**
  * **pkg_dir** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)) – Path to project directory
  * **check_ci** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Whether to check CI workflow
  * **project_name** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Optional project name for contextual checks
* **Returns:**
  - ‘has_pyproject’: bool
  - ’has_setup_cfg’: bool
  - ’has_ci’: bool
  - ’needs_attention’: list of issues
  - ’recommendations’: list of recommendations
  - Details for each file type
* **Return type:**
  [`Dict`](https://docs.python.org/3/library/typing.html#typing.Dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### Example

```pycon
>>> status = summarize_config_status('/path/to/project')
>>> for issue in status['needs_attention']:
...     print(f"⚠️  {issue}")
```
