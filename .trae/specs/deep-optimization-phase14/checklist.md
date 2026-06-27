# Checklist

## 拆分正确性

- [ ] 16 个 grandfathered 文件均已 ≤ 350 行
- [ ] 拆分后的新子模块/helper 模块均 ≤ 350 行
- [ ] 如使用 re-export 子包：`__init__.py` 显式定义 `__all__` + 导出公共 API + 已测试私有符号
- [ ] 如使用 helper 抽取：原文件保留为主入口，helper 模块命名清晰
- [ ] Logger 名硬编码为原模块名（不使用 `__name__`）
- [ ] CLI 脚本（如 `check_defect_analysis_report.py`）保留 thin shim 用于直接调用

## 行为兼容性

- [ ] `from <module> import *` 对所有 16 个拆分模块正常工作
- [ ] 原有测试套件无新增失败（pytest 主套件）
- [ ] Monkeypatch 兼容性保持
- [ ] 凭据扫描测试 `test_credential_leak_regression.py` 全绿

## 同步与审计

- [ ] `scripts/check_module_size.py:BASELINE_LINE_LIMITS` 已清空为 `{}`
- [ ] `python3 scripts/check_module_size.py --json` 输出 `ok=true findings=[] baseline_limits={}`

## 提交与推送

- [ ] `git commit` 使用规范中文提交消息（含 phase14 标识）
- [ ] `git push origin main` 推送成功
- [ ] 远端 `origin/main` 最新 commit 包含本阶段所有变更

## 文档与规格

- [ ] `tasks.md` 所有任务勾选完成
- [ ] `checklist.md` 所有检查项勾选完成
- [ ] 无新增 open 缺陷
- [ ] 仓库达到 "零 grandfathered 文件" 完全合规状态
