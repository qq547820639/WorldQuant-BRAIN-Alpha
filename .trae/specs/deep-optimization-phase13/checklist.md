# Checklist

## 拆分正确性

- [x] 16 个超限文件均已转换为 re-export 子包目录
- [x] 每个子包 `__init__.py` 显式定义 `__all__`
- [x] 每个子包 `__init__.py` 导出公共 API + 已测试私有符号
- [x] 所有新子模块行数 ≤ 350（通过 `check_module_size.py --json` 验证）
- [x] Logger 名硬编码为原模块名（不使用 `__name__`）
- [x] 原 `.py` 文件按需保留为 thin shim（CLI 调用场景）或删除（纯 Python 模块）

## 行为兼容性

- [x] `from <package> import *` 对所有 16 个拆分子包正常工作
- [x] 原有测试套件无新增失败（pytest 主套件）
- [x] Monkeypatch 兼容性保持（`monkeypatch.setattr(module, "_func", ...)` 仍生效）
- [x] 子进程 CLI 调用（如有）通过 thin shim 正常工作
- [x] 凭据扫描测试 `test_credential_leak_regression.py` 全绿

## 同步与审计

- [x] `scripts/check_module_size.py:BASELINE_LINE_LIMITS` 已移除 16 个拆分文件条目
- [x] `python3 scripts/check_module_size.py --json` 输出 `ok=true findings=0 baseline=16`
- [x] `DEFECT_TRACKING.md` 无需更新（本阶段不涉及缺陷修复）

## 提交与推送

- [x] `git commit` 使用规范中文提交消息（含 phase13 标识）
- [x] `git push origin main` 推送成功
- [x] 远端 `origin/main` 最新 commit 包含本阶段所有变更

## 文档与规格

- [x] `tasks.md` 所有任务勾选完成
- [x] `checklist.md` 所有检查项勾选完成
- [x] 无新增 open 缺陷
