# 正式发布前收尾与用户体验深化 Spec

## Why
当前项目功能已较完整，但存在若干发布阻断项（NumPy 依赖未声明导致全新环境 Pytest collection 失败、CI 中多项 `continue-on-error` 掩盖真实结果、React TypeScript 类型错误），且普通新用户首次安装与运行体验不足。目标是把项目从"功能较完整的 Beta"提升到"可重复安装、可稳定运行、可正式发布、普通用户容易使用"的版本。

## What Changes
- **P0-发布阻断**：恢复完整 CI 全绿；修复依赖契约（NumPy 延迟导入 + 正确声明）；收紧发布门禁并新增 `release-readiness` 汇总任务。
- **P1-新用户首次体验**：实现首次启动 Preflight/Onboarding；修正 README 全部占位符、过期命令与不一致版本号。
- **P1-运行过程体验**：为生产运行提供清晰阶段、数量/配额/耗时展示、暂停/继续/安全取消/仅重试失败项/断点恢复、各故障态明确界面。
- **P1-诊断与支持**：一键生成脱敏诊断包 + 脱敏回归测试。
- **P1-研究工作流**：Alpha 血缘、候选对比、研究批次、维度统计分析（不改变 BRAIN 官方规则）。
- **P2-版本/发布/数据可靠性**：确定新语义化版本号并全量同步；SQLite/JSONL schema 版本与迁移；SBOM、漏洞扫描、构建校验和。
- **测试**：补齐测试清单所列用例，全部可重复、无真实提交副作用。
- **文档**：输出最终验收报告与剩余已知限制。

## Impact
- Affected specs: 无（独立收尾任务，基于当前 main 分支现状）。
- Affected code:
  - `pyproject.toml`、`requirements.lock`（NumPy/依赖契约、版本号）
  - `brain_alpha_ops/scoring/anti_overfit/permutation.py`（NumPy 延迟导入）
  - `.github/workflows/quality-gate.yml`、`build-release.yml`（门禁、release-readiness）
  - `brain_alpha_ops/web/react_app/**`（ErrorBoundary 测试、Preflight 前端、阶段 UX、诊断 UI）
  - `brain_alpha_ops/web/**`、新增 Preflight/诊断/迁移模块
  - `README.md`、Release Notes、CHANGELOG
  - SQLite/JSONL 相关持久化模块（schema 版本、自动迁移、备份）
  - `Dockerfile`、`docker-compose.yml`（版本 label、健康检查）
- **BREAKING**: 无（保持现有 API 与数据文件向后兼容；仅新增 schema 版本与迁移机制）。

## 安全红线（必须在整个变更中保持）
- 默认禁止自动真实提交；真实提交必须经过 HIL 人工确认。
- 凭证不得写入磁盘、日志、截图或错误响应。
- 外部 API 异常时应 fail-closed。
- 不得绕过速率限制、CSRF、重放防护和日志脱敏。

## ADDED Requirements

### Requirement: 依赖契约完整性（P0-2）
系统 SHALL 让所有实际使用的第三方依赖（含 NumPy）被正确声明在 `pyproject.toml` 与 `requirements.lock`，并在全新 Python 3.12 环境中一次 `pip install -e ".[test,browser]"` 后完整 Pytest collection 成功。

#### Scenario: 全新环境安装
- **WHEN** 在无预装依赖的 Python 3.12 venv 中执行 `pip install -e ".[test,browser]"` 后运行 `pytest tests/ --cov=brain_alpha_ops`
- **THEN** 完整 collection 无错误，无 `ModuleNotFoundError`，覆盖率达标

#### Scenario: NumPy 属于可选能力
- **WHEN** NumPy 未被安装而普通模块被导入
- **THEN** 相关模块采用安全的延迟导入，不因顶层 `import numpy` 导致全项目 collection 失败
- **AND** 功能启用时给出清晰的依赖安装提示

### Requirement: 发布门禁强化（P0-3）
系统 SHALL 让 mock E2E、类型检查、单元测试、生产构建、完整依赖安装成为强制门禁；Prettier 修复后设为强制；npm/pip audit 对 high/critical 阻断；仅依赖真实 BRAIN 凭证的 live smoke test 可条件跳过且必须显示明确原因；新增 `release-readiness` 汇总任务，仅当所有必选任务成功时才成功。

#### Scenario: 任一必选任务失败
- **WHEN** 任何一个必选 CI 任务失败
- **THEN** `release-readiness` 状态为失败，发布被阻断

#### Scenario: live smoke 跳过
- **WHEN** 缺少真实 BRAIN 凭证导致 live smoke 被跳过
- **THEN** 跳过原因明确显示，不伪装成通过

### Requirement: 首次启动 Preflight/Onboarding（P1）
系统 SHALL 在首次启动时检查并展示：Python 版本、依赖完整性、Playwright 浏览器、端口 8765 占用、可用磁盘空间、数据目录可写、BRAIN 网络可达、本地缓存有效、前后端版本匹配、是否存在需迁移的旧数据。检查失败时提供失败原因、影响范围、推荐修复操作、可复制修复命令、修复后重新检测按钮。

### Requirement: 运行阶段体验（P1）
系统 SHALL 为每个生产运行显示清晰阶段（准备/字段同步/候选生成/本地预筛/官方回测/评分/稳健性检查/诊断优化/提交就绪），每阶段展示已完成数量、总数量、当前活动、API 配额/并发槽位、已耗时、可安全暂停或取消状态。支持暂停、继续、安全取消、仅重试失败项、从最后成功阶段恢复、查看失败原始原因、查看脱敏后的请求 ID 和响应摘要。不提供虚假精确剩余时间，仅提供基于历史批次的范围估计并标明依据。

### Requirement: 一键脱敏诊断包（P1）
系统 SHALL 提供一键生成脱敏诊断包，包含应用版本、Git commit、Python/Node/OS 版本、依赖版本、配置摘要、最近运行状态、最近错误及 Request ID、数据库 schema 版本、缓存状态、CI/健康检查摘要；自动删除用户名、密码、Token、Cookie、Authorization header、会话标识、Alpha 敏感数据。脱敏逻辑必须有回归测试。

### Requirement: 研究工作流深化（P1）
系统 SHALL 提供 Alpha 血缘（原始/变异/融合候选、父子关系、每次修改原因、指标变化）、候选对比（表达式/参数 diff、Sharpe/Fitness/Turnover/相关性、硬门禁、评分贡献、稳健性证据）、研究批次（名称/假设/数据集/预算/起止时间/成功率/失败原因分布/最佳候选/可导出总结）、维度统计分析（字段家族/算子家族/假设类型/失败原因）。不得改变 BRAIN 官方规则。

### Requirement: 版本、发布与数据可靠性（P2）
系统 SHALL 确定新的语义化版本号（不复用 v0.5.0）并同步到 `pyproject.toml`、应用内版本、README、构建产物名称、Docker image label、Release Notes、CHANGELOG；建立 RC 与正式版本流程；为 SQLite/JSONL 提供 schema 版本、自动迁移、迁移前备份、失败回滚、数据完整性检查、损坏恢复说明；增加 SBOM、依赖漏洞扫描、构建校验和；确保 Git tag、版本号、构建产物与源代码对应。

### Requirement: 补充测试（八）
系统 SHALL 至少补充：全新环境安装 smoke、NumPy/可选依赖缺失、前端 ErrorBoundary 类型与运行、凭证过期、API 429/5xx 重试与静默期、网络中断与恢复、SQLite 并发写入、服务重启续跑、缓存损坏、日志脱敏、真实提交默认禁用、HIL 确认不可绕过、prod correlation 获取失败 fail-closed、Docker healthcheck、Windows 路径与编码、macOS 打包启动、React 主要页面无障碍 smoke。测试必须可重复、无真实提交副作用。

## MODIFIED Requirements

### Requirement: Python 依赖声明
`pyproject.toml` `[project].dependencies` 与 `requirements.lock` SHALL 正确声明所有实际使用且非可选的能力（如 NumPy）；可选能力经延迟导入 + 明确安装提示处理。

### Requirement: CI 门禁
`quality-gate.yml` 与 `build-release.yml` SHALL 移除不合理的 `continue-on-error`（保留 live smoke 条件跳过但必须显示原因），新增 `release-readiness` 汇总任务。

### Requirement: 版本号一致性
README、pyproject.toml、`react_app/package.json`、Docker image label、构建产物名称 SHALL 反映新的语义化版本号，取代 0.5.0。

## REMOVED Requirements
无