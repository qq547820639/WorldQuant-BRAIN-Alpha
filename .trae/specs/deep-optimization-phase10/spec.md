# BRAIN Alpha Ops 深挖优化 Phase 10 - 规格

## Why

Phase 9 完成后（commit `47ed3b8`），代码库中仍有 **20 个 Python 文件超过 500 行**，违反项目在 Phase 6/7/8/9 中反复确立的"后端单文件 ≤500 行"规范。这些文件分布在 `research/`（12个）、`brain_api/`（3个）、`web/`（3个）、`scoring/`（1个）、`web_candidates/`（1个）和根目录（1个），持续阻碍可维护性目标。本轮 Phase 10 将这些遗留文件全部拆分到 ≤350 行的子模块，彻底完成 Python 后端的大型文件治理。

## What Changes

- 拆分 20 个 >500 行的 Python 文件为 re-export 子包（沿用 Phase 6-9 验证 8+ 次的模式）
- 修复 Phase 9 遗留：`brain_api/official/_api.py`（620 行，超出 350 行子模块上限）二次拆分
- 保持 100% 向后兼容：原 `.py` 文件改为 re-export shim 或被同名子包目录替代
- 保持 monkeypatch 兼容：`__init__.py` 显式重导出被测试引用的私有 `_underscore` 符号
- 保持 logger 身份：子模块硬编码 `logging.getLogger("original.module.name")`
- 完成后直接提交并推送到 origin/main

**BREAKING**: 无破坏性变更 — 所有现有导入路径保持有效。

## Impact

- **Affected specs**: `deep-optimization-final`（NFR-3 可维护性：工具模块 ≤500 行）、`deep-optimization-phase6/7`（向后兼容约束）
- **Affected code**:
  - `brain_alpha_ops/research/` — 12 个文件（observability, local_backtest/expression_evaluator, llm_service, simulation_scheduler, expression_sqlite_index, experience, cross_review_pipeline, expression_ast, pipeline_official_context, memory, iterative_optimizer, convergence）
  - `brain_alpha_ops/brain_api/` — 3 个文件（official/_api.py 二次拆分, official_helpers.py, official_alphas.py）
  - `brain_alpha_ops/web/` — 3 个文件（misc/web_service_namespace.py, config/web_config.py）
  - `brain_alpha_ops/scoring/official_scoring.py` — 1 个文件
  - `brain_alpha_ops/web_candidates/generation.py` — 1 个文件
  - `brain_alpha_ops/e2e_report.py` — 1 个文件（根目录）
- **Affected tests**: 约 15+ 个测试文件直接导入这些模块的符号，需确保 re-export 覆盖

## ADDED Requirements

### Requirement: 后端单文件行数治理

The system SHALL 保证所有 Python 后端源文件（不含 `__pycache__`、生成的子模块 `__init__.py` re-export shim）行数 ≤ 500 行，子模块文件 ≤ 350 行。

#### Scenario: 所有后端文件符合行数规范
- **WHEN** 运行 `find brain_alpha_ops -name "*.py" -not -path "*/__pycache__/*" | xargs wc -l | sort -rn | awk '$1 > 500'`
- **THEN** 输出为空（0 个文件超过 500 行）

#### Scenario: 子模块行数符合规范
- **WHEN** 检查新创建的子包内 `_*.py` 子模块文件
- **THEN** 每个子模块文件 ≤ 350 行（允许个别无法再拆分的单函数类文件例外，需在 tasks.md 标注）

### Requirement: 向后兼容性

The system SHALL 保持所有现有导入路径 100% 有效，包括 `from module import Class`、`from module import _private_symbol`、`module.attribute` 访问。

#### Scenario: 公共 API 导入保持有效
- **WHEN** 执行 `from brain_alpha_ops.research.llm_service import LLMService`
- **THEN** 导入成功，`LLMService` 可正常使用

#### Scenario: 私有符号 monkeypatch 兼容
- **WHEN** 测试执行 `monkeypatch.setattr(module, "_private_func", mock)`
- **THEN** 子模块内代码通过 `_pkg()` 模式访问到 patch 后的版本

#### Scenario: 模块级标准库属性访问兼容
- **WHEN** 测试执行 `monkeypatch.setattr(module.time, "monotonic", mock)`
- **THEN** `__init__.py` 已重导入 `time` 模块，属性访问正常

### Requirement: Phase 9 遗留修复

The system SHALL 修复 Phase 9 创建的 `brain_api/official/_api.py`（620 行）超规问题，将其进一步拆分到 ≤350 行。

#### Scenario: official 子包内所有子模块合规
- **WHEN** 检查 `brain_alpha_ops/brain_api/official/` 目录下所有 `_*.py` 文件
- **THEN** 每个文件 ≤ 350 行

## MODIFIED Requirements

### Requirement: 大型模块拆分（继承自 deep-optimization-final FR-4）

扩展拆分范围至剩余 20 个 >500 行后端文件，使用 Phase 6-9 验证的 re-export 子包模式：
1. 创建同名子包目录
2. 按功能拆分为 3-5 个子模块（≤350 行/文件）
3. `__init__.py` 统一导出所有公共 API + 被外部引用的私有符号
4. 原 `.py` 文件删除（包目录优先级覆盖同名 .py）
5. 验证 `from module import *` 正常工作

## REMOVED Requirements

无删除项。
