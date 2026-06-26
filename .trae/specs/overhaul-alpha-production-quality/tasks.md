# Tasks

> 工作流 A→F 顺序执行；同一工作流内无依赖子任务可并行。每完成一项立即勾选。所有变更前做全局影响评估，变更后输出结构化变更报告。

## 工作流 A：BRAIN 能力集注册表中心化

- [x] Task A1：创建 `brain_alpha_ops/data/capability_registry/` 子包骨架
  - [x] A1.1：`_types.py` 定义 `CapabilityEntry`、`CapabilityRegistry` 数据类（含来源、更新时间、适用范围、默认值、允许值、禁止值、校验规则、错误提示字段）
  - [x] A1.2：`_loaders.py` 从现有 `data/official_fields.json`、`official_operators.json`、`official_datasets.json` 构建注册表实例
  - [x] A1.3：`_defaults.py` 收编 `config_models.py:BrainSettings` 默认值（region/universe/delay/decay/neutralization/truncation/pasteurization/nanHandling/unitHandling）与 `config_domain_validation.py:_VALID_*` 枚举
  - [x] A1.4：`__init__.py` 导出公共 API + `__all__`，提供 `get_registry()` 单例
  - [x] A1.5：能力缺失时返回 `CapabilityResolutionError`，触发"需要人工确认"状态
- [x] Task A2：收编散落硬编码至注册表
  - [x] A2.1：`research/local_backtest/engine.py:supported_operators` 改为从 `get_registry().operators()` 派生
  - [x] A2.2：`presets.py` 5 个预设改为引用注册表默认值
  - [x] A2.3：`research/dataset_selector.py` 的 category→fields 索引改为从注册表读取
  - [x] A2.4：`research/expression_ast/_parser.py`、`research/expression_engine.py:validate` 的未知字段/算子校验改为查注册表
- [x] Task A3：注册表一致性校验脚本
  - [x] A3.1：补齐/修正 `scripts/check_capability_registry.py`，校验业务代码无散落硬编码、注册表与 `data/official_*.json` 一致
  - [x] A3.2：补齐 `scripts/check_brain_contract.py`（若不存在则创建），校验阈值与 BRAIN 官网标准零偏差

## 工作流 B：候选池状态机统一与生命周期审计

- [x] Task B1：扩展 `LifecycleState` 枚举对齐全规格状态
  - [x] B1.1：在 `candidate_lifecycle.py` 补齐 `draft`、`needs_optimization`、`ready_for_review` 等状态（若缺失）
  - [x] B1.2：补齐合法迁移图覆盖全部 11 态
- [x] Task B2：将状态机接入 pipeline
  - [x] B2.1：`research/candidate_pool.py` 的字符串 `lifecycle_status` 赋值改为 `CandidateLifecycle.transition()` 调用
  - [x] B2.2：`research/backtest_submission.py`、`research/backtest_polling.py` 同步改造
  - [x] B2.3：`research/submission_gate_service.py` 同步改造
  - [x] B2.4：保留 `INACTIVE_BACKTEST_STATUSES` 兼容映射（从枚举派生集合）
- [x] Task B3：扩展 `AuditTrailWriter` 覆盖全生命周期
  - [x] B3.1：`audit_trail/writer.py` 新增 `record_lifecycle_transition`、`record_gate_decision`、`record_optimization_suggestion`、`record_simulation_writeback` 方法
  - [x] B3.2：每条记录含输入参数、能力集版本、评分版本、门禁版本、模拟配置、结果摘要、变更记录
- [x] Task B4：反过拟合审计补全
  - [x] B4.1：记录每个 Alpha 的来源、变体生成原因、反馈信号、淘汰原因、优化次数、是否触达官方模拟
  - [x] B4.2：质量门禁自动拦截高度相似表达式、参数微调刷分、重复提交、异常高频失败重试
- [x] Task B5：历史回溯查询
  - [x] B5.1：新增按状态/日期/Dataset/Region/Universe/评分/门禁失败原因/模拟结果/表达式相似度过滤的查询接口

## 工作流 C：官方模拟三槽调度器硬化与候选池解耦

- [x] Task C1：调度器一致性硬化
  - [x] C1.1：校验 `BacktestSlotManager.active_limit` 与 `ThreeSlotScheduler.max_slots` 一致
  - [x] C1.2：`web/misc/web_backtest_slots.py:backtest_slot_limit()` 统一从调度器读取
  - [x] C1.3：消除 `ParallelBacktestExecutor`（max_workers=4）与官方 3 槽的混淆风险（文档化其适用场景为多市场批量，非官方模拟）
- [x] Task C2：槽级容错端到端验证
  - [x] C2.1：`CONCURRENT_SIMULATION_LIMIT_EXCEEDED` 仅暂停对应槽，不锁死生产链路
  - [x] C2.2：429 仅触发账号级冷却，候选池继续生产
  - [x] C2.3：网络异常仅重试对应槽
  - [x] C2.4：任务取消、超时中断、状态不明自愈、冷却恢复验证
- [x] Task C3：候选池生产与官方回测解耦
  - [x] C3.1：生产器持续维护候选池容量，不被官方模拟阻塞
  - [x] C3.2：本地评分+门禁先淘汰/排序/优化
  - [x] C3.3：官方模拟只消费 TopK 候选
  - [x] C3.4：官方结果回写触发状态更新/评分校准/优化方向调整，不阻塞生产

## 工作流 D：科学评分与质量门禁服务化

- [x] Task D1：评分服务参与生产决策
  - [x] D1.1：科学评分参与候选排序、淘汰、优化方向选择
  - [x] D1.2：科学评分参与官方模拟优先级决策
- [x] Task D2：质量门禁参与状态流转
  - [x] D2.1：门禁自动决定"继续优化/丢弃归档/候选进入官方模拟队列/进入人工确认"
  - [x] D2.2：门禁判定触发 `LifecycleState` 迁移
- [x] Task D3：评分归因与可导出
  - [x] D3.1：`scoring/attribution.py` 支持多维分析
  - [x] D3.2：所有评分结果、门禁判断、归因理由、触发规则、状态变更可追溯、可回放、可导出
- [x] Task D4：页面作为解释器
  - [x] D4.1：前端展示"为什么这样排序、为什么被拦截、下一步动作"

## 工作流 E：实时监控、状态一致性与错误体验

- [x] Task E1：监控覆盖扩展
  - [x] E1.1：`UnifiedMonitor` 扩展覆盖官方模拟队列、候选池生产、评分服务、质量门禁、登录会话、缓存状态
  - [x] E1.2：模拟结果长期未回写自动检测与中断
  - [x] E1.3：前后端状态不一致自动检测
- [x] Task E2：前端统一状态机
  - [x] E2.1：`useAppState` 补齐 Context Provider，消除 prop drilling 状态漂移
  - [x] E2.2：Dashboard/ConfigPanel/候选池/评分/门禁/模拟队列/历史/系统配置共享一致状态定义
- [x] Task E3：错误体验
  - [x] E3.1：11 类错误（登录失效/缓存不可用/官方限流/模拟并发超限/Dataset 缺失/字段不合规/表达式非法/网络超时/任务取消/队列阻塞/本地服务未启动）转换为原因+影响+建议+恢复入口
  - [x] E3.2：严禁只展示堆栈/空白/未知错误
- [x] Task E4：ConfigPanel 缓存模式回归测试
  - [x] E4.1：补齐 vitest 回归测试，确保缓存模式凭据折叠逻辑不退化
  - [x] E4.2：切换连接状态后 Dashboard/ConfigPanel/全局状态/后端会话状态一致

## 工作流 F：测试体系、CI 门禁、文档与交付

- [x] Task F1：测试缺口补齐
  - [x] F1.1：缓存损坏测试（`official_fields.json` 损坏→进入"需要人工确认"）
  - [x] F1.2：Dataset ID 缺失测试
  - [x] F1.3：移动端交互行为测试（jsdom/Playwright，不再仅静态文本检查）
  - [x] F1.4：并发超限拒绝测试
  - [x] F1.5：会话过期重认证测试
  - [x] F1.6：任务中断恢复测试
- [x] Task F2：前端行为测试
  - [x] F2.1：补齐关键链路 vitest（ConfigPanel 折叠、候选池状态、评分归因展示、门禁拦截展示、模拟队列状态）
- [x] Task F3：CI 门禁补齐
  - [x] F3.1：`quality-gate.yml` 加入 `npm run typecheck`（`tsc -b`）
  - [x] F3.2：加入 `npm run lint`（`eslint`）
  - [x] F3.3：加入 `prettier --check`
  - [x] F3.4：加入 `npm run test`（`vitest run`）
  - [x] F3.5：加入 E2E 冒烟（`tests/e2e/test_real_web_flow.py`，凭据缺失时 skip）
  - [x] F3.6：接入 `scripts/check_capability_registry.py` 与 `scripts/check_brain_contract.py`
  - [x] F3.7：`build-release.yml` 加入构建产物冒烟
  - [x] F3.8：`scripts/check_module_size.py:BASELINE_LINE_LIMITS` 同步当前实际行数
  - [x] F3.9：拆分 3 个超限文件为 re-export 子包
    - [x] F3.9a：`brain_alpha_ops/research/parallel_backtest.py`（382 行）→ `parallel_backtest/` 子包（`__init__.py` + `_executor.py` + `_helpers.py`）
    - [x] F3.9b：`brain_alpha_ops/web/misc/web_backtest_slots.py`（493 行）→ `web_backtest_slots/` 子包（`__init__.py` + `_handlers.py` + `_helpers.py`）
    - [x] F3.9c：`scripts/scan_sensitive_artifacts.py`（503 行）→ `scan_sensitive_artifacts/` 子包（`__init__.py` + `_scanners.py` + `_patterns.py`）+ thin shim
- [x] Task F4：安全扫描强化
  - [x] F4.1：`scripts/scan_sensitive_artifacts.py` 扫描范围确认覆盖 `config_models.py`、`runtime_constants.py`、`secure_credentials.py`
  - [x] F4.2：验证仓库无用户测试凭据字面量痕迹（邮箱与密码由用户本地持有）
  - [x] F4.3：新增 `tests/test_credential_leak_regression.py` 回归测试，扫描 .py/.ts/.tsx/.js/.json/.yml/.yaml/.md 中的凭据字面量与密钥赋值模式
- [x] Task F5：文档补齐
  - [x] F5.1：README 补 ConfigPanel 缓存模式、前端测试、CI 门禁清单、`.trae/specs/` 索引
  - [x] F5.2：README 修正过期指标与失效链接
  - [x] F5.3：新增开发者手册（架构、模块边界、凭据配置、BRAIN 能力集更新流程、三槽调度器、候选池状态机、故障排查）
- [x] Task F6：缺陷跟踪清单与最终交付报告
  - [x] F6.1：建立 `DEFECT_TRACKING.md`（缺陷编号、模块、严重级别、复现步骤、影响范围、根因、修复方案、受影响文件、验证方式、状态、关闭条件）
  - [x] F6.2：输出最终交付报告（已完成/部分完成/未完成/阻塞/风险/建议下一步六类状态）

# Task Dependencies

- Task A1 → A2 → A3（注册表骨架→收编→校验脚本）
- Task B1 → B2 → B3（枚举扩展→接入 pipeline→审计扩展）
- Task B2 依赖 A2（状态机接入需注册表就绪以记录能力集版本）
- Task C1 → C2 → C3（一致性→容错→解耦）
- Task C3 依赖 B2（解耦需状态机接入）
- Task D1 → D2 → D3 → D4（评分服务化→门禁流转→归因→页面）
- Task D2 依赖 B2（门禁流转需状态机）
- Task E1 依赖 C2（监控扩展需调度器容错就绪）
- Task E3 依赖 D4（错误体验需评分/门禁页面就绪）
- Task F1 依赖 B2/C2/D2/E1（测试需被测功能就绪）
- Task F3 依赖 A3/F1（CI 门禁需校验脚本与测试就绪）
- Task F6 依赖全部（交付报告需所有任务完成）

# 可并行任务

- A1 与 B1 可并行（无依赖）
- C1 与 D1 可并行（无依赖）
- E2 与 E3 可并行（前端状态机与错误体验无强依赖）
- F5 文档可与 F1/F2/F3 部分并行
