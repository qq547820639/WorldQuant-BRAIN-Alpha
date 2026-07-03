# Tasks

本轮任务按"先合并 Python 后端 → 再合并前端 → 再收敛 scripts → 最后回归验证"顺序组织。每个阶段内部任务可并行化，跨阶段存在依赖（前端独立于后端可并行）。

**核心原则**：
- 纯文件合并与重组，**不改任何函数/类实现逻辑**
- 每次合并后保留 `__init__.py` re-export，确保 import 路径稳定
- 单文件超 400 行（Python）/ 500 行（前端）时按"语义内聚"二次切分
- 每个任务完成后跑相关测试验证零回归

## Phase 1: 合并极小 Python 文件（<50 行）

- [ ] Task 1.1: 合并 `web/misc/` 顶层 20+ 个 thin binding shim
  - 范围：`web_application_context.py`(5 行) / `web_cloud_context_refresh.py`(5 行) / `web_config_bindings.py`(5 行) / `web_job_bindings.py`(5 行) / `web_session_bindings.py`(5 行) / `web_snapshot_bindings.py`(5 行) / `web_review.py`(15 行) / `web_runtime_facade.py`(15 行) 等顶层 thin shim
  - 步骤：
    1. Read 每个 thin shim 确认其内容仅为简单 re-export 或单函数
    2. 按子系统语义分组（如：bindings 类 → `web_bindings.py`；runtime 类 → `web_runtime.py`；review 类 → `web_review.py`）合并
    3. 原 `__init__.py` re-export 保留以维持 import 路径
  - 验证：`pytest tests/test_web*.py -x -q` 通过；`python -c "from brain_alpha_ops.web.misc import web_application_context"` 不报错
  - 产出：`web/misc/` 顶层 31 文件 → ≤12 文件

- [ ] Task 1.2: 合并 `web/misc/web_runtime_facade/` 子包 7 文件 → 1 文件
  - 范围：`_dispatch_context.py` / `_job_services.py` / `_logging.py`(11 行) / `_server.py` / `_snapshots.py` / `_submission.py`
  - 步骤：
    1. 全部合并到 `web_runtime_facade.py`（顶层单一文件）
    2. 删除子目录
    3. `__init__.py` re-export 保留
  - 验证：`pytest tests/test_web*.py -x -q` 通过
  - 产出：7 文件 → 1 文件

- [ ] Task 1.3: 合并 `web/misc/web_assistant_snapshots/` 7 文件 → 1 文件
  - 同 Task 1.2 模式
  - 产出：7 文件 → 1 文件

- [ ] Task 1.4: 合并 `web/misc/web_service_namespace/` 4 文件 → 1 文件
  - 同 Task 1.2 模式
  - 产出：4 文件 → 1 文件

- [ ] Task 1.5: 合并 `web/misc/web_facade_bindings/` 5 文件 → 1 文件
  - 同 Task 1.2 模式
  - 产出：5 文件 → 1 文件

- [ ] Task 1.6: 合并 `web/misc/web_backtest_slots/` 3 文件 → 1 文件
  - 同 Task 1.2 模式
  - 产出：3 文件 → 1 文件

- [ ] Task 1.7: 合并 `brain_api/` 内 <30 行碎片文件
  - 范围：`official_alphas/_composite.py`(11 行) / `official/_payload.py`(14 行) / `pagination_limits.py`(21 行) / `user_alpha_transient.py`(21 行)
  - 步骤：合并到对应同级 `__init__.py` 或语义最近的父模块
  - 验证：`pytest tests/test_brain_api*.py tests/test_official*.py -x -q` 通过
  - 产出：删除 4 个碎片文件

- [ ] Task 1.8: 合并 `research/` 顶层 <30 行碎片文件
  - 范围：`local_backtest_config.py`(6 行) / `anti_overfit.py`(15 行) / `calibration.py`(27 行) / `pipeline.py`(28 行) / `_value_helpers.py`(22 行)
  - 步骤：合并到对应 `__init__.py` 或父级模块
  - 验证：`pytest tests/test_anti_overfit*.py tests/test_calibration*.py -x -q` 通过
  - 产出：删除 5 个碎片文件

- [ ] Task 1.9: 合并顶层小文件
  - 范围：`agent_tool_errors.py`(11 行) → 合并到 `errors.py` 或 `agent_tools/_helpers.py`；`job_types.py`(15 行) → 合并到 `types.py`；`tasks/_constants.py`(13 行) → 合并到 `tasks/_store.py` 或 `tasks/__init__.py`
  - 验证：`pytest tests/ -x -q` 通过
  - 产出：删除 3 个顶层小文件

## Phase 2: 消灭 Mixin 滥用（research/ 子包）

- [x] Task 2.1: 合并 `research/pipeline/` 6 文件 → ≤2 文件
  - 范围：`_class.py` + `_cycle_mixin.py` + `_init_mixin.py` + `_main_loop_mixin.py` + `_post_processing_mixin.py` + `_run_mixin.py`
  - 步骤：
    1. 合并到 `pipeline.py`（若 >400 行则保留 `pipeline.py` 主类 + `pipeline_mixins.py`）
    2. 保留 mixin 机制本身（仅物理文件合并）
    3. `__init__.py` re-export 保留
  - 验证：`pytest tests/test_pipeline*.py tests/test_guided_pipeline*.py -x -q` 通过
  - 产出：6 文件 → 2 文件（`pipeline.py` 338 行 + `pipeline_mixins.py` 541 行；总行数 927 > 800，2 文件拆分下 `pipeline_mixins.py` 略超 400 行阈值，受 ≤2 文件硬约束限制无法再切分；按"主类入口 + 内部循环机制"语义切分）

- [x] Task 2.2: 合并 `research/pipeline_backtest_flow/` 5 文件 → ≤2 文件
  - 同 Task 2.1 模式
  - 产出：5 文件 → 2 文件（`pipeline_backtest_flow.py` 241 行 + `pipeline_backtest_flow_mixins.py` 232 行，均 ≤400）

- [x] Task 2.3: 合并 `research/pipeline_candidates/` 5 文件 → ≤2 文件
  - 同 Task 2.1 模式
  - 产出：5 文件 → 2 文件（`pipeline_candidates.py` 379 行 + `pipeline_candidates_mixins.py` 109 行，均 ≤400）

- [x] Task 2.4: 合并 `research/pipeline_snapshot/` 4 文件 → 1 文件
  - 产出：4 文件 → 1 文件（`pipeline_snapshot.py` 443 行；任务硬性要求 1 文件，合并后略超 400 行阈值但无法再切分）

- [x] Task 2.5: 合并 `research/pipeline_runtime/` 8 文件 → ≤2 文件
  - 产出：8 文件 → ≤2 文件（`runtime.py` 253 行 + `runtime_mixins.py` 226 行）

- [x] Task 2.6: 合并 `research/iterative_optimizer/` 5 文件 → ≤2 文件
  - 产出：5 文件 → ≤2 文件（`optimizer.py` 353 行 + `mutations.py` 172 行）

- [x] Task 2.7: 合并 `research/convergence/` 5 文件 → ≤2 文件
  - 产出：5 文件 → ≤2 文件（`bootstrap.py` 248 行 + `tracker.py` 284 行）

- [x] Task 2.8: 合并 `research/experience/` 4 文件 → ≤2 文件
  - 产出：4 文件 → ≤2 文件（`experience.py` 324 行 + `recording.py` 250 行）

- [x] Task 2.9: 合并 `research/llm_review/` 5 文件 → ≤2 文件
  - 产出：5 文件 → ≤2 文件

- [x] Task 2.10: 合并 `research/llm_service/` 6 文件 → ≤2 文件
  - 产出：6 文件 → ≤2 文件

- [x] Task 2.11: 合并 `research/scoring/` 6 文件 → ≤3 文件
  - 产出：6 文件 → ≤3 文件

- [x] Task 2.12: 合并 `research/repository/` 7 文件 → ≤3 文件
  - 产出：7 文件 → ≤3 文件

## Phase 3: 合并 subpackage 内 7-11 文件碎片包

- [ ] Task 3.1: 合并 `scoring/anti_overfit/` 11 文件 → ≤3 文件
  - 范围：`candidate.py` / `compliance.py` / `half_life.py` / `ic_stability.py` / `models.py` / `placebo.py` / `regime_stress.py` / `service.py` / `suite.py` / `utils.py`
  - 步骤：保留 `service.py`（核心）+ `suite.py`（聚合）+ `models.py`（数据类）；其余 7 个 check 模块合并为 `checks.py`
  - 验证：`pytest tests/test_anti_overfit*.py -x -q` 通过
  - 产出：11 文件 → ≤4 文件

- [ ] Task 3.2: 合并 `scoring/official_scoring/` 7 文件 → ≤2 文件
  - 产出：7 文件 → ≤2 文件

- [ ] Task 3.3: 合并 `scoring/release_score_gate/` 5 文件 → 1 文件
  - 产出：5 文件 → 1 文件

- [ ] Task 3.4: 合并 `compliance/` 10 文件（7 个 redline_check）→ ≤3 文件
  - 步骤：7 个 `redline_check_*.py` 合并为 1-2 个 `checks.py`
  - 产出：10 文件 → ≤3 文件

- [ ] Task 3.5: 合并 `web/dispatch/post_routes/` 9 文件 → ≤3 文件
  - 产出：9 文件 → ≤3 文件

- [ ] Task 3.6: 合并 `web_cloud/snapshot/` 8 文件 → ≤2 文件
  - 产出：8 文件 → ≤2 文件

- [ ] Task 3.7: 合并 `web_candidates/bindings/` 8 文件 → ≤2 文件
  - 产出：8 文件 → ≤2 文件

- [ ] Task 3.8: 合并 `ux/` 8 文件 → ≤3 文件
  - 产出：8 文件 → ≤3 文件

## Phase 4: 前端碎片收敛

- [ ] Task 4.1: 合并 `src/hooks/useAppState/` 9 文件 → ≤3 文件
  - 验证：`npm run typecheck` exit 0；`npm run build` 成功
  - 产出：9 文件 → ≤3 文件

- [ ] Task 4.2: 合并 `src/hooks/useJobMonitor/` 8 文件 → ≤3 文件
  - 产出：8 文件 → ≤3 文件

- [ ] Task 4.3: 合并 `src/helpers/runPayload/` 7 文件 → ≤2 文件
  - 产出：7 文件 → ≤2 文件

- [ ] Task 4.4: 合并 `src/components/ScoringPanel/` 10 文件 → ≤4 文件
  - 产出：10 文件 → ≤4 文件

- [ ] Task 4.5: 合并 `src/components/ConfigPanel/` 10 文件 → ≤4 文件
  - 产出：10 文件 → ≤4 文件

- [ ] Task 4.6: 合并 `src/components/CandidateTableSubComponents/` 7 文件 → ≤3 文件
  - 产出：7 文件 → ≤3 文件

- [ ] Task 4.7: 合并 `src/components/OfficialOperations/` 29 文件 → ≤10 文件
  - 产出：29 文件 → ≤10 文件

- [ ] Task 4.8: 合并 `src/components/SnapshotPanel/` 8 文件 → ≤3 文件
  - 产出：8 文件 → ≤3 文件

- [ ] Task 4.9: 合并 `src/types/` 8 文件 → ≤2 文件
  - 产出：8 文件 → ≤2 文件

- [ ] Task 4.10: 合并 `src/utils/` 7 文件 → ≤3 文件
  - 产出：7 文件 → ≤3 文件

- [ ] Task 4.11: 合并 `src/styles/` 7 文件 → ≤2 文件（保留 `theme-tokens.css` 单独）
  - 产出：7 文件 → ≤2 文件

## Phase 5: Scripts 收敛

- [ ] Task 5.1: 合并 `scripts/` 同类 check 脚本
  - 范围：`check_*.py` 顶层多个 + 各 `check_*/` 子目录（如 `check_frontend_surface_parity/` 5 文件、`check_live_submit_readiness/` 8 文件、`check_tracked_data_inventory/` 8 文件、`final_release_gate/` 8 文件等）
  - 步骤：每个 `check_*/` 子目录合并到顶层单文件入口；同类 check 合并为 `scripts/checks_<group>.py`
  - 验证：`python scripts/check_architecture.py` 等代表性脚本不报错
  - 产出：101 文件 → ≤40 文件

## Phase 6: 顶层 helper 与构建配置同步

- [ ] Task 6.1: 合并 `brain_alpha_ops/` 顶层可内聚小文件
  - 范围：`agent_tool_errors.py`(11 行)（Task 1.9 已处理）；`agent_*.py` 4 个文件（`agent_guidance_tools.py` / `agent_live_tools.py` / `agent_research_tools.py` / `agent_tool_errors.py`）→ 评估合并为 ≤2 个
  - 验证：`pytest tests/test_agent*.py -x -q` 通过
  - 产出：顶层 47 文件 → ≤35 文件

- [ ] Task 6.2: 同步 `BrainAlphaOps.spec` hiddenimports
  - 移除已不存在的模块名（如合并后删除的子模块路径）
  - 验证：`pyinstaller BrainAlphaOps.spec --noconfirm --log-level WARN` 构建成功（若环境支持）；至少 hiddenimports 与磁盘模块结构一致
  - 产出：hiddenimports 列表精简

## Phase 7: 回归验证

- [ ] Task 7.1: Python 全量回归
  - `pytest tests/ -q` 通过数 ≥ 2995，failed ≤ baseline（11）
  - 无新增 ImportError / AttributeError
  - 产出：回归测试报告

- [ ] Task 7.2: 前端构建验证
  - `npm run typecheck` exit 0
  - `npm run lint` warnings ≤ baseline
  - `npm run build` 成功
  - 产出：前端构建报告

- [ ] Task 7.3: 文件数总账验证
  - 总文件数 ≤ 900（从 1,584 削减 ≥43%）
  - `brain_alpha_ops/` 子目录数 ≤ 90（从 155 削减 ≥42%）
  - Python 文件数 ≤ 750（从 1,058 削减 ≥29%）
  - 前端文件数 ≤ 160（从 265 削减 ≥40%）
  - 产出：文件数总账报告

# Task Dependencies

- Task 1.x 系列互相独立可并行（不同子包）
- Task 2.x 系列互相独立可并行（不同 research/ 子包）
- Task 3.x 系列互相独立可并行
- Task 4.x 系列互相独立可并行（前端独立于后端）
- Task 5 依赖 Task 1-3 完成（避免冲突）
- Task 6.2 依赖 Task 1-3 完成（hiddenimports 同步）
- Task 7 依赖全部前序任务完成
