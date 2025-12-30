"""
Wads AI Agents

Autonomous agents for diagnosing and fixing common development issues.

Available Agents:
- ci_debug_agent: Analyzes failed CI runs and proposes fixes
- dependency_resolver: Analyzes import errors and missing dependencies
- test_analyzer: Analyzes pytest failures and categorizes them
"""

from wads.agents.ci_debug_agent import (
    diagnose_ci_failure,
    CIDiagnosis,
    TestFailure,
)

from wads.agents.dependency_resolver import (
    analyze_dependencies,
    DependencyReport,
    DependencyIssue,
)

from wads.agents.test_analyzer import (
    parse_pytest_output,
    TestAnalysisReport,
    TestFailurePattern,
)

__all__ = [
    # CI Debug Agent
    "diagnose_ci_failure",
    "CIDiagnosis",
    "TestFailure",
    # Dependency Resolver
    "analyze_dependencies",
    "DependencyReport",
    "DependencyIssue",
    # Test Analyzer
    "parse_pytest_output",
    "TestAnalysisReport",
    "TestFailurePattern",
]
