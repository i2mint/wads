# wads.setup_utils

Utilities for setting up packages based on pyproject.toml configuration.

This module provides tools for users to:

- Install Python dependencies with various options
- Install system dependencies based on OS and toml specs
- Validate environment variables
- Diagnose missing dependencies and provide instructions

### Functions

| [`check_environment_variables`](#wads.setup_utils.check_environment_variables)(pyproject_path)     | Check required environment variables from pyproject.toml.          |
|--------------------------------------------------------------------------------------------------|--------------------------------------------------------------------|
| [`check_system_dependency`](#wads.setup_utils.check_system_dependency)(dep_name, dep_ops, ...) | Check if a system dependency is installed using check commands.    |
| [`diagnose_setup`](#wads.setup_utils.diagnose_setup)(pyproject_path[, ...])           | Diagnose missing dependencies and configuration issues.            |
| [`get_current_platform`](#wads.setup_utils.get_current_platform)()                          | Get current platform identifier (linux, macos, windows).           |
| [`get_installed_pip_packages`](#wads.setup_utils.get_installed_pip_packages)()                    | Get set of installed pip package names.                            |
| [`install_python_dependencies`](#wads.setup_utils.install_python_dependencies)(pyproject_path)     | Install Python dependencies from pyproject.toml.                   |
| [`install_system_dependencies`](#wads.setup_utils.install_system_dependencies)(pyproject_path)     | Install system dependencies based on pyproject.toml configuration. |
| [`is_package_importable`](#wads.setup_utils.is_package_importable)(package_name)             | Check if a Python package can be imported.                         |
| [`print_diagnostic_report`](#wads.setup_utils.print_diagnostic_report)(result)                 | Print a formatted diagnostic report.                               |

### Classes

| [`DiagnosticResult`](#wads.setup_utils.DiagnosticResult)(missing_python_deps, ...)    | Result of dependency diagnostics.   |
|------------------------------------------------------------------------------------------------|-------------------------------------|
| [`InstallResult`](#wads.setup_utils.InstallResult)(success, package_name, message) | Result of an installation attempt.  |

### *class* wads.setup_utils.DiagnosticResult(missing_python_deps, missing_system_deps, missing_env_vars, warnings, recommendations)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Result of dependency diagnostics.

### *class* wads.setup_utils.InstallResult(success, package_name, message, command_executed=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Result of an installation attempt.

### wads.setup_utils.check_environment_variables(pyproject_path, verbose=True)

Check required environment variables from pyproject.toml.

* **Parameters:**
  * **pyproject_path** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)) – Path to pyproject.toml or directory containing it
  * **verbose** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Print warnings for missing variables
* **Return type:**
  [`Dict`](https://docs.python.org/3/library/typing.html#typing.Dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]
* **Returns:**
  Dict mapping variable names to their values (None if missing)

### wads.setup_utils.check_system_dependency(dep_name, dep_ops, platform, verbose=True)

Check if a system dependency is installed using check commands.

* **Parameters:**
  * **dep_name** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Simplified dependency name
  * **dep_ops** ([`Dict`](https://docs.python.org/3/library/typing.html#typing.Dict)) – Operational metadata for the dependency
  * **platform** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Platform identifier (linux, macos, windows)
  * **verbose** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Print check attempts
* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)
* **Returns:**
  True if dependency is installed (or no check command available)

### wads.setup_utils.diagnose_setup(pyproject_path, check_python=True, check_system=True, check_env=True, platform=None)

Diagnose missing dependencies and configuration issues.

* **Parameters:**
  * **pyproject_path** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)) – Path to pyproject.toml or directory containing it
  * **check_python** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Check Python dependencies
  * **check_system** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Check system dependencies
  * **check_env** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Check environment variables
  * **platform** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – Platform identifier (auto-detected if None)
* **Return type:**
  [`DiagnosticResult`](#wads.setup_utils.DiagnosticResult)
* **Returns:**
  DiagnosticResult with comprehensive analysis

### wads.setup_utils.get_current_platform()

Get current platform identifier (linux, macos, windows).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
* **Returns:**
  Platform string compatible with wads configuration

### wads.setup_utils.get_installed_pip_packages()

Get set of installed pip package names.

* **Return type:**
  [`Set`](https://docs.python.org/3/library/typing.html#typing.Set)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]
* **Returns:**
  Set of installed package names (lowercase)

### wads.setup_utils.install_python_dependencies(pyproject_path, exclude=None, check_importable=True, upgrade=False, allow_downgrade=False, extras=None, dry_run=False, verbose=True)

Install Python dependencies from pyproject.toml.

* **Parameters:**
  * **pyproject_path** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)) – Path to pyproject.toml or directory containing it
  * **exclude** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`List`](https://docs.python.org/3/library/typing.html#typing.List)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]) – List of package names to exclude from installation
  * **check_importable** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Only install if package is not already importable
  * **upgrade** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Pass –upgrade flag to pip
  * **allow_downgrade** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Allow pip to downgrade packages (adds –force-reinstall)
  * **extras** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`List`](https://docs.python.org/3/library/typing.html#typing.List)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]) – List of extras to install (e.g., [‘dev’, ‘test’])
  * **dry_run** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – If True, only show what would be installed
  * **verbose** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Print detailed progress information
* **Return type:**
  [`List`](https://docs.python.org/3/library/typing.html#typing.List)[[`InstallResult`](#wads.setup_utils.InstallResult)]
* **Returns:**
  List of InstallResult objects

### wads.setup_utils.install_system_dependencies(pyproject_path, platform=None, check_first=True, dry_run=False, verbose=True, interactive=True)

Install system dependencies based on pyproject.toml configuration.

This is a wrapper around wads.install_system_deps module.

* **Parameters:**
  * **pyproject_path** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)) – Path to pyproject.toml or directory containing it
  * **platform** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – Platform identifier (auto-detected if None)
  * **check_first** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Use check commands to verify if already installed (ignored in dry_run)
  * **dry_run** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – If True, only show what would be installed
  * **verbose** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Print detailed progress information
  * **interactive** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Ask for confirmation before installing (not yet implemented)
* **Return type:**
  [`List`](https://docs.python.org/3/library/typing.html#typing.List)[[`InstallResult`](#wads.setup_utils.InstallResult)]
* **Returns:**
  List of InstallResult objects

### wads.setup_utils.is_package_importable(package_name)

Check if a Python package can be imported.

* **Parameters:**
  **package_name** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Name of the package to check
* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)
* **Returns:**
  True if the package is importable

### wads.setup_utils.print_diagnostic_report(result)

Print a formatted diagnostic report.

* **Parameters:**
  **result** ([`DiagnosticResult`](#wads.setup_utils.DiagnosticResult)) – DiagnosticResult to display
