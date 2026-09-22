# wads.agents.ci_debug_agent

CI Debugging Agent for Wads

This agent analyzes failed CI runs, diagnoses issues, and proposes fixes.
It can:

- Fetch GitHub Actions logs via API
- Parse test failures and error messages
- Analyze code context
- Diagnose root causes (missing deps, config issues, code bugs)
- Propose fixes (install commands, code changes, config updates)

Usage:

```default
python -m wads.ci_debug_agent <repo> [--run-id RUN_ID] [--fix]
```

### Functions

| [`diagnose_ci_failure`](#wads.agents.ci_debug_agent.diagnose_ci_failure)(repo[, run_id])             | Diagnose a CI failure.                                    |
|--------------------------------------------------------------------------------------------------|-----------------------------------------------------------|
| [`diagnose_missing_python_deps`](#wads.agents.ci_debug_agent.diagnose_missing_python_deps)(failures)          | Identify missing Python dependencies from import errors.  |
| [`diagnose_missing_system_deps`](#wads.agents.ci_debug_agent.diagnose_missing_system_deps)(failures, logs)    | Identify missing system dependencies from error messages. |
| [`fetch_workflow_logs`](#wads.agents.ci_debug_agent.fetch_workflow_logs)(repo, run_id)               | Fetch logs for a specific workflow run.                   |
| [`fetch_workflow_runs`](#wads.agents.ci_debug_agent.fetch_workflow_runs)(repo[, limit])              | Fetch recent workflow runs for a repository.              |
| [`generate_fix_instructions`](#wads.agents.ci_debug_agent.generate_fix_instructions)(diagnosis, repo_path) | Generate detailed fix instructions.                       |
| [`get_github_token`](#wads.agents.ci_debug_agent.get_github_token)()                              | Get GitHub token from environment.                        |
| [`main`](#wads.agents.ci_debug_agent.main)()                                          | CLI entry point for wads CI debug agent.                  |
| [`parse_ci_warnings`](#wads.agents.ci_debug_agent.parse_ci_warnings)(logs)                         | Parse CI warnings from logs that may indicate issues.     |
| [`parse_pytest_failures`](#wads.agents.ci_debug_agent.parse_pytest_failures)(logs)                     | Parse pytest failures and collection errors from CI logs. |
| [`print_diagnosis`](#wads.agents.ci_debug_agent.print_diagnosis)(diagnosis)                      | Print formatted diagnosis report.                         |

### Classes

| [`CIDiagnosis`](#wads.agents.ci_debug_agent.CIDiagnosis)(failures, missing_system_deps, ...)   | Result of CI failure diagnosis.   |
|----------------------------------------------------------------------------------------------------|-----------------------------------|
| [`TestFailure`](#wads.agents.ci_debug_agent.TestFailure)(test_name, error_type, ...[, ...])    | Represents a single test failure. |

### *class* wads.agents.ci_debug_agent.CIDiagnosis(failures, missing_system_deps, missing_python_deps, config_issues, proposed_fixes, confidence, warnings=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Result of CI failure diagnosis.

### *class* wads.agents.ci_debug_agent.TestFailure(test_name, error_type, error_message, traceback, file_path=None, line_number=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Represents a single test failure.

### wads.agents.ci_debug_agent.diagnose_ci_failure(repo, run_id=None)

Diagnose a CI failure.

* **Parameters:**
  * **repo** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Repository in format ‘owner/name’
  * **run_id** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`int`](https://docs.python.org/3/builtins/functions.html#int)]) – Specific run ID, or None for latest failed run
* **Return type:**
  [`CIDiagnosis`](#wads.agents.ci_debug_agent.CIDiagnosis)
* **Returns:**
  CIDiagnosis with analysis results

### wads.agents.ci_debug_agent.diagnose_missing_python_deps(failures)

Identify missing Python dependencies from import errors.

* **Parameters:**
  **failures** ([`List`](https://docs.python.org/3/library/typing.html#typing.List)[[`TestFailure`](#wads.agents.ci_debug_agent.TestFailure)]) – List of test failures
* **Return type:**
  [`List`](https://docs.python.org/3/library/typing.html#typing.List)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]
* **Returns:**
  List of likely missing Python packages

### wads.agents.ci_debug_agent.diagnose_missing_system_deps(failures, logs)

Identify missing system dependencies from error messages.

* **Parameters:**
  * **failures** ([`List`](https://docs.python.org/3/library/typing.html#typing.List)[[`TestFailure`](#wads.agents.ci_debug_agent.TestFailure)]) – List of test failures
  * **logs** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Full CI logs
* **Return type:**
  [`List`](https://docs.python.org/3/library/typing.html#typing.List)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]
* **Returns:**
  List of likely missing system dependencies

### wads.agents.ci_debug_agent.fetch_workflow_logs(repo, run_id)

Fetch logs for a specific workflow run.

* **Parameters:**
  * **repo** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Repository in format ‘owner/name’
  * **run_id** ([`int`](https://docs.python.org/3/builtins/functions.html#int)) – Workflow run ID
* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
* **Returns:**
  Log content as string

### wads.agents.ci_debug_agent.fetch_workflow_runs(repo, limit=5)

Fetch recent workflow runs for a repository.

* **Parameters:**
  * **repo** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Repository in format ‘owner/name’
  * **limit** ([`int`](https://docs.python.org/3/builtins/functions.html#int)) – Number of runs to fetch
* **Return type:**
  [`List`](https://docs.python.org/3/library/typing.html#typing.List)[[`Dict`](https://docs.python.org/3/library/typing.html#typing.Dict)]
* **Returns:**
  List of workflow run dictionaries

### wads.agents.ci_debug_agent.generate_fix_instructions(diagnosis, repo_path)

Generate detailed fix instructions.

* **Parameters:**
  * **diagnosis** ([`CIDiagnosis`](#wads.agents.ci_debug_agent.CIDiagnosis)) – CIDiagnosis result
  * **repo_path** ([`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)) – Local path to repository
* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
* **Returns:**
  Formatted fix instructions

### wads.agents.ci_debug_agent.get_github_token()

Get GitHub token from environment.

* **Return type:**
  [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### wads.agents.ci_debug_agent.main()

CLI entry point for wads CI debug agent.

### wads.agents.ci_debug_agent.parse_ci_warnings(logs)

Parse CI warnings from logs that may indicate issues.

* **Parameters:**
  **logs** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Full CI logs
* **Return type:**
  [`List`](https://docs.python.org/3/library/typing.html#typing.List)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]
* **Returns:**
  List of warning messages

### wads.agents.ci_debug_agent.parse_pytest_failures(logs)

Parse pytest failures and collection errors from CI logs.

* **Parameters:**
  **logs** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – CI log content
* **Return type:**
  [`List`](https://docs.python.org/3/library/typing.html#typing.List)[[`TestFailure`](#wads.agents.ci_debug_agent.TestFailure)]
* **Returns:**
  List of TestFailure objects

### wads.agents.ci_debug_agent.print_diagnosis(diagnosis)

Print formatted diagnosis report.
