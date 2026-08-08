"""Tests for code quality metrics and reporting."""

from pathlib import Path

import pytest

from brain_alpha_ops.code_quality import (
    analyze_module,
    format_quality_report,
    generate_quality_report,
)


def _write_py(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_analyze_module_counts_functions_classes_imports(tmp_path):
    py_file = _write_py(
        tmp_path / "sample.py",
        '"""Module docstring."""\n'
        "import os\n"
        "from typing import Any\n"
        "\n"
        "class Foo:\n"
        "    def method(self) -> str:\n"
        "        return 'x'\n"
        "\n"
        "def helper(a: int) -> int:\n"
        "    return a\n",
    )
    metrics = analyze_module(py_file)
    assert metrics.lines_of_code > 0
    assert metrics.function_count == 2
    assert metrics.class_count == 1
    assert metrics.import_count == 2
    assert metrics.docstring_coverage == 1.0
    assert metrics.type_annotation_coverage == 1.0


def test_analyze_module_handles_missing_docstring(tmp_path):
    py_file = _write_py(
        tmp_path / "bare.py",
        "x = 1\n",
    )
    metrics = analyze_module(py_file)
    assert metrics.docstring_coverage == 0.0
    assert metrics.type_annotation_coverage == 0.0


def test_analyze_module_handles_unparseable_file(tmp_path):
    py_file = _write_py(tmp_path / "broken.py", "this is not python {{{")
    metrics = analyze_module(py_file)
    assert metrics.function_count == 0
    assert metrics.class_count == 0
    assert metrics.docstring_coverage == 0.0


def test_generate_quality_report_raises_for_missing_dir():
    with pytest.raises(ValueError):
        generate_quality_report("does_not_exist_dir_xyz")


def test_generate_quality_report_aggregates(tmp_path):
    _write_py(tmp_path / "a.py", '"""Doc."""\ndef f() -> int:\n    return 1\n')
    _write_py(tmp_path / "b.py", '"""Doc."""\nclass C:\n    pass\n')
    _write_py(tmp_path / "c.py", "value = 1\n")

    report = generate_quality_report(str(tmp_path))
    assert report.total_modules == 3
    assert report.total_functions == 1
    assert report.total_classes == 1
    assert report.modules_with_docstrings == 2
    assert report.modules_without_docstrings == 1
    assert report.avg_docstring_coverage == pytest.approx(2 / 3)
    assert len(report.details) == 3


def test_format_quality_report_includes_metrics():
    report = generate_quality_report("brain_alpha_ops/research/expression_ast")
    text = format_quality_report(report)
    assert "Code Quality Report" in text
    assert "Total modules" in text
    assert "Docstring coverage" in text
    assert "Type annotation coverage" in text