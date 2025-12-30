"""
Test Failure Analyzer Agent

Analyzes pytest test failures, categorizes them, and suggests fixes.
Identifies patterns in failures and provides actionable recommendations.
"""

import re
import sys
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass
from collections import Counter


@dataclass
class TestFailurePattern:
    """Represents a pattern of test failures."""

    pattern_type: str  # 'assertion', 'exception', 'timeout', 'setup', 'teardown'
    count: int
    examples: List[str]
    suggested_fix: str
    severity: str  # 'high', 'medium', 'low'


@dataclass
class TestAnalysisReport:
    """Result of test failure analysis."""

    total_failures: int
    total_errors: int
    failure_patterns: List[TestFailurePattern]
    flaky_tests: List[str]
    slow_tests: List[str]
    recommendations: List[str]


def categorize_failure(error_type: str, error_message: str) -> str:
    """
    Categorize test failure type.

    Args:
        error_type: Type of error (AssertionError, ValueError, etc.)
        error_message: Error message

    Returns:
        Category string
    """
    if error_type == "AssertionError":
        if "assert" in error_message.lower():
            return "assertion"
        return "assertion"

    if "timeout" in error_message.lower() or "timed out" in error_message.lower():
        return "timeout"

    if "fixture" in error_message.lower() or "setup" in error_message.lower():
        return "setup"

    if "teardown" in error_message.lower():
        return "teardown"

    if "AttributeError" in error_type:
        return "attribute_error"

    if "TypeError" in error_type:
        return "type_error"

    if "ValueError" in error_type:
        return "value_error"

    if "KeyError" in error_type or "IndexError" in error_type:
        return "data_access_error"

    return "exception"


def suggest_fix(category: str, error_message: str) -> str:
    """
    Suggest fix based on failure category.

    Args:
        category: Failure category
        error_message: Error message

    Returns:
        Suggested fix description
    """
    suggestions = {
        "assertion": "Review test expectations and actual values. Check if the test logic is correct.",
        "timeout": "Increase timeout value or optimize the code being tested. Check for infinite loops.",
        "setup": "Fix test setup/fixture. Ensure required data/mocks are properly initialized.",
        "teardown": "Fix test cleanup. Ensure resources are properly released.",
        "attribute_error": "Check object attributes. Ensure objects are properly initialized.",
        "type_error": "Verify argument types. Add type checking or conversion.",
        "value_error": "Validate input values. Add input validation or use correct values.",
        "data_access_error": "Check data structure access. Ensure keys/indices exist.",
        "exception": "Review the exception and add proper error handling.",
    }

    base_suggestion = suggestions.get(
        category, "Review the error and fix the underlying issue."
    )

    # Add specific suggestions based on error message
    if "None" in error_message and category == "attribute_error":
        base_suggestion += " (Possible None value - add null check)"

    if "expected" in error_message.lower() and "got" in error_message.lower():
        base_suggestion += " (Values mismatch - verify test expectations)"

    return base_suggestion


def parse_pytest_output(output: str) -> TestAnalysisReport:
    """
    Parse pytest output and analyze failures.

    Args:
        output: Pytest output text

    Returns:
        TestAnalysisReport with analysis
    """
    total_failures = 0
    total_errors = 0
    failures_by_category = {}
    all_failures = []

    # Parse failures and errors
    failure_pattern = re.compile(
        r"(FAILED|ERROR)\s+(.+?)\s+-\s+(.+?):\s*(.+?)$", re.MULTILINE
    )

    for match in failure_pattern.finditer(output):
        status = match.group(1)
        test_name = match.group(2).strip()
        error_type = match.group(3).strip()
        error_message = match.group(4).strip()

        if status == "FAILED":
            total_failures += 1
        else:
            total_errors += 1

        category = categorize_failure(error_type, error_message)

        if category not in failures_by_category:
            failures_by_category[category] = []

        failures_by_category[category].append(
            {
                "test": test_name,
                "error_type": error_type,
                "error_message": error_message,
            }
        )

        all_failures.append(test_name)

    # Create pattern summaries
    patterns = []
    for category, failures in failures_by_category.items():
        count = len(failures)
        examples = [f"{f['test']}: {f['error_message'][:100]}" for f in failures[:3]]

        # Determine severity
        if count > 10 or category in ["setup", "teardown"]:
            severity = "high"
        elif count > 5:
            severity = "medium"
        else:
            severity = "low"

        pattern = TestFailurePattern(
            pattern_type=category,
            count=count,
            examples=examples,
            suggested_fix=suggest_fix(category, failures[0]["error_message"]),
            severity=severity,
        )
        patterns.append(pattern)

    # Sort patterns by count (most common first)
    patterns.sort(key=lambda p: p.count, reverse=True)

    # Detect flaky tests (tests that appear multiple times if run multiple times)
    # For now, just return empty - would need multiple runs to detect
    flaky_tests = []

    # Parse slow tests
    slow_pattern = re.compile(r"(\d+\.\d+)s\s+call\s+(.+?)$", re.MULTILINE)
    slow_tests = []

    for match in slow_pattern.finditer(output):
        duration = float(match.group(1))
        test_name = match.group(2).strip()

        if duration > 5.0:  # Tests taking more than 5 seconds
            slow_tests.append(f"{test_name} ({duration:.2f}s)")

    # Generate recommendations
    recommendations = []

    if patterns:
        top_pattern = patterns[0]
        recommendations.append(
            f"Most common failure: {top_pattern.pattern_type} ({top_pattern.count} occurrences)"
        )
        recommendations.append(f"  Fix: {top_pattern.suggested_fix}")

    if total_failures > 10:
        recommendations.append(f"High number of failures ({total_failures}). Consider:")
        recommendations.append("  - Running tests in isolation to identify root cause")
        recommendations.append("  - Checking for shared state between tests")

    if slow_tests:
        recommendations.append(
            f"Found {len(slow_tests)} slow tests (>5s). Consider optimization or mocking."
        )

    # Check for setup/teardown issues
    setup_issues = any(p.pattern_type in ["setup", "teardown"] for p in patterns)
    if setup_issues:
        recommendations.append(
            "Setup/teardown failures detected. Fix fixtures before addressing test logic."
        )

    return TestAnalysisReport(
        total_failures=total_failures,
        total_errors=total_errors,
        failure_patterns=patterns,
        flaky_tests=flaky_tests,
        slow_tests=slow_tests,
        recommendations=recommendations,
    )


def print_report(report: TestAnalysisReport):
    """Print formatted test analysis report."""
    print("\n" + "=" * 70)
    print("TEST FAILURE ANALYSIS")
    print("=" * 70)

    print(f"\n📊 Summary:")
    print(f"  Failures: {report.total_failures}")
    print(f"  Errors: {report.total_errors}")
    print(f"  Total: {report.total_failures + report.total_errors}")

    if report.failure_patterns:
        print(f"\n🔍 Failure Patterns:")
        for pattern in report.failure_patterns:
            severity_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}[
                pattern.severity
            ]
            print(
                f"\n  {severity_icon} {pattern.pattern_type.upper()} ({pattern.count} occurrences)"
            )
            print(f"    Severity: {pattern.severity}")
            print(f"    Fix: {pattern.suggested_fix}")
            if pattern.examples:
                print(f"    Examples:")
                for ex in pattern.examples:
                    print(f"      - {ex}")

    if report.slow_tests:
        print(f"\n🐌 Slow Tests ({len(report.slow_tests)}):")
        for test in report.slow_tests[:5]:
            print(f"  - {test}")

    if report.recommendations:
        print(f"\n💡 Recommendations:")
        for rec in report.recommendations:
            print(f"  {rec}")

    print("\n" + "=" * 70)


def main():
    """CLI entry point for test analyzer."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Analyze pytest test failures and suggest fixes"
    )
    parser.add_argument(
        "pytest_output",
        nargs="?",
        help="Path to pytest output file (or stdin if not provided)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show detailed analysis"
    )

    args = parser.parse_args()

    # Read pytest output
    if args.pytest_output:
        with open(args.pytest_output, "r") as f:
            output = f.read()
    else:
        # Read from stdin
        output = sys.stdin.read()

    # Analyze
    report = parse_pytest_output(output)

    # Print report
    print_report(report)

    # Exit with error code if failures found
    sys.exit(1 if report.total_failures + report.total_errors > 0 else 0)


if __name__ == "__main__":
    main()
