# Tasks

## 阶段 A：后端核心防线与状态机 Critical

- [ ] Task A1: 修复反过拟合 returns→factor_values 回退链导致虚假 PASS
  - [ ] SubTask A1.1: 修改 `scoring/anti_overfit/service.py:31-56`，禁止 `returns → factor_values` 回退；returns 缺失时显式失败（reason: missing returns data）或使用语义不同的代理
  - [ ] SubTask A1.2: 新增测试：returns 缺失时断言反过拟合检查失败（非 PASS），IC/Spearman 不恒等于 1.0
- [ ] Task A2: 修复 Quality Gate 审计失败跳过状态转换
  - [ ] SubTask A2.1: 修改 `audit_trail/quality_gate.py:216-240` `intercept`，将 `record_gate_decision` 与 `transition(gate_rejected)` 解耦，审计失败仅 ERROR 日志不阻断转换
  - [ ] SubTask A2.2: 新增测试：审计写失败时断言候选仍转换到 gate_rejected
- [ ] Task A3: 移除候选生命周期非法转换静默回退 force_transition（BREAKING）
  - [ ] SubTask A3.1: 修改 `candidate_lifecycle.py:transition()`，非法转换抛 `IllegalTransitionError`
  - [ ] SubTask A3.2: 增加 `force: bool = False` 参数，仅 `force=True` 时 `force_transition`
  - [ ] SubTask A3.3: 排查生产调用方（submission_gate_service、backtest_submission、backtest_polling、audit_trail.quality_gate），迁移到显式 `force=False` 或修复非法转换源
  - [ ] SubTask A3.4: 测试用例显式传 `force=True`
- [ ] Task A4: 修复仿真并发超限 deferred 被计为 failed
  - [ ] SubTask A4.1: 修改 `web_candidates/simulation/_submit.py:102-221`，`CONCURRENT_SIMULATION_LIMIT_EXCEEDED` 分支：候选标记 `deferred_concurrency_limit`（非 failed），`state.failed` 不自增，`stop_new_submissions` 仅暂停受影响槽位
  - [ ] SubTask A4.2: 新增测试：并发超限后断言候选状态为 deferred、failed 不自增、可重试
- [ ] Task A5: 修复真实提交成功后审计失败冒泡为 400
  - [ ] SubTask A5.1: 修改 `web/submissions/web_submission_single.py:189-203`，`save_lifecycle_record` 包入 try/except，失败仅 ERROR 日志 + 指标
  - [ ] SubTask A5.2: 新增测试：审计失败时响应仍为成功
- [ ] Task A6: 修复 Facade 绑定静默吞异常
  - [ ] SubTask A6.1: 修改 `web/__init__.py:210-211`，移除静默吞，异常向上传播；修正 `JOB_REGISTRY = None` 预声明与 `__getattr__` 访问
  - [ ] SubTask A6.2: 新增测试：facade import 异常时断言启动失败且错误指向根因
- [ ] Task A7: 修复 web_cloud 同步任务心跳线程异常吞噬
  - [ ] SubTask A7.1: 修改 `web_cloud/sync_job/_service/_state.py:107` `_heartbeat_loop`，扩大异常捕获或加有限次重启；`stop_heartbeat` join 线程
  - [ ] SubTask A7.2: 新增测试：抛 KeyError 时断言线程不静默退出

## 阶段 B：研究引擎数值正确性 Critical

- [ ] Task B1: 修复 BCa Bootstrap 样本不足静默返回 (0,0)
  - [ ] SubTask B1.1: 修改 `research/convergence/_bootstrap_mixin.py:59-60`，n<5 时返回带 `insufficient_samples` 标记的 CI（非 (0,0)）；清理 `:88-92` 不可达死代码
  - [ ] SubTask B1.2: 修改 `research/convergence/_tracker.py:131-144`，insufficient samples 时 stall 检测视为 "no signal" 而非 "significant decline"
  - [ ] SubTask B1.3: 新增测试：n=3 时不触发误判策略切换
- [ ] Task B2: 修复 Pearson 系数 (n-1)/n 系统性缩小
  - [ ] SubTask B2.1: 修改 `scoring/anti_overfit/utils.py:12-32`，统一 cov 与 std 为同总体或同样本统计量
  - [ ] SubTask B2.2: 新增测试：n=3 时 Pearson 等于标准相关系数（非 0.667×）
- [ ] Task B3: 修复 ProdCorrelation 本地回退按表达式长度放行
  - [ ] SubTask B3.1: 修改 `research/prod_correlation.py:235-268`，本地回退返回 `unknown`/`blocked`（非 `passed=True`），≥100 分支不得放行
  - [ ] SubTask B3.2: 新增测试：API 不可用时长表达式断言不通过硬门禁
- [ ] Task B4: ProdCorrelationService 接入生产流水线
  - [ ] SubTask B4.1: 在评分流水线中调用 `ProdCorrelationService`（非消费 mock 值），或显式标注 gate 为 "degraded: local-only"
  - [ ] SubTask B4.2: 新增测试：流水线调用真实服务或正确标注降级

## 阶段 C：提交安全闭环 Critical（P0/P1）

- [ ] Task C1: 浏览器驱动真实提交闭环可验证（P0）
  - [ ] SubTask C1.1: `ApiExecutionAdapter.submit_alpha()` 限制为 dev/test only，生产路径必须走 Browser backend
  - [ ] SubTask C1.2: e2e 提交验证改用真实浏览器流程（非 `requests` 命中本地 `/api/*`）
  - [ ] SubTask C1.3: 新增/更新 e2e 测试覆盖浏览器提交闭环
- [ ] Task C2: 提交安全语义统一（P1）
  - [ ] SubTask C2.1: 统一三层守门语义，移除歧义 env 旁路：`BRAIN_ALPHA_FORCE_REAL_SUBMIT=1` 须配合 `BRAIN_ALPHA_ENABLE_REAL_SUBMIT_TESTS=1`，否则保持禁用
  - [ ] SubTask C2.2: API 层 `submit_alpha()` 公开入口须显式 browser-backend 确认
  - [ ] SubTask C2.3: 新增测试：单 env 旁路断言仍禁用

## 阶段 D：WebUI Critical

- [ ] Task D1: 修复默认 inline HTML 不存在导致首屏空白
  - [ ] SubTask D1.1: 修改 `web/misc/web_html.py`，`MISSING_TEMPLATE_HTML` 替换为内置引导 HTML（含 frontend 选取、缺失原因、`npm run build` 指引、端口）
  - [ ] SubTask D1.2: 修正 `safe_selected_frontend` 默认回退
  - [ ] SubTask D1.3: 新增测试：React 未构建时返回引导 HTML
- [ ] Task D2: 核心面板接入路由
  - [ ] SubTask D2.1: 修改 `main.tsx`，注册 `/dashboard` `/candidates` `/backtest` `/scoring` `/quality` `/submission` `/config` `/history`
  - [ ] SubTask D2.2: `App.tsx` 中 `setActiveView` 同步 URL，URL 变化同步 activeView
  - [ ] SubTask D2.3: 新增测试：切换面板后刷新停留、后退可回
- [ ] Task D3: 修复 PhaseShell 阻断阶段按钮仍可点
  - [ ] SubTask D3.1: 修改 `components/PhaseShell.tsx:102-107`，阻断/未就绪阶段关键操作区加 `inert`
  - [ ] SubTask D3.2: 新增测试：阻断阶段断言按钮不可点击、不可 Tab 到达

## 阶段 E：UX Critical

- [ ] Task E1: Web 端不可真实提交前置提示
  - [ ] SubTask E1.1: 候选进入提交队列或打开提交面板时展示「Web 端不可真实提交」+ BRAIN 平台外链
  - [ ] SubTask E1.2: 修改 `SubmissionConfirmPanel.tsx` 顶部 banner
  - [ ] SubTask E1.3: 新增测试：打开提交面板断言前置提示可见
- [ ] Task E2: SSE 断连取消须警示云端可能仍在运行
  - [ ] SubTask E2.1: 修改 `hooks/useJobDisconnectedState.ts`，断连取消时展示警示 + 槽位查询入口
  - [ ] SubTask E2.2: 新增测试：断连超时后断言警示与槽位查询入口可见

## 阶段 F：后端 High 修复（容错 + 资源 + 数值）

- [ ] Task F1: 修复 StallMonitor 超限静默放弃（`stall_monitor.py:175-182`）
- [ ] Task F2: 修复 BRAIN 认证仅 basic 单方法（`brain_api/official_auth.py:23-50`）
- [ ] Task F3: 修复 concurrent_simulate/check 超时 cancel 无效（`brain_api/official_simulation/_mixin.py:124-126`）
- [ ] Task F4: 修复并行回测 future.result() 无超时（`research/parallel_backtest/_executor.py:234`）
- [ ] Task F5: 修复心跳线程不重启（`web/business/web_run_job.py:265-267`）
- [ ] Task F6: 修复 WebSocket publish 不清理死订阅者（`web/ws.py:70-74`）
- [ ] Task F7: 修复 V5-001 无界分页（`brain_api/pagination_limits.py` `MAX_USER_ALPHAS_PAGES = None`）
- [ ] Task F8: 修复 Regime 压力测试全零 Sharpe 误判满分（`scoring/anti_overfit/regime_stress.py:51-64`）
- [ ] Task F9: 统一重试阈值运算符（`scoring/anti_overfit/compliance.py:158` 与 `audit_trail/quality_gate.py:156`）
- [ ] Task F10: 修复 Ranker scorecard None 致崩溃（`scoring/_ranker.py:88-98,181-183`）
- [ ] Task F11: 修复审计 64KB 截断丢失关键字段（`audit_trail/writer.py:67-79`、`lifecycle_writer.py:42-50`）
- [ ] Task F12: 修复 Evidence 清理单点解析失败中断循环（`monitoring/evidence.py:64-85`）
- [ ] Task F13: 修复诊断快照无异常隔离（`production_diagnostics/_snapshot.py:37-80`）
- [ ] Task F14: 修复官方 context 回退路径解析为包内 data（`web_cloud/snapshot/_official_context_read.py:230-232`）
- [ ] Task F15: 修复无身份候选 update 追加为新行（`web_candidates/simulation_state/_candidates.py:59-118`）
- [ ] Task F16: 修复 BaoStock logout 不在 finally（`data/ashare_adapter/_provider.py:88-110`）
- [ ] Task F17: 修复 FieldDatasetMapper 并发不安全（`data/field_dataset_mapper.py:14-15,79-93`）
- [ ] Task F18: 修复 check 证据持久化失败静默（`web_candidates/check_evidence.py:48-55`）
- [ ] Task F19: 修复 save_assistant_guidance 异常丢失生成结果（`web_candidates/generation/_generation.py:275-279`）
- [ ] Task F20: 修复 max_official_concurrent_simulations=0 被改写（`web_candidates/simulation/__init__.py:107`）
- [ ] Task F21: 修复滚动验证 decay_ratio 符号反转（`research/rolling_validation.py:38`）
- [ ] Task F22: 修复 ic_stability 分量上限不对称（`scoring/anti_overfit/ic_stability.py:40-42` 与 `suite.py:92-98`）
- [ ] Task F23: 修复 RecordSqliteIndex.refresh 仅索引尾部 10000（`research/record_sqlite_index.py:53-78`）
- [ ] Task F24: 修复 Placebo 全局固定 seed=42（`scoring/anti_overfit/placebo.py:27-28`）
- [ ] Task F25: 修复 sub_universe_sharpe 本地按符号下标前半切片（`research/local_backtest/metrics.py:186-200`）

## 阶段 G：WebUI High

- [ ] Task G1: 修复 useCandidateTableData 刷新循环（`hooks/useCandidateTableData.ts:149-198`）
- [ ] Task G2: 修复 OfficialBacktestSlots 5s 全量 refreshAll（`components/OfficialBacktestSlots.tsx:20-30`）
- [ ] Task G3: 修复 JobMonitor SSE 随 Dashboard 卸载断连（提升到 App 层 context）
- [ ] Task G4: 所有 Modal 接入 FocusTrap（ConfirmDialog、KeyboardShortcutsHelp、提交确认等）
- [ ] Task G5: 移除死代码 ToastProvider，统一 Toast 系统（`App.tsx:110`、`components/Toast.tsx:289-368`）

## 阶段 H：UX High

- [ ] Task H1: 批量提交 dry-run 预览与部分失败明细（`web/submissions/web_submission_batch.py`）
- [ ] Task H2: 配置保存生效条件提示（`hooks/useConfigForm.ts`）
- [ ] Task H3: 限流倒计时读取后端 retry_after（`helpers/connectionErrorGuide.ts`）
- [ ] Task H4: 前台任务完成可见提示（`hooks/useJobWatchdog.ts`、`useJobNotifications`）

## 阶段 I：验证

- [ ] Task I1: 全量回归测试通过（`python3 -m pytest tests/ -q`）
- [ ] Task I2: 前端测试通过（`cd brain_alpha_ops/web/react_app && npm run test && npm run typecheck`）
- [ ] Task I3: checklist.md 全部 checkpoint 验证通过

# Task Dependencies

- 阶段 A 各任务最高优先，A3 须先于阶段 F（F 中状态迁移依赖正确）
- 阶段 B 各任务相互独立，可并行
- 阶段 C 提交安全闭环独立
- 阶段 D 各任务相互独立，可并行；D3 依赖 D2 的 App 层结构调整
- 阶段 E 各任务相互独立，可并行
- 阶段 F 各任务相互独立，可并行（F9 依赖 A2 完成后的 quality_gate 状态）
- 阶段 G 各任务相互独立，可并行；G3 依赖 D2
- 阶段 H 各任务相互独立，可并行
- 阶段 I 依赖所有前置阶段完成
