"""Six technical red-line compliance verifier.

Red Line Verifier enforces six non-negotiable compliance rules against the
BRAIN platform technical specifications. No custom extensions.

Red Lines:
  1. 字段/算子禁自定义扩展 — zero custom field/operator extension
  2. 阈值零偏差 — zero threshold deviation from BRAIN official docs
  3. Dataset ID 全量可用 — all dataset IDs available and traceable
  4. 参数全链路可溯 — full parameter chain traceability
  5. 要素全覆盖 — complete factor coverage
  6. 代码强对齐 — strong code alignment with BRAIN API

Usage:
    python -m brain_alpha_ops.compliance.redline_verifier
    python -m brain_alpha_ops.compliance.redline_verifier --json
    python -m brain_alpha_ops.compliance.redline_verifier --block
"""
from __future__ import annotations

import json
from typing import Any

from brain_alpha_ops.compliance.redline_check_alignment import (
    _verify_redline_6_code_alignment,
)
from brain_alpha_ops.compliance.redline_check_coverage import (
    _verify_redline_5_factor_coverage,
)
from brain_alpha_ops.compliance.redline_check_datasets import (
    _verify_redline_3_dataset_ids,
)
from brain_alpha_ops.compliance.redline_check_no_custom_extension import (
    _verify_redline_1_no_custom_extension,
)
from brain_alpha_ops.compliance.redline_check_thresholds import (
    _verify_redline_2_threshold_zero_deviation,
)
from brain_alpha_ops.compliance.redline_check_traceability import (
    _verify_redline_4_parameter_traceability,
)
from brain_alpha_ops.compliance.redline_helpers import (
    _candidate_generator_fallback_templates,
    _project_root,
    _runtime_storage_dir,
    _sample_official_fields_for_templates,
    _verification_blocked,
    _verify_generator_templates_against_official_context,
)
from brain_alpha_ops.compliance.redline_models import (
    ComplianceReport,
    RedLineBlockedError,
    RedLineViolation,
)


class RedLineVerifier:
    """Six red-line compliance verification engine.

    Run this verifier before any production pipeline execution or deployment.
    Any BLOCKING violation MUST halt the pipeline.
    """

    def __init__(self, run_config: Any | None = None):
        self.run_config = run_config

    def verify_all(self) -> ComplianceReport:
        """Run all six red-line verifications."""
        report = ComplianceReport()
        _verify_redline_1_no_custom_extension(report, self.run_config)
        _verify_redline_2_threshold_zero_deviation(report, self.run_config)
        _verify_redline_3_dataset_ids(report, self.run_config)
        _verify_redline_4_parameter_traceability(report, self.run_config)
        _verify_redline_5_factor_coverage(report)
        _verify_redline_6_code_alignment(report, self.run_config)
        return report.finalize()

    def verify_and_block(self) -> ComplianceReport:
        """Run verification and raise if BLOCKING violations exist."""
        report = self.verify_all()
        if report.overall == "FAIL":
            blocking = [v for v in report.violations if v.severity == "BLOCKING"]
            msg = (
                f"TECH_REDLINE_BLOCKED: {len(blocking)} blocking violations detected.\n"
                + "\n".join(f"  - [RL-{v.redline_id}] {v.check_name}" for v in blocking[:10])
            )
            raise RedLineBlockedError(msg, report)
        return report

    @classmethod
    def verify_quick(cls) -> bool:
        """Quick pass/fail — returns True only if ALL six red lines pass."""
        return cls().verify_all().overall == "PASS"

def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="redline-verify",
        description="BRAIN Alpha Ops 技术红线合规验证",
    )
    parser.add_argument("--config", help="运行配置路径；用于验证真实 storage/API/thresholds")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")
    parser.add_argument("--block", action="store_true", help="阻断模式: 有违规即报错退出")
    args = parser.parse_args()

    run_config = None
    if args.config:
        from brain_alpha_ops.config import load_run_config

        run_config = load_run_config(args.config)

    verifier = RedLineVerifier(run_config)
    exit_code = 0
    try:
        if args.block:
            report = verifier.verify_and_block()
        else:
            report = verifier.verify_all()
        if args.json:
            print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        else:
            print(report.report())
        if report.overall == "FAIL":
            exit_code = 1
    except RedLineBlockedError as e:
        if args.json:
            print(json.dumps({"error": str(e), "report": e.report.to_dict()}, ensure_ascii=False, indent=2))
        else:
            print(str(e))
        exit_code = 2
    return exit_code

if __name__ == "__main__":
    raise SystemExit(main())
