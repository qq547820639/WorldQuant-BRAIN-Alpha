# BRAIN Alpha Ops 深挖优化 Phase 7 - 规格文档

## Why
Phase 6 完成了 9 个前端文件和 3 个后端文件的拆分，但扫描发现：(1) `snapshot.py` 虽然创建了子包但原文件未被转为 re-export，仍保留 905 行原始内容；(2) 仍有 20 个 Python 文件超过 500 行，其中 10 个超过 700 行，主要集中在 `research/` 和 `web/` 模块。

## What Changes
- 修复 `snapshot.py` → 转为 re-export（Phase 6 遗留问题）
- 拆分 10 个超过 700 行的 Python 后端文件：
  - `web_cloud/snapshot.py` (905行) - 已有子包，只需转换原文件
  - `research/generation/generator.py` (901行)
  - `research/scoring.py` (883行)
  - `web/candidates/web_check_availability.py` (878行)
  - `research/assistant.py` (838行)
  - `research/alpha_quality.py` (821行)
  - `research/pipeline.py` (817行)
  - `research/hypothesis_library.py` (810行)
  - `web/misc/web_runtime_facade.py` (784行)
  - `web/misc/web_assistant_snapshots.py` (779行)
- 所有拆分保持完全向后兼容（原文件保留为 re-export 入口）
- 拆分后每个子文件 ≤ 350 行

## Impact
- Affected specs: deep-optimization-phase6 (修复 snapshot.py 遗留问题)
- Affected code: brain_alpha_ops/web_cloud/、brain_alpha_ops/research/、brain_alpha_ops/web/candidates/、brain_alpha_ops/web/misc/

## ADDED Requirements

### Requirement: Python 后端文件大小合规
所有 Python 后端 .py 文件 SHALL 不超过 500 行。超过此限制的文件 SHALL 按功能拆分为子包，原文件保留为 re-export 入口。

#### Scenario: 文件超过 500 行
- **WHEN** Python 后端文件超过 500 行
- **THEN** 按功能职责拆分为子包
- **AND** 原文件保留为 re-export 入口
- **AND** 所有现有导入和测试继续通过

### Requirement: snapshot.py 修复
`web_cloud/snapshot.py` SHALL 转为从 `snapshot/` 子包重新导出，删除原始实现内容。

#### Scenario: snapshot.py 修复后
- **WHEN** 执行 `from brain_alpha_ops.web_cloud.snapshot import *`
- **THEN** 所有原有公共 API 正常导入
- **AND** 原文件行数 ≤ 100 行（仅 re-export）

### Requirement: 向后兼容
所有拆分操作 SHALL 保持 100% 向后兼容。

#### Scenario: 拆分后导入验证
- **WHEN** 任何现有代码执行 `from module import symbol`
- **THEN** 导入正常工作，行为与拆分前完全一致
- **AND** 所有现有测试通过（无新增失败）
