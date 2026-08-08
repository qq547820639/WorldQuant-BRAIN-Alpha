# Tasks

> 目标：把项目从"功能较完整的 Beta"提升到"可重复安装、可稳定运行、可正式发布、普通用户容易使用"。所有任务须保持安全红线。完成 `checklist.md` 全部检查点后方可宣布完成。

## P0 - 发布阻断

- [ ] Task 1: 修复依赖契约（NumPy 延迟导入 + 正确声明）
  - [ ] 1.1 全量扫描 `brain_alpha_ops` 中所有第三方导入，建立"实际使用 vs 声明"差异清单（重点：`permutation.py` 顶层 `import numpy`）
  - [ ] 1.2 将 `permutation.py` 改为安全的延迟导入（模块内 `_get_np()` / try-import），并在功能启用缺失时给出清晰安装提示
  - [ ] 1.3 在 `pyproject.toml` `[project].dependencies`（或可选依赖）与 `requirements.lock` 中正确声明 NumPy
  - [ ] 1.4 在全新 Python 3.12 venv 中执行 `pip install -e ".[test,browser]"` + `pytest tests/ --cov=brain_alpha_ops`，确认完整 collection 无 `ModuleNotFoundError`
- [ ] Task 2: 修复 React TypeScript/前端测试错误
  - [ ] 2.1 修复 `ErrorBoundary.test.tsx` 中 `'ThrowingChild' cannot be used as a JSX component`（为 unconditionally-throw 组件提供显式返回类型 / 用 `UnknownReturnType` 或返回 `never`），不关闭 strict、不滥用 any、不删断言
  - [ ] 2.2 修复其余 `No overload matches this call` 等类型错误
  - [ ] 2.3 运行 `npm run typecheck`、`npm run lint`、`npm run format:check`（修复格式）、`npm run test`、`npm run build`，全部通过
- [ ] Task 3: 恢复完整 CI 并强化发布门禁
  - [ ] 3.1 重新评估 `quality-gate.yml` 中所有 `continue-on-error`（npm audit critical、prettier、E2E smoke、codecov、npm audit moderate），只保留 live smoke 条件跳过且必须显示明确原因
  - [ ] 3.2 将 Prettier 修复现有格式问题后设为强制；npm/pip audit 对 high/critical 阻断
  - [ ] 3.3 新增 `release-readiness` 汇总任务（`needs:` 依赖全部必选任务，任一失败则失败）
  - [ ] 3.4 确认 Ubuntu/macOS Python 3.12 后端门禁、浏览器 mock/readonly 契约、完整 Pytest、覆盖率、Windows/macOS 构建、Docker build+healthcheck 配置正确
- [ ] Task 4: Docker 构建与健康检查
  - [ ] 4.1 本地 `docker build` 成功（runtime 与 runtime-full）
  - [ ] 4.2 容器启动后 `/api/health` 返回 200，HEALTHCHECK 通过
  - [ ] 4.3 同步版本 label 到 `Dockerfile`/`docker-compose.yml`

## P1 - 新用户首次体验

- [ ] Task 5: 实现首次启动 Preflight/Onboarding
  - [ ] 5.1 后端实现 Preflight 检查模块（Python 版本、依赖、Playwright、端口 8765、磁盘、数据目录可写、BRAIN 网络、缓存、前后端版本、旧数据迁移）
  - [ ] 5.2 每个检查项返回 状态/失败原因/影响范围/推荐修复操作/可复制修复命令
  - [ ] 5.3 前端 Preflight 界面 + "修复后重新检测"按钮；首次启动展示
  - [ ] 5.4 补充 Preflight 后端与前端测试
- [ ] Task 6: 修正 README 与安装/升级/卸载/备份文档
  - [ ] 6.1 清除所有占位仓库地址、过期命令、不一致版本号与数字
  - [ ] 6.2 提供真实可运行的 macOS/PowerShell Windows/Linux+Docker 安装、一键启动、一键升级、完全卸载、数据备份与恢复步骤
  - [ ] 6.3 实际执行记录在 README 中的核心命令并核对

## P1 - 运行过程体验

- [ ] Task 7: 运行阶段体验（阶段/数量/配额/耗时/恢复）
  - [ ] 7.1 为生产运行提供 9 个清晰阶段（准备…提交就绪）状态模型与展示
  - [ ] 7.2 每阶段展示已完成/总数、当前活动、API 配额/并发槽位、已耗时、可安全暂停/取消状态
  - [ ] 7.3 支持暂停、继续、安全取消、仅重试失败项、从最后成功阶段恢复、查看失败原始原因、查看脱敏 Request ID 与响应摘要
  - [ ] 7.4 不提供虚假精确剩余时间；基于历史批次给范围估计并标明依据
  - [ ] 7.5 为空状态/加载/部分成功/限流/凭证过期/网络断开/缓存损坏/服务重启设计明确界面
  - [ ] 7.6 补充相关后端 + 前端测试

## P1 - 诊断与支持

- [ ] Task 8: 一键脱敏诊断包
  - [ ] 8.1 实现诊断包生成（版本/commit/Python/Node/OS/依赖/配置摘要/最近运行/最近错误+RequestID/schema 版本/缓存/CI 健康）
  - [ ] 8.2 实现脱敏（用户名/密码/Token/Cookie/Authorization/会话标识/Alpha 敏感数据）
  - [ ] 8.3 前端"一键生成诊断包"入口与下载
  - [ ] 8.4 脱敏逻辑回归测试

## P1 - 研究工作流深化

- [ ] Task 9: Alpha 血缘、候选对比、研究批次与维度统计
  - [ ] 9.1 Alpha 血缘（原始/变异/融合/父子/修改原因/指标变化）
  - [ ] 9.2 候选对比（表达式/参数 diff、Sharpe/Fitness/Turnover/相关性、硬门禁、评分贡献、稳健性证据）
  - [ ] 9.3 研究批次（名称/假设/数据集/预算/起止/成功率/失败分布/最佳候选/可导出总结）
  - [ ] 9.4 字段家族/算子家族/假设类型/失败原因统计分析
  - [ ] 9.5 不改变 BRAIN 官方规则；补充测试

## P2 - 版本、发布与数据可靠性

- [ ] Task 10: 版本号与发布流程
  - [ ] 10.1 确定新语义化版本号（不复用 0.5.0）
  - [ ] 10.2 同步 pyproject.toml、应用内版本、README、构建产物名称、Docker label、Release Notes、CHANGELOG
  - [ ] 10.3 建立 RC 与正式版本流程（文档）
- [ ] Task 11: SQLite/JSONL 数据可靠性
  - [ ] 11.1 schema 版本 + 自动迁移 + 迁移前备份 + 失败回滚 + 完整性检查 + 损坏恢复说明
  - [ ] 11.2 补充迁移与完整性测试
- [ ] Task 12: SBOM、漏洞扫描、构建校验和
  - [ ] 12.1 增加 SBOM 生成、依赖漏洞扫描（pip-audit/npm audit high/critical 阻断）
  - [ ] 12.2 构建产物校验和；确保 Git tag、版本号、产物、源码一致

## 测试补充与验证

- [ ] Task 13: 补齐测试清单（八）
  - [ ] 全新环境安装 smoke；NumPy/可选依赖缺失；ErrorBoundary 类型与运行；凭证过期；429/5xx 重试与静默期；网络中断与恢复；SQLite 并发写入；服务重启续跑；缓存损坏；日志脱敏；真实提交默认禁用；HIL 确认不可绕过；prod correlation fail-closed；Docker healthcheck；Windows 路径/编码；macOS 打包启动；React 主要页面无障碍 smoke
- [ ] Task 14: 全量验证与最终验收报告
  - [ ] 14.1 全新环境安装 + 完整 Pytest + 覆盖率通过
  - [ ] 14.2 React typecheck/lint/format/test/build 通过；mock E2E 通过
  - [ ] 14.3 Docker build + healthcheck 通过；Windows/macOS 产物可启动
  - [ ] 14.4 输出最终验收报告（修改摘要/根因清单/文件清单/测试清单/验证命令与结果/CI 结果/UX 前后对照/安全红线复核/版本发布说明/遗留问题）
  - [ ] 14.5 结论：Release Ready / Release Candidate / Not Ready（CI 未全绿、测试未通过或依赖不完整时不得报 Release Ready）

# Task Dependencies
- [Task 1] 独立，先行（阻断 collection）
- [Task 2] 独立，可并行于 [Task 1]
- [Task 3] 依赖 [Task 1]、[Task 2]
- [Task 4] 依赖 [Task 1]、[Task 10]
- [Task 5] 依赖 [Task 1]
- [Task 6] 依赖 [Task 1]、[Task 10]
- [Task 7] 依赖 [Task 1]、[Task 3]
- [Task 8] 依赖 [Task 1]
- [Task 9] 依赖 [Task 1]
- [Task 10] 独立
- [Task 11] 独立
- [Task 12] 依赖 [Task 10]
- [Task 13] 依赖 [Task 1]、[Task 2] 及其余功能任务
- [Task 14] 依赖全部任务