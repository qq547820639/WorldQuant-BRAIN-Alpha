# Tasks

> 工作流 A→D 顺序执行；同一工作流内无依赖子任务可并行。
> 每完成一项立即勾选。所有变更前做全局影响评估，变更后输出结构化变更报告。
> 拆分模式遵循 `project_memory.md`：re-export 子包 + `__init__.py` 导出公共 API +
> 已测试私有符号 + logger 名硬编码 + `_pkg()` 兼容 monkeypatch。

## 工作流 A：拆分 10 个超限 scripts（≥ 477 行）

- [x] Task A1：拆分 `scripts/check_live_submit_readiness.py` (886 行)
  - [x] A1.1：读取全文，按职责切分为 `_checks.py` / `_reporters.py` / `_runners.py` 等子模块（每个 ≤ 350 行）
  - [x] A1.2：创建 `scripts/check_live_submit_readiness/__init__.py`，导出公共 API + `__all__`，logger 名硬编码为 `check_live_submit_readiness`
  - [x] A1.3：原 `check_live_submit_readiness.py` 改为 thin shim 或删除（由 `__init__.py` 取代）
  - [x] A1.4：验证 `python3 -c "from scripts.check_live_submit_readiness import main"` 正常
- [x] Task A2：拆分 `scripts/check_parameter_traceability.py` (798 行)
  - [x] A2.1：按职责切分子模块（≤ 350 行）
  - [x] A2.2：创建 `__init__.py` + `__all__` + 硬编码 logger
  - [x] A2.3：原文件改为 thin shim 或删除
  - [x] A2.4：验证导入正常
- [x] Task A3：拆分 `scripts/check_review_gap_closure_tracker.py` (793 行)
  - [x] A3.1：按职责切分子模块（≤ 350 行）
  - [x] A3.2：创建 `__init__.py` + `__all__` + 硬编码 logger
  - [x] A3.3：原文件改为 thin shim 或删除
  - [x] A3.4：验证导入正常
- [x] Task A4：拆分 `scripts/final_release_gate.py` (774 行)
  - [x] A4.1：按职责切分子模块（≤ 350 行）
  - [x] A4.2：创建 `__init__.py` + `__all__` + 硬编码 logger
  - [x] A4.3：原文件改为 thin shim 或删除
  - [x] A4.4：验证导入正常
- [x] Task A5：拆分 `scripts/quality_gate.py` (770 行)
  - [x] A5.1：按职责切分子模块（≤ 350 行）
  - [x] A5.2：创建 `__init__.py` + `__all__` + 硬编码 logger
  - [x] A5.3：原文件改为 thin shim 或删除
  - [x] A5.4：验证 `python3 scripts/quality_gate.py --help` 或等价调用正常
- [x] Task A6：拆分 `scripts/check_prod_defect_tracking.py` (729 行)
  - [x] A6.1：按职责切分子模块（≤ 350 行）
  - [x] A6.2：创建 `__init__.py` + `__all__` + 硬编码 logger
  - [x] A6.3：原文件改为 thin shim 或删除
  - [x] A6.4：验证导入正常
- [x] Task A7：拆分 `scripts/check_tracked_data_inventory.py` (573 行)
  - [x] A7.1：按职责切分子模块（≤ 350 行）
  - [x] A7.2：创建 `__init__.py` + `__all__` + 硬编码 logger
  - [x] A7.3：原文件改为 thin shim 或删除
  - [x] A7.4：验证导入正常
- [x] Task A8：拆分 `scripts/verify_canonical_compliance.py` (538 行)
  - [x] A8.1：按职责切分子模块（≤ 350 行）
  - [x] A8.2：创建 `__init__.py` + `__all__` + 硬编码 logger
  - [x] A8.3：原文件改为 thin shim 或删除
  - [x] A8.4：验证导入正常
- [x] Task A9：拆分 `scripts/check_review_gap_closure_tracker_helpers.py` (483 行)
  - [x] A9.1：按职责切分子模块（≤ 350 行）
  - [x] A9.2：创建 `__init__.py` + `__all__` + 硬编码 logger
  - [x] A9.3：原文件改为 thin shim 或删除
  - [x] A9.4：验证导入正常
- [x] Task A10：拆分 `scripts/check_frontend_surface_parity.py` (477 行)
  - [x] A10.1：按职责切分子模块（≤ 350 行）
  - [x] A10.2：创建 `__init__.py` + `__all__` + 硬编码 logger
  - [x] A10.3：原文件改为 thin shim 或删除
  - [x] A10.4：验证导入正常

## 工作流 B：拆分 10 个超限 brain_alpha_ops 文件（≥ 462 行）

- [x] Task B1：拆分 `brain_alpha_ops/web_candidates/simulation_state.py` (497 行)
  - [x] B1.1：读取全文，按职责切分子模块（≤ 350 行）
  - [x] B1.2：创建 `web_candidates/simulation_state/__init__.py` + `__all__` + 硬编码 logger
  - [x] B1.3：原 `simulation_state.py` 改为 thin shim 或删除
  - [x] B1.4：运行相关测试（`test_*simulation_state*`、`test_web_candidates*`）验证无回归
- [x] Task B2：拆分 `brain_alpha_ops/web_cloud/sync_job/_service.py` (493 行)
  - [x] B2.1：按职责切分子模块（≤ 350 行），保留 `_service` 命名前缀以维持 monkeypatch 路径
  - [x] B2.2：创建 `sync_job/_service/__init__.py` + `__all__` + 显式 re-export 私有符号
  - [x] B2.3：原 `_service.py` 改为 thin shim
  - [x] B2.4：运行 `test_*sync_job*`、`test_web_cloud*` 验证无回归
- [x] Task B3：拆分 `brain_alpha_ops/web/__init__.py` (491 行)
  - [x] B3.1：读取全文，识别 re-export 聚合 vs 实际逻辑
  - [x] B3.2：将实际逻辑抽离到 `web/_reexports.py` 或 `web/_bootstrap.py`（≤ 350 行）
  - [x] B3.3：`web/__init__.py` 仅保留 `from ._reexports import *` + 显式 `__all__`
  - [x] B3.4：运行 `test_web_*` 全套验证无回归（重点关注 monkeypatch 兼容性）
- [x] Task B4：拆分 `brain_alpha_ops/research/auto_calibrator.py` (482 行)
  - [x] B4.1：按职责切分子模块（≤ 350 行）
  - [x] B4.2：创建 `research/auto_calibrator/__init__.py` + `__all__` + 硬编码 logger
  - [x] B4.3：原 `auto_calibrator.py` 改为 thin shim
  - [x] B4.4：运行 `test_*calibrat*` 验证无回归
- [x] Task B5：拆分 `brain_alpha_ops/brain_api/official_simulation.py` (481 行)
  - [x] B5.1：按职责切分子模块（≤ 350 行）
  - [x] B5.2：创建 `brain_api/official_simulation/__init__.py` + `__all__` + 硬编码 logger
  - [x] B5.3：原 `official_simulation.py` 改为 thin shim
  - [x] B5.4：运行 `test_*official_simulation*`、`test_brain_api*` 验证无回归
- [x] Task B6：拆分 `brain_alpha_ops/research/calibration_engine.py` (471 行)
  - [x] B6.1：按职责切分子模块（≤ 350 行）
  - [x] B6.2：创建 `research/calibration_engine/__init__.py` + `__all__` + 硬编码 logger
  - [x] B6.3：原 `calibration_engine.py` 改为 thin shim
  - [x] B6.4：运行 `test_*calibrat*` 验证无回归
- [x] Task B7：拆分 `brain_alpha_ops/research/repository.py` (469 行)
  - [x] B7.1：按职责切分子模块（≤ 350 行）
  - [x] B7.2：创建 `research/repository/__init__.py` + `__all__` + 硬编码 logger
  - [x] B7.3：原 `repository.py` 改为 thin shim
  - [x] B7.4：运行 `test_*repository*`、`test_research_*` 验证无回归
- [x] Task B8：拆分 `brain_alpha_ops/web/misc/web_facade_bindings.py` (468 行)
  - [x] B8.1：按职责切分子模块（≤ 350 行）
  - [x] B8.2：创建 `web/misc/web_facade_bindings/__init__.py` + `__all__` + 硬编码 logger
  - [x] B8.3：原 `web_facade_bindings.py` 改为 thin shim
  - [x] B8.4：运行 `test_web_*facade*`、`test_web_misc*` 验证无回归
- [x] Task B9：拆分 `brain_alpha_ops/web/security/web_session.py` (463 行)
  - [x] B9.1：按职责切分子模块（≤ 350 行），注意 phase11 已修复重复导入，此处仅拆分
  - [x] B9.2：创建 `web/security/web_session/__init__.py` + `__all__` + 硬编码 logger
  - [x] B9.3：原 `web_session.py` 改为 thin shim
  - [x] B9.4：运行 `test_*session*`、`test_web_security*` 验证无回归
- [x] Task B10：拆分 `brain_alpha_ops/research/expression_index.py` (462 行)
  - [x] B10.1：按职责切分子模块（≤ 350 行）
  - [x] B10.2：创建 `research/expression_index/__init__.py` + `__all__` + 硬编码 logger
  - [x] B10.3：原 `expression_index.py` 改为 thin shim
  - [x] B10.4：运行 `test_*expression_index*`、`test_research_*` 验证无回归

## 工作流 C：闭合 4 个 open 缺陷

- [x] Task C1：修复 DEF-019 — `tests/test_web_backtest_slots.py` 0-arg API
  - [x] C1.1：读取 `tests/test_web_backtest_slots.py` 定位 6 处 `web._backtest_slots_payload()` 0-arg 调用
  - [x] C1.2：读取 `brain_alpha_ops/web/misc/web_backtest_slots/__init__.py` 与 `_handlers.py` 确认当前签名
  - [x] C1.3：更新 6 处调用至当前签名（或新增 0-arg 便利重载并 re-export）
  - [x] C1.4：运行 `python3 -m pytest tests/test_web_backtest_slots.py -v` 全绿
- [x] Task C2：修复 DEF-020 — `tests/test_comprehensive_scoring_edge_cases.py` `ScoreHistoryDB` ImportError
  - [x] C2.1：读取 `tests/test_comprehensive_scoring_edge_cases.py` 定位 `ScoreHistoryDB` 引用
  - [x] C2.2：Grep `brain_alpha_ops/` 确认 `ScoreHistoryDB` 是否存在或曾被重命名
  - [x] C2.3：若类已重命名，更新导入；若从未实现，移除 `TestScoreHistoryDB` 类
  - [x] C2.4：运行 `python3 -m pytest tests/test_comprehensive_scoring_edge_cases.py --collect-only` 无 ImportError
- [x] Task C3：闭合 DEF-021 — 本地执行 vitest 套件
  - [x] C3.1：在 `brain_alpha_ops/web/react_app` 运行 `npm ci`（若 node_modules 缺失）
  - [x] C3.2：运行 `npm run test`（vitest run）
  - [x] C3.3：若全绿，记录结果准备更新 DEFECT_TRACKING.md
  - [x] C3.4：若 Node 不可用或测试失败，记录失败原因，保留 open 并补充环境说明
- [x] Task C4：修复 DEF-022 — `CredentialsSection.tsx:44` TS6133 `environment` 未使用
  - [x] C4.1：读取 `brain_alpha_ops/web/react_app/src/components/ConfigPanel/CredentialsSection.tsx` 第 40-50 行
  - [x] C4.2：判断 `environment` 是否应被消费（用于渲染）或移除
  - [x] C4.3：移除未使用的 prop 或在渲染中消费
  - [x] C4.4：运行 `npm run typecheck` 退出 0

## 工作流 D：验证、同步与提交

- [x] Task D1：同步 `BASELINE_LINE_LIMITS`
  - [x] D1.1：从 `scripts/check_module_size.py:BASELINE_LINE_LIMITS` 删除 A1-A10、B1-B10 涉及的 20 个条目
  - [x] D1.2：运行 `python3 scripts/check_module_size.py --json` 确认 20 个文件不再出现在 `findings`
- [x] Task D2：更新 `DEFECT_TRACKING.md`
  - [x] D2.1：DEF-019 `Status` 改为 `closed`，填写 `Fix` / `Verification method`
  - [x] D2.2：DEF-020 `Status` 改为 `closed`，填写 `Fix` / `Verification method`
  - [x] D2.3：DEF-022 `Status` 改为 `closed`，填写 `Fix` / `Verification method`
  - [x] D2.4：DEF-021 按 C3 执行结果更新（closed 或保留 open + 环境说明）
  - [x] D2.5：更新摘要表 `Open` 计数
- [x] Task D3：全量回归测试
  - [x] D3.1：运行 `python3 -m pytest tests/ --ignore=tests/test_read_jsonl_tail.py --ignore=tests/test_quality_gate.py --ignore=tests/test_official_scoring_system.py -q --tb=short` 确认无新增失败
  - [x] D3.2：验证 20 个拆分子包 `from ... import *` 正常工作
  - [x] D3.3：验证凭据扫描 `python3 -m pytest tests/test_credential_leak_regression.py -q` 全绿
- [x] Task D4：提交并推送到 origin/main
  - [x] D4.1：`git add` 所有修改文件
  - [x] D4.2：`git commit` 使用规范中文提交消息（含 phase12 + 缺陷编号）
  - [x] D4.3：`git push origin main` 推送成功

# Task Dependencies

- Task A1-A10 相互独立，可并行（10 个 scripts 拆分无依赖）
- Task B1-B10 相互独立，可并行（10 个 brain_alpha_ops 拆分无依赖）
- Task A* 与 Task B* 可完全并行
- Task C1-C4 相互独立，可并行（4 个缺陷修复无依赖）
- Task C1-C4 与 A*/B* 可并行
- Task D1 依赖 A1-A10、B1-B10（拆分完成才能同步 BASELINE）
- Task D2 依赖 C1-C4（缺陷修复完成才能更新状态）
- Task D3 依赖 D1、D2、A*、B*、C*
- Task D4 依赖 D3

# 可并行任务

- A1-A10（10 个 scripts 拆分）一次性并行
- B1-B10（10 个 brain_alpha_ops 拆分）一次性并行
- C1-C4（4 个缺陷修复）一次性并行
- A* / B* / C* 三组可完全并行（共 24 个独立子任务）
