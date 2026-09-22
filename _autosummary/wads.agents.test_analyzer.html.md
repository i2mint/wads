# wads.agents.test_analyzer

Test Failure Analyzer Agent

Analyzes pytest test failures, categorizes them, and suggests fixes.
Identifies patterns in failures and provides actionable recommendations.

### Functions

| [`categorize_failure`](#wads.agents.test_analyzer.categorize_failure)(error_type, error_message)   | Categorize test failure type.             |
|--------------------------------------------------------------------------------------------------|-------------------------------------------|
| [`main`](#wads.agents.test_analyzer.main)()                                          | CLI entry point for test analyzer.        |
| [`parse_pytest_output`](#wads.agents.test_analyzer.parse_pytest_output)(output)                     | Parse pytest output and analyze failures. |
| [`print_report`](#wads.agents.test_analyzer.print_report)(report)                            | Print formatted test analysis report.     |
| [`suggest_fix`](#wads.agents.test_analyzer.suggest_fix)(category, error_message)            | Suggest fix based on failure category.    |

### Classes

| [`TestAnalysisReport`](#wads.agents.test_analyzer.TestAnalysisReport)(total_failures, ...)      | Result of test failure analysis.       |
|-----------------------------------------------------------------------------------------------|----------------------------------------|
| [`TestFailurePattern`](#wads.agents.test_analyzer.TestFailurePattern)(pattern_type, count, ...) | Represents a pattern of test failures. |

### *class* wads.agents.test_analyzer.TestAnalysisReport(total_failures, total_errors, failure_patterns, flaky_tests, slow_tests, recommendations)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Result of test failure analysis.

### *class* wads.agents.test_analyzer.TestFailurePattern(pattern_type, count, examples, suggested_fix, severity)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Represents a pattern of test failures.

### wads.agents.test_analyzer.categorize_failure(error_type, error_message)

Categorize test failure type.

* **Parameters:**
  * **error_type** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Type of error (AssertionError, ValueError, etc.)
  * **error_message** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Error message
* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
* **Returns:**
  Category string

### wads.agents.test_analyzer.main()

CLI entry point for test analyzer.

### wads.agents.test_analyzer.parse_pytest_output(output)

Parse pytest output and analyze failures.

* **Parameters:**
  **output** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Pytest output text
* **Return type:**
  [`TestAnalysisReport`](#wads.agents.test_analyzer.TestAnalysisReport)
* **Returns:**
  TestAnalysisReport with analysis

### wads.agents.test_analyzer.print_report(report)

Print formatted test analysis report.

### wads.agents.test_analyzer.suggest_fix(category, error_message)

Suggest fix based on failure category.

* **Parameters:**
  * **category** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Failure category
  * **error_message** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Error message
* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
* **Returns:**
  Suggested fix description
