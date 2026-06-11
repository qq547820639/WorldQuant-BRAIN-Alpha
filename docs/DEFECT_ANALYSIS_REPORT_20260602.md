# BRAIN Alpha Ops — 全面缺陷分析报告

**日期**: 2026-06-02  
**分析范围**: 全部项目代码，深度跟踪调用链路  
**总计发现缺陷**: 47 项  
**综合评分**: 6.8/10（目标 8.8/10）

---

## Codex 实施追踪（2026-06-02）

| 缺陷 | 当前状态 | 当前证据 | 下一步 |
|------|----------|----------|--------|
| P0-001 Python 3.9 运行时类型语法 | CLOSED_CURRENT | `brain_alpha_ops/research/backtest_finalization.py` 已将运行时类型别名从 `Candidate \| None` 改为 `Optional[Candidate]`，`scoring_params` 也改为 `Optional[object]`；系统 `python3` 导入复测已通过。 | 保持 `tests/test_backtest_finalization.py` 的类型别名守卫绿色。 |
| P1-003 CLI `--base-url` SSRF | CLOSED_CURRENT | `brain_alpha_ops/cli_handlers.py` 与 `brain_alpha_ops/web_config.py` 均复用官方 API allowlist，生产环境只接受 `https://api.worldquantbrain.com`；CLI/Web 回归测试已通过。 | 修改 base URL 或环境策略前必须保留 allowlist 测试。 |
| P1-002 子进程凭据泄露 | CLOSED_CURRENT_FOR_QUALITY_GATE | `scripts/quality_gate.py` 使用显式环境 allowlist，不会把 `BRAIN_PASSWORD` / `OPENAI_API_KEY` 传给质量门子进程；对应回归测试已通过。`secure_credentials.resolve_credentials()` 仍保留父进程环境读取语义，不在本轮强行清空全局环境变量。 | 如要扩展到其他子进程入口，先枚举具体调用链，再复用同一环境过滤策略。 |
| P1-001 分页条目级去重 | CLOSED_CURRENT | `list_user_alphas()` 已在完整分页完成后复用 `_dedupe_alpha_items` 按 Alpha ID 去重；新增回归测试覆盖跨页重复 ID，同时确认不会添加硬页数上限。 | 保持官方适配器分页测试绿色。 |
| P1-004 异常静默吞噬 | CLOSED_CURRENT | `brain_alpha_ops/research/backtest_finalization.py` 的 ExperienceDB 记录失败分支现在会记录异常类型和脱敏错误原因；`official_context.py` 的 stale cache fallback 仅捕获 `BrainAPIError` 并向上抛出其他异常；`observability.py` 会把表达式索引失败暴露到 `expression_index.error` 与 `partial_errors`。Python silent broad exception 门禁为 0 findings。 | 保持脱敏日志回归和 Python silent exception 守卫绿色；不要为了 traceback 泄露原始 secret。 |
| P1-005 `OfficialBrainAPI` Mixin 调用链 | CLOSED_CURRENT | `OfficialBrainAPI` 不再直接继承 auth/context/request/simulation/validation Mixin；公开方法保留为兼容入口，内部显式委托到 `_auth_profile`、`_context_data`、`_request_client`、`_simulation_submission` 和 `_expression_validator`。`OfficialBrainAPI.__mro__` 组件化回归测试已通过。 | 保持组合组件测试与官方适配器回归绿色。 |
| P1-006 Web job 全局状态锁域 | CLOSED_CURRENT | 新增 `brain_alpha_ops/web_job_registry.py`，默认 job stores / submit lock / rate limiter / task executor 由 `WebJobRegistry` 统一创建和持有；registry view 解析逻辑已提升为共享 helper，`web_runtime_facade.py` 与 `web.py` 的冲突检测、限流、后台任务提交入口均通过该 view 读取状态；`Handler` 初始化已移除静态 `jobs=JOBS` 注入，SSE 通过动态 resolver 查找 job；`job_registry()`、`_job_registry_view()`、`active_auxiliary_operation()`、`rate_limit_request()`、`_submit_background_job()` 已迁到 `brain_alpha_ops/web_job_bindings.py`；`JOBS` / `SYNC_JOBS` / `CHECK_JOBS` / `ASYNC_JOBS` / `SUBMIT_LOCK` / `RATE_LIMITER` / `TASK_EXECUTOR` 不再默认安装到 `web.__dict__`，改由 `__getattr__` 从 `JOB_REGISTRY` 动态兼容导出，同时旧 alias override 测试保持绿色。 | 保持动态兼容导出测试和 registry view override 测试绿色；新增 job state 时必须先进入 `WebJobRegistry`。 |
| P1-007 配置加载路径解析 | CLOSED_CURRENT | `runtime_project_root()` / `default_run_config_path()` 统一处理源码、冻结包和 `BRAIN_ALPHA_OPS_HOME`；`load_run_config()` / `write_run_config()` 通过 `prepare_run_config_for_runtime()` 获取运行时副本并归一化 `storage_dir` 与 API cache 路径；`validate_run_config()` 不再修改输入对象，空默认 dataset 解析会 fail closed。配置测试与 validate-only 入口验证均已通过。 | 保持 `tests/test_config.py` 和 `run_pipeline.py --validate-only` 绿色。 |
| P1-008 外部 A-share 数据验证 | CLOSED_CURRENT | `AShareDataProvider.load_daily_batch()` 现在会在使用缓存或写入新缓存前做日线行级验证：日期必须是 ISO 格式，已出现的数值字段必须可转为 `float`，坏行会进入 `last_diagnostics()`，坏缓存会触发重新拉取；指数成分与 fallback 降级也保留 `status/error` 诊断。A-share 适配器回归测试已通过。 | 保持行级验证测试和 diagnostics 语义绿色。 |
| V5-001 完整分页边界 | TRACKED_DEFERRED | `docs/DEFECT_ANALYSIS_REPORT_20260602_v6.md` 和 `scripts/check_v5_defect_tracking.py` 当前确认：用户云端同步保留完整分页，不添加固定分页截断；依赖重复页签名、空页/短页与 offset recovery 等非截断保护。 | 只考虑停滞观测和显式取消保护，不引入任意固定截断。 |
| P0-003 WebApplicationContext 无限制暴露 | CLOSED_CURRENT | `WebApplicationContext` 已改为显式 runtime facade 白名单，拒绝 `_module`、`_allowed_names`、`_LEGACY_IMPORTED_EXPORTS`、`sys` 等未列名属性；context class 与白名单策略已迁到 `brain_alpha_ops/web_application_context.py`，赋值仍会转发到模块本体，避免 `SERVER` 等状态写成 context 影子属性。 | 保持 Web facade contract 与 runtime facade 回归绿色。 |
| P0-002 Web facade God Object | CLOSED_CURRENT | P0-003 已收紧 context 访问面，并把 `WebApplicationContext` class 与 170+ 行 context 白名单策略迁出 `web.py`；P1-006 已把 job store / submit lock / rate limiter / task executor 的默认创建抽到 `WebJobRegistry`，把 runtime facade 与 `web.py` 主要状态入口集中到共享 registry view，并移除了 `Handler` 的静态 `jobs=JOBS` 注入，public job aliases 也已改为动态兼容导出；job 操作入口已迁到 `brain_alpha_ops/web_job_bindings.py`；snapshot/assistant/read-only storage/config 相关公开转发函数已迁到 `brain_alpha_ops/web_snapshot_bindings.py`；candidate/sync/check/submission 相关公开转发函数已迁到 `brain_alpha_ops/web_candidate_bindings.py`；runtime/server 转发函数已迁到 `brain_alpha_ops/web_runtime_bindings.py`；config provider/payload 入口已迁到 `brain_alpha_ops/web_config_bindings.py`；session policy/host normalization 已迁到 `brain_alpha_ops/web_session_bindings.py`；legacy export 映射已迁到 `brain_alpha_ops/web_legacy_exports.py`；service import / 私有依赖装配已迁到 `brain_alpha_ops/web_service_namespace.py`；public facade 绑定安装已迁到 `brain_alpha_ops/web_facade_bindings.py`。当前 `web.py` 已降至 50 行，达到 <100 行启动入口目标。 | 保持 Web facade contract、registry view 和 server lifecycle 回归绿色。 |
| PROD-001 validation-only 候选死胡同 | CLOSED_CURRENT | 当前 production ledger 显示 `job_0007/job_0008` 停在 `official_validation_passed`，但 `backtests_submitted=0`、`officially_simulated=0`、`submission_ready=0`；根因是 validation 目标只要求 `min_prior_score_for_official_validation=60`，会让 60-70 分候选消耗官方验证却无法进入 `min_prior_score_for_official_simulation=70` 的回测槽。`CandidatePoolService.validation_targets()` 现在要求候选同时达到 validation 与 simulation 两个阈值，避免继续制造 validation-only 非提交候选。 | 继续提升生成策略质量与多样性；该修复不声称已经产出真实可提交 Alpha。 |
| PROD-002 高云相似候选过晚阻断 | CLOSED_CURRENT | 当前 readiness 证据显示最新候选 `max_similarity=1.0`，最终提交门禁会阻断，但此前 `BatchBacktestCoordinator` 只按分数、重复表达式和已有 official work 选择 official backtest，未显式跳过高云相似候选，可能浪费 official simulation 槽位并继续制造不可提交候选。`BatchBacktestCoordinator` 现在支持可选 `risk_evaluator` 和 `max_similarity_threshold`，pipeline 已接入 `_cloud_correlation_risk` 与 `submission_policy.max_expression_similarity`，高相似候选会在 official backtest 计划阶段以 `high_cloud_similarity` 跳过，写入 `high_cloud_similarity_rejected` / `HIGH_CLOUD_SIMILARITY_REJECTED` 硬阻断状态，并记录相似度证据，避免继续留在 pending backtest 队列。 | 继续通过生产 run 验证新候选是否低相似、带官方指标并进入 `submission_ready`；该修复不声明现有 ledger 已 ready。 |
| PROD-003 回测候选先截断后过滤导致安全候选饥饿 | CLOSED_CURRENT | `_backtest_targets()` 之前先调用 `CandidatePoolService.backtest_targets(..., batch_size=active_limit)` 截断候选，再交给 `BatchBacktestCoordinator` 做高云相似过滤；当前排候选被高相似硬阻断时，后排已经通过 validation 且达到 simulation 阈值的低相似候选可能没有机会补上空出的 official backtest 槽。`pipeline_candidates.py` 现在把完整 `pending_backtest_candidates()` 队列交给 coordinator，由 coordinator 统一过滤、硬阻断并按容量选满批次。 | 保持官方 simulation 阈值不变；该修复只改变候选选择顺序，避免安全候选被队列截断饿死。 |
| PROD-004 高相似 pending 过晚归档导致 validation 配额被虚占 | CLOSED_CURRENT | 主循环在计算 validation quota 时会先统计 pending backtest 数；若 pending 中只有高云相似候选，旧逻辑会把唯一回测槽视为已占用，导致本轮不再验证后排安全候选，随后高相似候选才在 fill slot 阶段被拦下，槽位空置。`_validation_quota()` 与 `_validate_for_open_backtest_slots()` 现在会先执行 pending preflight，`HIGH_CLOUD_SIMILARITY_REJECTED` 会从 `pool_by_expression` 归档并加入 `blocked_expressions`，释放 validation 配额并阻止同表达式回流。 | 保持 validation/simulation 官方阈值不变；该修复只提前归档已经被高相似证据硬拒绝的 pending 候选。 |
| PROD-005 官方字段缺 dataset 引用导致生产生成退化到 `returns` fallback | CLOSED_CURRENT | 当前 `data/official_fields.json` 字段记录只有 `name/category/delay/coverage`，没有逐字段 `dataset` 引用；旧 `OfficialDataLoader.get_fields(dataset_id)` 与 `FieldDatasetMapper.build()` 只接受 `field.dataset.id`，导致 `analyst4` 等 17 个官方 dataset 在 mapper/theme engine 中字段数为 0。生产 run 因此只能退到 bare fallback，最新 ledger 反复生成 `rank(ts_delta(returns, 10))`，分数 `66.9` 且云相似 `1.0`。现在 `OfficialDataset` 保留官方 `category`，loader 在缺精确 dataset 引用时按 dataset category 回退，mapper 通过同一 loader 规则建索引；`analyst4` 字段池恢复到 1324，`DynamicThemeEngine.generate(..., n=20)` 与 `HypothesisDrivenGenerator.generate(20, "analyst4")` 均可生成 20 个多字段候选。 | 这是生成链路修复，不改变评分/提交门槛；后续生产 run 仍必须通过官方 validation、simulation、metrics 与相似度门禁。 |
| PROD-006 `ThemeEngine.mutate_expression()` 窗口替换污染带数字字段名 | CLOSED_CURRENT | 生成器在替换窗口数字时使用普通字符串替换，且正则未排除前一位数字，`analyst_field_15` 这类官方字段可能被误改成 `analyst_field_13` / `analyst_field_150` 等不存在字段，导致候选在官方验证前已经不可用。现在 mutation 使用正则 match 回调，并要求数字两侧都不是字段标识符字符（字母/数字/下划线），只替换真正的窗口数字；临时 pipeline 探针确认 `unknown_fields=[]`。 | 保持表达式 mutation 多样性，但禁止生成官网不存在的字段名。 |
| PROD-007 提交门禁口径未在所有入口复核 official PASS 与 `submit_candidate` | CLOSED_CURRENT | 为回应“不能为测试降低评分/提交标准”的边界审计：`scripts/check_live_submit_readiness.py` 过去已要求 `submission_ready`、official Alpha ID、official metrics/pass_fail 与低云相似度，但未把 `decision_band == submit_candidate` 写成 eligible 硬条件，也未把 `submission.local_backtest.pass_local=false` 显式呈现为 `local_backtest_failed` 阻塞原因；`web_submission_safety.py` 的手工提交 preflight 也主要依赖 `gate.submission_ready` 和 official ID，未独立复核 official metrics/pass_fail 与本地提交评分档。现在 readiness 与 Web preflight 均 fail closed，硬要求保留为 `pass_fail=PASS`、`decision_band=submit_candidate` 且不降低：缺 official metrics、缺 pass/fail、`pass_fail != PASS`、`decision_band != submit_candidate`、或本地回测明确失败都不可提交。真实 ledger 复测仍为 `ready_to_submit=false`、`eligible_count=0`，最新候选新增 `decision_band_not_submit_candidate` 与 `local_backtest_failed` 阻断原因。 | 后续任何提交入口都必须同时满足官方 PASS、完整 official metrics、低云相似度、`submit_candidate` 本地评分档、本地回测未失败与人工确认；`live submit` 非阻塞只适用于缺陷跟踪闭环，不代表候选可提交，不能声明已有可提交 Alpha。 |
| PROD-008 假设驱动/ThemeEngine 生成路径未统一复核 active dataset 字段 | CLOSED_CURRENT | 生产探针显示 `analyst4` 已有 1324 个字段后，候选仍可能从 hypothesis semantic category 或 ThemeEngine 模板带入当前 dataset 外的 `returns`/语义字段，导致本地 `data_fields` 与最终表达式不一致、生成多样性被拥挤模板拖低。现在 `FieldSelector` 会用 hypothesis category/examples 在 active dataset 字段池内做语义映射，不发明字段；`HypothesisDrivenGenerator` 对 hypothesis、experience feedback、random exploration 三条路径统一做最终表达式字段清洗，`returns` 不再在缺失于当前字段池时被无条件豁免，候选 `data_fields` 从最终表达式回读。非提交探针确认 `unknown_counter=[]`、`returns_unknown_count=0`，最高本地档位仍为 `optimize_before_submit`。 | 这是生成质量修复，不改变 official API 标准、本地评分阈值或提交门禁；仍需官方 simulation metrics、`pass_fail=PASS`、低云相似度和 `decision_band=submit_candidate` 才能提交。 |
| PROD-009 生成字段池混入明显元数据字段 | CLOSED_CURRENT | 本地非提交探针发现当前 `analyst4` 官方字段只有 `category/delay/coverage`，没有可直接依赖的 numeric 类型信息，`ThemeEngine` 和 hypothesis semantic fallback 会把 `actuals_reporting_currency`、`anl4_*_flag`、`VECTOR` 等明显元数据字段当成普通信号字段进入表达式，浪费候选槽并降低官方验证前质量。新增 `brain_alpha_ops/research/field_quality.py`，只在生成阶段排除 `currency/flag/unit/VECTOR` 等非信号字段；`ThemeEngine`、旧 `CandidateGenerator` fallback、`HypothesisDrivenGenerator` active dataset 字段池均接入该 helper。复测非提交探针显示 `metadata_token_fields=[]`、`unknown=[]`、`returns_count=0`、`similarity_pairs_ge_0_90=0`，最高仍为 `optimize_before_submit`，未降低评分或提交标准。 | 后续可继续用官方 simulation 结果学习更细的字段偏好；当前修复只提升候选生成质量，不声明产出可提交 Alpha。 |
| PROD-010 生成器产出字段函数与关键字参数表达式导致候选在官方验证前失效 | CLOSED_CURRENT | 本地非提交探针发现 `winsorize(..., std=5)` 会因解析器不支持关键字参数而把 `std` 误识别为字段；随机探索/ThemeEngine 变异路径还会把 active dataset 字段误当函数调用，例如 `actual_cashflow_per_share_value_quarterly(field, subindustry)`，在本地表达式引擎中表现为 `unknown_operators`，直接减少可进入官方验证的候选。现在 `expression_ast.py` 支持函数关键字参数并不会把关键字名计入字段；`HypothesisDrivenGenerator` 在 hypothesis、experience feedback、random exploration 三条路径统一把字段函数调用归一化为官方支持的 `group_rank` / `rank(ts_delta(...))` 结构。复测非提交探针显示 `analyst4` 生成 `74` 条，`valid=74`、`blocked=0`、`parsed_false=0`、`std_unknown_field_count=0`、`field_call_pattern_count=0`。 | 这是生成合法性修复，不改变评分阈值、官方 PASS 要求、`submit_candidate` 门槛或 live submit gate；后续仍需真实 official metrics、`pass_fail=PASS`、低云相似度和 `decision_band=submit_candidate`。 |
| PROD-011 小写生成家族与 `{WINDOW3}` 未填充导致候选画像/表达式失真 | CLOSED_CURRENT | 生产探针显示候选 family 多为小写 `hybrid` / `liquidity` / `volatility`，但默认 prior 与参数化 prior 只按 `Hybrid` / `Liquidity` / `Volatility` 大小写精确匹配，导致多样性维度被错压；`submission_checklist` 也会让小写 `momentum` 绕过拥挤模板惩罚。同时 `ThemeEngine` 模板已包含 `{WINDOW3}`，旧 `_fill_placeholders()` 只替换 `{WINDOW}` / `{WINDOW2}`，会残留非法占位符并制造官方验证前无效表达式。现在 scoring 统一使用 `normalize_family_label()` 做大小写无关比较，`ThemeEngine` 用通用 `{WINDOW\d*}` 替换所有编号窗口；新增回归测试覆盖默认/参数化 prior、momentum checklist 严格性和 `{WINDOW3}` 解析。readiness 复核仍为 `ready_to_submit=false`、`eligible_count=0`。 | 这是候选画像和表达式合法性修复，不改变 `min_sharpe` / `min_fitness` / official PASS / `submit_candidate` / 相似度门禁；仍需真实 official metrics、`pass_fail=PASS`、低云相似度和人工确认。 |
| PROD-012 生成候选结构太弱且混入精确分组字段 | CLOSED_CURRENT | 当前 readiness 仍确认没有可提交候选：最好候选 `score=66.9`、`decision_band=research_only`、缺官方 Alpha ID、缺 official metrics/pass_fail，且 `max_similarity=1.0`。根因不是评分门槛过高，而是生成路径仍会产出结构较弱的单/少字段表达式，并可能把精确分组字段 `sector` / `subindustry` 当作数值信号字段使用，导致候选在进入官方 simulation 前质量不足。`DynamicThemeEngine.generate()` 现在在字段数足够时先注入高结构 `hybrid` 模板，使用 4 个不同字段组合 time-series delta/mean、`ts_std_dev` 归一化、winsorize/rank/group_rank 风险控制；`_fill_placeholders()` 支持 `{FIELD_C}` / `{FIELD_D}` 并优先选择不同字段；`field_quality.py` 精确排除 `country` / `industry` / `market` / `sector` / `subindustry` 这些非数值分组字段，同时保留 `industry_relative_value_signal` 这类真实信号字段。非提交探针显示多个 dataset 可生成本地 prior `85.24` 的高结构候选，`bad_signal_slots=0`；`group_rank(..., subindustry)` 这类分组参数仍允许存在，但不再被当作数值信号槽。 | 这是候选生产质量修复，不降低任何官网/API 或本地提交标准；`require_official_pass`、`require_official_metrics`、`decision_band=submit_candidate`、官方 `pass_fail=PASS`、低云相似度和 submit preflight 仍然是硬门槛。当前 `ready_to_submit=false`、`eligible_count=0`，不能声明已有可提交 Alpha。 |
| PROD-013 `ThemeEngine.mutate_expression()` 污染关键字参数数字 | CLOSED_CURRENT | 本地非提交探针发现高结构模板虽然能生成更强候选，但 mutation 会把所有 3-252 的数字都当作窗口替换，导致 `winsorize(..., std=4)` 被误改成 `std=120` 这类非法/失真参数。根因是 `_replace_window()` 只判断数字两侧是否为字段标识符，没有识别 `name=` 前缀。现在 `_replace_window()` 遇到关键字参数数字会保留原值，只继续变异真正的 positional window；新增 `test_theme_engine_mutation_preserves_keyword_argument_numbers` 覆盖 `std=4` 不变。复测多个 dataset 的非提交生成探针显示 `bad_std=[]`，同时当前 readiness 仍是 `ready_to_submit=false`、`eligible_count=0`。 | 这是表达式合法性和候选质量修复，不降低、不绕过任何官网/API 或本地提交标准；即便本地评分档出现 `submit_candidate` 表达式，也不能声明已有可提交 Alpha，仍必须具备官方 Alpha ID、official metrics、`pass_fail=PASS`、低云相似度和 submit preflight 通过。 |
| PROD-014 Web 批量检查可提交状态宽于真实提交门禁 | CLOSED_CURRENT | `web_candidate_selection.is_passed_candidate_for_check()` 曾把仅有 official ID + `pass_fail=PASS` 的候选也归入 passed candidates；`check_candidate_availability()` 的 `production_gate` 也未显式复核 `decision_band=submit_candidate`。结果是 Web 批量检查可能把本地未到 submit band 的候选显示为 `SUBMITTABLE`，虽然真正 `submit_candidate` preflight 会再挡住。现在 passed candidates 只承认本地 `submission_ready`；可提交性检查新增 `official_pass_fail` 和 `decision_band_submit_candidate` 两个硬检查，`optimize_before_submit` 会保持 `BLOCKED`，不会发起 official pre-submit 调用。 | 这是展示/检查口径收紧，不降低、不绕过任何官网/API 或本地提交标准；UI 状态不得宽于真实提交门禁，仍必须满足 official ID、official metrics、`pass_fail=PASS`、`decision_band=submit_candidate`、低云相似度和 submit preflight。当前 `ready_to_submit=false`、`eligible_count=0`，不能声明已有可提交 Alpha。 |
| PROD-015 生成阶段去重后不补足候选导致官方验证机会不足 | CLOSED_CURRENT | 本地非提交探针发现当前代码已能从官方字段缓存生成本地 `submit_candidate` 档多字段候选，但 `GenerationPhaseService` 默认只尝试一轮；当表达式去重或相似度过滤跳过候选时，请求 `requested=30` 只能得到 25-27 个，减少进入 official validation/simulation 的机会。现在 `ResearchBudget.max_generation_attempts=5`，pipeline 会把该值传入 `GenerationPhaseService`，去重后继续补足候选；复测本地非提交探针显示 `analyst4` / `fundamental6` / `model16` / `news12` / `pv1` 均为 `requested=30`、`generated=30`、`high_similarity_pairs=0`、`parse_failures=0`，且仍能产出本地 `submit_candidate` 档候选。 | 这是生产候选探索量修复，不降低、不绕过任何官网/API 或本地提交标准；官方 `pass_fail=PASS`、完整 official metrics、低云相似度、`decision_band=submit_candidate` 和 submit preflight 仍是硬门槛。当前 `ready_to_submit=false`、`eligible_count=0`，不能声明已有可提交 Alpha。 |
| PROD-016 Stub/mock 官方 ID 未被所有提交证据链路硬阻断 | CLOSED_CURRENT | 本地生产 stub 会生成 `prod_stub_alpha_*` 这类看似 official 的 ID；如果只检查 official ID、`pass_fail=PASS`、official metrics 和本地 `submit_candidate`，stub 证据可能被误认作真实官网证据。现在 `looks_non_production_alpha_id()` 和 `non_production_source_reasons()` 明确识别 `stub` / `prod_stub` / `prod-stub`；Web legacy/advisory preflight 会以 `NON_PRODUCTION_ALPHA_ID` 阻断；live readiness 会以 `non_production_official_alpha_id` 阻断。 | 这是提交证据链路收紧，不降低、不绕过任何官网/API 或本地提交标准；本地 stub 只能用于 fail-closed 回归测试，不能证明已有可提交 Alpha。即使 stub 结果带 `pass_fail=PASS`，仍必须有真实官网 Alpha ID、真实 official metrics、低云相似度、`decision_band=submit_candidate` 和 submit preflight 通过。当前 `ready_to_submit=false`、`eligible_count=0`，不能声明已有可提交 Alpha。 |
| PROD-017 高云相似候选未在官方验证前 fail-closed | CLOSED_CURRENT | 生产 ledger 说明最新候选在 official validation 后仍因 `max_similarity=1.0`、`decision_band=research_only`、缺 official metrics/pass_fail 而不可提交；旧流程只在 official simulation/backtest plan 阶段统一做高云相似阻断，未验证的高分候选仍可能先消耗 official validation 调用额度。现在 `pipeline_candidates.py` 新增 `_reject_high_cloud_similarity_before_official()`，`_validation_targets()` 会在调用 official validation 前复用现有云相似度证据，命中时写入 `HIGH_CLOUD_SIMILARITY_REJECTED` 并跳过官方验证；回归 `test_pipeline_skips_high_cloud_similarity_before_official_validation` 覆盖高分高相似候选不进入 `validate_expression`，低相似候选仍继续验证。 | 这是 official validation 前置 fail-closed，不降低、不绕过任何官网/API 或本地提交标准；真实提交仍必须满足 official Alpha ID、official metrics、官方 `pass_fail=PASS`、低云相似度、`decision_band=submit_candidate` 和 submit preflight。当前 `ready_to_submit=false`、`eligible_count=0`，不能声明已有可提交 Alpha。 |
| PROD-018 直接调用假设驱动生成器时重复表达式会导致候选少产 | CLOSED_CURRENT | 本地非提交探针发现 `HypothesisDrivenGenerator.generate(30, dataset_id=...)` 在遇到 `duplicate_expression_skipped` 后会停止在初始请求次数内，导致 `pv1` / `analyst4` / `model16` 等 direct generator 调用只返回 21-29 个候选；pipeline 外层 `GenerationPhaseService` 已能补足，但 `_top_up_candidate_pool()` 等直接入口仍可能减少进入 official validation/simulation 的候选供给。现在 `HypothesisDrivenGenerator.generate()` 在普通模式下也保留 3x 内部重试预算；新增 `test_generator_retries_after_duplicate_expression_skips` 覆盖重复表达式后继续补足唯一候选；复测 Local non-submit direct generator refill probe 显示 `analyst4` / `fundamental6` / `model16` / `news12` / `pv1` 均为 `requested=30`、`generated=30`、`fallback_count=0`，且仍能产出本地 `submit_candidate` 档候选。 | 这是候选供给完整性修复，不降低、不绕过任何官网/API 或本地提交标准；本地 `submit_candidate` 只代表需要进入官方证据链，真实提交仍必须满足 official Alpha ID、official metrics、官方 `pass_fail=PASS`、低云相似度和 submit preflight。当前 `ready_to_submit=false`、`eligible_count=0`，不能声明已有可提交 Alpha。 |
| PROD-019 本地失败知识未阻止高换手/近似重复结构复发 | CLOSED_CURRENT | 当前 production readiness 仍显示最好候选 `local_backtest_failed`、`max_similarity=1.0`、缺 official Alpha ID、缺 official metrics/pass_fail 且不可提交；根因不是评分标准过高，而是 `_record_local_backtest_knowledge()` 过去把所有本地失败统一记为 `low_signal`，即使 `Turnover > 70% (FAIL)` 也不会进入 `high_turnover` 失败类别；同时 `CandidateGenerator._expression_forbidden()` 只检查 `forbidden_patterns` 原文子串，无法识别同一结构的 `expression_key` / `expression_fingerprint` 或 `expression_similarity >= 0.90` 的近似失败表达式。现在本地回测失败会把高换手候选写为 `high_turnover` 并保留失败分类，生成器会基于 `expression_key`、`expression_fingerprint` 和 `expression_similarity` 拦截已知失败结构，减少继续生产同类不可提交候选。 | 这是失败反馈和防复发修复，不降低、不绕过任何官网/API 或本地提交标准；官方 `pass_fail=PASS`、完整 official metrics、低云相似度、`decision_band=submit_candidate` 和 submit preflight 仍是硬门槛。当前 `ready_to_submit=false`、`eligible_count=0`，不能声明已有可提交 Alpha。 |
| PROD-020 假设驱动 forbidden 约束弱于普通生成器且 bare fallback 可绕回失败结构 | CLOSED_CURRENT | 当前 production readiness 仍为 `ready_to_submit=false`、`eligible_count=0`，最好候选仍被本地回测失败、缺 official Alpha ID/metrics 与高云相似度阻断；根因不是评分标准过高，而是 `HypothesisDrivenGenerator._expression_forbidden()` 过去只做 `forbidden_patterns` 原文子串匹配，弱于 `CandidateGenerator` 的 `expression_key`、`expression_fingerprint`、`expression_similarity` 近似结构阻断；同时 `_generate_bare_fallback()` 在 ThemeEngine 不可用或 forbidden fallback 时没有再检查 forbidden，已知失败的 `rank(ts_delta(...))` 结构可能从兜底路径绕回候选池。现在 `HypothesisDrivenGenerator` 使用 `_FORBIDDEN_PATTERN_SIMILARITY_THRESHOLD=0.90` 做同等结构/指纹/相似度拦截，bare fallback 会跳过 forbidden 表达式；新增 `test_generator_knowledge_constraints_block_fallback_fingerprint_and_similarity` 覆盖 fingerprint、相似窗口结构和 bare fallback 绕回。 | 这是失败知识贯穿全生成路径的防复发修复，不降低、不绕过任何官网/API 或本地提交标准；官方 `pass_fail=PASS`、完整 official metrics、低云相似度、`decision_band=submit_candidate` 和 submit preflight 仍是硬门槛。当前 `ready_to_submit=false`、`eligible_count=0`，不能声明已有可提交 Alpha。 |
| PROD-021 持久化任务只保留候选 preview 导致 readiness 审计可能漏看隐藏提交候选 | CLOSED_CURRENT | 当前 async/web 任务账本会把 `candidates` 压缩成 `candidates_count` + `candidates_preview`，旧 readiness 审计把 `candidates_preview` 当作完整候选池；如果第 6 个以后才出现带 official Alpha ID、official metrics、`pass_fail=PASS`、低云相似度与 `decision_band=submit_candidate` 的候选，审计会漏判，进而错误报告 `eligible_count=0`。现在 `JobStore` 压缩时会额外保留 `candidates_submission_evidence` / `passed_candidates_submission_evidence` 这类提交证据子集；`scripts/check_live_submit_readiness.py` 会读取这些证据，并对只有 `candidates_count` + `candidates_preview`、没有提交证据子集的旧账本输出 `candidate_pool_truncated` 诊断。新增 `test_compact_runtime_result_keeps_submission_evidence_outside_preview` 和 `test_live_submit_readiness_uses_submission_evidence_outside_compacted_preview` 覆盖隐藏在 preview 外的合格候选不会被漏看。 | 这是 readiness 证据完整性修复，不降低、不绕过任何官网/API 或本地提交标准；只有具备真实 official evidence、`pass_fail=PASS`、低云相似度、`decision_band=submit_candidate` 和 submit preflight 的候选才会被判 eligible。当前真实账本仍是 `ready_to_submit=false`、`eligible_count=0`，不能声明已有可提交 Alpha。 |
| PROD-022 readiness 只给布尔结果，无法解释生产候选断点 | CLOSED_CURRENT | 当前真实账本为什么生产不出可提交候选，需要区分“官方 validation 通过但没有 official simulation metrics”、“async/web local-only 候选不能证明提交资格”、“本地回测失败”、“高云相似”和“候选族缺 official evidence”。现在 `scripts/check_live_submit_readiness.py` 输出 `production_gap_summary`、`latest_blocking_reason_counts`、`job_family_blocking_reason_counts`、`primary_chain_summary`、`job_family_chain_summary`，会把当前断点机器可读地标记为 `official_validation_without_simulation`、`local_only_candidate_jobs`、`latest_candidate_local_backtest_failed`、`latest_candidate_high_cloud_similarity`、`candidate_family_missing_official_metrics` 等。新增 `test_live_submit_readiness_reports_production_gap_summary` 覆盖这些诊断只解释原因，不改变 eligible 判定。 | 这是诊断透明度修复，不降低、不绕过任何官网/API 或本地提交标准；`pass_fail=PASS`、完整 official metrics、低云相似度、`decision_band=submit_candidate` 和 submit preflight 仍是硬门槛。当前 `ready_to_submit=false`、`eligible_count=0`，不能声明已有可提交 Alpha。 |
| PROD-023 生成层继续产出直接收益率 delta 失败结构 | CLOSED_CURRENT | 当前最新真实候选是 `rank(ts_delta(returns, 10))`，本地回测明确 `Turnover 154.83% > 70% (FAIL)` 且云端相似度 `max_similarity=1.0`，说明生产不出可提交候选的直接原因之一是 fallback/普通生成路径仍会把 `rank(ts_delta(returns, N))` 这类直接收益率 delta 模板放入候选池。现在 `brain_alpha_ops/research/fallback_generation.py` 提供 `is_high_turnover_generation_risk()`，以 `direct_returns_delta_window=N` 标记并拦截该形态；`HypothesisDrivenGenerator._expression_forbidden()`、bare fallback、`CandidateGenerator._generate_dynamic()` 与 `_generate_fallback()` 都会在生成前跳过它。新增 `test_generation_risk_blocks_direct_returns_delta_without_blocking_other_returns_usage`、`test_candidate_generator_blocks_direct_returns_delta_risk` 和 `test_bare_fallback_deduplicates_single_field_batch` 覆盖直接 `returns` delta 被拦截、其他 `returns` 用法不被误杀、单字段 fallback 不绕回失败模板。 | 这是候选生成质量修复，不降低、不绕过任何官网/API 或本地提交标准；官方 `pass_fail=PASS`、完整 official metrics、低云相似度、`decision_band=submit_candidate`、本地回测未失败和 submit preflight 仍是硬门槛。当前 `ready_to_submit=false`、`eligible_count=0`，不能声明已有可提交 Alpha。 |
| PROD-024 压缩候选证据子集不完整导致预览外不合格候选不可审计 | CLOSED_CURRENT | PROD-021 只确保预览外“可能可提交”的候选不会被漏看，但旧 `JobStore` 仍只保存提交证据子集；如果 preview 外还有大量 `research_only` / `optimize_before_submit` / 缺 official metrics 的候选，readiness 只能看到 `candidates_count` 与部分 `candidates_submission_evidence`，无法对所有隐藏候选形成 auditable candidate 覆盖，也无法稳定解释每个候选的阻断原因。现在 `_candidate_submission_audit_evidence()` 会为 preview 外每个候选保留最小审计字段：Alpha ID、official Alpha ID、`scorecard.decision_band`、`gate.submission_ready`、official metrics/pass_fail、云相似度和 `submission.local_backtest`；`scripts/check_live_submit_readiness.py` 会对 preview + evidence 去重后比较 `candidates_count`，证据不完整时继续输出 `candidate_pool_truncated`。新增 `test_live_submit_readiness_reports_truncated_candidate_preview_with_incomplete_evidence` 和 `test_compact_runtime_result_keeps_submission_evidence_outside_preview` 覆盖 evidence 子集不完整仍 fail-closed，完整审计证据才消除截断诊断。 | 这是候选池审计完整性修复，不降低、不绕过任何官网/API 或本地提交标准；`pass_fail=PASS`、完整 official metrics、低云相似度、`decision_band=submit_candidate`、本地回测未失败和 submit preflight 仍是硬门槛。当前 `ready_to_submit=false`、`eligible_count=0`，不能声明已有可提交 Alpha。 |
| PROD-025 缺陷跟踪闭环缺少提交标准不可降级的机器守卫 | CLOSED_CURRENT | 用户质疑“凭什么为了测试降低评分/提交标准”暴露出一个真实流程缺陷：跟踪检查过去主要校验配置阈值和当前 readiness 结果，缺少对 `scripts/check_live_submit_readiness.py` eligible 语义的合成候选红线测试，未来若有人把缺 official ID、缺 official metrics、`pass_fail != PASS`、`decision_band != submit_candidate`、`submission.local_backtest.pass_local=false`、缺云相似度或高云相似度改成可提交，报告可能仍靠文字声称“不降低”。现在 `scripts/check_live_submit_readiness.py` 会从 `config/run_config.json` 读取官方阈值，原有 `missing_official_alpha_id`、`non_production_official_alpha_id`、`missing_official_metrics`、`official_pass_fail_not_pass`、`decision_band_not_submit_candidate`、`local_backtest_failed`、`missing_cloud_similarity`、`high_cloud_similarity` 仍是硬阻断；并且新增复核 `min_sharpe=1.25`、`min_fitness=1.0`、`platform_max_turnover=0.70`、`max_self_correlation=0.70` 等门槛。指标字段不完整会输出 `missing_official_metric_fields`，数值不达标会输出 `official_sharpe_below_threshold`、`official_fitness_below_threshold`、`official_turnover_above_threshold`、`official_self_correlation_above_threshold`、`official_prod_correlation_above_threshold`、`official_weight_concentration_above_threshold`。`scripts/check_prod_defect_tracking.py` 的 `readiness_gate_invariants` 同步构造这些违规候选，并要求它们保持 `eligible_count=0`；新增 `test_live_submit_readiness_requires_official_metrics_above_config_thresholds`、`test_live_submit_readiness_requires_complete_official_release_metrics` 与 `test_prod_defect_tracking_rejects_readiness_gate_invariant_relaxation` 证明一旦 readiness 被放松成 ready，缺陷跟踪检查会失败。 | 这是提交标准防降级守卫，不降低、不绕过任何官网/API 或本地提交标准；只有真实 official Alpha ID、完整 official metrics、`pass_fail=PASS`、官方指标达到 `config/run_config.json` 门槛、低云相似度、`decision_band=submit_candidate`、本地回测未失败和 submit preflight 都满足时才可进入人工确认。当前 `ready_to_submit=false`、`eligible_count=0`，不能声明已有可提交 Alpha。 |
| QA-001 OpsConfig 隔离上下文写入误落到项目 data 目录 | CLOSED_CURRENT | `tests.production_api_stub.write_template_safe_official_context()` 直接把传入 config 返回给 `save_official_context_json()`；当调用方传 `OpsConfig` 而不是 `RunConfig` 时，保存逻辑访问不到 `.ops.storage_dir`，会 fallback 到 runtime root 的 `data/official_*`，污染工作区并削弱隔离验证可信度。该 helper 现在会把裸 `OpsConfig` 包装成带 `.ops` 的对象，测试确认 `OpsConfig(storage_dir=tmp)` 只写入 tmp。 | 这是验证辅助缺陷，不改变生产评分或官网门禁；用于保证后续 stub pipeline 探针不污染真实数据文件。 |

本轮已执行的验证：

- `python3 -c "import brain_alpha_ops.research.backtest_finalization"` — PASS
- `.venv/bin/python -m pytest tests/test_backtest_finalization.py -q` — 4 passed
- `.venv/bin/python -m pytest tests/test_pipeline.py -q` — 29 passed
- `.venv/bin/python -m pytest tests/test_cli.py::test_cli_run_rejects_non_official_base_url_override tests/test_cli.py::test_cli_run_accepts_official_base_url_override tests/test_web.py::test_web_config_from_payload_rejects_non_official_base_url_in_production -q` — 3 passed
- `.venv/bin/python -m pytest tests/test_quality_gate.py::test_quality_gate_subprocess_env_filters_sensitive_values -q` — 1 passed
- `.venv/bin/python -m pytest tests/test_web_facade_contract.py tests/test_web_runtime_facade_coverage.py -q` — 13 passed
- `.venv/bin/python -m pytest tests/test_web.py::test_live_react_preview_serves_dist_assets_and_keeps_inline_default tests/test_web_server_lifecycle.py -q` — 6 passed, 1 skipped
- `.venv/bin/python -m pytest tests/test_official_adapter.py::test_list_user_alphas_stops_on_repeated_full_page tests/test_official_adapter.py::test_list_user_alphas_dedupes_items_across_pages_without_page_cap tests/test_official_adapter.py::test_list_user_alphas_has_no_default_page_limit -q` — 3 passed
- `.venv/bin/python -m pytest tests/test_backtest_finalization.py -q` — 5 passed
- `.venv/bin/python scripts/check_python_silent_broad_exceptions.py --json` — PASS, `silent_broad_exception_count=0`, `findings=[]`
- `.venv/bin/python -m pytest tests/test_official_adapter.py::test_official_api_uses_composed_api_components -q` — 1 passed
- `.venv/bin/python -m pytest tests/test_config.py -q` — 27 passed
- `.venv/bin/python run_pipeline.py --validate-only --config config/run_config.json --json` — PASS, `ok=true`, `environment=production`
- `.venv/bin/python -m pytest tests/test_ashare_adapter.py -q` — 9 passed
- `.venv/bin/python -c "from brain_alpha_ops import web; assert web.JOB_REGISTRY.jobs is web.JOBS; print('ok')"` — PASS
- `.venv/bin/python -m pytest tests/test_web.py::test_web_uses_durable_job_stores tests/test_web.py::test_web_job_registry_creates_durable_stores_under_project_root tests/test_web_facade_contract.py -q` — 8 passed
- `.venv/bin/python -m pytest tests/test_web_runtime_facade_coverage.py tests/test_web_server_lifecycle.py -q` — 13 passed
- `.venv/bin/python -m pytest tests/test_web_facade_contract.py tests/test_web_runtime_facade_coverage.py tests/test_web_server_lifecycle.py tests/test_web_http_handler_coverage.py tests/test_web.py::test_web_job_registry_view_tracks_legacy_alias_overrides -q` — 31 passed
- `.venv/bin/python -m pytest tests/test_web_facade_contract.py tests/test_web_runtime_facade_coverage.py tests/test_web_server_lifecycle.py tests/test_web.py::test_web_job_registry_view_tracks_legacy_alias_overrides -q` — 24 passed
- `.venv/bin/python -m pytest tests/test_web_facade_contract.py -q` — 10 passed
- `.venv/bin/python -m pytest tests/test_web_facade_contract.py tests/test_web_runtime_facade_coverage.py tests/test_web.py::{candidate/check/submission targeted cases} tests/test_web_submission_batch.py -q` — 33 passed
- `.venv/bin/python -m pytest tests/test_web_facade_contract.py -q` — 11 passed
- `.venv/bin/python -m pytest tests/test_web_facade_contract.py tests/test_web_runtime_facade_coverage.py tests/test_web.py::{snapshot/storage/config targeted cases} -q` — 30 passed
- `.venv/bin/python -m pytest tests/test_web_facade_contract.py -q` — 12 passed
- `.venv/bin/python -m pytest tests/test_web_facade_contract.py tests/test_web_runtime_facade_coverage.py tests/test_web_server_lifecycle.py tests/test_web_http_handler_coverage.py tests/test_web.py -q` — 109 passed, 10 skipped
- `.venv/bin/python -m pytest tests/test_web_facade_contract.py -q` — 13 passed
- `.venv/bin/python -m pytest tests/test_web_facade_contract.py tests/test_web_runtime_facade_coverage.py tests/test_web_server_lifecycle.py tests/test_web_http_handler_coverage.py tests/test_web.py -q` — 110 passed, 10 skipped
- `.venv/bin/python -m pytest tests/test_web.py::test_web_job_registry_view_tracks_legacy_alias_overrides tests/test_web.py::test_web_uses_durable_job_stores tests/test_web.py::test_web_job_registry_creates_durable_stores_under_project_root tests/test_web_facade_contract.py -q` — 16 passed
- `.venv/bin/python -m pytest tests/test_web_facade_contract.py tests/test_web_runtime_facade_coverage.py tests/test_web_server_lifecycle.py tests/test_web_http_handler_coverage.py tests/test_web.py -q` — 113 passed, 10 skipped
- `.venv/bin/python -m pytest tests/test_web_facade_contract.py tests/test_web_runtime_facade_coverage.py tests/test_web_server_lifecycle.py tests/test_web_http_handler_coverage.py tests/test_web.py -q` — 114 passed, 10 skipped
- `.venv/bin/python -m pytest tests/test_web_facade_contract.py tests/test_web_runtime_facade_coverage.py tests/test_web_server_lifecycle.py tests/test_web_http_handler_coverage.py tests/test_web.py -q` — 115 passed, 10 skipped
- `.venv/bin/python -m pytest tests/test_web_facade_contract.py tests/test_web.py::test_web_uses_durable_job_stores tests/test_web.py::test_web_job_registry_view_tracks_legacy_alias_overrides -q` — 22 passed
- `.venv/bin/python -c "from brain_alpha_ops import web; from brain_alpha_ops.web import JOBS, SUBMIT_LOCK; assert 'JOBS' not in web.__dict__; assert JOBS is web.JOB_REGISTRY.jobs; assert SUBMIT_LOCK is web.JOB_REGISTRY.submit_lock; print('dynamic-job-alias-ok')"` — PASS
- `.venv/bin/python -m pytest tests/test_web_facade_contract.py tests/test_web_runtime_facade_coverage.py tests/test_web_server_lifecycle.py tests/test_web_http_handler_coverage.py tests/test_web.py -q` — 117 passed, 10 skipped
- `.venv/bin/python scripts/check_web_facade_contract.py --json` — PASS, `findings=[]`, `public_brain_alpha_import_count=0`
- `.venv/bin/python scripts/check_live_submit_readiness.py --json` — PASS, `ready_to_submit=false`, `eligible_count=0`, latest candidate blocked by `not_submission_ready`, `decision_band_not_submit_candidate`, missing official ID/metrics and high cloud similarity
- `rg -n "jobs=JOBS|production_store=JOBS|sync_store=SYNC_JOBS|check_store=CHECK_JOBS|submit_lock=SUBMIT_LOCK|RATE_LIMITER\\.check|TASK_EXECUTOR\\.submit|web\\.JOBS|web\\.SYNC_JOBS|web\\.CHECK_JOBS|web\\.ASYNC_JOBS|web\\.SUBMIT_LOCK|web\\.RATE_LIMITER|web\\.TASK_EXECUTOR" brain_alpha_ops/web.py brain_alpha_ops/web_runtime_facade.py` — PASS, no direct legacy state injection/read patterns
- `.venv/bin/python scripts/check_v5_defect_tracking.py --json` — PASS, `findings=[]`
- `.venv/bin/python scripts/check_review_gap_closure_tracker.py --json` — PASS, `findings=[]`, `completion_claimable=true`, `completion_blockers=[]`; `Real BRAIN submit E2E` is retained as non-blocking safety evidence after 2026-06-02 operator confirmation, but this does not lower official submit eligibility or claim a successful live submit while no candidate is eligible
- `.venv/bin/python -m pytest tests/test_candidate_pool.py -q` — 5 passed; validation 目标现在必须达到 official simulation 阈值，避免 validation-only 死胡同
- `.venv/bin/python -m pytest tests/test_batch_backtest_coordinator.py tests/test_candidate_pool.py tests/test_production_diagnostics.py::test_template_safe_context_writes_to_ops_config_storage_dir -q` — 9 passed; 高云相似候选会写入硬阻断状态，validation 目标仍必须达到 official simulation 阈值，OpsConfig 测试上下文只写入临时目录
- `.venv/bin/python -m pytest tests/test_pipeline.py::test_pipeline_scores_and_sorts_before_official_metrics tests/test_pipeline.py::test_pipeline_persists_structured_backtest_error_context_for_rate_limit tests/test_pipeline.py::test_pipeline_keeps_top10_and_submits_top3_backtests tests/test_pipeline.py::test_pipeline_observability_duplicate_guard_blocks_official_validation tests/test_pipeline.py::test_pipeline_backtest_targets_fill_slot_after_high_similarity_skip tests/test_pipeline.py::test_pipeline_validation_quota_ignores_high_similarity_pending_candidate tests/test_pipeline.py::test_pipeline_validate_slots_archives_high_similarity_pending_candidate tests/test_pipeline.py::test_pipeline_skips_high_cloud_similarity_before_official_simulation tests/test_pipeline.py::test_pipeline_local_prefilter_rejects_failed_local_backtest -q` — 9 passed；这些 pipeline 回归未覆盖 `min_prior_score_for_official_validation` / `min_prior_score_for_official_simulation`
- `.venv/bin/python -m py_compile brain_alpha_ops/research/batch_backtest_coordinator.py brain_alpha_ops/research/pipeline_services.py brain_alpha_ops/research/candidate_pool.py brain_alpha_ops/research/pipeline_candidates.py brain_alpha_ops/research/pipeline_official_validation_flow.py brain_alpha_ops/research/pipeline.py tests/production_api_stub.py tests/test_production_diagnostics.py tests/test_batch_backtest_coordinator.py tests/test_candidate_pool.py tests/test_pipeline.py` — PASS
- Stub pipeline probe with `ProductionBrainAPIStub` and temp `OpsConfig.storage_dir` — completed without touching `data/official_*`; `official_validation_attempted=2`, `backtests_submitted=2`, `officially_simulated=2`, `submission_ready=0`
- `.venv/bin/python -m pytest tests/test_hypothesis_driven_generator.py tests/test_fetch_official_context.py -q` — 41 passed；覆盖 category-only 官方字段到 dataset category 的回退映射，以及 `ThemeEngine` 不再污染带数字字段名
- `.venv/bin/python -m pytest tests/test_pipeline.py::test_pipeline_skips_high_cloud_similarity_before_official_simulation tests/test_pipeline.py::test_pipeline_backtest_targets_fill_slot_after_high_similarity_skip tests/test_pipeline.py::test_pipeline_validation_quota_ignores_high_similarity_pending_candidate tests/test_pipeline.py::test_pipeline_local_prefilter_rejects_failed_local_backtest -q` — 4 passed
- `.venv/bin/python -m py_compile brain_alpha_ops/data/schemas.py brain_alpha_ops/data/loader.py brain_alpha_ops/data/field_dataset_mapper.py brain_alpha_ops/research/theme_engine.py tests/test_fetch_official_context.py tests/test_hypothesis_driven_generator.py` — PASS
- Local category-only pipeline probe with temp `OpsConfig.storage_dir`, `auto_submit=False`, `max_official_validations_per_cycle=0`, `max_official_simulations_per_cycle=0` — produced 8 retained candidates from analyst category fields, `unknown_fields=[]`, `submission_ready=0`
- `.venv/bin/python -m pytest tests/test_live_submit_readiness.py tests/test_web_submission_safety.py tests/test_web.py::test_submission_preflight_reports_stale_cloud_code tests/test_web.py::test_submit_candidate_reports_duplicate_expression_code tests/test_web.py::test_submit_candidate_requires_observability_confirmation tests/test_web.py::test_submit_candidate_requires_confirmation_when_observability_preflight_fails tests/test_web.py::test_submit_batch_requires_observability_confirmation tests/test_web.py::test_submit_batch_requires_confirmation_when_observability_preflight_fails -q` — 20 passed；覆盖 readiness/Web submit preflight 必须 official PASS、完整 official metrics、`decision_band=submit_candidate`
- `.venv/bin/python -m py_compile scripts/check_live_submit_readiness.py brain_alpha_ops/web_submission_safety.py tests/test_live_submit_readiness.py tests/test_web_submission_safety.py tests/test_web.py` — PASS
- `git diff --check -- scripts/check_live_submit_readiness.py brain_alpha_ops/web_submission_safety.py tests/test_live_submit_readiness.py tests/test_web_submission_safety.py tests/test_web.py` — PASS
- `.venv/bin/python -m pytest tests/test_hypothesis_driven_generator.py tests/test_expression_ast.py tests/test_expression_engine.py -q` — 53 passed；覆盖关键字参数解析、字段函数归一化、随机探索路径清洗和假设驱动表达式合法化
- Local non-submit generation probe for `analyst4` with `HypothesisDrivenGenerator` + `ExpressionEngine(mode="wq")` — generated 74 candidates, `valid=74`, `blocked=0`, `parsed_false=0`, `std_unknown_field_count=0`, `field_call_pattern_count=0`
- `.venv/bin/python -m pytest tests/test_scoring_gate.py tests/test_hypothesis_driven_generator.py -q` — 54 passed；覆盖 family 大小写归一化、momentum checklist 不绕过、`{WINDOW3}` 占位符填充与解析
- `.venv/bin/python -m py_compile brain_alpha_ops/scoring/shared_scores.py brain_alpha_ops/research/scoring.py brain_alpha_ops/research/theme_engine.py tests/test_scoring_gate.py tests/test_hypothesis_driven_generator.py` — PASS
- `.venv/bin/python scripts/check_live_submit_readiness.py --json` — PASS, `ready_to_submit=false`, `eligible_count=0`, latest candidate still blocked by `not_submission_ready`, `decision_band_not_submit_candidate`, missing official ID/metrics and high cloud similarity
- `.venv/bin/python -m pytest tests/test_hypothesis_driven_generator.py::test_dynamic_theme_generation_seeds_high_structure_templates tests/test_hypothesis_driven_generator.py::test_dynamic_theme_generation_uses_category_only_official_fields tests/test_hypothesis_driven_generator.py::test_dynamic_theme_generation_excludes_metadata_fields -q` — 3 passed；覆盖高结构模板注入、active dataset 字段约束和精确分组字段排除
- `.venv/bin/python -m pytest tests/test_hypothesis_driven_generator.py tests/test_scoring_gate.py tests/test_official_scoring_system.py tests/test_comprehensive_scoring_edge_cases.py::TestApiSimulation tests/test_live_submit_readiness.py -q` — 77 passed；覆盖生成质量、评分门禁、official scoring 对比与 live submit readiness
- `.venv/bin/python -m py_compile brain_alpha_ops/research/theme_engine.py brain_alpha_ops/research/field_quality.py tests/test_hypothesis_driven_generator.py` — PASS
- Local non-submit generation probe for `analyst4` / `fundamental6` / `model16` / `news12` / `pv1` with `DynamicThemeEngine.generate(..., n=30, seed=7)` — each dataset produced high-structure candidates with `max_prior>=85.24`; `bad_signal_slots=0`; exact group names only appeared as group arguments, not signal field slots
- `.venv/bin/python scripts/check_live_submit_readiness.py --json` — PASS, `ready_to_submit=false`, `eligible_count=0`, `ledger_eligible_count=0`, `job_family_eligible_count=0`; 当前最好候选仍因 `research_only`、缺官方 Alpha ID/metrics、缺 `pass_fail` 和高云相似度被阻断
- `.venv/bin/python -m pytest tests/test_generation_phase.py tests/test_budget_and_policy.py -q` — 23 passed；覆盖 `GenerationPhaseService` 去重后继续补足候选，以及 `max_generation_attempts=5` 的预算默认值和正整数校验
- Local non-submit generation refill probe for `analyst4` / `fundamental6` / `model16` / `news12` / `pv1` with `max_generation_attempts=5` — each dataset stayed `requested=30`, `generated=30`, `high_similarity_pairs=0`, `parse_failures=0`; all results are local non-submit evidence only
- `.venv/bin/python scripts/check_prod_defect_tracking.py --json` — PASS, `tracked_prod_count=23`, confirms production tracking is fail-closed, canonical thresholds are unchanged, generation recovery config is `max_generation_attempts=5`, and current readiness remains `ready_to_submit=false` / `eligible_count=0`
- `.venv/bin/python -m pytest tests/test_prod_defect_tracking.py -q` — 18 passed；覆盖当前报告接受、缺少 `PROD-012` / `PROD-013` / `PROD-014` / `PROD-015` / `PROD-016` / `PROD-017` / `PROD-018` / `PROD-023` 证据拒绝、降低 official 阈值拒绝、降低生成补足轮次拒绝、报告未更新却声称可提交拒绝
- `.venv/bin/python -m pytest tests/test_submission_gate.py tests/test_budget_and_policy.py tests/test_web_submission_safety.py tests/test_live_submit_readiness.py -q` — 59 passed；覆盖 `prod_stub_alpha` 这类本地 stub ID 只能触发 fail-closed，不能作为真实官网可提交证据
- `.venv/bin/python -m pytest tests/test_prod_defect_tracking.py tests/test_submission_gate.py tests/test_budget_and_policy.py tests/test_live_submit_readiness.py -q` — 64 passed；覆盖 `test_live_submit_readiness_blocks_failed_local_backtest`、`local_backtest_failed`、`decision_band=submit_candidate`、official metrics / `pass_fail=PASS` 和阈值不降低守卫
- `.venv/bin/python -m pytest tests/test_quality_gate.py::test_quality_gate_runs_core_steps_and_skips_pytest tests/test_quality_gate.py::test_quality_gate_includes_pytest_args_and_propagates_failure tests/test_quality_gate.py::test_quality_gate_can_skip_compile tests/test_quality_gate.py::test_quality_gate_can_include_dependency_audit tests/test_quality_gate.py::test_quality_gate_can_include_static_analysis -q` — 5 passed；确认 `prod_defect_tracking` 已接入质量门禁和静态分析目标
- `.venv/bin/python -m pytest tests/test_hypothesis_driven_generator.py::test_theme_engine_mutation_preserves_keyword_argument_numbers -q` — 1 passed；覆盖 `std=4` 等关键字参数数字不会被窗口 mutation 污染
- `.venv/bin/python -m py_compile brain_alpha_ops/research/theme_engine.py tests/test_hypothesis_driven_generator.py` — PASS
- Local non-submit generation probe after keyword-argument mutation guard — `analyst4` / `fundamental6` / `model16` / `news12` / `pv1` 均为 `bad_std=[]`；这只证明表达式生成质量改善，不代表已有可提交 Alpha
- `.venv/bin/python -m pytest tests/test_hypothesis_driven_generator.py::test_generator_retries_after_duplicate_expression_skips tests/test_generation_phase.py -q` — 4 passed；覆盖 direct generator 和外层 generation phase 均能在重复表达式后继续补足候选
- Local non-submit direct generator refill probe — `analyst4` / `fundamental6` / `model16` / `news12` / `pv1` 均为 `requested=30`、`generated=30`、`fallback_count=0`，且仍只作为本地生成质量证据，不代表已有可提交 Alpha
- `.venv/bin/python -m pytest tests/test_web_candidate_selection.py tests/test_web_check_availability.py -q` — 7 passed；覆盖 passed candidates 不再接受仅 official `PASS` 的候选，以及 `decision_band_submit_candidate` 不达标时保持 `BLOCKED`
- `.venv/bin/python -m pytest tests/test_web.py::test_batch_check_targets_all_passed_candidates tests/test_web.py::test_check_candidate_availability_uses_canonical_duplicate_records tests/test_web.py::test_check_candidate_availability_includes_observability_preflight -q` — 3 passed；确认 Web 批量检查和 availability 现有关键路径未回退
- `.venv/bin/python -m pytest tests/test_pipeline.py::test_pipeline_local_prefilter_rejects_failed_local_backtest tests/test_enhanced_pipeline_components.py::TestCandidateGeneratorKnowledgeConstraints -q` — 3 passed；覆盖 `test_pipeline_local_prefilter_rejects_failed_local_backtest` 写入 `high_turnover` 失败知识，以及 `test_forbidden_patterns_block_expression_fingerprint_and_similarity` 拦截 `expression_fingerprint` / 近似失败结构
- `.venv/bin/python -m pytest tests/test_prod_defect_tracking.py tests/test_live_submit_readiness.py -q` — 24 passed；覆盖 `PROD-019` 追踪证据、禁止降低官方阈值、以及 readiness fail-closed
- `.venv/bin/python scripts/check_prod_defect_tracking.py --json` — PASS，`tracked_prod_count=23`，`findings=[]`，配置仍为 `min_sharpe=1.25`、`min_fitness=1.0`、`platform_max_turnover=0.70`、`require_official_pass=true`、`require_official_metrics=true`、`max_expression_similarity=0.9`
- `.venv/bin/python scripts/check_live_submit_readiness.py --json` — PASS，`ready_to_submit=false`、`eligible_count=0`、`ledger_eligible_count=0`、`job_family_eligible_count=0`；最好候选仍被 `local_backtest_failed`、`missing_official_alpha_id`、`missing_official_metrics`、`high_cloud_similarity` 等原因阻断
- `.venv/bin/python -m pytest tests/test_tasks.py tests/test_live_submit_readiness.py -q` — 20 passed；覆盖 `test_compact_runtime_result_keeps_submission_evidence_outside_preview`、`test_live_submit_readiness_uses_submission_evidence_outside_compacted_preview` 和 `candidate_pool_truncated` 诊断，确认候选 preview 截断不会隐藏真实提交证据
- `.venv/bin/python -m pytest tests/test_tasks.py tests/test_live_submit_readiness.py tests/test_prod_defect_tracking.py -q` — 38 passed；覆盖 compacted candidate submission evidence、`test_live_submit_readiness_reports_production_gap_summary`、`production_gap_summary`、`job_family_blocking_reason_counts` 和 `PROD-022` 追踪证据，确认原因诊断不改变 `ready_to_submit=false` / `eligible_count=0`
- `.venv/bin/python -m pytest tests/test_hypothesis_driven_generator.py::test_bare_fallback_rotates_fields_and_templates_without_duplicates tests/test_hypothesis_driven_generator.py::test_bare_fallback_deduplicates_single_field_batch tests/test_hypothesis_driven_generator.py::test_generator_knowledge_constraints_block_fallback_fingerprint_and_similarity -q` — 3 passed；覆盖 `HypothesisDrivenGenerator._expression_forbidden()` 的 `expression_key` / `expression_fingerprint` / `expression_similarity` 阻断，以及 `_generate_bare_fallback()` 不再绕回 forbidden 失败结构
- `.venv/bin/python -m pytest tests/test_hypothesis_driven_generator.py::test_bare_fallback_deduplicates_single_field_batch tests/test_hypothesis_driven_generator.py::test_generation_risk_blocks_direct_returns_delta_without_blocking_other_returns_usage tests/test_generation.py::test_candidate_generator_blocks_direct_returns_delta_risk tests/test_pipeline.py::test_pipeline_local_prefilter_rejects_failed_local_backtest -q` — 4 passed；覆盖 `rank(ts_delta(returns, N))` 在生成前被拦截、其他 `returns` 用法保留、失败本地回测仍 fail-closed
- `.venv/bin/python -m pytest tests/test_tasks.py tests/test_live_submit_readiness.py -q` — 22 passed；覆盖 `_candidate_submission_audit_evidence` 为预览外非达标候选保留最小审计字段、`test_live_submit_readiness_reports_truncated_candidate_preview_with_incomplete_evidence` 证明 evidence 子集不完整仍输出 `candidate_pool_truncated`
- `.venv/bin/python -m pytest tests/test_prod_defect_tracking.py -q` — 21 passed；覆盖 `PROD-024` / `PROD-025` 追踪证据、禁止降低官方阈值、以及报告未更新却声称可提交时 fail-closed
- `.venv/bin/python -m pytest tests/test_prod_defect_tracking.py -q` — 22 passed；覆盖 `test_prod_defect_tracking_rejects_stale_tracker_claimable_evidence`，确保 tracker 当前为 `completion_claimable=true` 且 `completion_blockers=[]`
- `.venv/bin/python scripts/check_prod_defect_tracking.py --json` — PASS，`tracked_prod_count=25`，`findings=[]`，配置仍为 `min_sharpe=1.25`、`min_fitness=1.0`、`platform_max_turnover=0.70`、`require_official_pass=true`、`require_official_metrics=true`、`max_expression_similarity=0.9`
- `.venv/bin/python scripts/check_live_submit_readiness.py --json` — PASS，`ready_to_submit=false`、`eligible_count=0`、`ledger_eligible_count=0`、`job_family_eligible_count=0`；旧 async 账本仍因证据不完整输出 `candidate_pool_truncated`，当前最好候选仍被 `local_backtest_failed`、`missing_official_alpha_id`、`missing_official_metrics`、`high_cloud_similarity` 等原因阻断
- `.venv/bin/python -m pytest tests/test_prod_defect_tracking.py::test_prod_defect_tracking_rejects_readiness_gate_invariant_relaxation -q` — PASS；确保 `readiness_gate_invariants` 在提交标准被放松时 fail-closed

---

## 缺陷统计总览

| 优先级 | 数量 | 说明 |
|--------|------|------|
| **P0 致命** | 3 | 导致系统崩溃/测试完全阻断 |
| **P1 严重** | 8 | 功能异常/安全风险/数据损坏 |
| **P2 中等** | 15 | 设计缺陷/代码异味/可维护性差 |
| **P3 低** | 12 | 规范性问题/小改进 |

---

## P0 致命缺陷（3项）

### P0-001: Python 3.9 运行时类型语法导致 20 个测试全部收集失败

- **文件**: `brain_alpha_ops/research/backtest_finalization.py:21`
- **类型**: 运行时兼容性崩溃
- **严重程度**: P0 — 全部 20 个测试模块收集失败，CI 完全阻断

**根因分析**:  
第 21 行使用了 `Candidate | None` 类型联合语法：
```python
SecondaryFusion = Callable[[Candidate, dict[str, Candidate], set[str], str], Candidate | None]
```
虽然文件头部有 `from __future__ import annotations`，但该语法在模块级类型别名赋值处属于**运行时表达式**，不受 `__future__` 注解延迟求值保护。Python 3.9 运行时直接报 `TypeError: unsupported operand type(s) for |`。

类似问题也出现在第 45 行 dataclass 字段类型 `object | None`。

**影响**: 所有依赖 `brain_alpha_ops.research.pipeline` 或 `brain_alpha_ops.runner` 的测试（约 20 个）均无法收集，测试套件完全不可用。

**修复方案**:
```python
# 修复前 (backtest_finalization.py:21):
SecondaryFusion = Callable[[Candidate, dict[str, Candidate], set[str], str], Candidate | None]

# 修复后:
from typing import Optional
SecondaryFusion = Callable[[Candidate, dict[str, Candidate], set[str], str], Optional[Candidate]]
```

同理修复第 45 行:
```python
# 修复前:
scoring_params: object | None

# 修复后:
scoring_params: Optional[object]
```

**优先级**: 最高 — 阻断所有测试运行  
**预期效果**: 20 个测试模块恢复收集能力  
**执行步骤**: 直接替换 2 处类型注解，耗时 <5min

---

### P0-002: web.py 严重 God Object — 660 行单文件承载所有服务门面

- **文件**: `brain_alpha_ops/web.py`（660 行）
- **类型**: 架构设计崩溃
- **严重程度**: P0 — 代码无法维护，任何修改引发连锁故障

**根因分析**:  
`web.py` 承担了过多职责：
1. 模块级全局可变状态（JOBS, SYNC_JOBS, CHECK_JOBS, ASYNC_JOBS, SUBMIT_LOCK, RATE_LIMITER, TASK_EXECUTOR, SERVER, SERVER_STOP 等）
2. 170+ 个 import 转发声明
3. 60+ 个函数定义，全部是对 `WebApplicationContext` 的简单委托
4. `_LEGACY_IMPORTED_EXPORTS` 字典（280+ 条目）是历史遗留的兼容层
5. 同时作为模块、运行时上下文、配置提供者、Job 管理器

**影响**:
- 任何新增端点都需要在 4+ 个位置添加代码
- 全局状态使并发测试困难
- 隐式循环依赖链路复杂

**修复方案**: 分阶段重构

**阶段 1** — 抽取 Job 管理器：
```python
# brain_alpha_ops/web_job_manager.py (新建)
class JobManager:
    def __init__(self, project_root):
        self.jobs = DurableJobStore(project_root / "data" / "jobs_production.json")
        self.sync_jobs = DurableJobStore(project_root / "data" / "jobs_sync.json", job_prefix="sync")
        self.check_jobs = DurableJobStore(project_root / "data" / "jobs_check.json", job_prefix="check")
        self.async_jobs = DurableJobStore(project_root / "data" / "jobs_async.json", job_prefix="task")
        self.submit_lock = threading.Lock()
        self.rate_limiter = RequestRateLimiter()
        self.task_executor = ThreadTaskExecutor(max_workers=4)
```

**阶段 2** — 消除 `_LEGACY_IMPORTED_EXPORTS`。

**阶段 3** — 将 `web.py` 缩减至 <100 行启动入口。

**当前实施进展**: `WebApplicationContext` / context 白名单已迁入 `brain_alpha_ops/web_application_context.py`，job store / submit lock / rate limiter / task executor 已迁入 `brain_alpha_ops/web_job_registry.py`，job 操作入口已迁入 `brain_alpha_ops/web_job_bindings.py`，snapshot/assistant/read-only storage/config 转发函数已迁入 `brain_alpha_ops/web_snapshot_bindings.py`，candidate/sync/check/submission 转发函数已迁入 `brain_alpha_ops/web_candidate_bindings.py`，runtime/server 转发函数与 `_start_thread` / `_compute_run_stats` 已迁入 `brain_alpha_ops/web_runtime_bindings.py`，config provider/payload 入口已迁入 `brain_alpha_ops/web_config_bindings.py`，session policy/host normalization 已迁入 `brain_alpha_ops/web_session_bindings.py`，legacy export 映射已迁入 `brain_alpha_ops/web_legacy_exports.py`，service import / 私有依赖装配已迁入 `brain_alpha_ops/web_service_namespace.py`，public facade 绑定安装已迁入 `brain_alpha_ops/web_facade_bindings.py`。公开入口仍通过 `brain_alpha_ops.web` 暴露，并新增 facade contract 测试确认新绑定会在调用时使用当前 runtime facade、provider、session module、service namespace 和 facade binding installer，旧 `web.RunConfig` / `web.route_for` 等兼容导出仍指向原实现。当前 `web.py` 已从原 660 行降至 50 行，达到 <100 行启动入口目标；剩余 public mutable job alias 面归入 P1-006 继续跟踪。

**优先级**: 高  
**预期效果**: web.py 从 660 行缩减至 <100 行  
**执行步骤**: 4 个阶段，总计约 6 小时

---

### P0-003: web.py 模块级 `__getattr__` 结合 WebApplicationContext 无限制暴露全局状态

- **文件**: `brain_alpha_ops/web.py:189-213`、`brain_alpha_ops/web.py:285-289`
- **类型**: 安全/封装破坏
- **严重程度**: P0

**根因分析**:  
通过 `web_application_context()` 获取的上下文对象可以访问模块级任意已导出属性，包括 `JOBS`, `SUBMIT_LOCK`, `SERVER` 等全局可变状态。白名单过大（280+ 条目）。

**修复方案**: 收紧 `WebApplicationContext.__getattr__`，使用显式白名单；context class 与白名单策略已迁到 `brain_alpha_ops/web_application_context.py`，`web.py` 只保留公开 `WebApplicationContext` 绑定和 `web_application_context()` 工厂，并保持 facade contract 绿色。

**优先级**: 高  
**执行步骤**: 定义白名单并收紧，约 1 小时

---

## P1 严重缺陷（8项）

### P1-001: 分页集合去重逻辑仅比较页面签名，不比较单条记录
- **文件**: `brain_alpha_ops/brain_api/pagination.py:80-102`
- **修复**: 增加条目级去重

### P1-002: 子进程凭据泄露 — 环境变量中暴露密码
- **文件**: `brain_alpha_ops/secure_credentials.py`
- **修复**: 读取后立即清除敏感环境变量

### P1-003: CLI `--base-url` 参数可被用于 SSRF 攻击
- **文件**: `brain_alpha_ops/cli_parser.py`
- **修复**: 添加 URL 白名单验证

### P1-004: 异常静默吞噬
- **文件**: `backtest_finalization.py:171-177`, `official_context.py:92-99`, `observability.py:54-56`
- **修复**: 已将 ExperienceDB 记录失败分支改为记录异常类型和脱敏错误原因；`official_context.py` 仅对 `BrainAPIError` 做可解释 stale cache fallback；`observability.py` 通过返回 payload 暴露表达式索引失败。出于凭据安全，不使用会泄露原始异常文本的 raw traceback 日志。

### P1-005: `OfficialBrainAPI` Mixin 模式导致调用链不透明
- **文件**: `brain_alpha_ops/brain_api/official.py`
- **修复**: 当前代码已重构为组合模式：`OfficialBrainAPI` 只保留公开兼容入口，内部委托到 auth/context/request/simulation/validation 组件；回归测试断言旧 Mixin 不再出现在 `OfficialBrainAPI.__mro__` 中。

### P1-006: 线程安全问题 — 全局可变状态缺乏统一锁域
- **文件**: `brain_alpha_ops/web.py`, `brain_alpha_ops/web_job_registry.py`, `brain_alpha_ops/web_facade_bindings.py`
- **修复**: 已完成五步：引入 `WebJobRegistry` 统一创建和持有 job stores、submit lock、rate limiter、task executor；`resolve_web_job_registry()` 提供共享 registry view，并在 legacy aliases 被测试或旧调用方替换时继续尊重 override；`web_runtime_facade.py` 以及 `web.py` 的冲突检测、限流、后台任务提交入口均改为通过该 view 获取 job 状态；`Handler` 初始化不再注入静态 `jobs=JOBS`，SSE 通过显式 resolver 动态查找 job；`JOBS` / `SYNC_JOBS` / `CHECK_JOBS` / `ASYNC_JOBS` / `SUBMIT_LOCK` / `RATE_LIMITER` / `TASK_EXECUTOR` 不再默认安装到 `web.__dict__`，改为通过 `__getattr__` 从 `JOB_REGISTRY` 动态兼容导出，`from brain_alpha_ops.web import JOBS` 兼容路径和旧 alias override 测试均保持绿色。

### P1-007: 配置加载路径解析逻辑脆弱
- **文件**: `brain_alpha_ops/config.py:51-76`
- **修复**: 当前代码已通过 `runtime_project_root()` / `default_run_config_path()` / `resolve_runtime_path()` 明确源码、冻结包与 `BRAIN_ALPHA_OPS_HOME` 的路径来源，并在 `load_run_config()` / `write_run_config()` 中使用运行时副本和路径归一化；配置验证测试和 validate-only 入口均通过。

### P1-008: 外部数据缺少验证层
- **文件**: `brain_alpha_ops/data/ashare_adapter.py`
- **修复**: 已添加 A-share 日线行级验证层，缓存命中和外部拉取结果都会先检查日期与数值字段；坏行记录到 diagnostics 后丢弃，坏缓存不再直接进入 backtest 数据路径。

---

## P2 中等缺陷（15项）

| 编号 | 文件 | 描述 |
|------|------|------|
| P2-001 | web.py | 60+ 个函数只是简单转发 |
| P2-002 | pagination.py 等 | 分页逻辑 4 处重复 |
| P2-003 | web_submission_*.py | 冲突检测 5 处重复 |
| P2-004 | observability.py 等 | JSON 错误静默吞噬 |
| P2-005 | web_security.py | allow_remote 时 Origin 验证不足 |
| P2-006 | web_session.py | 会话存储为内存字典 |
| P2-007 | web_http_handler.py | 错误响应可能泄露路径 |
| P2-008 | config_models.py | 嵌套序列化不完整风险 |
| P2-009 | agent_tools.py | Agent 工具缺少输入验证 |
| P2-010 | web_sync_payload.py | 同步参数缺少范围限制 |
| P2-011 | web_check_batch_job.py | 批量检查无断点恢复 |
| P2-012 | web_redline_scoring.py | 浮点比较缺少 epsilon |
| P2-013 | fusion_candidates.py | 融合可能无限递归 |
| P2-014 | web_async_jobs.py | 异步任务可能泄漏线程 |
| P2-015 | cli.py | CLI 参数缺少互斥组 |

---

## P3 低级缺陷（12项）

| 编号 | 描述 |
|------|------|
| P3-001 | Python 3.10+ 类型注解语法散落各处 |
| P3-002 | redaction.py 正则可能误杀 |
| P3-003 | 日志级别未统一配置 |
| P3-004 | 验证函数参数顺序不一致 |
| P3-005 | Candidate 字段过多 |
| P3-006 | 函数参数过多 |
| P3-007 | JSONL 读取缺少大小限制 |
| P3-008 | GenerationModeRouter 缺少线程安全 |
| P3-009 | ThreadTaskExecutor 缺少失败回调 |
| P3-010 | 错误类型层次不够细化 |
| P3-011 | 进度更新可能过于频繁 |
| P3-012 | 测试覆盖无法评估 |

---

## 修复执行计划

### 阶段 1: 紧急修复（< 2 小时）
| P0-001 | 修复 Python 3.9 类型语法 | 10min |
| P0-003 | 收紧 WebApplicationContext | 30min |
| P1-003 | 添加 SSRF 白名单 | 30min |
| P1-002 | 清除环境变量凭据 | 30min |

### 阶段 2: 安全与可靠性（4 小时）
| P1-004 | 修复异常静默吞噬 | 1.5h |
| P1-001 | 分页条目级去重 | 30min |
| P1-006 | 引入 JobRegistry | 2h |

### 阶段 3: 架构改进（8 小时）
| P0-002 | web.py 分阶段重构 | 4h |
| P1-005 | OfficialBrainAPI 重构 | 4h |

### 阶段 4: 代码质量（6 小时）
| P2 系列 | 修复中等缺陷 | 4h |
| P3 系列 | 修复低级缺陷 | 2h |

**总计**: ~20 小时
