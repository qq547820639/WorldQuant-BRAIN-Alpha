# BRAIN Alpha Ops 深挖优化 Phase 11 - 规格

## Why

Phase 6-10 完成了 60+ 个后端大文件拆分，Python 后端单文件 ≤500 行的目标已彻底达成。但文件拆分过程中遗留了若干代码质量问题：1 个 i18n 测试失败阻断 CI、1 处重复导入 bug、9 个子包 `__init__.py` 缺少 `__all__` 封装定义导致命名空间泄漏、部分文件存在可清理的冗余 `# noqa: F401`。本轮聚焦这些遗留缺陷的修复，提升代码库整体质量。

## What Changes

- 修复 i18n 测试失败：`test_runtime_facade_connection_fails_when_profile_returns_auth_error` 断言与实现不一致（英文期望 vs 中文返回）
- 修复 `web_session.py` 重复导入 bug：第 10-11 行完全相同的导入语句
- 为 9 个子包 `__init__.py` 添加显式 `__all__` 定义，约束 `import *` 的导出范围
- 审计并清理 `agent_tools/__init__.py` 中 25 处 `# noqa: F401` 的冗余 re-export
- 合并 `web_session.py` 中 3 条独立的 `from .web_security import X` 语句
- 完成后直接提交并推送到 origin/main

**BREAKING**: 无破坏性变更 — `__all__` 添加仅影响 `import *` 行为，显式导入不受影响。

## Impact

- **Affected specs**: `deep-optimization-final`（AC-1: 前端测试 100% 通过 — 修复后端 i18n 失败间接影响前端契约）、`deep-optimization-phase10`（子包封装完善）
- **Affected code**:
  - `tests/test_web_runtime_facade_coverage.py` — 修复断言字符串
  - `brain_alpha_ops/web/react_app/tests/components.test.tsx` — 同步前端断言（如存在）
  - `brain_alpha_ops/web/security/web_session.py` — 删除重复导入、合并导入语句
  - 9 个子包 `__init__.py` — 添加 `__all__` 定义
  - `brain_alpha_ops/agent_tools/__init__.py` — 清理冗余 re-export
- **Affected tests**: `test_web_runtime_facade_coverage.py`（修复后通过）、`test_agent_tools.py`（验证清理后导入正常）

## ADDED Requirements

### Requirement: CI 测试全通过

The system SHALL 保证所有非环境限制的测试（排除 `test_read_jsonl_tail.py`、`test_quality_gate.py` 的 tomllib 问题）在 `pytest tests/` 运行时全部通过，无新增失败。

#### Scenario: i18n 测试通过
- **WHEN** 运行 `python3 -m pytest tests/test_web_runtime_facade_coverage.py::test_runtime_facade_connection_fails_when_profile_returns_auth_error`
- **THEN** 测试通过，断言与 `web_errors.py` 返回的中文错误消息一致

#### Scenario: 前后端错误消息契约一致
- **WHEN** 后端 `web_errors.py` 返回 `"认证失败，请检查凭据或连接设置。"`
- **THEN** 前端测试 `components.test.tsx` 的断言也期望同一中文字符串（或通过 i18n 配置统一）

### Requirement: 子包命名空间封装

The system SHALL 在所有 Phase 6-10 创建的子包 `__init__.py` 中定义 `__all__` 列表，显式声明公共 API surface，防止 `import *` 泄漏子模块的内部符号。

#### Scenario: import * 仅导出声明符号
- **WHEN** 执行 `from brain_alpha_ops.e2e_report import *`
- **THEN** 仅 `__all__` 中列出的符号被导入，子模块的内部辅助函数不被泄漏

#### Scenario: 显式导入不受影响
- **WHEN** 执行 `from brain_alpha_ops.e2e_report import build_e2e_artifact_summary`
- **THEN** 导入成功，无论 `__all__` 是否包含该符号

### Requirement: 代码无重复导入

The system SHALL 保证不存在完全相同的重复导入语句。

#### Scenario: web_session.py 无重复
- **WHEN** 检查 `brain_alpha_ops/web/security/web_session.py`
- **THEN** 不存在两行完全相同的 `from ... import ...` 语句

## MODIFIED Requirements

### Requirement: agent_tools re-export 清理（继承自 Phase 8）

审计 `agent_tools/__init__.py` 的 25 处 `# noqa: F401` re-export，移除未被外部引用且未在 `__all__` 中声明的冗余导出，保留真正被测试或下游模块使用的 re-export。

## REMOVED Requirements

无删除项。
