# Tasks

> 工作流 A→C 顺序执行；同一工作流内无依赖子任务可并行。
> 每完成一项立即勾选。拆分模式灵活选择（re-export 子包 或 helper 抽取），
> 以最小改动使文件 ≤ 350 行为目标。Logger 名硬编码 + monkeypatch 兼容性必须保持。

## 工作流 A：拆分 8 个 365+ 行文件（优先级最高）

- [x] Task A1：拆分 `brain_alpha_ops/runtime_constants.py` (382 行)
  - [x] A1.1：读取全文，判断拆分模式（子包 vs helper 抽取）
  - [x] A1.2：按职责切分子模块或抽取 helper（每个 ≤ 350 行）
  - [x] A1.3：验证 `from brain_alpha_ops.runtime_constants import *` 正常
  - [x] A1.4：运行相关测试验证无回归
- [x] Task A2：拆分 `brain_alpha_ops/browser/brain_ui_runner.py` (381 行)
  - [x] A2.1：读取全文，判断拆分模式
  - [x] A2.2：按职责切分子模块或抽取 helper（≤ 350 行）
  - [x] A2.3：验证导入正常
  - [x] A2.4：运行 `test_*brain_ui*`、`test_browser*` 验证无回归
- [x] Task A3：拆分 `brain_alpha_ops/types.py` (380 行)
  - [x] A3.1：读取全文，判断拆分模式（types 文件可能按类型类别分组）
  - [x] A3.2：按职责切分子模块或抽取 helper（≤ 350 行）
  - [x] A3.3：验证 `from brain_alpha_ops.types import *` 正常
  - [x] A3.4：运行相关测试验证无回归
- [x] Task A4：拆分 `scripts/check_defect_analysis_report.py` (378 行)
  - [x] A4.1：读取全文，判断拆分模式（CLI 脚本 → 子包 + thin shim）
  - [x] A4.2：按职责切分子模块（≤ 350 行），保留 thin shim 用于 CLI 调用
  - [x] A4.3：验证 `python3 scripts/check_defect_analysis_report.py` 正常
  - [x] A4.4：运行相关测试验证无回归
- [x] Task A5：拆分 `brain_alpha_ops/web/handlers/phase.py` (375 行)
  - [x] A5.1：读取全文，判断拆分模式
  - [x] A5.2：按职责切分子模块或抽取 helper（≤ 350 行）
  - [x] A5.3：验证导入正常
  - [x] A5.4：运行 `test_*phase*`、`test_web_handlers*` 验证无回归
- [x] Task A6：拆分 `brain_alpha_ops/config_schema.py` (374 行)
  - [x] A6.1：读取全文，判断拆分模式
  - [x] A6.2：按职责切分子模块或抽取 helper（≤ 350 行）
  - [x] A6.3：验证 `from brain_alpha_ops.config_schema import *` 正常
  - [x] A6.4：运行相关测试验证无回归
- [x] Task A7：拆分 `brain_alpha_ops/research/_observability_helpers.py` (372 行)
  - [x] A7.1：读取全文，判断拆分模式
  - [x] A7.2：按职责切分子模块或抽取 helper（≤ 350 行）
  - [x] A7.3：验证导入正常
  - [x] A7.4：运行 `test_*observability*`、`test_research*` 验证无回归
- [x] Task A8：拆分 `brain_alpha_ops/config_domain_validation.py` (371 行)
  - [x] A8.1：读取全文，判断拆分模式
  - [x] A8.2：按职责切分子模块或抽取 helper（≤ 350 行）
  - [x] A8.3：验证 `from brain_alpha_ops.config_domain_validation import *` 正常
  - [x] A8.4：运行相关测试验证无回归

## 工作流 B：拆分 8 个 351-364 行文件

- [x] Task B1：拆分 `brain_alpha_ops/web/business/web_async_jobs.py` (364 行)
  - [x] B1.1：读取全文，判断拆分模式
  - [x] B1.2：按职责切分子模块或抽取 helper（≤ 350 行）
  - [x] B1.3：验证导入正常
  - [x] B1.4：运行 `test_*async_jobs*`、`test_web_business*` 验证无回归
- [x] Task B2：拆分 `brain_alpha_ops/research/theme_engine/_engine.py` (363 行)
  - [x] B2.1：读取全文，判断拆分模式
  - [x] B2.2：按职责切分子模块或抽取 helper（≤ 350 行）
  - [x] B2.3：验证导入正常
  - [x] B2.4：运行 `test_*theme*` 验证无回归
- [x] Task B3：拆分 `brain_alpha_ops/web/security/web_security.py` (362 行)
  - [x] B3.1：读取全文，判断拆分模式
  - [x] B3.2：按职责切分子模块或抽取 helper（≤ 350 行）
  - [x] B3.3：验证导入正常
  - [x] B3.4：运行 `test_*security*`、`test_web_security*` 验证无回归
- [x] Task B4：拆分 `brain_alpha_ops/research/generator/_helpers.py` (355 行)
  - [x] B4.1：读取全文，判断拆分模式
  - [x] B4.2：按职责切分子模块或抽取 helper（≤ 350 行）
  - [x] B4.3：验证导入正常
  - [x] B4.4：运行 `test_*generator*`、`test_research*` 验证无回归
- [x] Task B5：拆分 `brain_alpha_ops/research/runtime_service.py` (355 行)
  - [x] B5.1：读取全文，判断拆分模式
  - [x] B5.2：按职责切分子模块或抽取 helper（≤ 350 行）
  - [x] B5.3：验证导入正常
  - [x] B5.4：运行 `test_*runtime_service*`、`test_research*` 验证无回归
- [x] Task B6：拆分 `brain_alpha_ops/research/market_data_cache.py` (354 行)
  - [x] B6.1：读取全文，判断拆分模式
  - [x] B6.2：按职责切分子模块或抽取 helper（≤ 350 行）
  - [x] B6.3：验证导入正常
  - [x] B6.4：运行 `test_*market_data*`、`test_research*` 验证无回归
- [x] Task B7：拆分 `brain_alpha_ops/web/business/web_jobs.py` (352 行)
  - [x] B7.1：读取全文，判断拆分模式
  - [x] B7.2：按职责切分子模块或抽取 helper（≤ 350 行）
  - [x] B7.3：验证导入正常
  - [x] B7.4：运行 `test_*web_jobs*`、`test_web_business*` 验证无回归
- [x] Task B8：拆分 `brain_alpha_ops/ux/user_messages.py` (351 行)
  - [x] B8.1：读取全文，判断拆分模式
  - [x] B8.2：按职责切分子模块或抽取 helper（≤ 350 行）
  - [x] B8.3：验证 `from brain_alpha_ops.ux.user_messages import *` 正常
  - [x] B8.4：运行 `test_*user_messages*`、`test_ux*` 验证无回归

## 工作流 C：验证、同步与提交

- [x] Task C1：同步 `BASELINE_LINE_LIMITS`
  - [x] C1.1：从 `scripts/check_module_size.py:BASELINE_LINE_LIMITS` 删除全部 16 个条目
  - [x] C1.2：运行 `python3 scripts/check_module_size.py --json` 确认 `baseline_limits={}`、`findings=[]`、`ok=true`
- [x] Task C2：全量回归测试
  - [x] C2.1：运行 `python3 -m pytest tests/ --ignore=tests/test_read_jsonl_tail.py --ignore=tests/test_quality_gate.py --ignore=tests/test_official_scoring_system.py -q --tb=short` 确认无新增失败
  - [x] C2.2：验证 16 个拆分模块 `from ... import *` 正常工作
  - [x] C2.3：验证凭据扫描 `python3 -m pytest tests/test_credential_leak_regression.py -q` 全绿
- [x] Task C3：提交并推送到 origin/main
  - [x] C3.1：`git add` 所有修改文件
  - [x] C3.2：`git commit` 使用规范中文提交消息（含 phase14 标识）
  - [x] C3.3：`git push origin main` 推送成功

# Task Dependencies

- Task A1-A8 相互独立，可并行
- Task B1-B8 相互独立，可并行
- Task A* 与 Task B* 可完全并行
- Task C1 依赖 A1-A8、B1-B8
- Task C2 依赖 C1、A*、B*
- Task C3 依赖 C2

# 可并行任务

- A1-A8（8 个 365+ 行文件拆分）一次性并行
- B1-B8（8 个 351-364 行文件拆分）一次性并行
- A* / B* 两组可完全并行（共 16 个独立子任务）
