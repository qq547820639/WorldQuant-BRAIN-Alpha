"""Red Line 3: official Dataset ID availability."""

from __future__ import annotations

import json
from typing import Any

from brain_alpha_ops.compliance.redline_helpers import _runtime_storage_dir, _verification_blocked
from brain_alpha_ops.compliance.redline_models import ComplianceReport, RedLineViolation


def _verify_redline_3_dataset_ids(
    report: ComplianceReport,
    run_config: Any | None = None,
) -> None:
    """Red Line 3: Dataset ID 全量可用."""
    redline_id = 3
    report.redline_summary[redline_id] = "Dataset ID 全量可用"

    data_dir = _runtime_storage_dir(run_config)
    datasets_path = data_dir / "official_datasets.json"

    if datasets_path.exists():
        try:
            datasets = json.loads(datasets_path.read_text(encoding="utf-8"))
            if not isinstance(datasets, list):
                report.add(RedLineViolation(
                    redline_id=redline_id, redline_name="Dataset ID 全量可用",
                    severity="BLOCKING", file_path=str(datasets_path),
                    check_name="official_datasets.json 格式错误",
                    actual_value=f"类型: {type(datasets).__name__}", expected_value="list",
                    deviation="文件内容不是数组",
                    fix_guidance="重新运行 fetch_official_context.py 拉取数据集",
                ))
            else:
                actual_ids = {d.get("id") for d in datasets if d.get("id")}
                if len(actual_ids) < 10:
                    report.add(RedLineViolation(
                        redline_id=redline_id, redline_name="Dataset ID 全量可用",
                        severity="WARNING", file_path=str(datasets_path),
                        check_name="Dataset 数量不足",
                        actual_value=len(actual_ids), expected_value=">= 10",
                        deviation=f"仅有 {len(actual_ids)} 个数据集",
                        fix_guidance="检查 BRAIN API 连接，重新拉取数据集",
                    ))
                else:
                    report.add_pass()
                # Check field completeness
                required = {"id", "name", "field_count"}
                field_ok = True
                for ds in datasets:
                    missing = required - set(ds.keys())
                    if missing:
                        field_ok = False
                        report.add(RedLineViolation(
                            redline_id=redline_id, redline_name="Dataset ID 全量可用",
                            severity="WARNING", file_path=str(datasets_path),
                            check_name=f"Dataset 字段缺失: {ds.get('id', '?')}",
                            actual_value=f"缺失: {missing}", expected_value="id, name, field_count",
                            deviation="数据集缺少必要字段",
                            fix_guidance="检查 BRAIN API 返回格式",
                        ))
                if field_ok:
                    report.add_pass()
        except json.JSONDecodeError as e:
            report.add(RedLineViolation(
                redline_id=redline_id, redline_name="Dataset ID 全量可用",
                severity="BLOCKING", file_path=str(datasets_path),
                check_name="official_datasets.json 解析失败",
                actual_value=str(e), expected_value="有效 JSON",
                deviation="JSON 解析错误",
                fix_guidance="修复或重新生成 official_datasets.json",
            ))
    else:
        report.add(RedLineViolation(
            redline_id=redline_id, redline_name="Dataset ID 全量可用",
            severity="BLOCKING", file_path=str(datasets_path),
            check_name="official_datasets.json 不存在",
            actual_value="文件缺失", expected_value="data/official_datasets.json",
            deviation="官方数据集文件不存在",
            fix_guidance="运行 fetch_official_context.py 或带有效凭据的 pipeline",
        ))

    # 3b. Verify Candidate.dataset_id field
    try:
        from brain_alpha_ops.models import Candidate
        fields_set = {f.name for f in Candidate.__dataclass_fields__.values()}
        if "dataset_id" in fields_set:
            report.add_pass()
        else:
            report.add(RedLineViolation(
                redline_id=redline_id, redline_name="Dataset ID 全量可用",
                severity="BLOCKING", file_path="brain_alpha_ops/models.py",
                check_name="Candidate 缺少 dataset_id",
                actual_value=f"已有: {sorted(fields_set)}", expected_value="包含 dataset_id",
                deviation="模型没有 dataset_id 字段",
                fix_guidance="在 Candidate dataclass 中添加 dataset_id: str = ''",
            ))
    except Exception as exc:
        _verification_blocked(
            report, redline_id=redline_id, redline_name="Dataset ID 全量可用",
            file_path="brain_alpha_ops/models.py", check_name="无法验证 Candidate.dataset_id",
            error=exc, expected="Candidate 包含 dataset_id 字段",
            fix_guidance="修复 Candidate 模型导入错误。",
        )

    # 3c. Verify official context dataset lineage
    try:
        from brain_alpha_ops.data.official_context_validation import validate_official_context
        validation = validate_official_context(data_dir=data_dir)
        if validation.get("blocking_ok"):
            report.add_pass()
        else:
            report.add(RedLineViolation(
                redline_id=redline_id,
                redline_name="Dataset ID 全量可用",
                severity="BLOCKING",
                file_path="data/official_datasets.json",
                check_name="官方上下文 Dataset 血缘不一致",
                actual_value=validation.get("detail", "invalid"),
                expected_value="matching official field counts",
                deviation="context lineage failed",
                fix_guidance="运行 fetch_official_context.py 后复核 metadata hash。",
            ))
    except Exception as exc:
        _verification_blocked(
            report, redline_id=redline_id, redline_name="Dataset ID 全量可用",
            file_path=str(datasets_path), check_name="官方上下文血缘校验不可用",
            error=exc, expected="可执行 validate_official_context",
            fix_guidance="确保官方上下文验证模块可导入并可读取运行存储目录。",
        )
