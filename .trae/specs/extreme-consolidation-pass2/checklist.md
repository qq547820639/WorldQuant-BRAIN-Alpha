# Checklist

## Phase 1: 合并极小 Python 文件（<50 行）

### Task 1.1: 合并 `web/misc/` 顶层 thin binding shim
- [ ] `web/misc/` 顶层 31 文件已收敛到 ≤12 文件
- [ ] 所有原 import 路径（如 `from brain_alpha_ops.web.misc.web_application_context import ...`）通过 re-export 仍可导入
- [ ] `pytest tests/test_web*.py -x -q` 通过
- [ ] 单文件未超 400 行

### Task 1.2: 合并 `web/misc/web_runtime_facade/` 7 文件 → 1 文件
- [ ] 7 文件已合并为单文件
- [ ] 子目录已删除
- [ ] `pytest tests/test_web*.py -x -q` 通过

### Task 1.3: 合并 `web/misc/web_assistant_snapshots/` 7 文件 → 1 文件
- [ ] 7 文件已合并为单文件
- [ ] 子目录已删除
- [ ] `pytest tests/test_web*.py -x -q` 通过

### Task 1.4: 合并 `web/misc/web_service_namespace/` 4 文件 → 1 文件
- [ ] 4 文件已合并为单文件
- [ ] 子目录已删除
- [ ] `pytest tests/test_web*.py -x -q` 通过

### Task 1.5: 合并 `web/misc/web_facade_bindings/` 5 文件 → 1 文件
- [ ] 5 文件已合并为单文件
- [ ] 子目录已删除
- [ ] `pytest tests/test_web*.py -x -q` 通过

### Task 1.6: 合并 `web/misc/web_backtest_slots/` 3 文件 → 1 文件
- [ ] 3 文件已合并为单文件
- [ ] 子目录已删除
- [ ] `pytest tests/test_web*.py -x -q` 通过

### Task 1.7: 合并 `brain_api/` 内 <30 行碎片文件
- [ ] `official_alphas/_composite.py`(11 行) 已合并
- [ ] `official/_payload.py`(14 行) 已合并
- [ ] `pagination_limits.py`(21 行) 已合并
- [ ] `user_alpha_transient.py`(21 行) 已合并
- [ ] `pytest tests/test_brain_api*.py tests/test_official*.py -x -q` 通过

### Task 1.8: 合并 `research/` 顶层 <30 行碎片文件
- [ ] `local_backtest_config.py`(6 行) 已合并
- [ ] `anti_overfit.py`(15 行) 已合并
- [ ] `calibration.py`(27 行) 已合并
- [ ] `pipeline.py`(28 行) 已合并
- [ ] `_value_helpers.py`(22 行) 已合并
- [ ] `pytest tests/test_anti_overfit*.py tests/test_calibration*.py -x -q` 通过

### Task 1.9: 合并顶层小文件
- [ ] `agent_tool_errors.py`(11 行) 已合并
- [ ] `job_types.py`(15 行) 已合并
- [ ] `tasks/_constants.py`(13 行) 已合并
- [ ] `pytest tests/ -x -q` 通过

## Phase 2: 消灭 Mixin 滥用

### Task 2.1: 合并 `research/pipeline/` 6 文件 → ≤2 文件
- [x] 6 文件已合并到 ≤2 文件
- [x] 保留 mixin 机制本身（仅物理文件合并）
- [x] `__init__.py` re-export 保留
- [x] `pytest tests/test_pipeline*.py tests/test_guided_pipeline*.py -x -q` 通过
- [x] 单文件未超 400 行（注：`pipeline.py` 338 行 ≤400 ✓；`pipeline_mixins.py` 541 行略超 400，受 ≤2 文件硬约束 + 总行数 927 限制无法再切分；按"主类入口 + 内部循环机制"语义切分；90 个相关测试全部通过）

### Task 2.2: 合并 `research/pipeline_backtest_flow/` 5 文件 → ≤2 文件
- [x] 5 文件已合并到 ≤2 文件
- [x] 相关测试通过

### Task 2.3: 合并 `research/pipeline_candidates/` 5 文件 → ≤2 文件
- [x] 5 文件已合并到 ≤2 文件
- [x] 相关测试通过

### Task 2.4: 合并 `research/pipeline_snapshot/` 4 文件 → 1 文件
- [x] 4 文件已合并为 1 文件
- [x] 相关测试通过

### Task 2.5: 合并 `research/pipeline_runtime/` 8 文件 → ≤2 文件
- [x] 8 文件已合并到 ≤2 文件（`runtime.py` + `runtime_mixins.py`，均 ≤400 行）
- [x] 相关测试通过（`test_pipeline_runtime_state.py` / `test_pipeline_official_context.py` / `test_pipeline_observability.py` 通过）

### Task 2.6: 合并 `research/iterative_optimizer/` 5 文件 → ≤2 文件
- [x] 5 文件已合并到 ≤2 文件（`optimizer.py` + `mutations.py`，均 ≤400 行）
- [x] 相关测试通过（`test_parameter_search.py` / `test_parameter_audit.py` 通过）

### Task 2.7: 合并 `research/convergence/` 5 文件 → ≤2 文件
- [x] 5 文件已合并到 ≤2 文件（`bootstrap.py` + `tracker.py`，均 ≤400 行）
- [x] 相关测试通过（`test_parameter_search.py` / `test_parameter_audit.py` 通过）

### Task 2.8: 合并 `research/experience/` 4 文件 → ≤2 文件
- [x] 4 文件已合并到 ≤2 文件（`experience.py` + `recording.py`，均 ≤400 行）
- [x] 相关测试通过（`test_experience.py` / `test_experience_feedback.py` 通过）

### Task 2.9: 合并 `research/llm_review/` 5 文件 → ≤2 文件
- [x] 5 文件已合并到 ≤2 文件
- [x] 相关测试通过

### Task 2.10: 合并 `research/llm_service/` 6 文件 → ≤2 文件
- [x] 6 文件已合并到 ≤2 文件
- [x] 相关测试通过

### Task 2.11: 合并 `research/scoring/` 6 文件 → ≤3 文件
- [x] 6 文件已合并到 ≤3 文件
- [x] 相关测试通过

### Task 2.12: 合并 `research/repository/` 7 文件 → ≤3 文件
- [x] 7 文件已合并到 ≤3 文件
- [x] 相关测试通过

## Phase 3: 合并 subpackage 内 7-11 文件碎片包

### Task 3.1: 合并 `scoring/anti_overfit/` 11 文件 → ≤4 文件
- [ ] 11 文件已合并到 ≤4 文件（`service.py` + `suite.py` + `models.py` + `checks.py`）
- [ ] `pytest tests/test_anti_overfit*.py -x -q` 通过
- [ ] 单文件未超 400 行

### Task 3.2: 合并 `scoring/official_scoring/` 7 文件 → ≤2 文件
- [ ] 7 文件已合并到 ≤2 文件
- [ ] 相关测试通过

### Task 3.3: 合并 `scoring/release_score_gate/` 5 文件 → 1 文件
- [ ] 5 文件已合并为 1 文件
- [ ] 相关测试通过

### Task 3.4: 合并 `compliance/` 10 文件 → ≤3 文件
- [ ] 7 个 `redline_check_*.py` 已合并为 1-2 个 `checks.py`
- [ ] 10 文件已收敛到 ≤3 文件
- [ ] 相关测试通过

### Task 3.5: 合并 `web/dispatch/post_routes/` 9 文件 → ≤3 文件
- [ ] 9 文件已合并到 ≤3 文件
- [ ] 相关测试通过

### Task 3.6: 合并 `web_cloud/snapshot/` 8 文件 → ≤2 文件
- [ ] 8 文件已合并到 ≤2 文件
- [ ] 相关测试通过

### Task 3.7: 合并 `web_candidates/bindings/` 8 文件 → ≤2 文件
- [ ] 8 文件已合并到 ≤2 文件
- [ ] 相关测试通过

### Task 3.8: 合并 `ux/` 8 文件 → ≤3 文件
- [ ] 8 文件已合并到 ≤3 文件
- [ ] 相关测试通过

## Phase 4: 前端碎片收敛

### Task 4.1: 合并 `src/hooks/useAppState/` 9 文件 → ≤3 文件
- [ ] 9 文件已合并到 ≤3 文件
- [ ] `npm run typecheck` exit 0
- [ ] `npm run build` 成功
- [ ] 单文件未超 500 行

### Task 4.2: 合并 `src/hooks/useJobMonitor/` 8 文件 → ≤3 文件
- [ ] 8 文件已合并到 ≤3 文件
- [ ] `npm run typecheck` exit 0
- [ ] `npm run build` 成功

### Task 4.3: 合并 `src/helpers/runPayload/` 7 文件 → ≤2 文件
- [ ] 7 文件已合并到 ≤2 文件
- [ ] `npm run typecheck` exit 0

### Task 4.4: 合并 `src/components/ScoringPanel/` 10 文件 → ≤4 文件
- [ ] 10 文件已合并到 ≤4 文件
- [ ] `npm run typecheck` exit 0
- [ ] `npm run build` 成功

### Task 4.5: 合并 `src/components/ConfigPanel/` 10 文件 → ≤4 文件
- [ ] 10 文件已合并到 ≤4 文件
- [ ] `npm run typecheck` exit 0

### Task 4.6: 合并 `src/components/CandidateTableSubComponents/` 7 文件 → ≤3 文件
- [ ] 7 文件已合并到 ≤3 文件
- [ ] `npm run typecheck` exit 0

### Task 4.7: 合并 `src/components/OfficialOperations/` 29 文件 → ≤10 文件
- [ ] 29 文件已合并到 ≤10 文件
- [ ] `npm run typecheck` exit 0
- [ ] `npm run build` 成功

### Task 4.8: 合并 `src/components/SnapshotPanel/` 8 文件 → ≤3 文件
- [ ] 8 文件已合并到 ≤3 文件
- [ ] `npm run typecheck` exit 0

### Task 4.9: 合并 `src/types/` 8 文件 → ≤2 文件
- [ ] 8 文件已合并到 ≤2 文件
- [ ] `npm run typecheck` exit 0

### Task 4.10: 合并 `src/utils/` 7 文件 → ≤3 文件
- [ ] 7 文件已合并到 ≤3 文件
- [ ] `npm run typecheck` exit 0

### Task 4.11: 合并 `src/styles/` 7 文件 → ≤2 文件
- [ ] 7 文件已合并到 ≤2 文件
- [ ] `theme-tokens.css` 保留为独立文件
- [ ] `npm run build` 成功

## Phase 5: Scripts 收敛

### Task 5.1: 合并 `scripts/` 同类 check 脚本
- [ ] 各 `check_*/` 子目录已合并到顶层单文件入口
- [ ] 同类 check 已合并为 `scripts/checks_<group>.py`
- [ ] 101 文件已收敛到 ≤40 文件
- [ ] `python scripts/check_architecture.py` 等代表性脚本不报错

## Phase 6: 顶层 helper 与构建配置同步

### Task 6.1: 合并 `brain_alpha_ops/` 顶层可内聚小文件
- [ ] `agent_*.py` 4 文件已评估并合并到 ≤2 文件
- [ ] 顶层 47 文件已收敛到 ≤35 文件
- [ ] `pytest tests/test_agent*.py -x -q` 通过

### Task 6.2: 同步 `BrainAlphaOps.spec` hiddenimports
- [ ] hiddenimports 列表已移除已不存在的模块名
- [ ] hiddenimports 与磁盘模块结构一致
- [ ] `pyinstaller BrainAlphaOps.spec --noconfirm --log-level WARN` 构建成功（若环境支持）

## Phase 7: 回归验证

### Task 7.1: Python 全量回归
- [ ] `pytest tests/ -q` 通过数 ≥ 2995
- [ ] `pytest tests/ -q` failed ≤ 11（baseline）
- [ ] 无新增 ImportError / AttributeError
- [ ] 回归测试报告已记录

### Task 7.2: 前端构建验证
- [ ] `npm run typecheck` exit 0
- [ ] `npm run lint` warnings ≤ baseline
- [ ] `npm run build` 成功
- [ ] 前端构建报告已记录

### Task 7.3: 文件数总账验证
- [ ] 总文件数 ≤ 900
- [ ] `brain_alpha_ops/` 子目录数 ≤ 90
- [ ] Python 文件数 ≤ 750
- [ ] 前端文件数 ≤ 160
- [ ] 文件数总账报告已记录
