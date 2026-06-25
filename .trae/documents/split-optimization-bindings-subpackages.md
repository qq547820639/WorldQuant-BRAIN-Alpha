# Plan: 完成 optimization 与 bindings 子包拆分

## Summary

继续并完成 4 个 Python 后端文件的子包拆分任务（保持完全向后兼容）。前两个文件（`audit.py`、`decisions.py`）已完成验证；剩余两个文件（`optimization.py`、`bindings.py`）的子模块文件已部分就绪，需要补齐 `__init__.py` 再导出垫片、删除原始文件并验证。

## Current State Analysis

### 已完成
- `brain_alpha_ops/web_candidates/audit/` 子包：4 个子模块 + `__init__.py` 已就位并通过验证。
- `brain_alpha_ops/web_candidates/decisions/` 子包：4 个子模块 + `__init__.py` 已就位并通过验证。
- `brain_alpha_ops/web_candidates/optimization/` 子目录：5 个子模块已创建（`_helpers.py`、`_explainability.py`、`_prepare.py`、`_summary.py`、`_payload.py`），**缺 `__init__.py`**；原始 `optimization.py` 仍存在。
- `brain_alpha_ops/web_candidates/bindings.py`：仍是原始单文件（581 行），**尚未拆分**。

### 外部引用情况（决定再导出范围）

**optimization.py 外部引用：**
- `brain_alpha_ops/web/dispatch/post_routes/helpers.py:112` — 导入 `optimize_candidates_payload`、`persist_optimized_candidates`。
- `tests/test_web_candidate_optimization.py:8-9` — `import ... as web_candidate_optimization` + 导入两个公开函数；并用 `monkeypatch.setattr(web_candidate_optimization, "LocalBacktestEngine", ...)` 替换（3 处）。
- 子模块内部 `_payload.py:48` 已用 late import `from brain_alpha_ops.web_candidates.optimization import LocalBacktestEngine` 以支持 monkeypatch。

**bindings.py 外部引用：**
- 6 个 `brain_alpha_ops/web/misc/web_*_bindings.py` 文件用 `from brain_alpha_ops.web_candidates.bindings import *` 做通配再导出。
- `brain_alpha_ops/web/misc/web_facade_bindings.py` 显式导入 23 个候选相关函数。
- 无测试直接依赖 `bindings`。

### 子模块文件验证（已读取确认）
- `optimization/_helpers.py` (138 行) — 含 `_candidate_needs_optimization`、`_candidate_rejected_by_local_gate`、`_candidate_rejection_reasons`、`_rejected_reason_counts`、`_candidate_score`、`_optional_float`、`_optional_int`、`_string_list`、`_int_list`、`_candidate_blocking_codes`、`_is_submit_only_blocker`、`_expression_key`、`_candidate_submission_ready`。
- `optimization/_explainability.py` (171 行) — 含 `_attach_expression_proof`、`_attach_optimization_explanation`、`_optimization_explanation`、`_expression_change_summary`、`_official_context_explanation`、`_optimizer_trace`、`_mark_official_context_proof_failed`、`_source_tags`。
- `optimization/_prepare.py` (142 行) — 含 `_prepare_optimized_candidate`。
- `optimization/_summary.py` (77 行) — 含 `_summary`、`_all_candidate_rows`、`_target_pool_size`。
- `optimization/_payload.py` (278 行) — 含 `RunConfigFromPayload`、`RepositoryFactory`、`ParameterSearchFactory`、`optimize_candidates_payload`、`persist_optimized_candidates`、`_resolve_dataset_id`、`_source_candidates`、`candidates_ledger_path`、`_rank_rework_sources`。

### bindings.py 结构（6 个分区，行号锚点）
1. `web_candidate_bindings` (26-160) — 23 个函数（candidate/check/submit/preflight）
2. `web_config_bindings` (161-192) — 5 个函数
3. `web_job_bindings` (193-234) — 5 个函数
4. `web_session_bindings` (235-257) — 2 个函数
5. `web_runtime_bindings` (258-348) — 14 个函数
6. `web_snapshot_bindings` (349-580) — 36 个函数

文件内重复定义了 `_web()`、`_app_context()`、`_runtime_facade()`、`_snapshot_facade()` 辅助函数（Python 取最后定义生效）。拆分时把这些共享辅助放进 `_helpers.py`，各子模块从 `_helpers` 导入。

## Proposed Changes

### 阶段 1：完成 optimization 子包

#### 1.1 创建 `brain_alpha_ops/web_candidates/optimization/__init__.py`
- 参照 `audit/__init__.py` 与 `decisions/__init__.py` 的模式。
- 从 `_helpers`、`_explainability`、`_prepare`、`_summary`、`_payload` 导入全部公开 + 私有符号。
- **关键**：再导出 `LocalBacktestEngine`（从 `brain_alpha_ops.research.local_backtest_engine`），以支持 `monkeypatch.setattr(web_candidate_optimization, "LocalBacktestEngine", ...)`。这与 `_payload.py` 内的 late import 配合：monkeypatch 替换包级属性后，late import 会拿到替换后的对象。
- 定义 `__all__` 列表，包含：
  - 类型别名：`RunConfigFromPayload`、`RepositoryFactory`、`ParameterSearchFactory`
  - 外部类：`LocalBacktestEngine`
  - 公开 API：`optimize_candidates_payload`、`persist_optimized_candidates`、`candidates_ledger_path`
  - 私有辅助（向后兼容）：`_candidate_needs_optimization`、`_candidate_submission_ready`、`_candidate_rejected_by_local_gate`、`_candidate_rejection_reasons`、`_rejected_reason_counts`、`_candidate_score`、`_optional_float`、`_optional_int`、`_string_list`、`_int_list`、`_candidate_blocking_codes`、`_is_submit_only_blocker`、`_expression_key`、`_attach_expression_proof`、`_attach_optimization_explanation`、`_optimization_explanation`、`_expression_change_summary`、`_official_context_explanation`、`_optimizer_trace`、`_mark_official_context_proof_failed`、`_source_tags`、`_prepare_optimized_candidate`、`_summary`、`_all_candidate_rows`、`_target_pool_size`、`_resolve_dataset_id`、`_source_candidates`、`_rank_rework_sources`

#### 1.2 删除原始 `brain_alpha_ops/web_candidates/optimization.py`
- 在 `__init__.py` 创建并验证可导入后，删除原文件。Python 包优先级：同名子包目录会遮蔽 `.py` 文件，但保留旧文件会引起混淆且可能触发 lint 错误。

#### 1.3 验证 optimization
```
python3 -c "from brain_alpha_ops.web_candidates.optimization import *; print('optimization OK')"
python3 -c "from brain_alpha_ops.web_candidates.optimization import LocalBacktestEngine, optimize_candidates_payload, persist_optimized_candidates; print('symbols OK')"
```

### 阶段 2：拆分 bindings.py → bindings/ 子包

#### 2.1 创建 `brain_alpha_ops/web_candidates/bindings/_helpers.py`
- 包含共享辅助：`_web()`、`_app_context()`、`_runtime_facade()`、`_snapshot_facade()`。
- 顶部导入 `threading`、`from brain_alpha_ops.runtime_constants import WebDefaults as _WebDefaults`、`from brain_alpha_ops.web_job_registry import resolve_web_job_registry`。
- 约 30 行。

#### 2.2 创建 6 个子模块（每个 ≤350 行）

**`bindings/_candidate.py`** (对应原 26-160 行，约 135 行)
- 公开函数：`generate_candidates_payload`、`run_generate_candidates_job`、`run_scoring_evaluate_job`、`run_submit_batch_job`、`candidate_from_payload`、`sync_cloud_alphas`、`run_sync_job`、`run_check_batch_job`、`refresh_cloud_context_for_check`、`datasets_from_fields`、`persist_official_context`、`save_official_context_json`、`passed_candidates_from_payload`、`check_candidate_availability`、`cloud_status_for`、`cloud_similarity_risk`、`check_candidate`、`submission_preflight_error`、`submission_preflight_advisory`、`observability_submission_preflight`、`record_submit_blocked`、`submit_candidate`、`load_check_results`、`submit_batch`。
- 别名：`submission_preflight_error_message = submission_preflight_error`。
- 从 `._helpers` 导入 `_app_context`、`_runtime_facade`。

**`bindings/_config.py`** (对应原 161-192 行，约 35 行)
- 公开函数：`load_run_config_provider`、`runtime_project_root_provider`、`run_config_from_payload`、`config_from_payload`、`save_run_config_payload`。
- 从 `._helpers` 导入 `_web`。

**`bindings/_job.py`** (对应原 193-234 行，约 45 行)
- 公开函数：`job_registry`、`job_registry_view`、`active_auxiliary_operation`、`rate_limit_request`、`submit_background_job`。
- 从 `._helpers` 导入 `_web`、`_app_context`。
- 从 `brain_alpha_ops.web_job_registry` 导入 `resolve_web_job_registry`。

**`bindings/_session.py`** (对应原 235-257 行，约 25 行)
- 公开函数：`configure_session_policy`、`normalize_host`。
- 从 `._helpers` 导入 `_web`。

**`bindings/_runtime.py`** (对应原 258-348 行，约 95 行)
- 公开函数：`test_connection`、`handler_dispatch_context`、`lookup_sse_job`、`run_job`、`start_thread`、`compute_run_stats`、`lifecycle_from_job`、`alpha_lifecycle_history`、`maybe_archive_lifecycle`、`find_free_port`、`shutdown_server`、`serve`、`smoke_test_server`、`main`。
- 从 `._helpers` 导入 `_web`、`_app_context`、`_runtime_facade`。
- 顶部 `import threading`、`from brain_alpha_ops.runtime_constants import WebDefaults as _WebDefaults`。

**`bindings/_snapshot.py`** (对应原 349-580 行，约 235 行)
- 公开函数（36 个）：`cloud_alpha_snapshot`、`cloud_alpha_cache_probe`、`snapshot_runtime`、`snapshot_facade`、`research_memory_snapshot`、`research_knowledge_snapshot`、`research_observability_snapshot`、`prompt_run_ledger_snapshot`、`sqlite_index_snapshot`、`sqlite_expression_lookup_payload`、`sqlite_record_lookup_payload`、`durable_job_rows`、`assistant_guidance_snapshot`、`assistant_guidance_history`、`assistant_context_snapshot`、`assistant_request_snapshot`、`assistant_response_parse_payload`、`assistant_response_guidance_payload`、`anti_overfit_snapshot`、`rolling_validation_snapshot`、`assistant_cross_review_payload`、`save_assistant_guidance_payload`、`latest_result_snapshot`、`latest_run_history_path`、`user_profile_snapshot`、`load_presets`、`match_preset_id`、`latest_cached_user_alphas`、`latest_cached_user_alpha_path`、`cached_user_alpha_paths`、`official_context_file_counts`、`read_official_context_metadata`、`read_official_context_json`、`cloud_alpha_summary`、`storage_jsonl_path`、`read_storage_jsonl`、`read_storage_jsonl_stats`、`public_run_config`。
- 从 `._helpers` 导入 `_web`、`_app_context`、`_runtime_facade`、`_snapshot_facade`。

#### 2.3 创建 `brain_alpha_ops/web_candidates/bindings/__init__.py`
- 模式与 `audit/__init__.py`、`decisions/__init__.py` 一致。
- 从 6 个子模块导入全部公开函数 + `submission_preflight_error_message` 别名。
- 定义 `__all__` 列出全部 85 个公开符号（不含下划线前缀的辅助函数 `_web` 等，因为这些是内部实现细节，外部通过 `import *` 不会拿到下划线符号，且 `web_facade_bindings.py` 显式导入的也都是公开名）。

#### 2.4 删除原始 `brain_alpha_ops/web_candidates/bindings.py`
- 在 `__init__.py` 创建并验证可导入后，删除原文件。

#### 2.5 验证 bindings
```
python3 -c "from brain_alpha_ops.web_candidates.bindings import *; print('bindings OK')"
python3 -c "from brain_alpha_ops.web_candidates.bindings import serve, generate_candidates_payload, submit_batch, snapshot_runtime, public_run_config; print('symbols OK')"
python3 -c "from brain_alpha_ops.web.misc.web_facade_bindings import build_web_facade_bindings; print('facade OK')"
```

### 阶段 3：最终验证
运行用户指定的 4 条验证命令：
```
python3 -c "from brain_alpha_ops.web_candidates.optimization import *; print('optimization OK')"
python3 -c "from brain_alpha_ops.web_candidates.bindings import *; print('bindings OK')"
python3 -c "from brain_alpha_ops.web_candidates.decisions import *; print('decisions OK')"
python3 -c "from brain_alpha_ops.web_candidates.audit import *; print('audit OK')"
```
并额外跑一次优化相关测试，确认 monkeypatch 仍生效：
```
python3 -m pytest tests/test_web_candidate_optimization.py -x -q
```

## Assumptions & Decisions

1. **monkeypatch 兼容性**：`optimization/__init__.py` 必须把 `LocalBacktestEngine` 作为模块级属性暴露；`_payload.py` 已用 late import `from brain_alpha_ops.web_candidates.optimization import LocalBacktestEngine` 从包内取值，这样 monkeypatch 替换包级属性后函数体内拿到的是替换后的对象。此模式已在 `_payload.py:48` 实现，本计划只需在 `__init__.py` 补上再导出。

2. **共享辅助放 `_helpers.py`**：原 `bindings.py` 在 6 个分区各自重复定义 `_web`/`_app_context`/`_runtime_facade`/`_snapshot_facade`（Python 取最后定义生效）。拆分后放进 `bindings/_helpers.py` 统一维护，避免 6 份重复。这不改变运行时行为，因为这些函数实现完全一致。

3. **`__all__` 范围**：
   - `optimization/__init__.py` 的 `__all__` 同时包含公开与私有符号（与 `audit`、`decisions` 一致），因为测试和子模块间引用了私有辅助。
   - `bindings/__init__.py` 的 `__all__` 只包含公开符号（不含 `_web` 等辅助），因为外部 `web_*_bindings.py` 只用 `import *` 或显式导入公开名；辅助函数属于实现细节。

4. **不改变任何函数签名或行为**：纯文本搬迁，逐字复制函数体，仅调整 import 来源（`from brain_alpha_ops.X` → `from ._helpers` 等）。

5. **`submission_preflight_error_message` 别名**：原文件 135 行 `submission_preflight_error_message = submission_preflight_error`，需在 `_candidate.py` 末尾保留，并在 `__init__.py` 再导出，因为 `web_facade_bindings.py:71` 显式导入此别名。

6. **不创建额外文件**：仅创建必要的子模块文件与 `__init__.py`，不添加 README、测试或文档。

## Verification steps

1. 4 条用户指定验证命令全部输出 `OK`。
2. `tests/test_web_candidate_optimization.py` 全部通过（验证 monkeypatch 仍生效）。
3. `from brain_alpha_ops.web.misc.web_facade_bindings import build_web_facade_bindings` 可正常导入（验证 bindings 通配再导出链路完整）。
4. 子模块行数均 ≤350 行（已核对：最大为 `_payload.py` 278 行、`_snapshot.py` 约 235 行）。
