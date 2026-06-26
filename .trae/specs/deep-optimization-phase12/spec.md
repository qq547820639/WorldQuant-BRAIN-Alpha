# 深度优化 Phase 12：Grandfathered 超限文件拆分 + 遗留缺陷闭合 Spec

## Why

`overhaul-alpha-production-quality` 收尾时在 `DELIVERY_REPORT_OVERHAUL.md` §10
明确建议：进入 grandfathered 文件拆分阶段。当前 `scripts/check_module_size.py:BASELINE_LINE_LIMITS`
冻结了 52 个超 350 行的 Python 文件，其中 20 个文件行数 ≥ 462（最高 886 行），
显著超出项目硬约束（Python 后端 ≤ 350 行）。同时 `DEFECT_TRACKING.md` 仍留有
4 个 open 缺陷（DEF-019/020/021/022），需在本阶段一并闭合，使仓库进入
"零超限文件 + 零 open 缺陷" 的收敛状态。

## What Changes

- **拆分 10 个超限 scripts（≥ 477 行）** 为 re-export 子包 + thin shim：
  `check_live_submit_readiness.py` (886)、`check_parameter_traceability.py` (798)、
  `check_review_gap_closure_tracker.py` (793)、`final_release_gate.py` (774)、
  `quality_gate.py` (770)、`check_prod_defect_tracking.py` (729)、
  `check_tracked_data_inventory.py` (573)、`verify_canonical_compliance.py` (538)、
  `check_review_gap_closure_tracker_helpers.py` (483)、`check_frontend_surface_parity.py` (477)。
- **拆分 10 个超限 brain_alpha_ops 文件（≥ 462 行）** 为 re-export 子包 + thin shim：
  `web_candidates/simulation_state.py` (497)、`web_cloud/sync_job/_service.py` (493)、
  `web/__init__.py` (491)、`research/auto_calibrator.py` (482)、
  `brain_api/official_simulation.py` (481)、`research/calibration_engine.py` (471)、
  `research/repository.py` (469)、`web/misc/web_facade_bindings.py` (468)、
  `web/security/web_session.py` (463)、`research/expression_index.py` (462)。
- **修复 DEF-019**：更新 `tests/test_web_backtest_slots.py` 6 处 0-arg 调用至当前签名。
- **修复 DEF-020**：移除或补齐 `tests/test_comprehensive_scoring_edge_cases.py` 中
  `ScoreHistoryDB` 引用，使测试文件可被 collect。
- **闭合 DEF-021**：本地执行 `npm run test`（vitest 套件），确认 8 个测试文件全绿；
  若 Node 工具链不可用，记录为环境限制并在 `DEFECT_TRACKING.md` 注明 GitHub Actions
  `frontend-quality` job 覆盖。
- **修复 DEF-022**：移除或消费 `CredentialsSection.tsx:44` 未使用的 `environment` prop，
  使 `tsc -b` 退出 0。
- **同步 `BASELINE_LINE_LIMITS`**：移除已拆分文件对应条目，使其受 `DEFAULT_LINE_LIMIT=350` 约束。
- **更新 `DEFECT_TRACKING.md`**：将 DEF-019/020/022 标记为 `closed`，DEF-021 按执行结果更新。
- **提交并推送** `origin/main`（遵循用户工作流约定）。

## Impact

- **Affected specs**：`overhaul-alpha-production-quality`（收尾报告 §10 建议的下一步）；
  本阶段不修改既有 spec，仅推进其遗留项。
- **Affected code**：
  - `scripts/` 下 10 个检查脚本拆分为子包 + shim
  - `brain_alpha_ops/` 下 10 个核心模块拆分为子包 + shim
  - `scripts/check_module_size.py:BASELINE_LINE_LIMITS` 删除 20 个条目
  - `tests/test_web_backtest_slots.py`、`tests/test_comprehensive_scoring_edge_cases.py` 修复
  - `brain_alpha_ops/web/react_app/src/components/ConfigPanel/CredentialsSection.tsx` 修复
  - `brain_alpha_ops/web/react_app/src/__tests__/*.test.tsx` 本地验证
  - `DEFECT_TRACKING.md` 状态更新
- **Backward compatibility**：所有拆分遵循项目既定 re-export 子包模式
  （`__init__.py` 导出公共 API + 已测试私有符号，原文件保留为 thin shim 或被 `__init__.py`
  直接替代），外部导入路径不变，monkeypatch 兼容性通过 `_pkg()` 模式与显式 re-export 维持。
- **Risk**：`web/__init__.py` 是 web 层聚合入口，拆分需格外谨慎保留所有 re-export；
  `research/repository.py`、`research/auto_calibrator.py` 等核心模块拆分后需全量回归测试。

## ADDED Requirements

### Requirement: Grandfathered 文件拆分收敛

系统 SHALL 在本阶段结束时，使 `scripts/check_module_size.py --json` 的 `findings`
数组对 20 个目标文件返回空（即每文件行数 ≤ 350），且 `BASELINE_LINE_LIMITS`
不再包含这 20 个条目。

#### Scenario: 拆分后行数合规
- **WHEN** 运行 `python3 scripts/check_module_size.py --json`
- **THEN** 20 个原超限文件不再出现在 `findings` 中
- **AND** `baseline_limits` 字典中不再包含这 20 个文件路径

#### Scenario: 外部导入路径不变
- **WHEN** 任意 `from brain_alpha_ops.web import X` 或 `from scripts.check_quality_gate import Y` 执行
- **THEN** 导入成功且返回与拆分前相同的对象
- **AND** 现有测试套件无新增 ImportError / AttributeError

### Requirement: Re-export 子包结构规范

每个被拆分的文件 SHALL 转换为 `<module_name>/` 子包，包含：
- `__init__.py`：导出公共 API + 已被测试引用的私有符号，定义 `__all__`，
  logger 名称硬编码为原模块名
- 若干 `< 350 行` 的子模块（按职责切分）
- 原 `<module_name>.py` 文件保留为 thin shim（仅 `from .<module_name> import *`），
  或直接删除并由 `__init__.py` 取代（取决于外部导入路径）

#### Scenario: 子包结构完整
- **WHEN** 检查 `<module>/__init__.py`
- **THEN** 文件存在且含 `__all__` 定义
- **AND** 所有子模块行数 ≤ 350

### Requirement: 遗留缺陷闭合

系统 SHALL 在本阶段结束时，使 `DEFECT_TRACKING.md` 中 DEF-019/020/022 状态变为 `closed`，
DEF-021 按本地执行结果更新为 `closed`（若 vitest 全绿）或保留 `open` 并补充环境说明。

#### Scenario: DEF-019 闭合
- **WHEN** 运行 `python3 -m pytest tests/test_web_backtest_slots.py -v`
- **THEN** 全部测试通过（无 0-arg API 失败）

#### Scenario: DEF-020 闭合
- **WHEN** 运行 `python3 -m pytest tests/test_comprehensive_scoring_edge_cases.py --collect-only`
- **THEN** 文件可被 collect，无 `ScoreHistoryDB` ImportError

#### Scenario: DEF-022 闭合
- **WHEN** 在 `brain_alpha_ops/web/react_app` 运行 `npm run typecheck`
- **THEN** 退出码 0，无 TS6133 `environment` 警告

## MODIFIED Requirements

### Requirement: BASELINE_LINE_LIMITS 同步

`scripts/check_module_size.py:BASELINE_LINE_LIMITS` 字典 SHALL 移除 20 个已拆分文件的条目，
使这些文件受 `DEFAULT_LINE_LIMIT=350` 约束。其余 32 个 grandfathered 文件保持现状
（行数 351–460，留待后续 phase 13+ 处理）。

### Requirement: DEFECT_TRACKING.md 状态同步

`DEFECT_TRACKING.md` SHALL 更新：
- DEF-019：`Status` 由 `open` 改为 `closed`，`Fix` / `Verification method` 填写实际修复
- DEF-020：`Status` 由 `open` 改为 `closed`，`Fix` / `Verification method` 填写实际修复
- DEF-022：`Status` 由 `open` 改为 `closed`，`Fix` / `Verification method` 填写实际修复
- DEF-021：按本地 vitest 执行结果更新；若 Node 不可用，保留 `open` 并在 `Notes` 注明
  GitHub Actions `frontend-quality` job 覆盖
- 摘要表 `Open` 计数由 4 降为 0 或 1（取决于 DEF-021）

## REMOVED Requirements

无删除项。本阶段为纯重构 + 缺陷闭合，不删除任何公开 API 或功能。
