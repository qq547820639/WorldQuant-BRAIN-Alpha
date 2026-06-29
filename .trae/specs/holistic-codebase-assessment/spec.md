# 全量源码整体评估报告 Spec

## Why

本项目（BRAIN Alpha Ops）是 WorldQuant BRAIN 平台的 Alpha 因子生产系统，包含约 600+ Python 后端文件、200+ React/TS 前端文件、7 个顶层入口、30+ 子模块包。仓库已存在 17 份历史审计/缺陷文档与 19 份 spec，但**结论相互矛盾**（内部审计评 8.5/10，外部顾问判"不合格"），且多数文档针对特定修复阶段而非全量代码的当前状态。

用户明确要求：**在完整阅读并深度分析项目全部源代码后**，输出一份整体评估报告，且**未读完全部代码前禁止输出任何内容**。报告仅需聚焦三大核心维度的重大问题与改进方向，**严格忽略代码风格、命名规范、注释缺失等细枝末节**，**仅限对项目有实质性影响的严重问题**。这意味着本次交付物是一份**纯分析报告**（不修改任何业务代码），作为后续优化决策的依据。

## What Changes

本次交付的唯一产物是一份 Markdown 评估报告文件，存放于 `/workspace/.trae/specs/holistic-codebase-assessment/ASSESSMENT_REPORT.md`，结构如下：

- **报告头**：评估日期、代码快照基准（git commit / 文件数 / 行数概览）、评估范围声明、方法论说明（全量源码深读 + 交叉核对历史文档）。
- **总体结论**：项目整体健康度一句话定性 + 三维度严重问题计数（Critical / High / Medium）。
- **维度一：功能缺陷**（Functional Defects）
  - 排查范围：逻辑漏洞、异常处理缺失、核心流程阻塞、状态机不一致、并发不安全、数值正确性、资源泄漏、数据丢失/污染、死代码导致功能失效。
  - 每条问题含：编号、严重级别、标题、受影响文件:行号引用、根因分析、影响范围、复现/触发条件、改进方向。
- **维度二：用户体验**（User Experience）
  - 排查范围：交互流程不畅、反直觉操作、关键反馈缺失、错误提示不可理解/不可恢复、阻塞流程未前置提示、长任务无进度、断连/超时无兜底、移动端交互断裂、配置生效语义不清。
  - 每条问题含：编号、严重级别、标题、用户路径描述、当前行为、期望行为、改进方向。
- **维度三：WebUI 问题**（WebUI Defects）
  - 排查范围：页面布局错乱、组件状态异常、严重渲染缺陷、首屏空白、路由不进 URL、阻断阶段按钮仍可点、Modal 无焦点陷阱、SSE/轮询导致内存泄漏或无限刷新、Toast/Modal 重复、移动端遮挡、可访问性阻断。
  - 每条问题含：编号、严重级别、标题、组件:行号引用、缺陷描述、视觉/交互后果、改进方向。
- **改进路线图**：按严重级别 + 维度给出建议处理顺序（P0 立即修复 / P1 本迭代 / P2 后续规划），不包含具体代码实现。
- **附录**：与历史审计文档（`docs/` 与根目录 17 份报告）的差异说明（哪些已修复、哪些仍存在、哪些是新发现）。

**严格排除**：代码风格、命名规范、注释缺失、类型注解风格、import 顺序、文件行数超标、lint 告警、测试覆盖率数字、文档拼写等非实质性问题。若某问题虽属上述类别但导致功能/体验/渲染实质性破坏（如超长文件导致逻辑分散产生 bug），仍可纳入。

**不修改任何业务代码、测试、配置**。仅产出报告文件。

## Impact

- **Affected specs**：本报告为只读分析产物，不修改任何代码，对现有 specs 无直接影响。报告结论可能作为后续 `remediate-major-defects-evaluation` / `overhaul-alpha-production-quality` / `improve-frontend-ux` 等 spec 的输入参考。
- **Affected code**：无（只读分析）。报告需引用的代码覆盖范围：
  - `brain_alpha_ops/` 全部子包（research / scoring / compliance / audit_trail / monitoring / production_diagnostics / web_candidates / web_cloud / brain_api / browser / data / config / agent_tools / agent_tool_registry / shared / tasks / ux / i18n / web / examples / e2e_report）
  - `brain_alpha_ops/web/` 全部子包（api / business / candidates / config / dispatch / handlers / misc / security / state / submissions / react_app/src）
  - 顶层入口：`launch_web.py` / `_launch_monitor.py` / `build_prod.py` / `fetch_official_context.py`
  - 桥接文件：`_web_bridge.py` / `_config_domain_helpers.py` / `_runtime_constants_helpers.py` / `_config_schema_helpers.py` / `_types_extras.py`
  - 配置/构建：`pyproject.toml` / `Dockerfile` / `docker-compose.yml` / `environment.yml` / `requirements.lock`
  - CI：`.github/workflows/`
  - 脚本：`scripts/` 全部检查脚本（仅作为代码现状证据，不执行）

## ADDED Requirements

### Requirement: 评估报告必须基于全量源码深读

报告 SHALL 基于**完整阅读项目全部源代码**后产出。在未完成全量代码阅读前，禁止输出任何评估结论。阅读范围 SHALL 覆盖 `brain_alpha_ops/` 下所有 `.py` 文件、`brain_alpha_ops/web/react_app/src/` 下所有 `.ts/.tsx` 文件、顶层入口与桥接文件、配置与构建文件、CI 工作流。阅读 SHALL 采用子智能体并行策略（按子系统切分），但汇总阶段须确保所有子系统均已被覆盖，无遗漏。

#### Scenario: 全量覆盖验证
- **WHEN** 报告产出前进行覆盖核查
- **THEN** 报告附录 SHALL 列出已阅读的子系统清单
- **AND** 每个子系统的关键文件 SHALL 在报告问题中被至少抽查引用一次
- **AND NOT** 仅凭历史审计文档或 spec 推断结论

### Requirement: 报告仅聚焦三大维度的重大问题

报告 SHALL 仅包含三个维度的**实质性重大问题**：
1. **功能缺陷**：逻辑漏洞、异常处理缺失、核心流程阻塞、状态机/并发/数值/资源/数据正确性问题、死代码导致功能失效。
2. **用户体验**：交互流程不畅、反直觉操作、关键反馈缺失、错误提示不可恢复、阻塞流程未前置、长任务无进度、断连无兜底、移动端交互断裂。
3. **WebUI**：页面布局错乱、组件状态异常、严重渲染缺陷、首屏空白、路由异常、阻断阶段交互未禁用、Modal 焦点陷阱缺失、SSE/轮询泄漏、Toast/Modal 重复、移动端遮挡、可访问性阻断。

报告 SHALL NOT 包含代码风格、命名规范、注释缺失、类型注解风格、import 顺序、文件行数、lint 告警、测试覆盖率数字、文档拼写等非实质问题。

#### Scenario: 问题严重性筛选
- **WHEN** 发现一个"变量命名不符合 PEP8"问题
- **THEN** 报告 SHALL NOT 包含此问题
- **WHEN** 发现一个"反过拟合 returns→factor_values 回退链导致 IC 恒等于 1.0 虚假 PASS"问题
- **THEN** 报告 SHALL 包含此问题，标注 Critical，并给出根因与改进方向

### Requirement: 每条问题须含可验证证据

报告每条问题 SHALL 包含：
- 编号（如 `F-001` / `U-001` / `W-001`）
- 严重级别（Critical / High / Medium）
- 标题
- 受影响文件与行号引用（`path/to/file.py:LINE` 或 `path/to/Component.tsx:LINE`）
- 根因分析（为什么这是问题）
- 影响范围（对功能/账户安全/数据完整性/用户体验的具体后果）
- 触发条件或用户路径
- 改进方向（不要求代码实现，但须指向具体修复策略）

#### Scenario: 问题可追溯
- **WHEN** 读者想验证报告中 `F-005` 问题
- **THEN** 读者可凭报告中给出的 `file:line` 引用直接定位代码
- **AND** 根因分析说明为什么当前代码是错的
- **AND** 改进方向说明应改成什么样

### Requirement: 报告须与历史审计文档交叉核对

报告附录 SHALL 列出仓库已有的 17 份审计/缺陷文档（`docs/*.md` 与根目录 `*_AUDIT_*.md` / `*_REPORT_*.md` / `DEFECT_TRACKING.md` 等），并对每份文档中提出的重大问题标注当前状态：
- **已修复**：当前代码已不存在该问题（给出修复证据 `file:line`）
- **仍存在**：当前代码仍存在该问题（与报告主体交叉引用）
- **部分修复**：部分场景已修复，但仍有残留（说明残留场景）
- **新发现**：本次深读新发现的问题（历史文档未提及）

#### Scenario: 历史问题状态更新
- **WHEN** 历史文档 `BRAINALPHA_FULLSTACK_AUDIT_20260622.md` 提到"真实浏览器驱动的主路径未打通"
- **THEN** 报告附录 SHALL 标注该问题当前状态（已修复 / 仍存在 / 部分修复）并给出代码证据

### Requirement: 报告须按严重级别排序并给出路线图

报告 SHALL 按以下顺序组织问题：
1. Critical（阻断核心功能或导致虚假结果/数据污染/账户安全风险）
2. High（严重影响功能或体验，但有 workaround）
3. Medium（影响有限但值得记录）

报告末尾 SHALL 提供改进路线图，按 P0（立即）/ P1（本迭代）/ P2（后续规划）分级，并标注每项改进对应的问题编号。

#### Scenario: 路线图可执行
- **WHEN** 决策者阅读路线图
- **THEN** 能凭问题编号追溯到报告主体
- **AND** 能凭严重级别判断优先级
- **AND** 能凭改进方向判断修复策略

### Requirement: 报告语言与用户语言一致

报告 SHALL 使用中文撰写（与用户最新消息语言一致）。代码引用、文件路径、函数名、变量名保持英文原文。严重级别标签使用英文（Critical / High / Medium）。

### Requirement: 报告须基于代码当前状态而非历史推断

报告所有结论 SHALL 基于当前磁盘上的代码状态（git working tree），不基于版本历史、git log、历史 spec 推断。若历史文档结论与当前代码不符，以当前代码为准并在附录标注差异。

#### Scenario: 历史文档结论过时
- **WHEN** 历史文档 `CODE_DIAGNOSTIC_REPORT_20260618.md` 称某问题存在
- **AND** 当前代码已修复该问题
- **THEN** 报告 SHALL 标注"已修复"并给出当前代码证据
- **AND NOT** 直接引用历史文档结论作为问题来源

## MODIFIED Requirements

无（本 spec 为独立只读分析任务，不修改任何现有 requirement）。

## REMOVED Requirements

无。
