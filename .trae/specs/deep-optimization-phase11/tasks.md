# Tasks

## 批次 A: P0 缺陷修复（立即可验证）

- [x] Task 1: 修复 i18n 测试失败
  - [ ] SubTask 1.1: 读取 `tests/test_web_runtime_facade_coverage.py` 第 155-180 行，定位 `test_runtime_facade_connection_fails_when_profile_returns_auth_error` 断言
  - [ ] SubTask 1.2: 读取 `brain_alpha_ops/web/misc/web_errors.py` 第 26-69 行，确认中文错误消息 `"认证失败，请检查凭据或连接设置。"`
  - [ ] SubTask 1.3: 将测试断言从英文 `"Authentication failed; check credentials or connection settings."` 改为中文 `"认证失败，请检查凭据或连接设置。"`
  - [ ] SubTask 1.4: 检查 `brain_alpha_ops/web/react_app/tests/components.test.tsx` 第 733 行附近是否有相同英文断言，如有则同步修改
  - [ ] SubTask 1.5: 运行 `python3 -m pytest tests/test_web_runtime_facade_coverage.py -q --tb=short` 验证全部通过

- [ ] Task 2: 修复 web_session.py 重复导入
  - [ ] SubTask 2.1: 读取 `brain_alpha_ops/web/security/web_session.py` 第 1-15 行和第 455-465 行
  - [ ] SubTask 2.2: 删除第 11 行的重复 `from brain_alpha_ops.web.dispatch.web_post_handlers import session_end_payload`
  - [ ] SubTask 2.3: 合并第 459-463 行的 3 条 `from .web_security import X` 语句为单条
  - [ ] SubTask 2.4: 运行 `python3 -c "from brain_alpha_ops.web.security.web_session import *; print('OK')"` 验证导入正常

## 批次 B: 子包 __all__ 封装（可并行）

- [ ] Task 3: 为 9 个子包 __init__.py 添加 __all__ 定义
  - [ ] SubTask 3.1: `e2e_report/__init__.py` — 读取子模块，收集公共符号，定义 `__all__`
  - [ ] SubTask 3.2: `research/observability/__init__.py` — 同上
  - [ ] SubTask 3.3: `research/cross_review_pipeline/__init__.py` — 同上
  - [ ] SubTask 3.4: `research/experience/__init__.py` — 同上
  - [ ] SubTask 3.5: `research/expression_sqlite_index/__init__.py` — 同上
  - [ ] SubTask 3.6: `research/decoupled_pipeline/__init__.py` — 同上
  - [ ] SubTask 3.7: `research/expression_ast/__init__.py` — 同上（已有部分显式 re-export，补充 `__all__`）
  - [ ] SubTask 3.8: `research/llm_service/__init__.py` — 同上
  - [ ] SubTask 3.9: `web/misc/web_service_namespace/__init__.py` — 同上
  - [ ] SubTask 3.10: 验证所有 9 个子包 `from ... import *` 仍正常工作，且显式导入不受影响

## 批次 C: agent_tools re-export 审计

- [ ] Task 4: 审计并清理 agent_tools/__init__.py 冗余 re-export
  - [ ] SubTask 4.1: 读取 `brain_alpha_ops/agent_tools/__init__.py` 全部内容
  - [ ] SubTask 4.2: 对每个 `# noqa: F401` re-export，用 Grep 搜索其在 `tests/` 和 `brain_alpha_ops/` 中的引用
  - [ ] SubTask 4.3: 移除未被任何外部模块引用且未在 `__all__` 中的冗余 re-export
  - [ ] SubTask 4.4: 运行 `python3 -m pytest tests/test_agent_tools.py -q --tb=short` 验证无回归

## 批次 D: 验证与提交

- [ ] Task 5: 全量验证
  - [ ] SubTask 5.1: 运行 `python3 -m pytest tests/ --ignore=tests/test_read_jsonl_tail.py --ignore=tests/test_quality_gate.py -q --tb=no` 确认无新增失败（预存失败从 1 个降为 0 个）
  - [ ] SubTask 5.2: 验证 9 个子包 `from ... import *` 正常工作
  - [ ] SubTask 5.3: 验证 `web_session.py` 无重复导入

- [ ] Task 6: 提交并推送到 origin/main
  - [ ] SubTask 6.1: `git add` 所有修改文件
  - [ ] SubTask 6.2: `git commit` 使用规范中文提交消息
  - [ ] SubTask 6.3: `git push origin main` 推送成功

# Task Dependencies

- Task 1 和 Task 2 相互独立，可并行
- Task 3 的 9 个子任务相互独立，可并行
- Task 4 独立于 Task 1-3，可并行
- Task 5-6 依赖 Task 1-4 全部完成
- 无循环依赖
