# BRAIN Alpha Ops 深挖优化 Phase 6 - 规格文档

## Why
前五轮深挖优化已完成模块拆分、构建优化、UX组件库等工作，但代码扫描发现仍有 9 个前端文件超过 400 行、多个 Python 后端文件超过 800 行，违反了项目的文件大小规范。这些大文件影响可维护性、增加 code review 难度，且容易产生合并冲突。

## What Changes
- 拆分 9 个超过 400 行的前端文件（useJobMonitor 465行、ScoringPanel 464行、ConfigPanel/utils 462行、SnapshotPanel 461行、CandidateTableSubComponents 455行、CandidateTable 444行、runPayload 443行、StateCards 430行、useAppState 408行）
- 拆分 3 个超过 900 行的 Python 后端文件（web_candidates/simulation.py 1031行、web/dispatch/web_routes.py 961行、web_cloud/snapshot.py 905行）
- 所有拆分保持完全向后兼容（原文件保留为 re-export 入口）
- 拆分后每个文件控制在 400 行以内（前端）/ 350 行以内（后端）

## Impact
- Affected specs: deep-optimization-final (延续未完成的 checklist 项)
- Affected code: 前端 src/hooks/、src/components/、src/helpers/；后端 brain_alpha_ops/web_candidates/、brain_alpha_ops/web/dispatch/、brain_alpha_ops/web_cloud/

## ADDED Requirements

### Requirement: 前端文件大小合规
所有前端 .ts/.tsx 文件 SHALL 不超过 400 行。超过此限制的文件 SHALL 按功能拆分为子模块，原文件保留为 re-export 入口以保持向后兼容。

#### Scenario: 文件超过 400 行
- **WHEN** 前端源文件超过 400 行
- **THEN** 按功能职责拆分为多个子模块，每个子模块 ≤ 400 行
- **AND** 原文件改为从子模块重新导出所有内容
- **AND** 所有现有导入路径继续正常工作

### Requirement: Python 后端文件大小合规
所有 Python 后端 .py 文件 SHALL 不超过 500 行。超过此限制的文件 SHALL 按功能拆分为子模块。

#### Scenario: 文件超过 500 行
- **WHEN** Python 后端文件超过 500 行
- **THEN** 按功能职责拆分为子包
- **AND** 原文件保留为 re-export 入口
- **AND** 所有现有导入和测试继续通过

### Requirement: 向后兼容
所有拆分操作 SHALL 保持 100% 向后兼容。

#### Scenario: 拆分后导入验证
- **WHEN** 任何现有代码执行 `from module import symbol`
- **THEN** 导入正常工作，行为与拆分前完全一致
- **AND** 所有现有测试通过（无新增失败）
