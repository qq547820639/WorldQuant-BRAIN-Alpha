# Checklist

> 全部检查点通过后方可宣布完成。CI 未全绿、完整测试未通过或依赖不完整时不得输出 "Release Ready"。

## P0 - 发布阻断
- [ ] `permutation.py` 等模块对 NumPy 采用延迟导入，普通模块导入不抛 `ModuleNotFoundError`；缺失时给出安装提示
- [ ] NumPy 已正确声明于 `pyproject.toml` 与 `requirements.lock`
- [ ] 全新 Python 3.12 venv `pip install -e ".[test,browser]"` 后完整 `pytest tests/ --cov=brain_alpha_ops` collection 无错误，覆盖率达标
- [ ] `ErrorBoundary.test.tsx` 的 `ThrowingChild` JSX 类型错误已修复（未关 strict、未全局 any、未删断言）
- [ ] 前端 `typecheck`、`lint`、`format:check`、`test`、`build` 全部通过
- [ ] `quality-gate.yml` 不合理的 `continue-on-error` 已移除；live smoke 条件跳过显示明确原因
- [ ] `release-readiness` 汇总任务存在，仅当所有必选任务成功时才成功
- [ ] Docker build（runtime/runtime-full）成功，容器 `/api/health` 200 且 HEALTHCHECK 通过

## P1 - 新用户首次体验
- [ ] Preflight 检查项齐全（Python/依赖/Playwright/端口/磁盘/目录可写/网络/缓存/前后端版本/旧数据），失败项含原因/影响/修复操作/可复制命令/重新检测按钮
- [ ] README 无占位仓库地址、过期命令、不一致版本号；macOS/Windows PowerShell/Linux Docker 安装、一键启动、一键升级、完全卸载、备份恢复步骤真实可运行

## P1 - 运行过程体验
- [ ] 生产运行展示 9 个阶段、每阶段已完成/总数/当前活动/配额/耗时/可暂停或取消状态
- [ ] 支持暂停/继续/安全取消/仅重试失败项/从最后成功阶段恢复/查看失败原因/脱敏 Request ID 与响应摘要
- [ ] 无虚假精确剩余时间；空态/加载/部分成功/限流/凭证过期/断网/缓存损坏/重启各有明确界面

## P1 - 诊断与支持
- [ ] 一键脱敏诊断包包含全部指定字段，脱敏规则齐全，且有脱敏回归测试

## P1 - 研究工作流
- [ ] Alpha 血缘、候选对比、研究批次、维度统计分析已实现且不改变 BRAIN 官方规则

## P2 - 版本、发布与数据可靠性
- [ ] 新语义化版本号（非 0.5.0）已同步 pyproject.toml/应用内/README/构建产物/Docker label/Release Notes/CHANGELOG
- [ ] SQLite/JSONL 具 schema 版本、自动迁移、迁移前备份、失败回滚、完整性检查、损坏恢复说明
- [ ] SBOM、依赖漏洞扫描（high/critical 阻断）、构建校验和已增加；Git tag/版本/产物/源码一致

## 测试与验证
- [ ] 测试清单（八）所列用例均已补充且可重复、无真实提交副作用
- [ ] 全新环境安装一次性成功；完整 Pytest 通过；覆盖率达标
- [ ] React typecheck/lint/format/unit/build 通过；mock E2E 通过
- [ ] Docker build+healthcheck 通过；Windows/macOS 构建产物可启动
- [ ] 安全红线复核通过（真实提交默认禁用、HIL 不可绕过、凭证不入盘/日志/响应、fail-closed、速率限制/CSRF/重放/脱敏未削弱）
- [ ] 最终验收报告已输出（含修改摘要、根因清单、文件清单、测试清单、验证命令及真实结果、CI 结果、UX 前后对照、安全红线复核、版本发布说明、遗留问题与原因）
- [ ] 最终结论基于真实结果给出 Release Ready / Release Candidate / Not Ready