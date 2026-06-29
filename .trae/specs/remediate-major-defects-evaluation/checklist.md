# Checklist

## 阶段 A：后端 Critical

- [ ] Facade 绑定安装失败时异常向上传播，日志记录原始堆栈，不再静默吞
- [ ] `JOB_REGISTRY` 不再出现 `None` 后被访问为 `AttributeError` 的情况
- [ ] 真实提交成功后审计写失败不再冒泡为 400 响应
- [ ] 真实提交成功响应在审计失败时仍返回成功
- [ ] 审计失败记录到 ERROR 级日志与监控指标
- [ ] `candidate_lifecycle.transition()` 非法转换抛 `IllegalTransitionError`，不静默回退 `force_transition`
- [ ] 仅 `force=True` 时才允许 `force_transition`，且仅测试用例使用
- [ ] 生产调用方（submission_gate_service / backtest_submission / backtest_polling / audit_trail.quality_gate）已迁移

## 阶段 B：后端 High

- [ ] StallMonitor 超过 max_retry_count 后调用 `_on_interrupt` 中断作业并升级告警
- [ ] BRAIN 认证 401 时尝试 token 刷新与备选认证方法，指数退避后有限次重试
- [ ] concurrent_simulate/concurrent_check 超时后显式释放槽位，不依赖无效 `future.cancel()`
- [ ] 并行回测 `as_completed` 与 `future.result()` 有批次级 timeout，单作业卡死不阻塞全批
- [ ] 心跳线程异常退出前有限次重启
- [ ] WebSocket publish 失败 sender 从 `_subscribers` 移除，延迟不累积

## 阶段 C：WebUI Critical

- [ ] React 未构建且 inline 模板缺失时返回内置引导 HTML（含诊断信息），非 `Template not found`
- [ ] `safe_selected_frontend` 默认回退不再指向不存在的 inline
- [ ] 核心面板（dashboard/candidates/backtest/scoring/quality/submission/config/history）接入路由
- [ ] 切换面板后 URL 变化，刷新停留，浏览器后退可回
- [ ] PhaseShell 阻断/未就绪阶段关键操作区 `inert` 或 `pointer-events:none`
- [ ] 阻断阶段按钮不可点击、不可 Tab 到达

## 阶段 D：WebUI High

- [ ] `useCandidateTableData` 无刷新循环，切换到 CandidateTable 无高频连环请求
- [ ] `OfficialBacktestSlots` 仅轮询 `/api/backtest_slots`，不每 5s 全量 `refreshAll`
- [ ] 任务 SSE 连接独立于 Dashboard 视图生命周期，切离 Dashboard 后进度仍实时更新
- [ ] 所有 Modal 接入 FocusTrap，Tab 不跳出背景可点击元素
- [ ] 死代码 ToastProvider 已移除，单一 Toast 系统生效

## 阶段 E：UX Critical/High

- [ ] 候选进入提交队列或打开提交面板时前置提示「Web 端不可真实提交」+ BRAIN 平台外链
- [ ] SSE 断连超时取消时展示「云端可能仍在运行」警示 + 槽位查询入口
- [ ] 批量提交响应包含 `submitted` 与 `failed` 明细列表
- [ ] 批量提交前显示候选清单预览
- [ ] 涉及 Final 常量的配置项保存后提示「需重启服务生效」并标注受影响项
- [ ] 限流倒计时读取后端 `retry_after`，非固定 30s
- [ ] 前台任务完成时有 toast/徽标提示，不限于 `document.hidden`

## 阶段 F：验证

- [ ] `python3 -m pytest tests/ -q` 全量通过
- [ ] `cd brain_alpha_ops/web/react_app && npm run test` 通过
- [ ] `cd brain_alpha_ops/web/react_app && npm run typecheck` 通过
- [ ] 无新增回归（关键场景：启动、认证、回测、评分、提交队列、SSE 推送）
