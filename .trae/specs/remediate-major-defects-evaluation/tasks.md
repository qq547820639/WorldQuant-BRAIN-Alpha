# Tasks

## 阶段 A：后端 Critical 修复（账户安全 + 状态机 + 启动稳定性）

- [ ] Task A1: 修复 Facade 绑定静默吞异常导致整站不可用
  - [ ] SubTask A1.1: 移除 `_install_facade_bindings` 中的 `try/except Exception` 静默吞异常，改为异常向上传播（保留日志但不吞）
  - [ ] SubTask A1.2: 修正 `web/__init__.py` 模块级 `JOB_REGISTRY = None` 预声明与 `__getattr__` 访问逻辑，绑定未完成时给出明确启动失败原因
  - [ ] SubTask A1.3: 新增测试：模拟 facade 子模块 import 异常，断言服务启动失败且错误信息指向根因
- [ ] Task A2: 修复真实提交成功后审计写失败冒泡为 400 导致重复提交
  - [ ] SubTask A2.1: 在 `web/submissions/web_submission_single.py` 中将 `api.authenticate()` + `api.submit_alpha()` 后的 `save_lifecycle_record()` 包入 try/except，失败仅 ERROR 日志 + 指标，不抛出
  - [ ] SubTask A2.2: 提交成功后响应必须返回成功（即使审计失败）
  - [ ] SubTask A2.3: 新增测试：模拟 `save_lifecycle_record` 抛异常，断言响应仍为成功、审计失败被记录
- [ ] Task A3: 移除候选生命周期非法转换静默回退 force_transition（BREAKING）
  - [ ] SubTask A3.1: 修改 `candidate_lifecycle.py:transition()`，非法转换（`lc.transition(target)` 返回 False）抛 `IllegalTransitionError`
  - [ ] SubTask A3.2: 增加 `force: bool = False` 参数，仅 `force=True` 时调用 `force_transition`
  - [ ] SubTask A3.3: 排查生产调用方（`submission_gate_service.py`、`backtest_submission.py`、`backtest_polling.py`、`audit_trail/quality_gate.py`），确认迁移到显式 `force=False` 或修复非法转换源
  - [ ] SubTask A3.4: 测试用例显式传 `force=True`，更新相关测试

## 阶段 B：后端 High 修复（容错 + 资源 + 超时）

- [ ] Task B1: 修复 StallMonitor 超限静默放弃
  - [ ] SubTask B1.1: 修改 `stall_monitor.py:_auto_interrupt`，`stall_count > max_retry_count` 时调用 `_on_interrupt` 中断作业并升级告警（非 `return`）
  - [ ] SubTask B1.2: 新增测试：超限后断言作业被中断、告警升级
- [ ] Task B2: 修复 BRAIN 认证仅 basic 单方法、401 无刷新重试
  - [ ] SubTask B2.1: 修改 `brain_api/official_auth.py:authenticate()`，401 时尝试 token 刷新与备选认证方法（token / cookie），指数退避后有限次重试
  - [ ] SubTask B2.2: 新增测试：basic 401 后回退 token 认证成功
- [ ] Task B3: 修复 concurrent_simulate/concurrent_check 超时 cancel 无效线程泄漏
  - [ ] SubTask B3.1: 修改 `brain_api/official_simulation/_mixin.py`，超时后显式标记槽位释放，改用可中断执行机制（如协作式取消标志）替代无效 `future.cancel()`
  - [ ] SubTask B3.2: 新增测试：超时后槽位被释放、无累积泄漏
- [ ] Task B4: 修复并行回测 future.result() 无超时阻塞全批
  - [ ] SubTask B4.1: 修改 `research/parallel_backtest/_executor.py`，`as_completed` 与 `future.result()` 加批次级 timeout，超时作业标记失败并继续收集其余结果
  - [ ] SubTask B4.2: 新增测试：单作业卡死不阻塞其余作业结果收集
- [ ] Task B5: 修复心跳线程异常退出不重启
  - [ ] SubTask B5.1: 修改 `web/business/web_run_job.py:_heartbeat_loop`，异常退出前有限次（如 3 次）重启，全部失败才放弃
  - [ ] SubTask B5.2: 新增测试：心跳异常后断言线程重启
- [ ] Task B6: 修复 WebSocket publish 不清理死亡订阅者
  - [ ] SubTask B6.1: 修改 `web/ws.py:publish`，失败 sender 从 `_subscribers` 移除
  - [ ] SubTask B6.2: 新增测试：死连接累积后断言被清理、publish 延迟不增长

## 阶段 C：WebUI Critical 修复（首屏 + 路由 + 阻断交互）

- [ ] Task C1: 修复默认 inline HTML 不存在导致首屏空白
  - [ ] SubTask C1.1: 修改 `web/misc/web_html.py`，`MISSING_TEMPLATE_HTML` 替换为内置引导 HTML（含 frontend 选取结果、缺失原因、`npm run build` 指引、端口信息）
  - [ ] SubTask C1.2: 修正 `safe_selected_frontend` 默认回退逻辑，避免回退到不存在的 inline
  - [ ] SubTask C1.3: 新增测试：React 未构建时返回引导 HTML 而非 `Template not found`
- [ ] Task C2: 核心面板接入路由
  - [ ] SubTask C2.1: 修改 `main.tsx`，注册 `/dashboard` `/candidates` `/backtest` `/scoring` `/quality` `/submission` `/config` `/history` 路由
  - [ ] SubTask C2.2: `App.tsx` 中 `setActiveView` 同步更新 URL（`navigate`），URL 变化同步更新 `activeView`
  - [ ] SubTask C2.3: 新增测试：切换面板后刷新停留、后退可回
- [ ] Task C3: 修复 PhaseShell 阻断阶段按钮仍可点
  - [ ] SubTask C3.1: 修改 `components/PhaseShell.tsx`，`statusTone` 为 `pending`/`blocked` 时对关键操作区加 `inert` 属性（或 `pointer-events:none` + 可聚焦元素 `tabindex=-1`）
  - [ ] SubTask C3.2: 新增测试：阻断阶段断言按钮不可点击、不可 Tab 到达

## 阶段 D：WebUI High 修复（数据流 + SSE + 可访问性）

- [ ] Task D1: 修复 useCandidateTableData 刷新循环
  - [ ] SubTask D1.1: 修改 `hooks/useCandidateTableData.ts`，拆分 `loadCandidates` 对 `globalCandidatesData` 的依赖（用 ref 锁或 useCallback 正确依赖）
  - [ ] SubTask D1.2: 新增测试：切换到 CandidateTable 后断言无高频连环请求
- [ ] Task D2: 修复 OfficialBacktestSlots 5s 全量 refreshAll
  - [ ] SubTask D2.1: 修改 `components/OfficialBacktestSlots.tsx`，`load` 改为仅请求 `/api/backtest_slots`
  - [ ] SubTask D2.2: 新增测试：停留回测监控页断言不拉 `/api/candidates`
- [ ] Task D3: 修复 JobMonitor SSE 随 Dashboard 卸载断连
  - [ ] SubTask D3.1: 将任务 SSE 连接提升到 App 层 context/provider，独立于 Dashboard 视图生命周期
  - [ ] SubTask D3.2: 新增测试：切离 Dashboard 后 TopBar 进度仍实时更新
- [ ] Task D4: 所有 Modal 接入 FocusTrap
  - [ ] SubTask D4.1: 修改 `ConfirmDialog.tsx`、`KeyboardShortcutsHelp.tsx`、提交确认等 Modal，包裹 `A11y/FocusTrap`
  - [ ] SubTask D4.2: 新增测试：Modal 打开后 Tab 不跳出背景可点击元素
- [ ] Task D5: 移除死代码 ToastProvider，统一 Toast 系统
  - [ ] SubTask D5.1: 删除 `App.tsx` 中的 `<ToastProvider>` 包裹与 `components/Toast.tsx` 中的 ToastProvider/Container 死代码
  - [ ] SubTask D5.2: 确认无业务代码引用 `@/components/Toast` 的 `useToast`
  - [ ] SubTask D5.3: 新增测试：单一 Toast 容器渲染

## 阶段 E：UX Critical/High 修复（提交闭环 + 反馈 + 配置 + 限流）

- [ ] Task E1: Web 端不可真实提交前置提示
  - [ ] SubTask E1.1: 候选进入提交队列或打开提交面板时，明确展示「Web 端不可真实提交，最终提交需在 BRAIN 平台完成」+ BRAIN 平台外链
  - [ ] SubTask E1.2: 修改 `SubmissionConfirmPanel.tsx` 顶部 banner，前置告知
  - [ ] SubTask E1.3: 新增测试：打开提交面板断言前置提示可见
- [ ] Task E2: SSE 断连取消须警示云端可能仍在运行
  - [ ] SubTask E2.1: 修改 `hooks/useJobDisconnectedState.ts`，断连取消时展示明确警示 + 槽位查询入口
  - [ ] SubTask E2.2: 新增测试：断连超时后断言警示文案与槽位查询入口可见
- [ ] Task E3: 批量提交 dry-run 预览与部分失败明细
  - [ ] SubTask E3.1: 修改 `web/submissions/web_submission_batch.py`，响应包含 `submitted` 与 `failed` 两个明细列表
  - [ ] SubTask E3.2: 前端批量提交前显示候选清单预览
  - [ ] SubTask E3.3: 新增测试：部分失败断言明细列表正确
- [ ] Task E4: 配置保存生效条件提示
  - [ ] SubTask E4.1: 修改 `hooks/useConfigForm.ts`，涉及 Final 常量的配置项保存后提示「需重启服务生效」并标注受影响项
  - [ ] SubTask E4.2: 新增测试：保存涉及 Final 常量的配置断言提示出现
- [ ] Task E5: 限流倒计时读取后端 retry_after
  - [ ] SubTask E5.1: 修改 `helpers/connectionErrorGuide.ts`，rate_limit 倒计时读取后端 `retry_after` 而非固定 30s
  - [ ] SubTask E5.2: 新增测试：后端返回 retry_after=60 断言倒计时为 60s
- [ ] Task E6: 前台任务完成可见提示
  - [ ] SubTask E6.1: 修改 `hooks/useJobWatchdog.ts` 与 `useJobNotifications`，前台完成时补充 toast/徽标提示（不限于 `document.hidden`）
  - [ ] SubTask E6.2: 新增测试：前台任务完成断言 toast 可见

## 阶段 F：验证

- [ ] Task F1: 全量回归测试通过（`python3 -m pytest tests/ -q`）
- [ ] Task F2: 前端测试通过（`cd brain_alpha_ops/web/react_app && npm run test && npm run typecheck`）
- [ ] Task F3: checklist.md 全部 checkpoint 验证通过

# Task Dependencies

- Task A1 独立（启动稳定性，最高优先）
- Task A2 独立（账户安全，最高优先）
- Task A3 影响后端调用方，须先于阶段 B 完成（B 中状态迁移依赖正确）
- 阶段 B 各任务相互独立，可并行
- 阶段 C 各任务相互独立，可并行
- Task D3 依赖 Task C2（路由）的 App 层结构调整
- 阶段 E 各任务相互独立，可并行
- 阶段 F 依赖所有前置阶段完成
