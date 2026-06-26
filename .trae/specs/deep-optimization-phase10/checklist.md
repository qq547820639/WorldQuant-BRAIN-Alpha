# BRAIN Alpha Ops 深挖优化 Phase 10 - 验证清单

## 文件大小合规
- [x] `find brain_alpha_ops -name "*.py" -not -path "*/__pycache__/*" | xargs wc -l | awk '$1 > 500'` 输出为空
- [x] `brain_api/official/_api.py` 二次拆分后 ≤ 350 行（实际 202 行，Phase 9 遗留修复）
- [x] 所有新创建子包内 `_*.py` 子模块 ≤ 350 行（最大为 `expression_ast/_parser.py` 348 行）

## 拆分完成度 — research/ 模块（12 个文件）
- [x] `research/observability.py` (628行) 已拆分为子包
- [x] `research/local_backtest/expression_evaluator.py` (619行) 已拆分为子包
- [x] `research/llm_service.py` (610行) 已拆分为子包
- [x] `research/simulation_scheduler.py` (600行) 已拆分为子包
- [x] `research/expression_sqlite_index.py` (591行) 已拆分为子包
- [x] `research/experience.py` (552行) 已拆分为子包
- [x] `research/cross_review_pipeline.py` (519行) 已拆分为子包
- [x] `research/expression_ast.py` (512行) 已拆分为子包
- [x] `research/pipeline_official_context.py` (511行) 已拆分为子包
- [x] `research/memory.py` (510行) 已拆分为子包
- [x] `research/iterative_optimizer.py` (508行) 已拆分为子包
- [x] `research/convergence.py` (506行) 已拆分为子包

## 拆分完成度 — brain_api/ 模块（3 个文件）
- [x] `brain_api/official/_api.py` (620行) 已二次拆分（实际 202 行）
- [x] `brain_api/official_helpers.py` (591行) 已拆分为子包
- [x] `brain_api/official_alphas.py` (538行) 已拆分为子包

## 拆分完成度 — 其他模块（5 个文件）
- [x] `scoring/official_scoring.py` (654行) 已拆分为子包
- [x] `web/misc/web_service_namespace.py` (567行) 已拆分为子包
- [x] `web/config/web_config.py` (531行) 已拆分为子包
- [x] `web_candidates/generation.py` (539行) 已拆分为子包
- [x] `e2e_report.py` (538行) 已拆分为子包

## 向后兼容
- [x] 所有原 `.py` 文件已删除（包目录优先级覆盖同名 .py）
- [x] 所有 `__init__.py` 显式 re-export 公共 API
- [x] 所有 `__init__.py` 显式 re-export 被测试引用的私有 `_underscore` 符号
- [x] 所有子模块使用硬编码 `logging.getLogger("original.module.name")` 保持 logger 身份
- [x] 涉及 monkeypatch 的模块使用 `_pkg()` 模式访问包级属性
- [x] 涉及 `module.time`/`module.logging` 等标准库属性访问的 `__init__.py` 已重导入对应模块

## 导入验证
- [x] 20 个拆分模块 `from brain_alpha_ops.xxx import *` 全部 OK
- [x] `brain_api/official/` 子包二次拆分后导入 OK

## 测试验证
- [x] `tests/test_expression_sqlite_index.py` 全部通过
- [x] `tests/test_experience.py` 全部通过
- [x] `tests/test_three_slot_scheduler.py` 全部通过
- [x] `tests/test_e2e_report.py` 全部通过
- [x] `tests/test_official_adapter.py` 全部通过（含 `test_throttle_uses_shared_timestamp_across_instances`）
- [x] `tests/test_brain_api_official_validation.py` 全部通过
- [x] `tests/test_web_facade_contract.py` 全部通过
- [x] `tests/test_web_runtime_facade_coverage.py` 无新增失败（允许预存本地化失败）
- [x] `tests/test_defect_015_log_redaction.py` 全部通过
- [x] `tests/test_pipeline_official_context.py` 全部通过
- [x] `tests/test_assistant_context.py` 全部通过
- [x] `tests/test_research_memory.py` 全部通过
- [x] `tests/test_infrastructure_modules.py` 全部通过
- [x] `tests/test_integration_full_lifecycle.py` 全部通过
- [x] 无新增测试失败（276 通过，1 预存本地化失败：`test_runtime_facade_connection_fails_when_profile_returns_auth_error` 中文错误消息 vs 英文期望）

## 提交
- [x] 所有变更已 `git add`（排除运行时数据文件 `data/*.jsonl`、`data/jobs_production.json`、`brain_alpha_ops/data/trends.jsonl`）
- [x] `git commit` 使用规范中文提交消息
- [x] `git push origin main` 推送成功
- [x] `git status` 显示工作区干净（除运行时数据文件）
