"""Code quality metrics and reporting.

This module provides functions to measure and report code quality metrics
for the BRAIN Alpha Ops codebase.

Usage:
    from brain_alpha_ops.code_quality import generate_quality_report

    report = generate_quality_report()
    print(report)
"""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass, field
from pathlib import Path

from brain_alpha_ops.redaction import redact_error_message, redact_text

logger = logging.getLogger(__name__)


@dataclass
class ModuleMetrics:
    """Metrics for a single Python module."""
    file_path: str
    lines_of_code: int
    function_count: int
    class_count: int
    import_count: int
    docstring_coverage: float
    type_annotation_coverage: float


@dataclass
class QualityReport:
    """Overall code quality report."""
    total_modules: int
    total_lines: int
    total_functions: int
    total_classes: int
    avg_docstring_coverage: float
    avg_type_annotation_coverage: float
    modules_with_docstrings: int
    modules_without_docstrings: int
    details: list[ModuleMetrics] = field(default_factory=list)


def _count_lines(filepath: Path) -> int:
    """Count lines in a Python file."""
    try:
        content = filepath.read_text(encoding="utf-8")
        return len(content.splitlines())
    except Exception as exc:
        logger.debug("Failed to count lines in %s: %s", redact_text(filepath), redact_error_message(exc))
        return 0


def _has_docstring(filepath: Path) -> bool:
    """Check if a Python file has a module docstring."""
    try:
        content = filepath.read_text(encoding="utf-8")
        tree = ast.parse(content)
        return ast.get_docstring(tree) is not None
    except Exception as exc:
        logger.debug("Failed to check docstring in %s: %s", redact_text(filepath), redact_error_message(exc))
        return False


def _count_functions(filepath: Path) -> int:
    """Count functions in a Python file."""
    try:
        content = filepath.read_text(encoding="utf-8")
        tree = ast.parse(content)
        return sum(1 for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)))
    except Exception as exc:
        logger.debug("Failed to count functions in %s: %s", redact_text(filepath), redact_error_message(exc))
        return 0


def _count_classes(filepath: Path) -> int:
    """Count classes in a Python file."""
    try:
        content = filepath.read_text(encoding="utf-8")
        tree = ast.parse(content)
        return sum(1 for node in ast.walk(tree) if isinstance(node, ast.ClassDef))
    except Exception as exc:
        logger.debug("Failed to count classes in %s: %s", redact_text(filepath), redact_error_message(exc))
        return 0


def _count_imports(filepath: Path) -> int:
    """Count imports in a Python file."""
    try:
        content = filepath.read_text(encoding="utf-8")
        tree = ast.parse(content)
        return sum(1 for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom)))
    except Exception as exc:
        logger.debug("Failed to count imports in %s: %s", redact_text(filepath), redact_error_message(exc))
        return 0


def _has_type_annotations(filepath: Path) -> bool:
    """Check if a Python file has type annotations."""
    try:
        content = filepath.read_text(encoding="utf-8")
        return "def " in content and "->" in content
    except Exception as exc:
        logger.debug("Failed to check type annotations in %s: %s", redact_text(filepath), redact_error_message(exc))
        return False


def analyze_module(filepath: Path) -> ModuleMetrics:
    """Analyze a single Python module."""
    loc = _count_lines(filepath)
    functions = _count_functions(filepath)
    classes = _count_classes(filepath)
    imports = _count_imports(filepath)
    has_docstring = _has_docstring(filepath)
    has_annotations = _has_type_annotations(filepath)

    return ModuleMetrics(
        file_path=str(filepath),
        lines_of_code=loc,
        function_count=functions,
        class_count=classes,
        import_count=imports,
        docstring_coverage=1.0 if has_docstring else 0.0,
        type_annotation_coverage=1.0 if has_annotations else 0.0,
    )


def generate_quality_report(root_dir: str = "brain_alpha_ops") -> QualityReport:
    """Generate a code quality report for the codebase."""
    root = Path(root_dir)
    if not root.exists():
        raise ValueError(f"Directory not found: {root_dir}")

    modules = []
    for py_file in sorted(root.rglob("*.py")):
        metrics = analyze_module(py_file)
        modules.append(metrics)

    total_modules = len(modules)
    total_lines = sum(m.lines_of_code for m in modules)
    total_functions = sum(m.function_count for m in modules)
    total_classes = sum(m.class_count for m in modules)
    modules_with_docstrings = sum(1 for m in modules if m.docstring_coverage > 0)
    modules_without_docstrings = total_modules - modules_with_docstrings

    avg_docstring_coverage = (
        sum(m.docstring_coverage for m in modules) / total_modules
        if total_modules > 0
        else 0.0
    )
    avg_type_annotation_coverage = (
        sum(m.type_annotation_coverage for m in modules) / total_modules
        if total_modules > 0
        else 0.0
    )

    return QualityReport(
        total_modules=total_modules,
        total_lines=total_lines,
        total_functions=total_functions,
        total_classes=total_classes,
        avg_docstring_coverage=avg_docstring_coverage,
        avg_type_annotation_coverage=avg_type_annotation_coverage,
        modules_with_docstrings=modules_with_docstrings,
        modules_without_docstrings=modules_without_docstrings,
        details=modules,
    )


def format_quality_report(report: QualityReport) -> str:
    """Format a quality report as a string."""
    lines = [
        "=" * 60,
        "  BRAIN Alpha Ops — Code Quality Report",
        "=" * 60,
        f"  Total modules: {report.total_modules}",
        f"  Total lines: {report.total_lines:,}",
        f"  Total functions: {report.total_functions}",
        f"  Total classes: {report.total_classes}",
        "",
        f"  Docstring coverage: {report.avg_docstring_coverage:.1%}",
        f"  Modules with docstrings: {report.modules_with_docstrings}",
        f"  Modules without docstrings: {report.modules_without_docstrings}",
        "",
        f"  Type annotation coverage: {report.avg_type_annotation_coverage:.1%}",
        "=" * 60,
    ]
    return "\n".join(lines)
