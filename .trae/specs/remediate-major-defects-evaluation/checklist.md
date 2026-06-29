# Checklist

## 阶段 A：后端核心防线与状态机 Critical

- [ ] 反过拟合 `returns` 不再回退到 `factor_values`，returns 缺失时显式失败或使用语义不同代理
- [ ] returns 缺失时反过拟合检查失败（非 PASS），IC/Spearman 不恒等于 1.0
- [ ] Quality Gate `intercept` 中审计写失败不再跳过 `transition(gate_rejected)`
- [ ] 审计写失败时候选仍转换到 gate_rejected，审计失败记 ERROR 日志
- [ ] `candidate_lifecycle.transition()` 非法转换抛 `IllegalTransitionError`，不静默回退 `force_transition`
- [ ] 仅 `force=True` 时才允许 `force_transition`，且仅测试用例使用
- [ ] 生产调用方已迁移
- [ ] 仿真并发超限（`CONCURRENT_SIMULATION_LIMIT_EXCEEDED`）候选标记 `deferred_concurrency_limit`（非 failed）
- [ ] `state.failed` 不自增，`stop_new_submissions` 仅暂停受影响槽位
- [ ] deferred 候选冷却后可重试
- [ ] 真实提交成功后审计写失败不再冒泡为 400 响应
- [ ] 提交成功响应在审计失败时仍返回成功
- [ ] 审计失败记录到 ERROR 级日志与监控指标
- [ ] Facade 绑定安装失败时异常向上传播，日志记录原始堆栈
- [ ] `JOB_REGISTRY` 不再出现 `None` 后被访问为 `AttributeError`
- [ ] web_cloud 同步任务心跳线程不再因非 (OSError,ValueError,TypeError) 静默退出
- [ ] `stop_heartbeat` join 线程

## 阶段 B：研究引擎数值正确性 Critical

- [ ] BCa Bootstrap n<5 时返回带 `insufficient_samples` 标记的 CI（非 (0,0)）
- [ ] 不可达死代码（`_bootstrap_mixin.py:88-92`）已清理
- [ ] insufficient samples 时 stall 检测视为 "no signal" 而非 "significant decline"
- [ ] n=3 时不触发误判策略切换
- [ ] Pearson `cov` 与 `std` 统计量一致（同总体或同样本）
- [ ] n=3 时 Pearson 等于标准相关系数（非 0.667×）
- [ ] IC_stability / regime_stress / placebo 分数不再系统性偏低
- [ ] ProdCorrelation 本地回退返回 `unknown`/`blocked`，≥100 分支不放行
- [ ] API 不可用时长表达式不通过 prod_correlation 硬门禁
- [ ] ProdCorrelationService 接入评分流水线（非消费 mock 值）或显式标注降级模式

## 阶段 C：提交安全闭环 Critical（P0/P1）

- [ ] `ApiExecutionAdapter.submit_alpha()` 限制为 dev/test only
- [ ] 生产提交路径必须走 Browser backend
- [ ] e2e 提交验证使用真实浏览器流程（非 `requests` 命中本地 `/api/*`）
- [ ] 单 env 旁路（`BRAIN_ALPHA_FORCE_REAL_SUBMIT=1` 无 `BRAIN_ALPHA_ENABLE_REAL_SUBMIT_TESTS=1`）保持禁用
- [ ] API 层 `submit_alpha()` 公开入口须显式 browser-backend 确认

## 阶段 D：WebUI Critical

- [ ] React 未构建且 inline 模板缺失时返回内置引导 HTML（含诊断信息）
- [ ] `safe_selected_frontend` 默认回退不再指向不存在的 inline
- [ ] 核心面板（dashboard/candidates/backtest/scoring/quality/submission/config/history）接入路由
- [ ] 切换面板后 URL 变化，刷新停留，浏览器后退可回
- [ ] PhaseShell 阻断/未就绪阶段关键操作区 `inert` 或 `pointer-events:none`
- [ ] 阻断阶段按钮不可点击、不可 Tab 到达

## 阶段 E：UX Critical

- [ ] 候选进入提交队列或打开提交面板时前置提示「Web 端不可真实提交」+ BRAIN 平台外链
- [ ] SSE 断连超时取消时展示「云端可能仍在运行」警示 + 槽位查询入口

## 阶段 F：后端 High

- [ ] StallMonitor 超过 max_retry_count 后调用 `_on_interrupt` 中断作业并升级告警
- [ ] BRAIN 认证 401 时尝试 token 刷新与备选认证方法，指数退避后有限次重试
- [ ] concurrent_simulate/concurrent_check 超时后显式释放槽位，不依赖无效 `future.cancel()`
- [ ] 并行回测 `as_completed` 与 `future.result()` 有批次级 timeout
- [ ] 心跳线程（web_run_job）异常退出前有限次重启
- [ ] WebSocket publish 失败 sender 从 `_subscribers` 移除
- [ ] `MAX_USER_ALPHAS_PAGES` 有上界，长期同步报告截断
- [ ] Regime 压力测试全零 Sharpe 判失败（score=0, passed=False）
- [ ] 重试阈值运算符统一（`>` 与 `>=` 同语义）
- [ ] Ranker 对 `scorecard=None` 降级（不崩溃整批排序）
- [ ] 审计 64KB 截断保留 `gate_decisions` 与 `triggered_rules`（仅截断非关键 details）
- [ ] Evidence `cleanup_old`/`list_sessions` 单文件损坏跳过不中断循环
- [ ] 诊断快照每个探针 try/except，单探针失败不终止整体
- [ ] 官方 context 回退路径解析为项目根 `data`（非包内 `brain_alpha_ops/data`）
- [ ] 无身份候选 update 被拒绝（非追加为新行）
- [ ] BaoStock `logout` 在 finally 块
- [ ] FieldDatasetMapper `build()`/`_add_mapping()` 并发安全，无映射丢失
- [ ] check 证据持久化失败传播或标记 stale
- [ ] `save_assistant_guidance` 失败不丢失生成结果
- [ ] `max_official_concurrent_simulations=0` 被尊重（不改写为 3）
- [ ] 滚动验证 `decay_ratio` first 为负时符号正确，score 不倒置
- [ ] `ic_stability` 分量上限统一
- [ ] `RecordSqliteIndex.refresh` 暴露覆盖率或全量索引
- [ ] Placebo seed 按候选派生（非全局固定 42）
- [ ] `sub_universe_sharpe` 本地计算按权重 top-half 或明确标注非 BRAIN 语义

## 阶段 G：WebUI High

- [ ] `useCandidateTableData` 无刷新循环
- [ ] `OfficialBacktestSlots` 仅轮询 `/api/backtest_slots`
- [ ] 任务 SSE 连接独立于 Dashboard 视图生命周期
- [ ] 所有 Modal 接入 FocusTrap
- [ ] 死代码 ToastProvider 已移除，单一 Toast 系统生效

## 阶段 H：UX High

- [ ] 批量提交响应包含 `submitted` 与 `failed` 明细列表
- [ ] 批量提交前显示候选清单预览
- [ ] 涉及 Final 常量的配置项保存后提示「需重启服务生效」
- [ ] 限流倒计时读取后端 `retry_after`（非固定 30s）
- [ ] 前台任务完成时有 toast/徽标提示

## 阶段 I：验证

- [ ] `python3 -m pytest tests/ -q` 全量通过
- [ ] `cd brain_alpha_ops/web/react_app && npm run test` 通过
- [ ] `cd brain_alpha_ops/web/react_app && npm run typecheck` 通过
- [ ] 无新增回归（关键场景：启动、认证、回测、评分、反过拟合、提交队列、SSE 推送、prod_correlation）

## 阶段 J：安全 Critical（部署 + 证据 + 旁路 + 脱敏）

- [ ] Docker 容器以非 root 用户运行
- [ ] evidence 目录不再 chmod 777
- [ ] docker-compose 绑定 `127.0.0.1:8765:8765`，含 `cap_drop: [ALL]`、`no-new-privileges`、`read_only`、资源限制
- [ ] 证据归档时 HAR 文件 Authorization/Set-Cookie/Cookie 头已脱敏
- [ ] network_logs / console_logs 经 `redact_text` 处理
- [ ] 归档后断言无明文凭证
- [ ] `real_submit_test_override_enabled` 不再依赖 `PYTEST_CURRENT_TEST` env
- [ ] 生产 env 设置三变量断言仍禁用真实提交
- [ ] `_SECRET_FRAGMENT_RE` 不再强制要求含数字，纯字母 token 被脱敏
- [ ] `web_security` allow_remote 时信任锚为配置 allowlist（非 Host 头），DNS rebinding 攻击被拒
- [ ] CI `npm audit --audit-level=critical` 无 `continue-on-error`，critical CVE 阻断合并
- [ ] CI 含 `pip-audit` 步骤扫描 Python 依赖
- [ ] Python 版本在 Docker / CI / pyproject 一致

## 阶段 K：Agent / MCP / LLM / Browser Critical

- [ ] MCP stdio 长轮询工具不阻塞主循环，其他工具可服务、notifications/cancelled 可消费
- [ ] LLM 调用前 `wait_for_quota`、调用后 `record` token、预算耗尽停止
- [ ] 超 200K token 预算断言停止 LLM 调用
- [ ] Browser 提交幂等键持久化或不淘汰，超 1000 键或重启后重放被拒
- [ ] Browser 登录判定不使用 `nav` 通用选择器，错误凭证断言 is_logged_in=False
- [ ] `BrainBrowserRunner` weakref.finalize 不捕获 None，异常逃逸后 playwright 资源释放
- [ ] `cross_review_expression` 加锁保护 provider 交换，并发无串号
- [ ] `review_expression` 重试耗尽后实际调用 `_offline_review`（非死代码）

## 阶段 L：架构与配置 High

- [ ] 生产 pipeline（runner / Web `_handle_pipeline_start`）传 `execution_backend`（browser 模式）
- [ ] 启动时调用 `register_all_backends()`
- [ ] `register_backend` 检测重复注册
- [ ] registry 校验区分数据字段与枚举值，不再必然误报 BLOCKING
- [ ] strategy profile_id 哈希种子含 delay，同名不同 delay 的 profile id 不同
- [ ] `strategy_switch.build_application` 索引越界不静默取模映射
- [ ] 参数审计覆盖 official_api 全部参数（cache_dir/timeout_seconds/rate_limit_retry_attempts 等）
- [ ] `lifecycle_records` 有上限（如 last 500），长跑不 OOM
- [ ] `convergence_stats` records 缺 total_score 时不崩溃
- [ ] `build_attribution_tree` 用 `.get()` 而非硬下标，不完整 scorecard 不崩溃
- [ ] `StrategySwitchService._explore` bandit_counts 全零时不崩溃
- [ ] `_launch_monitor.py` 引用 `BrainAlphaConsole.exe`，Popen 有 try/except
- [ ] SBOM 含传递依赖（urllib3/certifi 等）

## 阶段 M：解耦流水线 / 校准 / 进化 / 调度 Critical

- [ ] DecoupledPipeline `SharedState` 所有计数器与列表修改有锁保护
- [ ] 4 worker 并发断言计数无丢失
- [ ] `ValidationWorker` 默认 `submission_ready=False`，未评分候选不被提交
- [ ] Candidate 跨 worker 读改写有 per-candidate 锁，无 torn reads
- [ ] `structure_refine` 不用 `rfind(",")`，含逗号表达式（如 `if(x>0,a,b)`）保留完整
- [ ] `calibrate_prior_weights` 用有符号 pearson_r，负相关维度权重不为最高
- [ ] `calibrate_scorecard_weights` 用有符号 corr 选最优，corr=-0.95 不被选
- [ ] `auto_calibrator` 从正确路径导入校准模块，`AutoCalibrator.calibrate()` 权重实际更新
- [ ] `EvolutionRunner.evolve` 突变体在剪枝前重新评分，种群已满时不被立即淘汰
- [ ] `WebApplicationContext` 白名单不含安全函数（`_csrf_for_session` 等），覆盖被拒
- [ ] `JobStore` 跳过加载后 jobs 变化时恢复持久化，不永久 `persistence_load_skipped=True`
- [ ] 生产 `compute_run_stats` 接入真实实现，任务 stats 非零

## 阶段 N：Dispatch / Runtime / Scheduler High

- [ ] `OptimizationWorker` 接收真实 optimizer，优化阶段非死代码
- [ ] `DecoupledCoordinator.wait_for_completion` worker 退出时设 STOPPED，不依赖 timeout
- [ ] `RepositoryFileLock` 不按 mtime 误判 stale，`__exit__` 不 unlink 他人锁文件
- [ ] `RecordSqliteIndex` 配置 WAL 与 busy_timeout，并发写不立即 `database is locked`
- [ ] `recoverable_backtest_candidates` 取最新（max timestamp）记录而非最旧
- [ ] 非 429 poll 错误（500/502/503）有 halt 或 cooldown，不无限重试饿死其他候选
- [ ] `global_cooldown` 到期自动清除，不依赖手动 `resume()`
- [ ] `_scheduler_tick` 匹配 `COMPLETE` 与 `COMPLETED`（无重复字符串 bug）
- [ ] `ExpressionHistoryIndex.records` 不跨源尾部截断，覆盖所有源
- [ ] `_status_payload` 用数值排序 `updated_at`，返回真正最新 job
- [ ] `record_trend` 有锁保护、走 `_validated_post_route`；`get_trends` 容忍非数值 ts
- [ ] `_read_json` 校验 `Content-Length >= 0`，负值返回 400（非 500）
- [ ] `JobStore.update` 处理显式 `updated_at=None`（设为 now），watchdog 不误判
- [ ] `JobStore` 读操作无 watchdog 副作用，返回调用时刻状态
- [ ] `evaluate_release_score` 当 settings 为 None 时不误用 metrics 当 settings
- [ ] 提交异常走 `redact_error_message`，凭据不泄漏到 status_message
- [ ] `fetch_official_thresholds` 用正确签名调用 `_request`，动态阈值实际拉取
- [ ] 浏览器 `check_alpha` 解析真实 PASS/FAIL，不返回 `ok=True` + 截断 inner_text
- [ ] A-Share 缓存 Parquet 损坏时删除并回退 JSON/重取，不永久返回 None
- [ ] Loader 加载失败时 ERROR 日志，不静默 return 致全量 alpha 被拒
