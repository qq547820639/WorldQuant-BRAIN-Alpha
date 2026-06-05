# Alpha Production Diagnosis and Gap Matrix

> 生成时间: 2026-06-04T16:35 UTC
> 环境: production | 综合判定: **PASS**
> 红线: 75/75 通过 (0 BLOCKING) | 参数审计: zero_deviation=True

## Gap Matrix (六维度)

| 维度 | 状态 | Gap | 严重度 | 证据 | 升级建议 |
|------|------|-----|--------|------|---------|
| **功能闭环** | 10阶段Pipeline，断点续跑，历史回溯，次留检查，提交流程全链路可用 | 无阻断性功能缺口 | PASS | env=production, history_ready, 10 phases wired | 保持断点续跑和历史对比在质量门禁中 |
| **技术合规** | 6条红线全部可执行、全部阻断生效 | 无阻断性gap | PASS | 75/75 all checks passed | 保持redline verifier在pre-run和quality-gate流程 |
| **参数准确性** | 阈值、API路径、配置全部可溯源，SHA-256版本锁定 | 无偏差 | PASS | config_hash verified, refresh_source=official_api | 保持credential-backed context refresh |
| **数据链路** | 7780字段/66算子/17数据集通过OfficialDataLoader加载和交叉验证 | 无阻断性gap | PASS | fields=7780, operators=66, datasets=17, lineage=verified | 每次refresh保持metadata对齐 |
| **体验** | Web控制台提供状态条/Toast/详细模态框/断点/历史分析/结构化错误/分阶段进度 | 无阻断性gap | PASS | frontend_inline_synced, comparison_ready | 可继续增加更深的可视化历史分析 |
| **评分** | OfficialScoringSystem输出API格式仿真、零偏差门禁、可溯源分数、多维归因树 | 校准需要更多PASS/FAIL样本 | P2 | probe_status=PASS, zero_deviation=true, 6 checks all passed | 积累足够的官方结果后再使用评分历史和自动校准 |

## Priority Attack List（已修复项）

| 优先级 | 领域 | 发现 | 修复 | 验证 |
|--------|------|------|------|------|
| **P0** | API路径 | `run_config.json` 缺失 `data_sets_path`、`alpha_correlations_path`、`user_profile_path` | 补充3个缺失的API路径字段，使11个路径与CANONICAL_API_PATHS完全对齐 | `verify_canonical_compliance.py` 6/6 pass |
| **P0** | 评分仿真 | 评分API仿真缺少全部canonical指标对比、SELF_CORRELATION状态交叉验证、brain_checks字典输出 | 增强scoring_comparison.py：9项完整指标对比、阈值零偏差检测、brain_checks格式对齐 | 46/46 新增测试 pass |
| **P1** | 用户体验 | 错误消息目录未覆盖阈值漂移、配置偏差、上下文过期等边界场景 | 新增6个关键错误码：SCORE_INSUFFICIENT、GATE_CONFIG_DEVIATION、API_DEVIATION_DETECTED、CONTEXT_STALE、THRESHOLD_DRIFT_DETECTED、DATASET_NOT_IN_OFFICIAL_CONTEXT | test_critical_error_codes_exist pass |
| **P1** | 自动化验证 | 缺少一键canonical合规自动化验证脚本 | 新建verify_canonical_compliance.py：6项全覆盖验证（阈值/API路径/设置枚举/评分仿真/字段算子/数据集ID） | `--json` 输出 6/6 PASS |

## 变更文件清单

| 文件 | 修改原因 | 影响范围 |
|------|---------|---------|
| `config/run_config.json` | 补充 `data_sets_path: "/data-sets"`，`alpha_correlations_path: "/alphas/correlations/check"`，`user_profile_path: "/users/self"` | RedLine 6 API路径对齐、参数审计完整6段 |
| `brain_alpha_ops/scoring/scoring_comparison.py` | 增强BRAIN API仿真：新增 `_compare_canonical_metrics()` 覆盖9项指标对比、阈值零偏差检测、brain_checks格式对齐、新增 `check_threshold_compliance()` 和 `is_zero_deviation()` 公共API | 评分系统零偏差、门禁对比、参数审计 |
| `brain_alpha_ops/ux/user_messages.py` | 新增6个错误码定义，覆盖阈值漂移、API偏差、配置偏差等关键场景 | Web/CLI错误提示、用户引导 |
| `scripts/verify_canonical_compliance.py` | **新建** 自动化canonical合规验证：(1)阈值零偏差 (2)API路径对齐 (3)设置枚举对齐 (4)评分仿真零偏差 (5)字段/算子无自定义 (6)数据集ID全量可用 | 预发布质量门、开发自查、CI/CD |
| `tests/test_canonical_compliance.py` | **新建** 46项综合测试：边界值(空值/NAN/无穷)、极端值(负Sharpe/零换手)、参数化(Gate阈值)、弹性(损坏数据) | 测试覆盖核心链路全部边界场景 |

## 验证结果

| 验证项 | 状态 | 详情 |
|--------|------|------|
| `test_canonical_compliance.py` | **46/46 PASS** | 0.10s, 零失败 |
| `test_official_scoring_system.py` + `test_comprehensive_scoring_edge_cases.py` | **80/80 PASS** | 0.10s, 零失败 |
| `test_parameter_audit.py` | **2/2 PASS** | 零失败 |
| RedLineVerifier (6条红线) | **75/75 PASS** | 0 BLOCKING, 0 WARNING |
| Canonical Compliance Script | **6/6 PASS** | 0 deviations |

## 尚未覆盖的验证项

1. **真实API集成测试**：所有BRAIN API测试使用stub，未用真实凭据做端到端
2. **并发竞态条件**：JobStore线程安全有基本测试，管道并发场景测试不足
3. **大容量数据压力**：缺少10K+候选alpha大数据量压力测试
4. **网络异常状态**（超时/连接重置/DNS失败）：`test_official_adapter.py`未充分覆盖

## 待人工确认

1. `config/run_config.json` 的 `dataset_strategy` 设置为 `"fixed"`，但 `ResearchBudget.dataset_strategy` 默认值为 `"rotate"` — 确认生产环境期望值
2. `config/run_config.json` 的 `stop_official_calls_on_rate_limit` 设为 `false`，默认值为 `true` — 确认生产环境策略
