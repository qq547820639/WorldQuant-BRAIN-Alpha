# Tasks

## 批次 A: research/ 模块文件拆分（12 个文件，可并行）

- [x] Task 1: 拆分 `research/observability.py` (628行) → `observability/` 子包
  - [x] SubTask 1.1: 读取原文件，识别所有类/函数/常量/被测试导入的私有符号
  - [x] SubTask 1.2: 按功能拆分为 3-5 个子模块（≤350行），创建 `__init__.py` re-export
  - [x] SubTask 1.3: 删除原 `.py` 文件，验证导入 `from brain_alpha_ops.research.observability import *`

- [x] Task 2: 拆分 `research/local_backtest/expression_evaluator.py` (619行) → `expression_evaluator/` 子包
  - [x] SubTask 2.1: 读取原文件，识别 `LocalExpressionEvaluator` 类及辅助函数
  - [x] SubTask 2.2: 按算子类别拆分子模块（基础算子/时序算子/辅助函数）
  - [x] SubTask 2.3: 删除原文件，验证导入

- [x] Task 3: 拆分 `research/llm_service.py` (610行) → `llm_service/` 子包
  - [x] SubTask 3.1: 识别 `LLMService`/`LLMReviewResult`/`LLMGenerationGuidance` 及辅助函数
  - [x] SubTask 3.2: 按职责拆分（类型定义/服务类/辅助函数）
  - [x] SubTask 3.3: 删除原文件，验证 `tests/test_integration_full_lifecycle.py` 导入

- [x] Task 4: 拆分 `research/simulation_scheduler.py` (600行) → `simulation_scheduler/` 子包
  - [x] SubTask 4.1: 识别 `SlotState`/`SimulationSlot`/`ThreeSlotScheduler`/`SlotOutcome`
  - [x] SubTask 4.2: 按职责拆分（类型/槽位管理/调度器）
  - [x] SubTask 4.3: 删除原文件，验证 `tests/test_three_slot_scheduler.py` 导入

- [x] Task 5: 拆分 `research/expression_sqlite_index.py` (591行) → `expression_sqlite_index/` 子包
  - [x] SubTask 5.1: 识别 `ExpressionSqliteIndex` 类及辅助函数
  - [x] SubTask 5.2: 按功能拆分（类核心/查询方法/辅助函数）
  - [x] SubTask 5.3: 删除原文件，验证 `tests/test_expression_sqlite_index.py` 导入

- [x] Task 6: 拆分 `research/experience.py` (552行) → `experience/` 子包
  - [x] SubTask 6.1: 识别 `record_alpha_result`/`get_winning_patterns`/`update_hypothesis_weights` 等函数
  - [x] SubTask 6.2: 按职责拆分（记录/模式提取/假设更新）
  - [x] SubTask 6.3: 删除原文件，验证 `tests/test_experience.py`/`tests/test_ratio_consistency.py`/`tests/qa_hypothesis_system.py` 导入

- [x] Task 7: 拆分 `research/cross_review_pipeline.py` (519行) → `cross_review_pipeline/` 子包
  - [x] SubTask 7.1: 识别 `CrossReviewPipeline`/`KnowledgeEvidenceChecker`/`ReviewDecisionEngine` 类
  - [x] SubTask 7.2: 按类拆分子模块
  - [x] SubTask 7.3: 删除原文件，验证 `tests/test_defect_015_log_redaction.py` 导入

- [x] Task 8: 拆分 `research/expression_ast.py` (512行) → `expression_ast/` 子包
  - [x] SubTask 8.1: 识别 `ExpressionParseError`/`ExprNode`/`ExpressionProfile`/`parse_expression` 等
  - [x] SubTask 8.2: 按职责拆分（类型/解析/相似性检查）
  - [x] SubTask 8.3: 删除原文件，验证 6+ 个测试文件导入

- [x] Task 9: 拆分 `research/pipeline_official_context.py` (511行) → `pipeline_official_context/` 子包
  - [x] SubTask 9.1: 识别 `OfficialContextLoadResult`/`OfficialContextValidationState` 及函数
  - [x] SubTask 9.2: 按职责拆分（类型/加载器/验证器）
  - [x] SubTask 9.3: 删除原文件，验证 `tests/test_pipeline_official_context.py` 导入

- [x] Task 10: 拆分 `research/memory.py` (510行) → `memory/` 子包
  - [x] SubTask 10.1: 识别 `ResearchMemory` 类及辅助函数
  - [x] SubTask 10.2: 按职责拆分（类核心/方法组/辅助函数）
  - [x] SubTask 10.3: 删除原文件，验证 `tests/test_assistant_context.py`/`tests/test_research_memory.py` 导入

- [x] Task 11: 拆分 `research/iterative_optimizer.py` (508行) → `iterative_optimizer/` 子包
  - [x] SubTask 11.1: 识别 `IterativeOptimizer` 类及辅助函数
  - [x] SubTask 11.2: 按变异策略拆分子模块
  - [x] SubTask 11.3: 删除原文件，验证 `tests/test_pipeline_e2e_mock.py`/`tests/test_infrastructure_modules.py` 导入

- [x] Task 12: 拆分 `research/convergence.py` (506行) → `convergence/` 子包
  - [x] SubTask 12.1: 识别 `ConvergenceTracker` 类及 `_inv_norm_cdf` 等辅助函数
  - [x] SubTask 12.2: 按职责拆分（统计辅助/追踪器类/趋势分析）
  - [x] SubTask 12.3: 删除原文件，验证 4+ 个测试文件导入

## 批次 B: brain_api/ 模块文件拆分（3 个文件）

- [x] Task 13: 二次拆分 `brain_api/official/_api.py` (620行) — Phase 9 遗留修复
  - [x] SubTask 13.1: 读取 `_api.py`，识别 `OfficialBrainAPI` 类的方法组
  - [x] SubTask 13.2: 按方法组拆分为多个 mixin（auth/simulation/data_access），组合到 `_api.py`
  - [x] SubTask 13.3: 确保 `_api.py` ≤ 350 行（实际 202 行），验证 `tests/test_official_adapter.py`/`tests/test_brain_api_official_validation.py` 全部通过

- [x] Task 14: 拆分 `brain_api/official_helpers.py` (591行) → `official_helpers/` 子包
  - [x] SubTask 14.1: 识别 `build_official_url`/`normal_field`/`_ratio`/`looks_non_production_alpha_id` 等函数
  - [x] SubTask 14.2: 按功能拆分（URL构建/数据规范化/分页/去重）
  - [x] SubTask 14.3: 删除原文件，验证 `tests/test_official_adapter.py`/`tests/test_ratio_consistency.py`/`tests/production_api_stub.py` 导入

- [x] Task 15: 拆分 `brain_api/official_alphas.py` (538行) → `official_alphas/` 子包
  - [x] SubTask 15.1: 识别 `AlphaQueryMixin` 类
  - [x] SubTask 15.2: 按方法组拆分为多个 mixin 并组合
  - [x] SubTask 15.3: 删除原文件，验证导入

## 批次 C: 其他模块文件拆分（5 个文件）

- [x] Task 16: 拆分 `scoring/official_scoring.py` (654行) → `official_scoring/` 子包
  - [x] SubTask 16.1: 识别评分逻辑类/函数及常量
  - [x] SubTask 16.2: 按职责拆分（评分规则/权重计算/辅助函数）
  - [x] SubTask 16.3: 删除原文件，验证导入

- [x] Task 17: 拆分 `web/misc/web_service_namespace.py` (567行) → `web_service_namespace/` 子包
  - [x] SubTask 17.1: 识别 `build_web_service_namespace` 函数及模块级导入
  - [x] SubTask 17.2: 按命名空间分组拆分子构建器
  - [x] SubTask 17.3: 删除原文件，验证 `tests/test_web_facade_contract.py` 导入

- [x] Task 18: 拆分 `web/config/web_config.py` (531行) → `web_config/` 子包
  - [x] SubTask 18.1: 识别 `public_run_config_dict`/`_load_presets` 及验证函数
  - [x] SubTask 18.2: 按职责拆分（常量/解析/验证）
  - [x] SubTask 18.3: 删除原文件，验证 `tests/test_web_runtime_facade_coverage.py`/`tests/qa_full_chain_backend.py` 导入

- [x] Task 19: 拆分 `web_candidates/generation.py` (539行) → `generation/` 子包
  - [x] SubTask 19.1: 识别生成逻辑类/函数
  - [x] SubTask 19.2: 按职责拆分子模块
  - [x] SubTask 19.3: 删除原文件，验证导入

- [x] Task 20: 拆分 `e2e_report.py` (538行) → `e2e_report/` 子包
  - [x] SubTask 20.1: 识别 `build_e2e_artifact_summary`/`render_markdown_summary` 函数
  - [x] SubTask 20.2: 按职责拆分（截图/账本/预览/渲染）
  - [x] SubTask 20.3: 删除原文件，验证 `tests/test_e2e_report.py` 导入

## 批次 D: 验证与提交

- [x] Task 21: 全量导入验证
  - [x] SubTask 21.1: 验证 20 个拆分模块 `from brain_alpha_ops.xxx import *` 全部 OK
  - [x] SubTask 21.2: 验证 `brain_api/official/_api.py` 二次拆分后 ≤ 350 行（实际 202 行）

- [x] Task 22: 测试套件验证
  - [x] SubTask 22.1: 运行受影响测试文件，确认无新增失败（276 通过，1 预存本地化失败，符合允许范围）
  - [x] SubTask 22.2: 抽样运行跨模块集成测试

- [x] Task 23: 文件大小最终验证
  - [x] SubTask 23.1: 运行 `find brain_alpha_ops -name "*.py" -not -path "*/__pycache__/*" | xargs wc -l | sort -rn | awk '$1 > 500'`，确认输出为空

- [x] Task 24: 提交并推送到 origin/main
  - [x] SubTask 24.1: `git add` 所有拆分相关文件（排除运行时数据文件）
  - [x] SubTask 24.2: `git commit` 使用规范提交消息
  - [x] SubTask 24.3: `git push origin main` 推送成功

# Task Dependencies

- Task 13（official/_api.py 二次拆分）独立于其他任务，可并行
- Task 1-12（research/ 文件）相互独立，可并行执行（建议分 3-4 组并行 sub-agent）
- Task 14-15（brain_api/）独立，可并行
- Task 16-20（其他模块）独立，可并行
- Task 21-24 依赖 Task 1-20 全部完成
- 无循环依赖
