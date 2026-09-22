# wads.agents

Wads AI Agents

Autonomous agents for diagnosing and fixing common development issues.

Available Agents:

- ci_debug_agent: Analyzes failed CI runs and proposes fixes
- dependency_resolver: Analyzes import errors and missing dependencies
- test_analyzer: Analyzes pytest failures and categorizes them

### Functions

| [`diagnose_ci_failure`](#wads.agents.diagnose_ci_failure)(repo[, run_id])       | Diagnose a CI failure.                            |
|--------------------------------------------------------------------------------------------|---------------------------------------------------|
| [`analyze_dependencies`](#wads.agents.analyze_dependencies)(project_path[, ...]) | Analyze project dependencies and identify issues. |
| [`parse_pytest_output`](#wads.agents.parse_pytest_output)(output)               | Parse pytest output and analyze failures.         |

### Classes

| [`CIDiagnosis`](#wads.agents.CIDiagnosis)(failures, missing_system_deps, ...)   | Result of CI failure diagnosis.                 |
|----------------------------------------------------------------------------------------------------|-------------------------------------------------|
| [`TestFailure`](#wads.agents.TestFailure)(test_name, error_type, ...[, ...])    | Represents a single test failure.               |
| [`DependencyReport`](#wads.agents.DependencyReport)(missing_packages, ...)           | Result of dependency analysis.                  |
| [`DependencyIssue`](#wads.agents.DependencyIssue)(package_name, import_statement)   | Represents a missing or problematic dependency. |
| [`TestAnalysisReport`](#wads.agents.TestAnalysisReport)(total_failures, ...)           | Result of test failure analysis.                |
| [`TestFailurePattern`](#wads.agents.TestFailurePattern)(pattern_type, count, ...)      | Represents a pattern of test failures.          |

### *class* wads.agents.CIDiagnosis(failures, missing_system_deps, missing_python_deps, config_issues, proposed_fixes, confidence, warnings=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Result of CI failure diagnosis.

### *class* wads.agents.DependencyIssue(package_name, import_statement, file_path=None, line_number=None, suggested_package=None, error_message=None, is_installed=False)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Represents a missing or problematic dependency.

### *class* wads.agents.DependencyReport(missing_packages, unused_packages, version_conflicts, recommendations)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Result of dependency analysis.

### *class* wads.agents.TestAnalysisReport(total_failures, total_errors, failure_patterns, flaky_tests, slow_tests, recommendations)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Result of test failure analysis.

### *class* wads.agents.TestFailure(test_name, error_type, error_message, traceback, file_path=None, line_number=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Represents a single test failure.

### *class* wads.agents.TestFailurePattern(pattern_type, count, examples, suggested_fix, severity)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Represents a pattern of test failures.

### wads.agents.analyze_dependencies(project_path, error_logs=None, check_unused=True)

Analyze project dependencies and identify issues.

* **Parameters:**
  * **project_path** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)) – Path to project directory
  * **error_logs** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – Optional error logs to parse
  * **check_unused** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Whether to check for unused dependencies
* **Return type:**
  [`DependencyReport`](wads.agents.dependency_resolver.html.md#wads.agents.dependency_resolver.DependencyReport)
* **Returns:**
  DependencyReport with analysis results

### wads.agents.diagnose_ci_failure(repo, run_id=None)

Diagnose a CI failure.

* **Parameters:**
  * **repo** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Repository in format ‘owner/name’
  * **run_id** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`int`](https://docs.python.org/3/builtins/functions.html#int)]) – Specific run ID, or None for latest failed run
* **Return type:**
  [`CIDiagnosis`](wads.agents.ci_debug_agent.html.md#wads.agents.ci_debug_agent.CIDiagnosis)
* **Returns:**
  CIDiagnosis with analysis results

### wads.agents.parse_pytest_output(output)

Parse pytest output and analyze failures.

* **Parameters:**
  **output** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Pytest output text
* **Return type:**
  [`TestAnalysisReport`](wads.agents.test_analyzer.html.md#wads.agents.test_analyzer.TestAnalysisReport)
* **Returns:**
  TestAnalysisReport with analysis

### Modules

| [`ci_debug_agent`](wads.agents.ci_debug_agent.html.md#module-wads.agents.ci_debug_agent)           | CI Debugging Agent for Wads   |
|-------------------------------------------------------------------------------------------------------------|-------------------------------|
| [`dependency_resolver`](wads.agents.dependency_resolver.html.md#module-wads.agents.dependency_resolver) | Dependency Resolver Agent     |
| [`test_analyzer`](wads.agents.test_analyzer.html.md#module-wads.agents.test_analyzer)             | Test Failure Analyzer Agent   |
