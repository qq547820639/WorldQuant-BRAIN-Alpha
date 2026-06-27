# 深度优化 Phase 14：Grandfathered 超限文件拆分（最终收敛）Spec

## Why

`deep-optimization-phase13` 将 `BASELINE_LINE_LIMITS` 从 32 条缩减至 16 条。
当前仅剩 16 个 grandfathered 文件（行数 351-382），仅轻微超出 350 行硬约束
（最大超出 32 行）。本阶段作为 grandfathered 收敛的**最终阶段**，目标是将
这 16 个文件全部拆分，使 `BASELINE_LINE_LIMITS` 归零，仓库进入
"零 grandfathered 文件" 的完全合规状态。

由于这些文件仅轻微超限，拆分策略可灵活选择：
- 内容职责分明且可独立分组的 → re-export 子包（沿用 Phase 12/13 模式）
- 仅差几行的 → 抽取少量 helper 到同级 `_helpers.py` 模块，原文件保留为主入口

## What Changes

- **拆分 16 个 grandfathered 文件**（按行数降序）使其全部 ≤ 350 行：
  - `runtime_constants.py` (382)
  - `browser/brain_ui_runner.py` (381)
  - `types.py` (380)
  - `scripts/check_defect_analysis_report.py` (378)
  - `web/handlers/phase.py` (375)
  - `config_schema.py` (374)
  - `research/_observability_helpers.py` (372)
  - `config_domain_validation.py` (371)
  - `web/business/web_async_jobs.py` (364)
  - `research/theme_engine/_engine.py` (363)
  - `web/security/web_security.py` (362)
  - `research/generator/_helpers.py` (355)
  - `research/runtime_service.py` (355)
  - `research/market_data_cache.py` (354)
  - `web/business/web_jobs.py` (352)
  - `ux/user_messages.py` (351)
- **同步 `BASELINE_LINE_LIMITS`**：清空全部 16 个条目，使 `baseline=0`。
- **全量回归测试**：确保拆分无回归。
- **提交并推送** `origin/main`。

## Impact

- **Affected specs**：`deep-optimization-phase12/13`（同一收敛序列的最终阶段）。
- **Affected code**：`brain_alpha_ops/` 顶层 4 个文件 + `browser/`、`web/`、
  `research/`、`ux/`、`scripts/` 子目录共 16 个文件；`scripts/check_module_size.py`。
- **Risk**：纯结构性重构。因文件仅轻微超限，风险低于 Phase 12/13 的大文件拆分。
  Monkeypatch 兼容性仍需关注（沿用 `_pkg()` 模式 + `__init__.py` 显式 re-export）。

## ADDED Requirements

### Requirement: 16 个文件全部 ≤ 350 行

每个 grandfathered 文件 SHALL 通过拆分或抽取使其行数 ≤ 350 行。拆分模式可选：
- **re-export 子包**（文件 → 同名目录 + `__init__.py`，适用于职责可分组的文件）
- **helper 抽取**（抽取少量函数/常量到同级 `_helpers.py`，原文件保留为主入口，
  适用于仅差几行的文件）

#### Scenario: 拆分后行为不变

- **WHEN** 调用方执行 `from <original_module> import *`
- **THEN** 所有原有公共符号均可访问
- **AND** 原有测试套件无新增失败

#### Scenario: 行数合规

- **WHEN** 运行 `python3 scripts/check_module_size.py --json`
- **THEN** `baseline_limits` 为空字典
- **AND** `findings=[]`、`ok=true`

#### Scenario: Monkeypatch 兼容性

- **WHEN** 测试通过 `monkeypatch.setattr(module, "_private_func", ...)` 替换私有函数
- **THEN** 被测代码观察到替换
- **AND** 相关测试无新增失败

### Requirement: Logger 名硬编码（如适用）

被拆分子包中的 logger 名 SHALL 硬编码为原模块名，不使用 `__name__`。

## MODIFIED Requirements

### Requirement: `BASELINE_LINE_LIMITS` 清零

`scripts/check_module_size.py:BASELINE_LINE_LIMITS` SHALL 清空为 `{}`。

#### Scenario: 模块大小审计通过

- **WHEN** 运行 `python3 scripts/check_module_size.py --json`
- **THEN** 输出 `ok=true findings=[] baseline_limits={}`

## REMOVED Requirements

无。纯结构性重构。
