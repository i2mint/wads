# wads.agents.dependency_resolver

Dependency Resolver Agent

Automatically analyzes import errors, missing dependencies, and suggests fixes.
Can scan local code, analyze error messages, and propose dependency additions.

### Functions

| [`analyze_dependencies`](#wads.agents.dependency_resolver.analyze_dependencies)(project_path[, ...])   | Analyze project dependencies and identify issues.     |
|----------------------------------------------------------------------------------------------|-------------------------------------------------------|
| [`extract_imports_from_file`](#wads.agents.dependency_resolver.extract_imports_from_file)(file_path)        | Extract all import statements from a Python file.     |
| [`get_installed_packages`](#wads.agents.dependency_resolver.get_installed_packages)()                    | Get list of installed packages using pip.             |
| [`main`](#wads.agents.dependency_resolver.main)()                                      | CLI entry point for dependency resolver.              |
| [`parse_error_message`](#wads.agents.dependency_resolver.parse_error_message)(error_msg)              | Parse error messages to extract missing dependencies. |
| [`print_report`](#wads.agents.dependency_resolver.print_report)(report)                        | Print formatted dependency report.                    |
| [`read_project_dependencies`](#wads.agents.dependency_resolver.read_project_dependencies)(pyproject_path)   | Read declared dependencies from pyproject.toml.       |
| [`resolve_package_name`](#wads.agents.dependency_resolver.resolve_package_name)(import_name)           | Resolve import name to package name.                  |
| [`scan_project_imports`](#wads.agents.dependency_resolver.scan_project_imports)(project_path[, ...])   | Scan all Python files in a project for imports.       |

### Classes

| [`DependencyIssue`](#wads.agents.dependency_resolver.DependencyIssue)(package_name, import_statement)   | Represents a missing or problematic dependency.   |
|----------------------------------------------------------------------------------------------------|---------------------------------------------------|
| [`DependencyReport`](#wads.agents.dependency_resolver.DependencyReport)(missing_packages, ...)           | Result of dependency analysis.                    |

### *class* wads.agents.dependency_resolver.DependencyIssue(package_name, import_statement, file_path=None, line_number=None, suggested_package=None, error_message=None, is_installed=False)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Represents a missing or problematic dependency.

### *class* wads.agents.dependency_resolver.DependencyReport(missing_packages, unused_packages, version_conflicts, recommendations)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Result of dependency analysis.

### wads.agents.dependency_resolver.analyze_dependencies(project_path, error_logs=None, check_unused=True)

Analyze project dependencies and identify issues.

* **Parameters:**
  * **project_path** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)) – Path to project directory
  * **error_logs** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – Optional error logs to parse
  * **check_unused** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Whether to check for unused dependencies
* **Return type:**
  [`DependencyReport`](#wads.agents.dependency_resolver.DependencyReport)
* **Returns:**
  DependencyReport with analysis results

### wads.agents.dependency_resolver.extract_imports_from_file(file_path)

Extract all import statements from a Python file.

* **Parameters:**
  **file_path** ([`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)) – Path to Python file
* **Return type:**
  [`Set`](https://docs.python.org/3/library/typing.html#typing.Set)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]
* **Returns:**
  Set of imported module names

### wads.agents.dependency_resolver.get_installed_packages()

Get list of installed packages using pip.

* **Return type:**
  [`Set`](https://docs.python.org/3/library/typing.html#typing.Set)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]
* **Returns:**
  Set of installed package names (lowercase)

### wads.agents.dependency_resolver.main()

CLI entry point for dependency resolver.

### wads.agents.dependency_resolver.parse_error_message(error_msg)

Parse error messages to extract missing dependencies.

* **Parameters:**
  **error_msg** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Error message from Python/pytest
* **Return type:**
  [`List`](https://docs.python.org/3/library/typing.html#typing.List)[[`DependencyIssue`](#wads.agents.dependency_resolver.DependencyIssue)]
* **Returns:**
  List of DependencyIssue objects

### wads.agents.dependency_resolver.print_report(report)

Print formatted dependency report.

### wads.agents.dependency_resolver.read_project_dependencies(pyproject_path)

Read declared dependencies from pyproject.toml.

* **Parameters:**
  **pyproject_path** ([`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)) – Path to pyproject.toml
* **Return type:**
  [`Tuple`](https://docs.python.org/3/library/typing.html#typing.Tuple)[[`Set`](https://docs.python.org/3/library/typing.html#typing.Set)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)], [`Set`](https://docs.python.org/3/library/typing.html#typing.Set)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]
* **Returns:**
  Tuple of (main_dependencies, dev_dependencies)

### wads.agents.dependency_resolver.resolve_package_name(import_name)

Resolve import name to package name.

* **Parameters:**
  **import_name** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Name used in import statement
* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
* **Returns:**
  Likely package name for pip install

### wads.agents.dependency_resolver.scan_project_imports(project_path, exclude_patterns=None)

Scan all Python files in a project for imports.

* **Parameters:**
  * **project_path** ([`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)) – Root path of project
  * **exclude_patterns** ([`List`](https://docs.python.org/3/library/typing.html#typing.List)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – Patterns to exclude (e.g., ‘tests’, ‘venv’)
* **Return type:**
  [`Dict`](https://docs.python.org/3/library/typing.html#typing.Dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Set`](https://docs.python.org/3/library/typing.html#typing.Set)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]
* **Returns:**
  Dict mapping file paths to sets of imported modules
