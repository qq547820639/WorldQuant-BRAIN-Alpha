"""Data structures for technical red-line compliance reports."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class RedLineViolation:
    """Single red-line violation with severity and fix guidance."""

    redline_id: int
    redline_name: str
    severity: str
    file_path: str
    check_name: str
    actual_value: Any
    expected_value: Any
    deviation: str
    fix_guidance: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ComplianceReport:
    """Aggregated compliance verification report."""

    verified_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    total_checks: int = 0
    passed: int = 0
    failed: int = 0
    warnings: int = 0
    violations: list[RedLineViolation] = field(default_factory=list)
    redline_summary: dict[int, str] = field(default_factory=dict)
    overall: str = "PENDING"

    def add(self, v: RedLineViolation) -> None:
        self.total_checks += 1
        if v.severity == "BLOCKING":
            self.failed += 1
        else:
            self.warnings += 1
        self.violations.append(v)

    def add_pass(self) -> None:
        self.total_checks += 1
        self.passed += 1

    @property
    def ok(self) -> bool:
        """Compatibility flag for CLI/Web callers: no blocking violations."""
        return self.overall != "FAIL"

    def finalize(self) -> "ComplianceReport":
        if self.failed > 0:
            self.overall = "FAIL"
        elif self.warnings > 0:
            self.overall = "WARNING"
        else:
            self.overall = "PASS"
        return self

    def report(self) -> str:
        lines = [
            "=" * 72,
            "  BRAIN Alpha Ops — 技术红线合规验证报告",
            "=" * 72,
            f"  验证时间 : {self.verified_at}",
            f"  总体结果 : {self.overall}",
            f"  检查项   : {self.total_checks} (通过:{self.passed}, 阻断:{self.failed}, 警告:{self.warnings})",
            "",
        ]
        if not self.violations:
            lines.append("  [PASS] 所有六条技术红线全部通过。")
        else:
            for redline_id in sorted(self.redline_summary.keys()):
                rl_violations = [v for v in self.violations if v.redline_id == redline_id]
                status_icon = "[FAIL]" if any(v.severity == "BLOCKING" for v in rl_violations) else "[WARN]"
                lines.append(f"  {status_icon} 红线-{redline_id}: {self.redline_summary[redline_id]}")
                lines.append(f"     违规数: {len(rl_violations)}")
                for v in rl_violations:
                    lines.append(f"     [{v.severity}] {v.check_name}")
                    lines.append(f"       文件   : {v.file_path}")
                    lines.append(f"       实际值 : {v.actual_value}")
                    lines.append(f"       期望值 : {v.expected_value}")
                    lines.append(f"       偏差   : {v.deviation}")
                    lines.append(f"       修复   : {v.fix_guidance}")
                lines.append("")
        lines.append("=" * 72)
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "verified_at": self.verified_at,
            "overall": self.overall,
            "total_checks": self.total_checks,
            "passed": self.passed,
            "failed": self.failed,
            "warnings": self.warnings,
            "redline_summary": self.redline_summary,
            "violations": [
                {
                    "redline_id": v.redline_id,
                    "redline_name": v.redline_name,
                    "severity": v.severity,
                    "check_name": v.check_name,
                    "actual_value": str(v.actual_value),
                    "expected_value": str(v.expected_value),
                    "deviation": v.deviation,
                    "fix_guidance": v.fix_guidance,
                }
                for v in self.violations
            ],
        }


class RedLineBlockedError(RuntimeError):
    """Raised when red-line verification blocks pipeline execution."""

    def __init__(self, message: str, report: ComplianceReport):
        super().__init__(message)
        self.report = report
