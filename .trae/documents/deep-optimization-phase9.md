# 深挖优化 Phase 9 - 实施计划

## Summary

Phase 8 完成了 11 个后端大文件拆分（web_candidates/、data/、web_cloud/、ux/、根目录）+ 前端配置优化（manualChunks、tsconfig noUnusedLocals、孤儿测试 include）。但仍遗留 **29 个 Python 文件 > 500 行**，其中 12 个文件 ≥ 636 行，集中在 `research/`（8个）、`brain_api/`（2个）、`web/business/`（1个）、`web/dispatch/`（1个）。

本轮 Phase 9 聚焦 **拆分 top 12 最大文件**（≥636 行），按已验证 7+ 次的 re-export 子包模式执行，保持 100% 向后兼容，完成后直接推送到 origin/main。

剩余 17 个文件（506-619 行）作为 Phase 10 候选，不在本轮范围。

## Current State Analysis

### 已完成（Phase 5-8）
- 前端：所有 .ts/.tsx 文件 ≤ 400 行
- 后端：web_candidates/、data/、web_cloud/sync_job、ux/guided_pipeline、tasks/、production_diagnostics/、agent_tools/、research/(6个)、web/misc/(2个)、web_cloud/snapshot 已拆分
- 前端 tsconfig: noUnusedLocals + noUnusedParameters 已启用
- vite manualChunks 已细化（react-vendor / tanstack-vendor / vendor）
- 孤儿测试 include 已修复

### 未完成（本轮目标）
12 个 ≥ 636 行的 Python 文件需要拆分：

| # | 文件 | 行数 | 模块 | 测试直接导入 |
|---|------|------|------|------------|
| 1 | `brain_alpha_ops/research/alpha_checks.py` | 778 | research | 是（verify_quality_fixes.py）|
| 2 | `brain_alpha_ops/web/business/web_business.py` | 744 | web/business | 否（间接）|
| 3 | `brain_alpha_ops/research/theme_engine.py` | 739 | research | 是（test_dynamic_research_components.py 等）|
| 4 | `brain_alpha_ops/web/dispatch/web_get_routes.py` | 716 | web/dispatch | 否（间接）|
| 5 | `brain_alpha_ops/research/context.py` | 709 | research | 是（test_canonical_alignment.py）|
| 6 | `brain_alpha_ops/research/evolution.py` | 701 | research | 是（test_evolution_engine.py）|
| 7 | `brain_alpha_ops/research/generator.py` | 701 | research | 是（test_generation.py 等）|
| 8 | `brain_alpha_ops/research/decoupled_pipeline.py` | 699 | research | 否 |
| 9 | `brain_alpha_ops/brain_api/official_context.py` | 688 | brain_api | 是（test_official_adapter.py）|
| 10 | `brain_alpha_ops/brain_api/official.py` | 671 | brain_api | 是（test_brain_api_official_validation.py 等）|
| 11 | `brain_alpha_ops/research/validated_generator.py` | 650 | research | 是（test_generation.py）|
| 12 | `brain_alpha_ops/research/knowledge_base.py` | 636 | research | 是（test_knowledge_base.py 等）|

合计约 8433 行需要拆分到 ≤350 行的子模块。

## Proposed Changes

### Task 1: 拆分 12 个 Python 后端大文件

按模块分组并行执行，使用 Phase 6/7/8 验证过的 re-export 子包模式。

#### 1a. research/ 模块（8 个文件）

**`research/alpha_checks.py` (778行) → `alpha_checks/` 子包**
- 已读取结构：`CheckResult`/`CheckReport` dataclass + `AlphaCheck`/`AlphaCheckRegistry` 类 + 20+ 检查函数
- 拆分方案：
  - `_types.py` (~80行)：`CheckResult`、`CheckReport` dataclass
  - `_registry.py` (~150行)：`AlphaCheck`、`AlphaCheckRegistry` 类
  - `_checks_basic.py` (~200行)：基础检查函数（sharpe/returns/drawdown/turnover 等）
  - `_checks_advanced.py` (~200行)：高级检查函数（self_correlation/sub_universe/margin 等）
  - `_checks_registry_builder.py` (~100行)：`build_default_checks` 工厂函数
  - `__init__.py`：re-export 全部公共 API + `_check_self_correlation`（被测试导入）
  - 原 `alpha_checks.py` 改为 re-export shim

**`research/theme_engine.py` (739行) → `theme_engine/` 子包**
- 已读取结构：`ThemeTemplate` dataclass + `TEMPLATE_SKELETONS` 字典（52+ 模板）+ `ThemeEngine` 类
- 拆分方案：
  - `_template.py` (~60行)：`ThemeTemplate` dataclass
  - `_skeletons.py` (~250行)：`TEMPLATE_SKELETONS` 字典（52+ 模板按类别）
  - `_engine.py` (~300行)：`ThemeEngine` 类
  - `_helpers.py` (~80行)：辅助函数
  - `__init__.py`：re-export

**`research/context.py` (709行) → `context/` 子包**
- 结构：`build_assistant_context_pack` + 多个 `_xxx_context` 辅助函数
- 拆分方案：
  - `_pack.py` (~200行)：`build_assistant_context_pack` 主函数
  - `_sections.py` (~250行)：各 `_xxx_context` 子构建器（run/local/cloud/memory）
  - `_helpers.py` (~150行)：通用辅助函数
  - `_compliance.py` (~100行)：`_compliance_context`（被测试导入）
  - `__init__.py`：re-export

**`research/evolution.py` (701行) → `evolution/` 子包**
- 结构：`MutationResult` dataclass + `MutationEngine`/`CrossoverEngine`/`MetaEvolutionSelector` 类
- 拆分方案：
  - `_types.py` (~50行)：`MutationResult` dataclass
  - `_mutation.py` (~250行)：`MutationEngine` 类（8 种变异策略）
  - `_crossover.py` (~150行)：`CrossoverEngine` 类
  - `_meta.py` (~200行)：`MetaEvolutionSelector` 类
  - `__init__.py`：re-export

**`research/generator.py` (701行) → `generator/` 子包**
- 结构：`CandidateGenerator` 类 + 辅助函数
- 拆分方案：
  - `_generator.py` (~350行)：`CandidateGenerator` 类核心
  - `_helpers.py` (~200行)：辅助函数
  - `_filters.py` (~150行)：预过滤函数
  - `__init__.py`：re-export

**`research/decoupled_pipeline.py` (699行) → `decoupled_pipeline/` 子包**
- 结构：`WorkerState` enum + `SharedState` dataclass + `DecoupledPipeline` 类 + 4 个 worker
- 拆分方案：
  - `_state.py` (~100行)：`WorkerState`、`SharedState` dataclass
  - `_workers.py` (~300行)：4 个 worker 函数
  - `_pipeline.py` (~250行)：`DecoupledPipeline` 类
  - `__init__.py`：re-export

**`research/validated_generator.py` (650行) → `validated_generator/` 子包**
- 结构：`OPERATOR_SIGNATURES` 字典 + `prefilter_quality`/`_passes_diversity`/`_tokenize` 函数
- 拆分方案：
  - `_signatures.py` (~150行)：`OPERATOR_SIGNATURES` 字典
  - `_prefilter.py` (~250行)：`prefilter_quality`、`_passes_diversity` 函数
  - `_validate.py` (~200行)：验证函数
  - `__init__.py`：re-export `_passes_diversity`、`_tokenize`、`prefilter_quality`

**`research/knowledge_base.py` (636行) → `knowledge_base/` 子包**
- 结构：`KnowledgeRecord`/`ResearchKnowledgeBase`/`KnowledgeEntry`/`StructuredKnowledgeBase` 类 + 常量
- 拆分方案：
  - `_types.py` (~100行)：`KnowledgeRecord`、`KnowledgeEntry` dataclass + 常量
  - `_base.py` (~200行)：`ResearchKnowledgeBase` 类
  - `_structured.py` (~250行)：`StructuredKnowledgeBase` 类
  - `__init__.py`：re-export

#### 1b. brain_api/ 模块（2 个文件）

**`brain_api/official_context.py` (688行) → `official_context/` 子包**
- 结构：`OfficialContextDataMixin` mixin 类（分页获取字段/算子/数据集）
- 拆分方案（mixin 拆分模式）：
  - `_fields_mixin.py` (~200行)：字段获取方法 mixin
  - `_operators_mixin.py` (~200行)：算子获取方法 mixin
  - `_datasets_mixin.py` (~150行)：数据集获取方法 mixin
  - `_composite.py` (~100行)：`OfficialContextDataMixin` 组合类（多继承）
  - `__init__.py`：re-export `OfficialContextDataMixin`

**`brain_api/official.py` (671行) → `official/` 子包**
- 结构：`OfficialBrainAPI` 类组合多个 mixin + `build_simulation_payload`/`normalize_metrics` 函数
- 拆分方案：
  - `_payload.py` (~200行)：`build_simulation_payload`、`normalize_metrics` 函数
  - `_api.py` (~350行)：`OfficialBrainAPI` 主类
  - `_helpers.py` (~100行)：辅助函数
  - `__init__.py`：re-export `OfficialBrainAPI`、`build_simulation_payload`、`normalize_metrics`

#### 1c. web/ 模块（2 个文件）

**`web/business/web_business.py` (744行) → `web_business/` 子包**
- 结构：模块级变量 + `inject_dependencies` 函数 + 多个 `_real_*` 处理器函数
- 拆分方案：
  - `_injection.py` (~100行)：`inject_dependencies` 函数 + 模块级变量
  - `_handlers_alpha.py` (~250行)：Alpha 相关 `_real_*` 处理器
  - `_handlers_simulation.py` (~200行)：模拟相关处理器
  - `_handlers_misc.py` (~150行)：其他处理器
  - `__init__.py`：re-export

**`web/dispatch/web_get_routes.py` (716行) → `web_get_routes/` 子包**
- 结构：36 个 `_get_*` 处理函数 + 辅助工具函数
- 拆分方案：
  - `_helpers.py` (~100行)：辅助工具函数
  - `_routes_alpha.py` (~250行)：Alpha 相关 GET 路由
  - `_routes_simulation.py` (~200行)：模拟相关 GET 路由
  - `_routes_misc.py` (~150行)：其他 GET 路由
  - `__init__.py`：re-export 全部 `_get_*` 函数

### Task 2: 测试文件路径修复

部分测试通过文件路径读取原 `.py` 文件（如 `test_web_sync_payload.py`、`test_review_gap_closure_tracker.py` 在 Phase 8 已修复）。本轮需检查并修复类似情况：

- 检查 `tests/test_canonical_alignment.py` 是否通过路径读取 `context.py` → 如是，更新为读取 `context/` 目录
- 检查 `tests/test_official_adapter.py` 是否通过路径读取 `official_context.py`/`official.py` → 如是，更新
- 检查 `tests/test_brain_api_official_validation.py` 同上
- 检查 `tests/test_knowledge_base.py` 同上

### Task 3: 验证与提交

- 验证所有 12 个拆分模块 `from brain_alpha_ops.xxx import *` 正常工作
- 验证 `git diff --stat` 显示原文件被替换为子包目录
- 运行 Python 测试套件：`python3 -m pytest tests/ -x --ignore=tests/test_read_jsonl_tail.py -q`
- 确认无新增失败（4 个预存失败：TestReadJSONLTail + submit_readiness contract 保持不变）
- 提交并推送到 origin/main

## Assumptions & Decisions

1. **向后兼容优先**：所有拆分保持 100% 向后兼容，原 `.py` 文件改为 re-export shim（≤100行），保留所有公共 API + 被测试引用的私有 `_underscore` 符号
2. **Python 包优先规则**：同名 `.py` 文件和 `/` 目录不能共存，包目录优先 — 删除原 `.py` 文件，`__init__.py` 作为 re-export 入口
3. **Monkeypatch 兼容**：测试通过 `monkeypatch.setattr(module, "attr", ...)` 修改模块属性 — `__init__.py` 显式 re-export 所有被 patch 的私有符号；子模块使用 `sys.modules["brain_alpha_ops.original.module.name"]` 访问包级属性（`_pkg()` 模式）
4. **Logger 名称保持**：子模块使用硬编码 `logging.getLogger("brain_alpha_ops.original.module.name")` 保持 logger 身份，确保测试 caplog 过滤正常
5. **Mixin 拆分模式**：大类（如 `OfficialContextDataMixin`）拆分为多个小 mixin，通过多继承在 `_composite.py` 中组合，保持对外接口不变
6. **本轮不处理 17 个 506-619 行文件**：留给 Phase 10，避免单轮过大
7. **前端无新增工作**：前端文件已全部 ≤ 400 行，本轮聚焦后端
8. **Node.js 不可用**：环境无 node/npx，前端无需验证；Python 3.9 可用运行 pytest

## Verification Steps

1. **文件大小验证**：
   ```bash
   find brain_alpha_ops -name "*.py" -not -path "*/__pycache__/*" | xargs wc -l | sort -rn | awk '$1 > 500'
   ```
   预期：12 个目标文件不再出现（剩余 17 个 506-619 行文件为 Phase 10 候选）

2. **导入验证**（每个拆分模块）：
   ```bash
   python3 -c "from brain_alpha_ops.research.alpha_checks import *; print('OK')"
   python3 -c "from brain_alpha_ops.research.theme_engine import *; print('OK')"
   # ... 12 个模块逐一验证
   ```

3. **测试套件**：
   ```bash
   python3 -m pytest tests/ -x --ignore=tests/test_read_jsonl_tail.py -q
   ```
   预期：无新增失败（保持 91 通过 + 4 预存失败）

4. **Git 状态**：
   ```bash
   git status --short
   git diff --stat HEAD~1
   ```
   预期：12 个原 .py 文件被删除，每个对应一个新子包目录（含 __init__.py + 3-5 个 _module.py）

5. **推送**：
   ```bash
   git push origin main
   ```
   预期：推送成功

## Implementation Order

1. **批次 A（并行）**：research/ 8 个文件拆分（可启动 2-3 个并行 sub-agent）
2. **批次 B（并行）**：brain_api/ 2 个文件 + web/ 2 个文件拆分（1-2 个 sub-agent）
3. **批次 C**：测试文件路径修复 + 导入验证
4. **批次 D**：运行测试套件 + 提交推送

## File List (12 target files)

**删除（转为子包）**：
- `brain_alpha_ops/research/alpha_checks.py`
- `brain_alpha_ops/research/theme_engine.py`
- `brain_alpha_ops/research/context.py`
- `brain_alpha_ops/research/evolution.py`
- `brain_alpha_ops/research/generator.py`
- `brain_alpha_ops/research/decoupled_pipeline.py`
- `brain_alpha_ops/research/validated_generator.py`
- `brain_alpha_ops/research/knowledge_base.py`
- `brain_alpha_ops/brain_api/official_context.py`
- `brain_alpha_ops/brain_api/official.py`
- `brain_alpha_ops/web/business/web_business.py`
- `brain_alpha_ops/web/dispatch/web_get_routes.py`

**新增**：每个文件对应一个子包目录，含 `__init__.py`（re-export）+ 3-5 个 `_module.py`（≤350行）

**修改**：可能需要更新 2-4 个测试文件的路径读取（Task 2）

**预计变更**：约 60 个文件（12 删除 + 48 新增），+8000/-7000 行
