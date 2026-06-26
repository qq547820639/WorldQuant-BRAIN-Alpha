# 深度优化 Phase 13：Grandfathered 超限文件拆分（第二轮）Spec

## Why

`deep-optimization-phase12` 已将 20 个最高行数的 grandfathered 文件（≥ 462 行）
拆分为 re-export 子包，并将 `BASELINE_LINE_LIMITS` 从 51 条缩减至 32 条。当前
`scripts/check_module_size.py --json` 仍报告 `baseline=32`，其中 16 个文件行数
≥ 382 行（最高 448 行），显著超出项目硬约束（Python 后端 ≤ 350 行）。

本阶段（Phase 13）继续推进 grandfathered 文件收敛，目标是将这 16 个文件拆分为
re-export 子包，使 `BASELINE_LINE_LIMITS` 进一步缩减至 16 条，向 "零超限文件"
的最终收敛目标再进一步。

Phase 12 收尾时仓库已进入 "零 open 缺陷" 状态，本阶段不涉及缺陷修复，聚焦于
纯结构性重构。

## What Changes

- **拆分 8 个 web/dispatch/state/scoring/ux 超限文件** 为 re-export 子包 + thin shim：
  - `web/dispatch/web_dispatch_context.py` (448)
  - `web/state/web_state_contract.py` (436)
  - `web/submissions/web_submission_safety.py` (407)
  - `web/dispatch/web_http_handler.py` (382)
  - `scoring/release_score_gate.py` (396)
  - `ux/errors.py` (390)
  - `browser/execution_adapter.py` (396)
  - `agent_tool_registry.py` (419)
- **拆分 8 个 research/pipeline 超限文件** 为 re-export 子包 + thin shim：
  - `research/pipeline_snapshot.py` (435)
  - `research/pipeline_runtime.py` (429)
  - `research/pipeline_candidates.py` (419)
  - `research/hypothesis_expression_support.py` (416)
  - `research/pipeline_backtest_flow.py` (412)
  - `research/llm_review.py` (398)
  - `research/candidate_pool_service_.py` (390)
  - `research/backtest_flow_service.py` (389)
- **同步 `BASELINE_LINE_LIMITS`**：移除已拆分文件对应条目，使其受 `DEFAULT_LINE_LIMIT=350` 约束。
- **全量回归测试**：确保拆分无回归（pytest + vitest + check_module_size）。
- **提交并推送** `origin/main`（遵循用户工作流约定）。

## Impact

- **Affected specs**：`deep-optimization-phase12`（同一收敛序列的延续）；
  `overhaul-alpha-production-quality` §10 建议的后续工作。
- **Affected code**：
  - `brain_alpha_ops/web/dispatch/`、`brain_alpha_ops/web/state/`、
    `brain_alpha_ops/web/submissions/`、`brain_alpha_ops/scoring/`、
    `brain_alpha_ops/ux/`、`brain_alpha_ops/browser/`、
    `brain_alpha_ops/agent_tool_registry.py` 顶层
  - `brain_alpha_ops/research/pipeline_*.py`、`hypothesis_expression_support.py`、
    `llm_review.py`、`candidate_pool_service_.py`、`backtest_flow_service.py`
  - `scripts/check_module_size.py:BASELINE_LINE_LIMITS`
  - 相关测试文件（`tests/test_*pipeline*`、`test_*web_dispatch*`、`test_*web_state*`、
    `test_*submission_safety*`、`test_*release_score_gate*`、`test_*errors*`、
    `test_*execution_adapter*`、`test_*agent_tool_registry*`、`test_*llm_review*`、
    `test_*candidate_pool_service*`、`test_*backtest_flow_service*`、
    `test_*hypothesis_expression*`）
- **Risk**：纯结构性重构，行为不变。Monkeypatch 兼容性是主要风险点，需沿用
  Phase 12 的 `_pkg()` 模式 + 在 `__init__.py` 中显式 re-export 测试中 monkeypatch
  的私有符号。

## ADDED Requirements

### Requirement: Re-export 子包拆分（16 个文件）

每个被拆分的文件 SHALL 转换为同名子包目录，包含多个职责分明的子模块（每个
≤ 350 行），并通过 `__init__.py` 导出公共 API + 已测试私有符号 + `__all__`。

#### Scenario: 拆分后行为不变

- **WHEN** 调用方执行 `from brain_alpha_ops.web.dispatch.web_dispatch_context import *`
- **THEN** 所有原有公共符号均可访问
- **AND** 原有测试套件无新增失败

#### Scenario: 子模块行数合规

- **WHEN** 运行 `python3 scripts/check_module_size.py --json`
- **THEN** 拆分后的 16 个文件不再出现在 `findings` 中
- **AND** 所有新子模块行数 ≤ 350

#### Scenario: Monkeypatch 兼容性

- **WHEN** 测试通过 `monkeypatch.setattr(module, "_private_func", ...)` 替换私有函数
- **THEN** 被测代码通过包命名空间观察到替换
- **AND** 相关测试无新增失败

### Requirement: Logger 名硬编码

被拆分子包中的 logger 名 SHALL 硬编码为原模块名（如
`logging.getLogger("brain_alpha_ops.research.pipeline_snapshot")`），不使用
`__name__`，以保留日志前缀。

#### Scenario: 日志前缀稳定

- **WHEN** 拆分后子模块记录日志
- **THEN** 日志前缀仍为原模块名
- **AND** 不出现 `<subpackage>._submodule` 形式的前缀

### Requirement: Thin shim 保留 CLI 入口

被拆分文件如被其他脚本以 `python <path>.py` 形式调用，原 `.py` 文件 SHALL
保留为 thin shim（≤ 40 行），引导 `sys.path` 后委托到 `from <package> import main`。

#### Scenario: 直接 CLI 调用

- **WHEN** 执行 `python brain_alpha_ops/<some_split_module>.py`
- **AND** 该模块有 `main()` 函数
- **THEN** thin shim 委托执行成功
- **AND** 退出码与拆分前一致

## MODIFIED Requirements

### Requirement: `BASELINE_LINE_LIMITS` 同步

`scripts/check_module_size.py:BASELINE_LINE_LIMITS` SHALL 移除本阶段拆分的
16 个文件条目，从 32 条缩减至 16 条。

#### Scenario: 模块大小审计通过

- **WHEN** 运行 `python3 scripts/check_module_size.py --json`
- **THEN** 输出 `ok=true findings=0 baseline=16 checked=<N>`
- **AND** 16 个新拆分子包受 `DEFAULT_LINE_LIMIT=350` 约束

## REMOVED Requirements

无。本阶段为纯结构性重构，不移除任何既有功能。
