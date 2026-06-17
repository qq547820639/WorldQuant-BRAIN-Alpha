"""Test coverage tracking and reporting.

This module provides functions to track and report test coverage metrics
for the BRAIN Alpha Ops codebase.

Usage:
    from brain_alpha_ops.test_coverage import generate_coverage_report

    report = generate_coverage_report()
    print(report)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class TestFileMetrics:
    """Metrics for a single test file."""
    file_path: str
    test_count: int
    test_names: list[str] = field(default_factory=list)


@dataclass
class CoverageReport:
    """Overall test coverage report."""
    total_test_files: int
    total_tests: int
    test_files_with_tests: int
    test_files_without_tests: int
    details: list[TestFileMetrics] = field(default_factory=list)


def _count_tests_in_file(filepath: Path) -> tuple[int, list[str]]:
    """Count tests in a Python test file."""
    try:
        content = filepath.read_text(encoding="utf-8")
        test_names = []
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("def test_") and "(" in stripped:
                # Extract test name
                name = stripped.split("def ")[1].split("(")[0]
                test_names.append(name)
        return len(test_names), test_names
    except Exception:
        return 0, []


def analyze_test_file(filepath: Path) -> TestFileMetrics:
    """Analyze a single test file."""
    count, names = _count_tests_in_file(filepath)
    return TestFileMetrics(
        file_path=str(filepath),
        test_count=count,
        test_names=names,
    )


def generate_coverage_report(test_dir: str = "tests") -> CoverageReport:
    """Generate a test coverage report."""
    test_path = Path(test_dir)
    if not test_path.exists():
        raise ValueError(f"Test directory not found: {test_dir}")

    test_files = []
    for py_file in sorted(test_path.glob("test_*.py")):
        metrics = analyze_test_file(py_file)
        test_files.append(metrics)

    total_test_files = len(test_files)
    total_tests = sum(m.test_count for m in test_files)
    test_files_with_tests = sum(1 for m in test_files if m.test_count > 0)
    test_files_without_tests = total_test_files - test_files_with_tests

    return CoverageReport(
        total_test_files=total_test_files,
        total_tests=total_tests,
        test_files_with_tests=test_files_with_tests,
        test_files_without_tests=test_files_without_tests,
        details=test_files,
    )


def format_coverage_report(report: CoverageReport) -> str:
    """Format a coverage report as a string."""
    lines = [
        "=" * 60,
        "  BRAIN Alpha Ops — Test Coverage Report",
        "=" * 60,
        f"  Total test files: {report.total_test_files}",
        f"  Total tests: {report.total_tests}",
        f"  Files with tests: {report.test_files_with_tests}",
        f"  Files without tests: {report.test_files_without_tests}",
        "",
        "  Top 10 test files by test count:",
    ]

    # Sort by test count and show top 10
    sorted_files = sorted(report.details, key=lambda m: m.test_count, reverse=True)
    for i, metrics in enumerate(sorted_files[:10], 1):
        name = Path(metrics.file_path).name
        lines.append(f"    {i:2d}. {name}: {metrics.test_count} tests")

    lines.append("=" * 60)
    return "\n".join(lines)
