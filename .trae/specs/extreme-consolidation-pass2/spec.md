# 极致精简第二轮 Spec（Extreme Consolidation Pass 2）

## Why

第一轮 `comprehensive-simplification-refactor` 完成了"删死代码 + 修缺陷"的瘦身（已合并约 30 个死文件），但**架构碎片化问题依然严重**：项目共 **1,584 个文件**（1,058 Python + 307 前端 + 101 scripts + 其他），其中 `brain_alpha_ops/` 一个包就拆出 **155 个子目录**，单个简单功能被切到 5-11 个文件。对一个量化选股工具来说，这个文件数严重失真，影响可读性、维护成本和构建速度。

用户明确要求："**继续精简代码，要极致的精简**"。本轮聚焦纯粹的**文件数与目录层级压缩**，不做功能改动、不引入新抽象、不改对外 API。

## What Changes

### 阶段一：合并极小 Python 文件（<50 行）—— 最大头

- 合并 50+ 个 <50 行的 Python 文件到其语义内聚的父模块
- 重点合并：
  - `web/misc/` 顶层 20+ 个 5-15 行的 `web_*.py` thin binding shim → 收敛到 ≤3 个 facade 文件
  - `web/misc/web_runtime_facade/` 7 文件 → 1 个 `web_runtime_facade.py`（≤350 行）
  - `web/misc/web_assistant_snapshots/` 7 文件 → 1 个 `web_assistant_snapshots.py`
  - `web/misc/web_service_namespace/` 4 文件 → 1 个 `web_service_namespace.py`
  - `web/misc/web_facade_bindings/` 5 文件 → 1 个 `web_facade_bindings.py`
  - `web/misc/web_backtest_slots/` 3 文件 → 1 个 `web_backtest_slots.py`
  - `brain_api/official_alphas/_composite.py` (11 行) → 合并到同级 `__init__.py` 或父模块
  - `brain_api/official/_payload.py` (14 行) → 合并到 `__init__.py`
  - `research/local_backtest_config.py` (6 行)、`research/anti_overfit.py` (15 行)、`research/calibration.py` (27 行)、`research/pipeline.py` (28 行) → 合并到对应 `__init__.py` 或父级
  - `agent_tool_errors.py` (11 行)、`job_types.py` (15 行)、`tasks/_constants.py` (13 行) → 合并到最近的内聚模块
- **目标**：删除 50+ 个 <50 行文件，`web/misc/` 文件数 31 → ≤12

### 阶段二：消灭 Mixin 滥用 —— 单类拆 6 文件

- `research/pipeline/` 6 文件（`_class.py` + 5 个 mixin）→ 合并为单文件 `pipeline.py`（若超 350 行则保留 ≤2 个文件，按"主类 + 单独 mixin 包"语义切分）
- `research/pipeline_backtest_flow/` 5 mixin 文件 → ≤2 文件
- `research/pipeline_candidates/` 5 mixin 文件 → ≤2 文件
- `research/pipeline_snapshot/` 4 文件 → 1 文件
- `research/pipeline_runtime/` 8 文件 → ≤2 文件
- `research/iterative_optimizer/` 5 mixin 文件 → ≤2 文件
- `research/convergence/` 5 mixin 文件 → ≤2 文件
- `research/experience/` 4 mixin 文件 → ≤2 文件
- `research/llm_review/` 5 文件 → ≤2 文件
- `research/llm_service/` 6 文件 → ≤2 文件
- `research/scoring/` 6 文件 → ≤3 文件
- `research/repository/` 7 文件 → ≤3 文件
- **目标**：删除 30+ 个 mixin 文件，`research/` 子包文件数 94 → ≤50

### 阶段三：合并 subpackage 内 7-11 文件碎片包

- `scoring/anti_overfit/` 11 文件 → ≤3 文件（`service.py` + `suite.py` + `models.py`；`half_life.py`/`placebo.py`/`regime_stress.py`/`ic_stability.py`/`compliance.py`/`candidate.py`/`utils.py` 合并到对应内聚模块）
- `scoring/official_scoring/` 7 文件 → ≤2 文件
- `scoring/release_score_gate/` 5 文件 → 1 文件
- `compliance/` 10 文件（7 个 `redline_check_*.py`）→ ≤3 文件（按"check 类型"合并为 1-2 个 `checks.py`）
- `web/dispatch/post_routes/` 9 文件 → ≤3 文件
- `web_cloud/snapshot/` 8 文件 → ≤2 文件
- `web_candidates/bindings/` 8 文件 → ≤2 文件
- `ux/` 8 文件 → ≤3 文件
- **目标**：删除 30+ 个碎片文件

### 阶段四：前端碎片收敛

- `src/hooks/useAppState/` 9 文件 → ≤3 文件
- `src/hooks/useJobMonitor/` 8 文件 → ≤3 文件
- `src/helpers/runPayload/` 7 文件 → ≤2 文件
- `src/components/ScoringPanel/` 10 文件 → ≤4 文件
- `src/components/ConfigPanel/` 10 文件 → ≤4 文件
- `src/components/CandidateTableSubComponents/` 7 文件 → ≤3 文件
- `src/components/OfficialOperations/` 29 文件 → ≤10 文件
- `src/components/SnapshotPanel/` 8 文件 → ≤3 文件
- `src/types/` 8 文件 → ≤2 文件
- `src/utils/` 7 文件 → ≤3 文件
- `src/styles/` 7 文件 → ≤2 文件（保留 `theme-tokens.css` 单独）
- **目标**：删除 60+ 个前端碎片文件，`src/` 文件数 265 → ≤160

### 阶段五：Scripts 与 Tests 收敛

- `scripts/` 101 文件 → ≤40 文件：合并同类 check 脚本（如 `check_*.py` 子目录化合并到 `scripts/checks/` 单文件入口）
- `tests/` 206 文件 → 不强行合并（测试隔离原则保留），仅删除重复/已死测试（与 Phase 5.1 协调）
- **目标**：删除 60+ 个 scripts 文件

### 阶段六：顶层 helper 与历史遗留

- 合并 `brain_alpha_ops/` 顶层 47 个文件中可内聚的小文件（如 `agent_*.py` 4 个 → ≤2 个）
- 删除 `web/dispatch/get_routes/_dispatch.py` 中已确认的 dead helpers（若 Task 1.2 中已删则跳过）
- `BrainAlphaOps.spec` hiddenimports 列表与精简后模块结构同步
- **目标**：顶层文件数 47 → ≤35

### 阶段七：回归验证

- `pytest tests/ -q` 通过数 ≥ baseline（2995 passed），无新增 failure
- `npm run typecheck` exit 0
- `npm run build` 成功
- 文件数总账：1,584 → ≤900（≥43% 削减）
- Python 子目录数：155 → ≤90

## Impact

- **架构层面**：删除约 200+ 个碎片文件，子目录数 155 → ≤90，单文件平均行数从 ~140 → ~280（更接近内聚阈值），消除"打开 5 个文件才能读完 1 个类"的反模式
- **代码层面**：所有合并为纯重组，无逻辑变更，无对外 API 变更；保留 `__init__.py` re-export 以维持导入路径稳定
- **风险**：
  - 单文件超 350 行风险 → 严控合并后行数，超限时按"语义内聚"二次切分（非按 mixin 切）
  - 测试 import 路径风险 → `__init__.py` re-export 保底，测试不改
  - 隐藏循环依赖风险 → 合并前先 grep 验证引用图
- **不做的事**：
  - 不改任何函数/类的实现逻辑
  - 不引入新抽象/新依赖
  - 不改对外 API/CLI/路由
  - 不删除任何"功能上"的代码（仅合并与重组）

## ADDED Requirements

### Requirement: 极致文件数压缩

系统 SHALL 在不改变对外行为的前提下，将项目文件数从 1,584 削减至 ≤900，`brain_alpha_ops/` 子目录数从 155 削减至 ≤90。

#### Scenario: 合并后无功能回归
- **WHEN** 子智能体完成阶段一至阶段六的全部合并
- **THEN** `pytest tests/ -q` 通过数 ≥ 2995，无新增 failure；`npm run typecheck` exit 0；`npm run build` 成功

#### Scenario: 合并后导入路径稳定
- **WHEN** 任意下游消费者（含测试）使用原有 import 路径
- **THEN** 通过 `__init__.py` re-export 仍可成功导入，无 ImportError

#### Scenario: 单文件不超阈值
- **WHEN** 合并产生新文件
- **THEN** Python 文件 ≤ 400 行，前端文件 ≤ 500 行；超限时按"语义内聚"二次切分而非行数切分

## MODIFIED Requirements

### Requirement: 模块组织原则

模块组织 SHALL 优先**语义内聚**而非"每方法一文件"或"每 mixin 一文件"。单文件可包含多个紧密相关的类/函数；仅当文件超过阈值或语义明显分叉时才拆分。

## REMOVED Requirements

### Requirement: Mixin 强制单文件拆分
**Reason**: 原"每 mixin 一文件"模式导致单类拆出 5-6 个文件，可读性下降，违反内聚原则
**Migration**: 合并到主类文件或 ≤2 个内聚文件；保留 mixin 机制本身（仅是物理文件合并）
