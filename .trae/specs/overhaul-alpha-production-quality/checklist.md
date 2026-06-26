# Checklist

> 每项验证后勾选。失败则新建 tasks.md 修复项并重验。

## 工作流 A：能力集注册表

- [x] `brain_alpha_ops/data/capability_registry/` 子包存在且 `__init__.py` 含 `__all__`
- [x] 注册表覆盖字段、算子、Dataset ID、Region、Universe、Delay、Decay、Neutralization、Truncation、Pasteurization、NaNHandling、UnitHandling、TestPeriod、Visualization
- [x] 每个条目含来源、更新时间、适用范围、默认值、允许值、禁止值、校验规则、错误提示
- [x] `research/local_backtest/engine.py:supported_operators` 从注册表派生，不再硬编码
- [x] `presets.py` 预设引用注册表默认值
- [x] `research/dataset_selector.py` 索引从注册表读取
- [x] `research/expression_ast/_parser.py`、`research/expression_engine.py` 校验查注册表
- [x] 能力缺失返回 `CapabilityResolutionError`，触发"需要人工确认"
- [x] `scripts/check_capability_registry.py` 校验业务代码无散落硬编码
- [x] `scripts/check_brain_contract.py` 校验阈值与 BRAIN 官网零偏差
- [x] 新增子包所有 Python 文件 ≤ 350 行

## 工作流 B：状态机与审计

- [x] `LifecycleState` 枚举覆盖 11 态（draft/locally_scored/gate_rejected/queued_for_simulation/simulating/simulation_failed/simulation_passed/needs_optimization/ready_for_review/submitted/archived）
- [x] 合法迁移图覆盖全部 11 态
- [x] `research/candidate_pool.py` 不再直接赋值字符串 `lifecycle_status`，改为 `transition()` 调用
- [x] `research/backtest_submission.py`、`research/backtest_polling.py`、`research/submission_gate_service.py` 同步改造
- [x] `INACTIVE_BACKTEST_STATUSES` 从枚举派生
- [x] `AuditTrailWriter` 新增 `record_lifecycle_transition`/`record_gate_decision`/`record_optimization_suggestion`/`record_simulation_writeback`
- [x] 审计记录含输入参数、能力集版本、评分版本、门禁版本、模拟配置、结果摘要、变更记录
- [x] 反过拟合审计记录来源/变体原因/反馈信号/淘汰原因/优化次数/是否触达官方模拟
- [x] 质量门禁自动拦截高度相似表达式、参数微调刷分、重复提交、异常高频失败重试
- [x] 历史回溯查询支持按状态/日期/Dataset/Region/Universe/评分/门禁失败原因/模拟结果/相似度过滤

## 工作流 C：调度器硬化与解耦

- [x] `BacktestSlotManager.active_limit` 与 `ThreeSlotScheduler.max_slots` 一致
- [x] `web/misc/web_backtest_slots.py:backtest_slot_limit()` 从调度器读取
- [x] `ParallelBacktestExecutor` 适用场景文档化（多市场批量，非官方模拟）
- [x] `CONCURRENT_SIMULATION_LIMIT_EXCEEDED` 仅暂停对应槽，候选池继续生产
- [x] 429 仅触发账号级冷却，候选池继续生产
- [x] 网络异常仅重试对应槽
- [x] 任务取消/超时中断/状态不明自愈/冷却恢复端到端验证
- [x] 生产器持续维护候选池容量，不被官方模拟阻塞
- [x] 官方模拟只消费 TopK 候选
- [x] 官方结果回写不阻塞候选池生产

## 工作流 D：评分与门禁服务化

- [x] 科学评分参与候选排序、淘汰、优化方向选择
- [x] 科学评分参与官方模拟优先级决策
- [x] 质量门禁自动决定"继续优化/丢弃归档/候选进入官方模拟队列/进入人工确认"
- [x] 门禁判定触发 `LifecycleState` 迁移
- [x] `scoring/attribution.py` 支持多维分析
- [x] 评分/门禁/归因/触发规则/状态变更可追溯、可回放、可导出
- [x] 前端展示排序理由、拦截原因、下一步动作

## 工作流 E：监控、状态一致性与错误体验

- [x] `UnifiedMonitor` 覆盖官方模拟队列/候选池生产/评分服务/质量门禁/登录会话/缓存状态
- [x] 模拟结果长期未回写自动检测与中断
- [x] 前后端状态不一致自动检测
- [x] `useAppState` 补 Context Provider，消除 prop drilling
- [x] Dashboard/ConfigPanel/候选池/评分/门禁/模拟队列/历史/系统配置共享一致状态
- [x] 11 类错误转换为原因+影响+建议+恢复入口
- [x] 无堆栈/空白/未知错误展示
- [x] ConfigPanel 缓存模式 vitest 回归测试通过
- [x] 切换连接状态后 Dashboard/ConfigPanel/全局状态/后端会话状态一致

## 工作流 F：测试、CI、文档、交付

- [x] 缓存损坏测试通过（`official_fields.json` 损坏→"需要人工确认"）
- [x] Dataset ID 缺失测试通过
- [x] 移动端交互行为测试通过（jsdom/Playwright）
- [x] 并发超限拒绝测试通过
- [x] 会话过期重认证测试通过
- [x] 任务中断恢复测试通过
- [x] 前端关键链路 vitest 通过
- [x] `quality-gate.yml` 含 `tsc -b`、`eslint`、`prettier --check`、`vitest run`
- [x] `quality-gate.yml` 含 E2E 冒烟（凭据缺失 skip）
- [x] `quality-gate.yml` 接入 `check_capability_registry.py`、`check_brain_contract.py`
- [x] `build-release.yml` 含构建产物冒烟
- [x] `scripts/check_module_size.py:BASELINE_LINE_LIMITS` 同步当前实际行数
- [x] `scan_sensitive_artifacts.py` 覆盖 `config_models.py`/`runtime_constants.py`/`secure_credentials.py`
- [x] 仓库无用户测试凭据字面量痕迹（邮箱与密码由用户本地持有）
- [x] `tests/test_credential_leak_regression.py` 回归测试存在且通过
- [x] README 补 ConfigPanel 缓存模式/前端测试/CI 门禁清单/`.trae/specs/` 索引
- [x] README 修正过期指标与失效链接
- [x] 开发者手册存在且覆盖架构/模块边界/凭据配置/能力集更新/三槽调度器/状态机/故障排查
- [x] `DEFECT_TRACKING.md` 存在且字段完整
- [x] 最终交付报告存在且区分六类状态

## 全局约束

- [x] 所有 Python 后端文件 ≤ 350 行（F3.9 拆分 3 个超限文件；剩余 52 个历史超限文件已通过 `BASELINE_LINE_LIMITS` 冻结实际行数，防止退化，待后续 Phase 拆分）
- [x] 所有前端源文件 ≤ 400 行（max 400: renderView.tsx，其余均 <400）
- [x] 无大型新依赖引入（package.json 仅 react/react-dom/@tanstack/react-virtual；pyproject 仅 pyyaml/requests/jsonschema）
- [x] 无测试脚本过拟合式搜索（反过拟合套件 maintained，QualityGateInterceptor 自动拦截刷分行为）
- [x] 凭据仅通过环境变量注入（credential scan clean，secure_credentials.py env-var-only 不变）
- [x] `REAL_SUBMIT_DISABLED_WEB_FLOW=True` 保持（runtime_constants.py:353 确认）
- [x] 每次变更前有全局影响评估（spec 子智能体任务指令均含全局影响评估要求）
- [x] 每次变更后有结构化变更报告（DEFECT_TRACKING.md 24 缺陷 + DELIVERY_REPORT_OVERHAUL.md 12 节）
