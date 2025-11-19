"""
Pytest configuration and hooks for wads tests.
"""

import pytest
from collections import Counter


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """
    Custom hook to count and display error messages in the summary.
    Provides a grouped view of errors to make logs more readable.
    """
    terminalreporter.section("Error Summary Analysis")

    # Collect all error messages
    error_counts = Counter()
    for report in terminalreporter.stats.get("failed", []):
        if report.longrepr:
            # Extract the last line of the error (usually the Exception message)
            msg = str(report.longrepr).split("\n")[-1]
            error_counts[msg] += 1

    for report in terminalreporter.stats.get("error", []):
        if report.longrepr:
            msg = str(report.longrepr).split("\n")[-1]
            error_counts[msg] += 1

    # Print the counts
    if error_counts:
        terminalreporter.write_line("Counts of error types:")
        for error, count in error_counts.most_common():
            terminalreporter.write_line(f"  {count}x: {error}")
    else:
        terminalreporter.write_line("No distinct errors found to summarize.")
