# BRAIN Alpha Ops 深挖优化 Phase 11 - 验证清单

## P0 缺陷修复
- [x] `test_runtime_facade_connection_fails_when_profile_returns_auth_error` 测试通过（i18n 断言修复）
- [x] `web_session.py` 无重复导入语句（第 10-11 行重复已删除）
- [x] `web_session.py` 的 3 条 `from .web_security import X` 已合并为 1 条
- [x] 前端 `components.test.tsx` 的对应断言已同步（第 733 行改为中文）

## 子包 __all__ 封装
- [x] `e2e_report/__init__.py` 已定义 `__all__`（31 symbols）
- [x] `research/observability/__init__.py` 已定义 `__all__`（26 symbols）
- [x] `research/cross_review_pipeline/__init__.py` 已定义 `__all__`（11 symbols）
- [x] `research/experience/__init__.py` 已定义 `__all__`（12 symbols）
- [x] `research/expression_sqlite_index/__init__.py` 已定义 `__all__`（20 symbols）
- [x] `research/decoupled_pipeline/__init__.py` 已定义 `__all__`（9 symbols）
- [x] `research/expression_ast/__init__.py` 已定义 `__all__`（36 symbols）
- [x] `research/llm_service/__init__.py` 已定义 `__all__`（6 symbols）
- [x] `web/misc/web_service_namespace/__init__.py` 已定义 `__all__`（162 symbols）

## agent_tools re-export 审计
- [x] `agent_tools/__init__.py` 的 25 处 `# noqa: F401` 已逐一审计
- [x] 49 个未被外部引用的冗余 re-export 已移除（文件从 98 行缩减到 32 行）
- [x] `__all__` 中 8 个符号 + 2 个 monkeypatch 依赖符号完整保留
- [x] `tests/test_agent_tools.py` 全部通过（38 passed）

## 向后兼容
- [x] 所有 9 个子包 `from ... import *` 仍正常工作
- [x] 所有显式导入（`from ... import SpecificSymbol`）不受影响
- [x] `web_session.py` 导入功能正常

## 测试验证
- [x] `python3 -m pytest tests/test_web_runtime_facade_coverage.py -q` 全部通过（11 passed）
- [x] `python3 -m pytest tests/test_agent_tools.py -q` 全部通过（38 passed）
- [x] 跨模块测试 153 passed（含 e2e_report, defect_015, web_facade_contract, research_memory, assistant_context, research_observability, expression_ast, experience, expression_sqlite_index, generation）

## 提交
- [ ] 所有变更已 `git add`
- [ ] `git commit` 使用规范中文提交消息
- [ ] `git push origin main` 推送成功
- [ ] `git status` 显示工作区干净（除运行时数据文件）
