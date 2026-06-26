# Tasks

> 工作流 A→C 顺序执行；同一工作流内无依赖子任务可并行。
> 每完成一项立即勾选。所有变更前做全局影响评估，变更后输出结构化变更报告。
> 拆分模式遵循 `project_memory.md`：re-export 子包 + `__init__.py` 导出公共 API +
> 已测试私有符号 + logger 名硬编码 + `_pkg()` 兼容 monkeypatch。

## 工作流 A：拆分 8 个 web/dispatch/state/scoring/ux/browser/agent 超限文件

- [x] Task A1：拆分 `brain_alpha_ops/web/dispatch/web_dispatch_context.py` (448 行)
  - [x] A1.1：读取全文，按职责切分子模块（每个 ≤ 350 行）
  - [x] A1.2：创建 `web/dispatch/web_dispatch_context/__init__.py`，导出公共 API + `__all__`，logger 名硬编码为 `brain_alpha_ops.web.dispatch.web_dispatch_context`
  - [x] A1.3：原 `web_dispatch_context.py` 改为 thin shim 或删除（由 `__init__.py` 取代）
  - [x] A1.4：运行 `python3 -c "from brain_alpha_ops.web.dispatch.web_dispatch_context import *"` 与相关测试验证无回归
- [x] Task A2：拆分 `brain_alpha_ops/web/state/web_state_contract.py` (436 行)
  - [x] A2.1：按职责切分子模块（≤ 350 行）
  - [x] A2.2：创建 `web/state/web_state_contract/__init__.py` + `__all__` + 硬编码 logger
  - [x] A2.3：原 `web_state_contract.py` 改为 thin shim 或删除
  - [x] A2.4：运行相关测试（`test_*web_state*`、`test_*state_contract*`）验证无回归
- [x] Task A3：拆分 `brain_alpha_ops/web/submissions/web_submission_safety.py` (407 行)
  - [x] A3.1：按职责切分子模块（≤ 350 行）
  - [x] A3.2：创建 `web/submissions/web_submission_safety/__init__.py` + `__all__` + 硬编码 logger
  - [x] A3.3：原 `web_submission_safety.py` 改为 thin shim 或删除
  - [x] A3.4：运行相关测试（`test_*submission_safety*`、`test_web_submissions*`）验证无回归
- [x] Task A4：拆分 `brain_alpha_ops/web/dispatch/web_http_handler.py` (382 行)
  - [x] A4.1：按职责切分子模块（≤ 350 行）
  - [x] A4.2：创建 `web/dispatch/web_http_handler/__init__.py` + `__all__` + 硬编码 logger
  - [x] A4.3：原 `web_http_handler.py` 改为 thin shim 或删除
  - [x] A4.4：运行相关测试（`test_*web_http*`、`test_web_dispatch*`）验证无回归
- [x] Task A5：拆分 `brain_alpha_ops/scoring/release_score_gate.py` (396 行)
  - [x] A5.1：按职责切分子模块（≤ 350 行）
  - [x] A5.2：创建 `scoring/release_score_gate/__init__.py` + `__all__` + 硬编码 logger
  - [x] A5.3：原 `release_score_gate.py` 改为 thin shim 或删除
  - [x] A5.4：运行相关测试（`test_*release_score_gate*`、`test_scoring*`）验证无回归
- [x] Task A6：拆分 `brain_alpha_ops/ux/errors.py` (390 行)
  - [x] A6.1：按职责切分子模块（≤ 350 行），按错误类别分组
  - [x] A6.2：创建 `ux/errors/__init__.py` + `__all__` + 硬编码 logger
  - [x] A6.3：原 `errors.py` 改为 thin shim 或删除
  - [x] A6.4：运行相关测试（`test_*errors*`、`test_ux*`）验证无回归
- [x] Task A7：拆分 `brain_alpha_ops/browser/execution_adapter.py` (396 行)
  - [x] A7.1：按职责切分子模块（≤ 350 行）
  - [x] A7.2：创建 `browser/execution_adapter/__init__.py` + `__all__` + 硬编码 logger
  - [x] A7.3：原 `execution_adapter.py` 改为 thin shim 或删除
  - [x] A7.4：运行相关测试（`test_*execution_adapter*`、`test_browser*`）验证无回归
- [x] Task A8：拆分 `brain_alpha_ops/agent_tool_registry.py` (419 行)
  - [x] A8.1：按职责切分子模块（≤ 350 行），如 `_types.py` / `_loaders.py` / `_registry.py`
  - [x] A8.2：创建 `agent_tool_registry/__init__.py` + `__all__` + 硬编码 logger
  - [x] A8.3：原 `agent_tool_registry.py` 改为 thin shim 或删除（注意：作为顶层模块，需保持导入路径 `from brain_alpha_ops.agent_tool_registry import ...` 正常）
  - [x] A8.4：运行相关测试（`test_*agent_tool*`、`test_agent_tools*`）验证无回归

## 工作流 B：拆分 8 个 research/pipeline 超限文件

- [x] Task B1：拆分 `brain_alpha_ops/research/pipeline_snapshot.py` (435 行)
  - [x] B1.1：读取全文，按职责切分子模块（≤ 350 行）
  - [x] B1.2：创建 `research/pipeline_snapshot/__init__.py` + `__all__` + 硬编码 logger
  - [x] B1.3：原 `pipeline_snapshot.py` 改为 thin shim 或删除
  - [x] B1.4：运行相关测试（`test_*pipeline_snapshot*`、`test_research_pipeline*`）验证无回归
- [x] Task B2：拆分 `brain_alpha_ops/research/pipeline_runtime.py` (429 行)
  - [x] B2.1：按职责切分子模块（≤ 350 行）
  - [x] B2.2：创建 `research/pipeline_runtime/__init__.py` + `__all__` + 硬编码 logger
  - [x] B2.3：原 `pipeline_runtime.py` 改为 thin shim 或删除
  - [x] B2.4：运行相关测试（`test_*pipeline_runtime*`、`test_research_pipeline*`）验证无回归
- [x] Task B3：拆分 `brain_alpha_ops/research/pipeline_candidates.py` (419 行)
  - [x] B3.1：按职责切分子模块（≤ 350 行）
  - [x] B3.2：创建 `research/pipeline_candidates/__init__.py` + `__all__` + 硬编码 logger
  - [x] B3.3：原 `pipeline_candidates.py` 改为 thin shim 或删除
  - [x] B3.4：运行相关测试（`test_*pipeline_candidates*`、`test_research_pipeline*`）验证无回归
- [x] Task B4：拆分 `brain_alpha_ops/research/hypothesis_expression_support.py` (416 行)
  - [x] B4.1：按职责切分子模块（≤ 350 行）
  - [x] B4.2：创建 `research/hypothesis_expression_support/__init__.py` + `__all__` + 硬编码 logger
  - [x] B4.3：原 `hypothesis_expression_support.py` 改为 thin shim 或删除
  - [x] B4.4：运行相关测试（`test_*hypothesis_expression*`、`test_research_*`）验证无回归
- [x] Task B5：拆分 `brain_alpha_ops/research/pipeline_backtest_flow.py` (412 行)
  - [x] B5.1：按职责切分子模块（≤ 350 行）
  - [x] B5.2：创建 `research/pipeline_backtest_flow/__init__.py` + `__all__` + 硬编码 logger
  - [x] B5.3：原 `pipeline_backtest_flow.py` 改为 thin shim 或删除
  - [x] B5.4：运行相关测试（`test_*pipeline_backtest*`、`test_research_pipeline*`）验证无回归
- [x] Task B6：拆分 `brain_alpha_ops/research/llm_review.py` (398 行)
  - [x] B6.1：按职责切分子模块（≤ 350 行）
  - [x] B6.2：创建 `research/llm_review/__init__.py` + `__all__` + 硬编码 logger
  - [x] B6.3：原 `llm_review.py` 改为 thin shim 或删除
  - [x] B6.4：运行相关测试（`test_*llm_review*`、`test_research_*`）验证无回归
- [x] Task B7：拆分 `brain_alpha_ops/research/candidate_pool_service_.py` (390 行)
  - [x] B7.1：按职责切分子模块（≤ 350 行），注意文件名末尾下划线为命名约定
  - [x] B7.2：创建 `research/candidate_pool_service_/__init__.py` + `__all__` + 硬编码 logger
  - [x] B7.3：原 `candidate_pool_service_.py` 改为 thin shim 或删除
  - [x] B7.4：运行相关测试（`test_*candidate_pool_service*`、`test_research_*`）验证无回归
- [x] Task B8：拆分 `brain_alpha_ops/research/backtest_flow_service.py` (389 行)
  - [x] B8.1：按职责切分子模块（≤ 350 行）
  - [x] B8.2：创建 `research/backtest_flow_service/__init__.py` + `__all__` + 硬编码 logger
  - [x] B8.3：原 `backtest_flow_service.py` 改为 thin shim 或删除
  - [x] B8.4：运行相关测试（`test_*backtest_flow_service*`、`test_research_*`）验证无回归

## 工作流 C：验证、同步与提交

- [x] Task C1：同步 `BASELINE_LINE_LIMITS`
  - [x] C1.1：从 `scripts/check_module_size.py:BASELINE_LINE_LIMITS` 删除 A1-A8、B1-B8 涉及的 16 个条目
  - [x] C1.2：运行 `python3 scripts/check_module_size.py --json` 确认 16 个文件不再出现在 `findings`，`baseline=16`
- [x] Task C2：全量回归测试
  - [x] C2.1：运行 `python3 -m pytest tests/ --ignore=tests/test_read_jsonl_tail.py --ignore=tests/test_quality_gate.py --ignore=tests/test_official_scoring_system.py -q --tb=short` 确认无新增失败
  - [x] C2.2：验证 16 个拆分子包 `from ... import *` 正常工作
  - [x] C2.3：验证凭据扫描 `python3 -m pytest tests/test_credential_leak_regression.py -q` 全绿
- [x] Task C3：提交并推送到 origin/main
  - [x] C3.1：`git add` 所有修改文件
  - [x] C3.2：`git commit` 使用规范中文提交消息（含 phase13 标识）
  - [x] C3.3：`git push origin main` 推送成功

# Task Dependencies

- Task A1-A8 相互独立，可并行（8 个 web/scoring/ux/browser/agent 拆分无依赖）
- Task B1-B8 相互独立，可并行（8 个 research/pipeline 拆分无依赖）
- Task A* 与 Task B* 可完全并行
- Task C1 依赖 A1-A8、B1-B8（拆分完成才能同步 BASELINE）
- Task C2 依赖 C1、A*、B*
- Task C3 依赖 C2

# 可并行任务

- A1-A8（8 个 web/dispatch/state/scoring/ux/browser/agent 拆分）一次性并行
- B1-B8（8 个 research/pipeline 拆分）一次性并行
- A* / B* 两组可完全并行（共 16 个独立子任务）
