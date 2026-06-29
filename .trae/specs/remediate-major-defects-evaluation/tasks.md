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

## 阶段 J：安全 Critical（部署 + 证据 + 旁路 + 脱敏）

- [ ] Task J1: Docker 容器不以 root 运行 + evidence 目录不 chmod 777
  - [ ] SubTask J1.1: 修改 `Dockerfile`，添加非 root `USER`，移除 `chmod 777`，evidence 目录改为受限权限
  - [ ] SubTask J1.2: 修改 `docker-compose.yml`，绑定 `127.0.0.1:8765:8765`，加 `cap_drop: [ALL]`、`security_opt: [no-new-privileges:true]`、`read_only` 与资源限制
  - [ ] SubTask J1.3: 验证容器以非 root 启动、evidence 目录非 777
- [ ] Task J2: 证据归档脱敏
  - [ ] SubTask J2.1: 修改 `monitoring/evidence.py:archive_session` 与 `pipeline_evidence.py`，HAR 文件 redact Authorization/Set-Cookie/Cookie 头，network_logs/console_logs 走 `redact_text`
  - [ ] SubTask J2.2: 新增测试：归档后断言 HAR 无明文凭证、日志已脱敏
- [ ] Task J3: REAL_SUBMIT 旁路改用进程内可信判定
  - [ ] SubTask J3.1: 修改 `runtime_constants.py:real_submit_test_override_enabled`，移除 `PYTEST_CURRENT_TEST` env 判定，改用 `sys.modules` 检查 pytest 实际在进程内，或直接移除该旁路
  - [ ] SubTask J3.2: 新增测试：生产 env 设置三个变量断言仍禁用
- [ ] Task J4: 日志脱敏覆盖纯字母 token
  - [ ] SubTask J4.1: 修改 `redaction.py:126-130` `_SECRET_FRAGMENT_RE`，移除强制 `\d` 要求
  - [ ] SubTask J4.2: 新增测试：纯字母 token（如 `token-abc-def-xyz`）断言被脱敏
- [ ] Task J5: web_security allow_remote 防 DNS rebinding
  - [ ] SubTask J5.1: 修改 `web/security/web_security.py:is_allowed_local_request`，allow_remote 时信任锚改为配置 allowlist（非 Host 头）
  - [ ] SubTask J5.2: 新增测试：Host: evil.com + Origin: http://evil.com 断言被拒
- [ ] Task J6: CI 真正检查依赖 CVE
  - [ ] SubTask J6.1: 修改 `.github/workflows/quality-gate.yml`，移除 `npm audit --audit-level=critical` 的 `continue-on-error`
  - [ ] SubTask J6.2: 新增 `pip-audit` 步骤扫描 Python 依赖
  - [ ] SubTask J6.3: 统一 Python 版本（Docker/CI/pyproject 一致，如 3.12）

## 阶段 K：Agent / MCP / LLM / Browser Critical

- [ ] Task K1: MCP stdio 不被长轮询工具阻塞
  - [ ] SubTask K1.1: 修改 `mcp_server.py:serve_stdio`，长轮询工具派发到 worker 线程，主循环继续读取 stdin；或返回 progress notification
  - [ ] SubTask K1.2: 新增测试：长轮询调用期间其他工具可被服务、notifications/cancelled 可消费
- [ ] Task K2: LLM 配额账本实际生效
  - [ ] SubTask K2.1: 修改 `research/llm_service/_service_review.py` 与 `_service_guidance.py`，调用前 `wait_for_quota`、调用后 `record` token、预算耗尽 `budget_exhausted` 停止
  - [ ] SubTask K2.2: 新增测试：超 200K token 预算断言停止 LLM 调用
- [ ] Task K3: Browser 提交幂等键持久化或不淘汰
  - [ ] SubTask K3.1: 修改 `browser/execution_adapter/_submit.py` 与 `_base.py`，幂等键持久化到磁盘或使用更大 store，不淘汰可重放键
  - [ ] SubTask K3.2: 新增测试：超 1000 键或重启后断言重放被拒
- [ ] Task K4: Browser 登录判定可靠
  - [ ] SubTask K4.1: 修改 `browser/brain_ui_runner.py:267` 与 `_base.py:98-100`，移除 `nav` 通用选择器，改用登录页特定负向信号（密码字段、登录错误消息）
  - [ ] SubTask K4.2: 新增测试：错误凭证停留在登录页断言 is_logged_in=False
- [ ] Task K5: BrainBrowserRunner weakref.finalize 修复
  - [ ] SubTask K5.1: 修改 `browser/brain_ui_runner.py:71`，finalizer 通过闭包延迟求值（或用 `weakref.finalize(self, _cleanup, self_ref)` 内部读取属性），不传 None
  - [ ] SubTask K5.2: 新增测试：异常逃逸 with 块后断言 playwright 资源释放
- [ ] Task K6: LLMService.cross_review_expression 线程安全
  - [ ] SubTask K6.1: 修改 `research/llm_service/_service_review.py:76-83`，加锁保护 provider 交换
  - [ ] SubTask K6.2: 新增测试：并发交叉评审断言无串号
- [ ] Task K7: review_expression 离线 fallback 可达
  - [ ] SubTask K7.1: 修改 `research/llm_service/_service_review.py:37-52`，重试耗尽后实际调用 `_offline_review`（移除死代码）
  - [ ] SubTask K7.2: 新增测试：provider 持续异常断言返回离线评审结果

## 阶段 L：架构与配置 High

- [ ] Task L1: 生产 pipeline 接入 execution_backend
  - [ ] SubTask L1.1: 修改 `runner.py` 与 Web `_handle_pipeline_start`，构造 pipeline 时传 `execution_backend`（生产 browser 模式）
  - [ ] SubTask L1.2: 启动时调用 `backend_registration.register_all_backends()`
  - [ ] SubTask L1.3: `register_backend` 增加重复注册检测
  - [ ] SubTask L1.4: 新增测试：生产路径断言使用 browser backend
- [ ] Task L2: registry 校验修正枚举值误判
  - [ ] SubTask L2.1: 修改 `registry_validation.py:237-245`，区分数据字段与枚举值，不再把 settings_options 当字段集
  - [ ] SubTask L2.2: 新增测试：registry 校验不再必然误报 BLOCKING
- [ ] Task L3: strategy profile_id 包含 delay
  - [ ] SubTask L3.1: 修改 `research/strategy_lifecycle.py:161-167`，profile_id 哈希种子加 delay
  - [ ] SubTask L3.2: 新增测试：同名不同 delay 的 profile 断言 id 不同、rewards 不串扰
- [ ] Task L4: strategy_switch.build_application 越界不静默取模
  - [ ] SubTask L4.1: 修改 `research/strategy_switch.py:89-90`，索引越界时抛异常或显式处理，不静默取模映射
  - [ ] SubTask L4.2: 新增测试：索引 ≥ n_profiles 断言不静默映射错误 profile
- [ ] Task L5: 参数审计覆盖 official_api 全部参数
  - [ ] SubTask L5.1: 修改 `parameter_audit.py:26-41` `_API_ATTR_TO_CANONICAL`，补全 cache_dir/context_cache_ttl_seconds/timeout_seconds/rate_limit_retry_attempts 等 10+ 参数
  - [ ] SubTask L5.2: 新增测试：timeout_seconds 篡改断言产生 finding
- [ ] Task L6: lifecycle_records 加上限
  - [ ] SubTask L6.1: 修改 `research/runtime_service.py:73-86`，append 后截断（如 last 500），去重窗口相应调整
  - [ ] SubTask L6.2: 新增测试：长跑后断言 lifecycle_records 有上限
- [ ] Task L7: convergence_stats 防除零与越界
  - [ ] SubTask L7.1: 修改 `scoring/history.py:50-67`，scores 为空时返回默认值，不触发 ZeroDivisionError/IndexError
  - [ ] SubTask L7.2: 新增测试：records 缺 total_score 字段断言不崩溃
- [ ] Task L8: build_attribution_tree 用 .get() 而非硬下标
  - [ ] SubTask L8.1: 修改 `scoring/attribution.py:147-181`，empirical/checklist item 取值改用 `.get()` 带默认
  - [ ] SubTask L8.2: 新增测试：不完整 scorecard 断言归因接口不崩溃
- [ ] Task L9: StrategySwitchService._explore 防除零
  - [ ] SubTask L9.1: 修改 `research/strategy_switch.py:60-62`，bandit_counts 全零时 max_count 兜底为 1
  - [ ] SubTask L9.2: 新增测试：全零计数断言不崩溃
- [ ] Task L10: _launch_monitor 修正 exe 名
  - [ ] SubTask L10.1: 修改 `_launch_monitor.py:14`，`BrainAlphaProd.exe` 改为 `BrainAlphaConsole.exe`，Popen 加 try/except
  - [ ] SubTask L10.2: 验证 Windows 上 launch monitor 可启动
- [ ] Task L11: SBOM 含传递依赖
  - [ ] SubTask L11.1: 修改 `scripts/generate_sbom.py`，读取 `requirements.lock` 与 `package-lock.json` 提取传递依赖
  - [ ] SubTask L11.2: 验证 SBOM 含 urllib3/certifi 等传递依赖

## 阶段 M：解耦流水线 / 校准 / 进化 / 调度 Critical

- [ ] Task M1: DecoupledPipeline SharedState 线程安全
  - [ ] SubTask M1.1: 修改 `research/decoupled_pipeline/_state.py` 与 `_workers.py`/`_workers_ext.py`，所有计数器与列表修改纳入 `_lock` 或加独立锁
  - [ ] SubTask M1.2: 新增测试：4 worker 并发断言计数无丢失
- [ ] Task M2: ValidationWorker 默认 submission_ready=False
  - [ ] SubTask M2.1: 修改 `research/decoupled_pipeline/_workers_ext.py:147-154`，`gate.get("submission_ready", False)`
  - [ ] SubTask M2.2: 新增测试：未评分候选断言不被提交
- [ ] Task M3: Candidate 跨 worker 加 per-candidate 锁
  - [ ] SubTask M3.1: 修改 `research/decoupled_pipeline/_workers.py` 与 `_workers_ext.py`，对共享 Candidate 的读改写加 per-candidate 锁
  - [ ] SubTask M3.2: 新增测试：Filter/Validation 并发断言无 torn reads
- [ ] Task M4: structure_refine 不破坏含逗号表达式
  - [ ] SubTask M4.1: 修改 `research/iterative_optimizer/_mutations_mixin.py:130-133`，用 AST 解析或括号匹配移除包装层，不用 rfind(",")
  - [ ] SubTask M4.2: 新增测试：`zscore(if(x>0,a,b))` 断言保留完整
- [ ] Task M5: calibrate_prior_weights 保留相关性符号
  - [ ] SubTask M5.1: 修改 `research/calibration_engine/_calibration.py:79`，用有符号 pearson_r 计算权重（负相关维度零或负权重）
  - [ ] SubTask M5.2: 新增测试：pearson_r=-0.8 断言权重不为最高
- [ ] Task M6: calibrate_scorecard_weights 用有符号相关性
  - [ ] SubTask M6.1: 修改 `research/calibration_engine/_calibration.py:164`，用有符号 corr 选最优
  - [ ] SubTask M6.2: 新增测试：corr=-0.95 断言不被选为最优
- [ ] Task M7: auto_calibrator 正确导入校准模块
  - [ ] SubTask M7.1: 修改 `research/auto_calibrator/_weight_calibration.py:29,45`，从正确路径导入 `calibrate_prior_weights`/`calibrate_scorecard_weights`
  - [ ] SubTask M7.2: 新增测试：AutoCalibrator.calibrate() 断言权重实际更新
- [ ] Task M8: EvolutionRunner 用更新后 scores 剪枝
  - [ ] SubTask M8.1: 修改 `research/evolution/_meta.py:126-198`，突变/交叉产生的新表达式在剪枝前重新评分
  - [ ] SubTask M8.2: 新增测试：种群已满时断言突变体不被立即淘汰
- [ ] Task M9: WebApplicationContext 白名单移除安全函数
  - [ ] SubTask M9.1: 修改 `web/dispatch/web_dispatch_context/_allowed_names.py`，移除 `_csrf_for_session`/`_has_valid_admin_token`/`_get_or_create_session`/`_validate_session` 等安全函数
  - [ ] SubTask M9.2: 新增测试：注入 handler 覆盖安全函数断言被拒
- [ ] Task M10: JobStore 跳过加载后可重置持久化
  - [ ] SubTask M10.1: 修改 `tasks/_store.py:317-336`，`persistence_load_skipped` 在 jobs 变化后可重置；`_persist_locked` 重试写入
  - [ ] SubTask M10.2: 新增测试：跳过加载后 jobs 变化断言恢复持久化
- [ ] Task M11: compute_run_stats 接入真实实现
  - [ ] SubTask M11.1: 修改 `web/misc/web_runtime_facade/_server.py` 或绑定路径，生产 `compute_run_stats`/`status_category` 调用真实实现（`web/state/web_runtime_state.py`）
  - [ ] SubTask M11.2: 新增测试：生产任务 stats 断言非零

## 阶段 N：Dispatch / Runtime / Scheduler High

- [ ] Task N1: OptimizationWorker 接收真实 optimizer（`research/decoupled_pipeline/_pipeline.py:192-197`）
- [ ] Task N2: DecoupledCoordinator.wait_for_completion 可靠（worker 退出时设 STOPPED）
- [ ] Task N3: RepositoryFileLock 防 stale 误判与 unlink 竞态（`research/repository/_file_lock.py`）
- [ ] Task N4: RecordSqliteIndex 配置 WAL 与 busy_timeout（`research/record_sqlite_index.py:150-153`）
- [ ] Task N5: recoverable_backtest_candidates 取最新记录（`research/contracts.py:188-224`）
- [ ] Task N6: 非 429 poll 错误有 halt 或 cooldown（`research/simulation_scheduler/_scheduler_tick.py:329-341`）
- [ ] Task N7: global_cooldown 自动到期清除（`research/simulation_scheduler/_scheduler_helpers.py`）
- [ ] Task N8: _scheduler_tick 状态匹配修正（`_scheduler_tick.py:148`，COMPLETE/COMPLETED）
- [ ] Task N9: ExpressionHistoryIndex.records 不跨源尾部截断（`research/expression_index/_core.py:216-238`）
- [ ] Task N10: _status_payload 用数值排序时间戳（`web/dispatch/get_routes/_helpers.py:86-92`）
- [ ] Task N11: trends 写入并发安全与 ts 容错（`web/api/trends.py` + `web/dispatch/post_routes/misc.py`）
- [ ] Task N12: _read_json 校验 Content-Length 返回 4xx（`web/dispatch/web_http_handler/_handler.py:152-162`）
- [ ] Task N13: JobStore update 处理显式 None updated_at（`tasks/_store.py:111-121`）
- [ ] Task N14: JobStore 读操作无 watchdog 副作用（`tasks/_store.py:195-212`）
- [ ] Task N15: evaluate_release_score 区分 settings 与 metrics（`scoring/release_score_gate/_decision.py:74-85`）
- [ ] Task N16: 提交异常走 redact_error_message（`web/business/web_business/_handlers_simulation.py:87-118`）
- [ ] Task N17: fetch_official_thresholds 用正确签名调用 _request（`brain_api/official_context/_composite.py:237`）
- [ ] Task N18: 浏览器 check_alpha 解析真实 PASS/FAIL（`browser/execution_adapter/_simulate.py:128-134`）
- [ ] Task N19: A-Share 缓存损坏自愈（`data/ashare_adapter/_cache.py:22-34`）
- [ ] Task N20: Loader 加载失败 ERROR 日志而非静默 return（`data/loader/_loader.py:194-255`）

## 阶段 O：扫尾验证 Critical（第五轮 — 顶层入口 / 桥接 / 安全 / 中断机制）

- [ ] Task O1: redaction 脱敏 BRAIN_TOKEN / brain_token / brain_password 键
  - [ ] SubTask O1.1: 修改 `redaction.py:271`，移除 `{"brain", "alpha", "token"}` 反向排除集对含 token/password/secret 键的影响
  - [ ] SubTask O1.2: 修改 `redaction.py:120-124` `_KEY_VALUE_RE`，支持 `[_-]` 前缀键名（覆盖 `BRAIN_TOKEN=xxx`）
  - [ ] SubTask O1.3: 新增测试：`redact_data({"brain_token":"x","brain_password":"y"})` 断言值被替换；日志含 `BRAIN_TOKEN=abc` 断言被脱敏
- [ ] Task O2: StallMonitor._on_interrupt 真正中断任务
  - [ ] SubTask O2.1: 修改 `stall_monitor.py:244-251` `create_stall_monitor_for_web_server` 的 `on_interrupt`，调用 `future.cancel()` + 浏览器/进程终止接口
  - [ ] SubTask O2.2: 修改 `stall_monitor.py:177-182` 超过 `max_retry_count` 时升级为强制 kill 而非仅 log
  - [ ] SubTask O2.3: 修改 `stall_monitor.py:121-173` 回调移出锁外执行，避免死锁/阻塞
  - [ ] SubTask O2.4: 新增测试：stall 触发后断言 future.cancel 被调用、job 状态为 interrupted
- [ ] Task O3: errors.classify_error 比较运算符修正
  - [ ] SubTask O3.1: 修改 `errors.py:141`，`_safe_status(status_code) == 0` 改为 `is None`
  - [ ] SubTask O3.2: 新增测试：`classify_error(RuntimeError("..."), default_code="VALIDATION_ERROR")` 断言 category=="validation"
- [ ] Task O4: ashare_adapter load_index_universe 缓存键含真实 end
  - [ ] SubTask O4.1: 修改 `data/ashare_adapter/_provider.py:112-144`，在构造 cache_key 前先 `end = end or date.today().isoformat()`
  - [ ] SubTask O4.2: 新增测试：跨天调用断言 cache_key 不同 / 第 2 天不命中第 1 天缓存
- [ ] Task O5: agent_live_tools ThreadPoolExecutor 真正可中断
  - [ ] SubTask O5.1: 修改 `agent_live_tools.py:91-124`，捕获 TimeoutError 后 `executor.shutdown(wait=False, cancel_futures=True)`，不依赖 `with` 块退出
  - [ ] SubTask O5.2: 新增测试：3 个 future 卡死时断言函数在 bounded 时间内返回
- [ ] Task O6: task_executor Python 3.11+ TimeoutError 语义区分
  - [ ] SubTask O6.1: 修改 `task_executor.py:75-78` 与 `adaptive_executor.py:322`，通过 `exc.__module__` 或显式异常类型区分业务超时与执行器超时
  - [ ] SubTask O6.2: 新增测试：业务 `raise TimeoutError` 不被误归类为执行器超时
- [ ] Task O7: task_executor.submit 失败 job 标记 failed
  - [ ] SubTask O7.1: 修改 `task_executor.py:71-72` 与 `adaptive_executor.py:316-318`，`executor.submit(...)` 包入 try/except，失败时 `store.update(status="failed")`
  - [ ] SubTask O7.2: 新增测试：submit 抛 RuntimeError/PicklingError 时断言 job 状态为 failed（非 running）
- [ ] Task O8: _real_session 截断 csrf 修复 / 删除
  - [ ] SubTask O8.1: 静态分析 `web/business/web_business/_handlers_misc.py:226-236` `_real_session` 的所有调用路径
  - [ ] SubTask O8.2: 若 dead code 则删除；若仍可能被调用则修正返回完整 sid/csrf（截断仅用于 display 字段）
  - [ ] SubTask O8.3: 新增测试：若保留则断言返回完整 token；若删除则断言无引用

## 阶段 P：扫尾验证 High（第五轮 — Web 安全 / 数据加载 / 中断 / 调度）

- [ ] Task P1: web_runtime_facade secure_cookies HTTP 下默认 False
  - [ ] SubTask P1.1: 修改 `web/misc/web_runtime_facade/_server.py` 中 secure_cookies 默认推导逻辑，HTTP 监听时不强制 True
  - [ ] SubTask P1.2: 新增测试：allow_remote=True + HTTP 监听断言 secure_cookies=False
- [ ] Task P2: web_security 空 Host 头拒绝 + replay timestamp 单位明确
  - [ ] SubTask P2.1: 修改 `web/security/web_security.py:30-55`，allow_remote=True 时空 Host 直接 reject
  - [ ] SubTask P2.2: 修改 `web/security/web_security.py:246-249`，timestamp 强制秒级或显式 unit 参数，移除启发式阈值
  - [ ] SubTask P2.3: 新增测试：空 Host 断言 400；毫秒 timestamp 断言 reject 或正确转换
- [ ] Task P3: backtest_polling 未知状态槽位释放兜底
  - [ ] SubTask P3.1: 修改 `research/backtest_polling.py:36,94-116`，引入 `defer_count`，连续 5 次后 `release_slot=True` + 候选标记 `failed_unknown_status`
  - [ ] SubTask P3.2: 新增测试：连续 5 次未知状态断言槽位释放
- [ ] Task P4: 提交异常 status_message 走 redact_error_message
  - [ ] SubTask P4.1: 修改 `web/business/web_business/_handlers_simulation.py:115`，`str(exc)` 改为 `redact_error_message(exc)`
  - [ ] SubTask P4.2: 修改 `_submit_and_poll_simulation` 区分瞬时错误与永久错误，永久错误立即 fail job
  - [ ] SubTask P4.3: 新增测试：异常含 token 时断言 status_message 不含 token
- [ ] Task P5: guided_pipeline threading 超时可取消
  - [ ] SubTask P5.1: 修改 `ux/guided_pipeline/_phases.py:180-192`，传入 cancel event，超时后 set event，daemon 线程在取消点检查
  - [ ] SubTask P5.2: 新增测试：超时后断言 daemon 线程在 bounded 时间内退出
- [ ] Task P6: capability_registry language 显式 kind
  - [ ] SubTask P6.1: 修改 `data/capability_registry/_types.py` `CapabilityKind` Literal 增加 `"language"`
  - [ ] SubTask P6.2: 修改 `data/capability_registry/_defaults.py:104-117`，language 条目用 `kind="language"`
  - [ ] SubTask P6.3: 新增测试：`get(name, kind="test_period")` 不返回 language 条目
- [ ] Task P7: error_catalog 区分 dataset KeyError 与其它 KeyError
  - [ ] SubTask P7.1: 修改 `error_catalog.py:309-310`，仅当 KeyError 键名符合 dataset_id 模式或来自已知 dataset 查询路径时归 dataset_missing
  - [ ] SubTask P7.2: 新增测试：普通配置 KeyError 断言不归 dataset_missing
- [ ] Task P8: data/loader _load_operators/_load_datasets isinstance 防御
  - [ ] SubTask P8.1: 修改 `data/loader/_loader.py:240-265`，循环顶部加 `if not isinstance(item, dict): continue`
  - [ ] SubTask P8.2: 新增测试：JSON 含 `[1, "x", null]` 元素时断言 loader 不崩溃
- [ ] Task P9: agent_tools._context_mixin._get_job_status 防 **job 覆盖 + None 解包
  - [ ] SubTask P9.1: 修改 `agent_tools/_context_mixin.py:207,211-212`，剥离 job 的 ok/source/job_id 键；处理 `("", None)` truthy tuple
  - [ ] SubTask P9.2: 新增测试：job 含 `"ok": False` 时断言返回 ok=True；latest_active 返回 ("", None) 时不崩溃
- [ ] Task P10: adaptive_executor.shutdown 阻止后续 submit 重建池
  - [ ] SubTask P10.1: 修改 `adaptive_executor.py:99-111,130-137`，引入 `_shutdown` 标志，submit 时检查并抛 RuntimeError
  - [ ] SubTask P10.2: 新增测试：shutdown 后 submit 断言抛 RuntimeError
- [ ] Task P11: fetch_official_context Windows/非主线程 + HTTP-date Retry-After
  - [ ] SubTask P11.1: 修改 `fetch_official_context.py:360-385`，Windows/非主线程回退 threading.Timer
  - [ ] SubTask P11.2: 修改 `_retry_after_seconds` 支持 HTTP-date 格式
  - [ ] SubTask P11.3: 新增测试：HTTP-date Retry-After 断言正确解析
- [ ] Task P12: _launch_monitor 看门狗 + 完成判据 + 告警正则
  - [ ] SubTask P12.1: 修改 `_launch_monitor.py:89-118`，加看门狗线程 N 秒无输出时 `proc.kill()`
  - [ ] SubTask P12.2: 修改 `_launch_monitor.py:101-103`，删除 `\bDONE\b` 分支，仅保留 `"run_completed"`
  - [ ] SubTask P12.3: 修改 `_launch_monitor.py:104-109`，用否定上下文正则排除 `0 errors`/`no failed`/`error handling completed`
  - [ ] SubTask P12.4: 修改 `_launch_monitor.py:17-53`，文档化或修复 `sanitized_child_env` 凭证剥离
  - [ ] SubTask P12.5: 修改 `_launch_monitor.py:110-114`，`proc.wait(timeout=10)` 超时后 `proc.kill()`
- [ ] Task P13: backend_registration._api_instance 线程安全 + 可刷新
  - [ ] SubTask P13.1: 修改 `backend_registration.py:63-74`，加锁；提供 `reset_brain_api()`；`OfficialBrainAPI()` 传入 config
  - [ ] SubTask P13.2: 新增测试：多线程并发 `_get_brain_api` 断言单例；`reset_brain_api` 后断言新实例
- [ ] Task P14: fusion.composite_ensemble max 模式验证
  - [ ] SubTask P14.1: 修改 `research/fusion.py:152-156`，`return result` 前加 `_validate_fusion_expr(result, "ensemble_max")`
  - [ ] SubTask P14.2: 新增测试：max 模式超长表达式断言被拒绝
- [ ] Task P15: diagnostics.weight_concentration 用 bounded ratio
  - [ ] SubTask P15.1: 修改 `research/diagnostics.py:82`，`_ratio(..., bounded=True)`（与 correlation/drawdown 对齐）
  - [ ] SubTask P15.2: 新增测试：concentration=5（百分比形式）断言不触发 HIGH_CONCENTRATION
- [ ] Task P16: agent_live_tools.poll_interval_seconds 先 bounded_float
  - [ ] SubTask P16.1: 修改 `agent_live_tools.py:198-199`，删除裸 `float()`，直接 `bounded_float(args.get(...), 0.5, 30.0, default=2.0)`
  - [ ] SubTask P16.2: 新增测试：传入 `"abc"` 断言返回 default=2.0 而非 ValueError
- [ ] Task P17: capability_registry 字段名大小写统一
  - [ ] SubTask P17.1: 修改 `data/capability_registry/_types.py:107-126`，`fields()` 与 `field_category_index()` 统一小写
  - [ ] SubTask P17.2: 新增测试：`fields()` 结果可作为 `field_category_index()` 的 key
- [ ] Task P18: JobStore 协议与 latest_any/all 调用方统一
  - [ ] SubTask P18.1: 修改 `shared/contracts.py:95-101` `JobStore` Protocol，纳入 `all(limit)` / `latest_any`
  - [ ] SubTask P18.2: 修改 `agent_research_tools.py:317-322` 与 `_context_mixin.py:208`，使用统一方法名
  - [ ] SubTask P18.3: 新增测试：所有 JobStore 实现都通过 `enforce_protocol(JobStore)`
- [ ] Task P19: i18n.t() 兜底 IndexError
  - [ ] SubTask P19.1: 修改 `i18n/__init__.py:36-39`，except 增加 IndexError，回退到 `default or key`
  - [ ] SubTask P19.2: 新增测试：含 `{}` 位置占位的模板断言不抛 IndexError
- [ ] Task P20: metrics 全局单例线程安全
  - [ ] SubTask P20.1: 修改 `metrics.py:43-51,105`，用 `threading.Lock` 包裹 `_counters`/`_histograms` 写操作；删除未使用的 `_timers`
  - [ ] SubTask P20.2: 新增测试：高并发 counter/histogram 断言无丢失
- [ ] Task P21: jsonl 读取加共享锁 + 跳过统计
  - [ ] SubTask P21.1: 修改 `jsonl.py:56-72`，读取加 `fcntl.flock(LOCK_SH)`（Windows 用 msvcrt）；`iter_jsonl_records` 返回跳过统计
  - [ ] SubTask P21.2: 新增测试：并发写时读断言不丢行
- [ ] Task P22: secure_credentials ResolutionTrace.masked 不存明文片段
  - [ ] SubTask P22.1: 修改 `secure_credentials.py:180,192`，`masked` 字段不存任何明文片段，改为 `"***"` 或 `"*"*len`
  - [ ] SubTask P22.2: 修改 `secure_credentials.py:271-285`，filter 加到全局 handler 级别，覆盖 `propagate=False` logger
  - [ ] SubTask P22.3: 新增测试：`json.dumps(trace)` 断言无明文；propagate=False logger 断言被脱敏

## 阶段 Q：扫尾验证 Medium（第五轮 — UX / 派生 / 死代码）

- [ ] Task Q1: trends.jsonl 路径走 runtime_project_root + 读取尾部扫描
  - [ ] SubTask Q1.1: 修改 `web/api/trends.py:13-15`，路径统一走 `runtime_project_root() / "data" / "trends.jsonl"`
  - [ ] SubTask Q1.2: 修改 `get_trends` 从文件尾部按行回扫至 N 天前 ts，不全量读取
  - [ ] SubTask Q1.3: 新增测试：trends.jsonl >10MB 时 GET /api/trends 断言响应时间 < 100ms
- [ ] Task Q2: ux/guided_storage list_checkpoints 按 mtime 排序
  - [ ] SubTask Q2.1: 修改 `ux/guided_storage.py:57,77-81`，按 `path.stat().st_mtime` 排序；`latest_checkpoint` 加防御
  - [ ] SubTask Q2.2: 新增测试：文件名格式变化时断言 latest_checkpoint 返回真正最新
- [ ] Task Q3: ux/guided_pipeline resume 按阶段跳转
  - [ ] SubTask Q3.1: 修改 `ux/guided_pipeline/_base.py:110-126`，根据 `phase_completed` 跳到下一阶段继续，非从头跑
  - [ ] SubTask Q3.2: 新增测试：checkpoint 完成 generation 后 resume 断言不重跑 init/context
- [ ] Task Q4: assistant_request_snapshot include_prompt 透传
  - [ ] SubTask Q4.1: 修改 `web/misc/web_assistant_snapshots/_assistant_payloads.py:73-88`，`include_prompt=True` 改为 `include_prompt=include_prompt`
  - [ ] SubTask Q4.2: 新增测试：传 `include_prompt=False` 断言 prompt 不在响应中
- [ ] Task Q5: web_runtime_state lifecycle_from_job limit=0 返回空
  - [ ] SubTask Q5.1: 修改 `web/state/web_runtime_state.py:95`，`if limit is not None and limit <= 0: return []`
  - [ ] SubTask Q5.2: 新增测试：limit=0 断言返回空列表
- [ ] Task Q6: backtest_slots backtest_row_submitted 与 slot_active 状态集合统一
  - [ ] SubTask Q6.1: 修改 `web/misc/web_backtest_slots/_helpers.py:87-99,140-148`，POLL_TIMEOUT 明确归入 active 或 inactive
  - [ ] SubTask Q6.2: 新增测试：POLL_TIMEOUT 任务断言 slot_active 与 backtest_row_submitted 一致
- [ ] Task Q7: strategy_switch._explore 全零 bandit_counts 防御
  - [ ] SubTask Q7.1: 修改 `research/strategy_switch.py:60-62`，`max_count = max(bandit_counts.values(), default=1) or 1`
  - [ ] SubTask Q7.2: 新增测试：bandit_counts 全零时断言不抛 ZeroDivisionError
- [ ] Task Q8: checkpoint _register_index_entry 拆分无锁版本
  - [ ] SubTask Q8.1: 修改 `research/checkpoint.py:138,159,204-205`，拆为 `_register_index_entry_locked`（无锁）与公共版本
  - [ ] SubTask Q8.2: 新增测试：`_atomic_write` 内调用无锁版本断言无冗余加锁
- [ ] Task Q9: backtest_finalization/submission_gate_service 拆分 try 块 + 提升日志级别
  - [ ] SubTask Q9.1: 修改 `research/backtest_finalization.py:159-196`，分离 metrics 解包与 check_registry.evaluate
  - [ ] SubTask Q9.2: 修改 `research/submission_gate_service.py:236-237`，`logger.debug` 改为 `logger.warning`
  - [ ] SubTask Q9.3: 新增测试：check_registry 抛 AttributeError 时断言不被静默吞为 check_registry_error
- [ ] Task Q10: diagnosis_gap_coverage 副作用 import 下沉
  - [ ] SubTask Q10.1: 修改 `diagnosis_gap_coverage.py:9`，`import brain_alpha_ops.web` 下沉到函数体内
  - [ ] SubTask Q10.2: 新增测试：import diagnosis_gap_coverage 不触发 web 子包加载
- [ ] Task Q11: parameter_audit slot 类与 _threshold_trace 非 None 标记
  - [ ] SubTask Q11.1: 修改 `parameter_audit.py:104-109`，`vars(value)` try/except TypeError 兜底
  - [ ] SubTask Q11.2: 修改 `parameter_audit.py:118,195-199`，current 非 None 且 _num 失败时 deviation 设为 None
  - [ ] SubTask Q11.3: 新增测试：slot 类对象断言不抛；非数值 current 断言 deviation 为 None
- [ ] Task Q12: code_quality._has_type_annotations 用 ast
  - [ ] SubTask Q12.1: 修改 `code_quality.py:105-112`，用 ast 遍历 FunctionDef/AsyncFunctionDef 检查 returns
  - [ ] SubTask Q12.2: 新增测试：仅变量注解无返回注解断言 False
- [ ] Task Q13: observability.context_payload 类型一致 + 空容器过滤
  - [ ] SubTask Q13.1: 修改 `observability.py:47-50`，统一 str() 化或保留原值；空容器用 truthy 判断
  - [ ] SubTask Q13.2: 新增测试：value=0/False/[]/{} 断言不写入 payload
- [ ] Task Q14: official_validation_service / pipeline_official_validation_flow 删除裸 pool 语句
  - [ ] SubTask Q14.1: 修改 `research/official_validation_service.py:48,56` 与 `research/pipeline_official_validation_flow.py:30,38`，删除裸 `pool` 语句
  - [ ] SubTask Q14.2: 静态分析确认无遗漏逻辑

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
