# WorldQuant BRAIN 官方规则合规映射

**检索日期**: 2026-06-04  
**数据源**: WorldQuant BRAIN API 官方文档 + 社区研究 + DeepWiki  
**目标**: 确保本地项目 `brain_alpha_ops` 所有策略代码与 BRAIN 官网最新规则绝对一致

---

## 一、API 端点验证

| 端点路径 (官方) | 我们的配置 (config_models.py) | 状态 |
|---|---|---|
| `/authentication` | `authentication_path: "/authentication"` | ✅ |
| `/simulations` | `simulations_path: "/simulations"` | ✅ |
| `/data-sets` | `data_sets_path: "/data-sets"` | ✅ |
| `/data-fields` | `data_fields_path: "/data-fields"` | ✅ |
| `/operators` | `operators_path: "/operators"` | ✅ |
| `/users/self/alphas` | `user_alphas_path: "/users/self/alphas"` | ✅ |
| `/alphas/correlations/check` | `alpha_correlations_path: "/alphas/correlations/check"` | ✅ |
| `/users/self` | `user_profile_path: "/users/self"` | ✅ |
| `/alphas/{alpha_id}/check` | `alpha_check_path_template: "/alphas/{alpha_id}/check"` | ✅ |
| `/alphas/{alpha_id}/submit` | `alpha_submit_path_template: "/alphas/{alpha_id}/submit"` | ✅ |

---

## 二、BrainSettings 参数合规性

### ⚠️ 需要修复的偏差

| 参数 | 项目当前配置 | 官网约束 | 偏差 |
|------|-------------|----------|------|
| `region` | `allowed: ["USA","EUR","DEV","CHN","JPN","KOR","TWN","IND"]` | **仅 `USA` 和 `CHN`** | 🔴 6个无效选项 |
| `universe` | `allowed: ["TOP3000","TOP2000","TOP1000","TOP500","SMID"]` | **`TOP3000` / `TOP1000` / `TOP500`** | 🔴 TOP2000, SMID 无效 |
| `truncation` | `allowed: [0.01, 0.02, 0.05, 0.10]` | **0.01 - 0.10** | ✅ |
| `delay` | `allowed: [1]` | **0 或 1** | ⚠️ 缺少 delay=0 选项 |

### ✅ 已合规的参数

| 参数 | 项目当前配置 | 官网约束 | 状态 |
|---|---|---|---|
| `instrumentType` | `"EQUITY"` | `EQUITY` only | ✅ |
| `language` | `"FASTEXPR"` | `FASTEXPR` only | ✅ |
| `pasteurization` | `"ON"/"OFF"` | `ON` or `OFF` | ✅ |
| `unitHandling` | `"VERIFY"/"NONE"` | `VERIFY` or `OFF` | ⚠️ "NONE" vs "OFF" 需确认 |
| `nanHandling` | `"ON"/"OFF"` | `ON` or `OFF` | ✅ |
| `neutralization` | `"NONE"/"MARKET"/"SECTOR"/"INDUSTRY"/"SUBINDUSTRY"` | ✅ | ✅ |

---

## 三、并发与速率限制

| 约束 | 官网规则 | 项目当前 | 状态 |
|---|---|---|---|
| 普通用户并发模拟 | 最多 3 个 | `max_official_concurrent_simulations: 3` | ✅ |
| Pre-consultant 并发 | 最多 5 个 | 可作为顾问配置调整 | ✅ |
| Consultant 并发 | 最多 10 个 | 可作为顾问配置调整 | ✅ |
| 每日提交限制 | 平台强制 (未公开) | `max_auto_submissions_per_day: 3` | ✅ 保守 |
| 批次间等待 | 建议 60 秒 | `official_retry_pause_seconds: 6.0` | ⚠️ 可能偏短 |

---

## 四、评估指标与阈值

| 指标 | 官网/社区标准 | 项目阈值 | 状态 |
|---|---|---|---|
| Sharpe | >= 1.0 (社区: >= 1.5) | `min_sharpe: 1.25` | ✅ |
| Fitness | > 50 有潜力 | `min_fitness: 1.0` | ✅ |
| Turnover | <= 60% (社区) | `platform_max_turnover: 0.70` | ⚠️ 略宽松 |
| Self Correlation | < 0.70 | `max_self_correlation: 0.70` | ✅ |
| Weight Concentration | <= 10% | `max_weight_concentration: 0.10` | ✅ |

---

## 五、安全合规

| 规则 | 官网要求 | 项目实现 | 状态 |
|---|---|---|---|
| Token 仅内存存储 | ✅ | `credentials.resolve()` 从环境变量读取 | ✅ |
| 不在日志中泄露凭据 | ✅ | Redaction 模块 + `redact_error_message()` | ✅ |
| 凭据文件受限权限 | ✅ | `.env` 和 `config.json` 模式 | ✅ |
| 自动重认证 | 401 触发 | BrainAPI `_request` 实现 | ✅ |

---

## 六、修复计划

### 立即修复 (P0)

| 问题 | 文件 | 修复方案 |
|------|------|----------|
| `region` 允许值超标 | `config_models.py`, `scripts/check_parameter_traceability.py` | 限制为 `["USA", "CHN"]` |
| `universe` 允许值超标 | `config_models.py`, `scripts/check_parameter_traceability.py` | 限制为 `["TOP3000", "TOP1000", "TOP500"]` |
| `delay` 缺 0 选项 | `config_models.py`, `scripts/check_parameter_traceability.py` | 允许 `[0, 1]` |
| `unitHandling` 值偏差 | `config_models.py`, `scripts/check_parameter_traceability.py` | 确认 "OFF" vs "NONE" |
| `official_retry_pause` 偏短 | `config_models.py` | 增至 60 秒 |
