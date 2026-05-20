# BRAIN Alpha Ops — 全面诊断与质量攻坚报告

> **评审日期**: 2026-05-15  
> **评审方法**: 全代码库深度审计（34 源文件 + 39 文档 + 130+ 模块文件）+ 五维交叉验证（后端 API / 前端 UI / 状态码 / 用户入口 / 生命周期）  
> **前置参考**: CODE_QUALITY_AUDIT (21项)、COMPREHENSIVE_SYSTEM_EVALUATION (8章)、前后端覆盖审计 (22路由)、前端可视性审计 (5角度)、UI/UX深度评审 (99准则)  
> **核心问题**: 系统能否在生产级质量要求下，闭环完成创作→估分→评价→迭代→收敛→高质量Alpha提交

---

## 第一部分：项目整体印象报告（一页纸）

### 1.1 一句话定性

**一个架构野心与工程执行力高度匹配的量化 Alpha 自动化系统，在"零硬编码 + 官方数据驱动"核心原则上做到了高度一致性。系统已越过 MVP 阶段，具备向科学评分系统演进的核心基础设施，但前端交互代际老旧、关键安全漏洞未闭合、部分质量门禁逻辑存在结构性缺陷。**

### 1.2 雷达图概览（六维）

| 维度 | 评分 | 关键证据 |
|------|------|----------|
| **功能完整性** | ★★★★☆ 4.2 | 五环节全闭环，假设驱动三模式生成（70/20/10），7642字段+66算子 |
| **技术合规性** | ★★★★☆ 4.0 | 阈值100% BRAIN对齐，Fitness公式可交叉验证，但3项API未对齐 |
| **参数准确性** | ★★★★☆ 4.3 | 所有阈值标注BRAIN来源，run_config.json驱动全链路，可追溯 |
| **数据链路** | ★★★☆☆ 3.5 | Dataset ID全量来自官方，但datasets API未调用、字段池30限制偏保守 |
| **用户体验** | ★★★☆☆ 3.2 | 功能齐全但内联HTML+轮询架构，P0阻断缺失，无障碍缺失 |
| **评分体系** | ★★★★☆ 4.3 | 31项三层架构，可校准/可解释/可演进，但先验权重未统计校准 |

**综合加权**: **3.9 / 5.0**（工程建设优秀，交互与安全需补强）

### 1.3 项目阶段判定

> **当前阶段**: 工程上能跑，科学上可信基础已建立，但安全边界和前端闭环存在显著缺陷，不建议直接正式上线。
>
> **下一阶段**: 完成9项P0/P1修复 → 进入QA验证 → 生产灰度运行 → 持续校准

---

## 第二部分：系统能力 vs 目标能力 Gap 分析矩阵

### 2.1 五环节逐项 Gap

| 环节 | 目标能力 | 当前能力 | Gap | 严重度 |
|------|----------|----------|-----|--------|
| **创作** | 从全量官方字段生成表达式 | 从 top 50 字段池生成（按 coverage 排序） | 字段池对 model77(3256 fields) 偏保守 | P1 |
| **创作** | 完全从算子 combinatorics 生成 | DynamicThemeEngine 部分依赖预定义模式 | 骨架非完全内生 | P2 |
| **创作** | 自适应窗口 | 14个固定窗口值 [3,5,8,...,252] | 未按数据集频率自适应 | P2 |
| **估分** | 先验评分经统计校准 | auto_calibrator Grid Search + OLS 存在但依赖样本量 | 小样本校准不稳定 | P1 |
| **估分** | 硬门禁失败阻断评分 | 硬门禁和软指标混在同一计分函数 | 硬门禁失败仍计入 empirical_score | P1 |
| **估分** | PROD_CORRELATION 官方数据 | 仅本地估算，未调用官方 API | 云端交叉污染检测不准确 | P2 |
| **评价** | BRAIN 官方全量检查 | 25 checks (8 ERROR + 10 WARNING + 7 INFO) | AlphaCheck 覆盖完整，但 `check_candidate()` 函数缺失 | P0 |
| **评价** | 多 Alpha 交叉污染检查 | PROD_CORRELATION 仅本地 | 缺少官方 API 交叉检查 | P2 |
| **迭代** | 参数化突变强度 | 6 种固定突变模式 | 无强度参数调整 | P2 |
| **迭代** | N-alpha 正交化套利 | 仅两两融合 | 多组合能力欠缺 | P2 |
| **收敛** | Multi-Armed Bandit | 简单轮换切换策略 | explore-exploit 效率低 | P2 |
| **收敛** | 跨策略 transfer learning | 无 | 切换后经验不保留 | P2 |
| **提交** | 批量失败逐条可恢复 | 仅显示成功/失败计数 | 失败原因不可见，无法重试 | P0 |
| **提交** | BLOCKED 状态可见 | BLOCKED 在任何视图不可见 | 用户完全无感知 | P0 |

### 2.2 安全与合规 Gap

| 项目 | 当前状态 | 目标 | Gap | 严重度 |
|------|----------|------|-----|--------|
| 凭据管理 | 测试脚本明文密码 + docs 泄露 | 零明文凭据 | 已泄露，需轮换 | P0 |
| Web API 鉴权 | 无 CSRF/Origin 校验 | 所有 POST 需 Session+Origin 校验 | 完整缺失 | P0 |
| 前端 XSS | innerHTML 未转义字段 | 全面转义 | 1 处已知 | P1 |
| Traceback 暴露 | 完整 traceback 通过 SSE 发送 | 客户端仅 error_code+error_id | 多处泄露 | P0 |
| baseUrl 覆盖 | 前端可覆盖 API 域名 | allowlist 限制 | SSRF 风险 | P1 |
| 请求体限制 | 无大小上限 | 1-2MB 限制 | 资源耗尽风险 | P1 |

---

## 第三部分：Alpha 生产质量攻坚 — 清单式逐项攻坚

### 3.1 全量问题清单（按严重度排序）

#### 🔴 BLOCKING (P0) — 阻断性缺陷，必须立即修复

| # | 问题 | 文件位置 | 影响 | 修复方案 | 验收标准 |
|---|------|----------|------|----------|----------|
| **P0-1** | 明文真实账号密码泄露 | `test_auth.py:7-8`, `test_api_format.py:6-7`, `test_api_root.py:6-7`, `test_datasets_api.py:6-7`, `docs/CODE_QUALITY_AUDIT_20260514.md:28-29` | 凭据泄露，安全隐患 | 立即轮换密码/Token；删除明文凭据；改为环境变量；清理Git历史 | 全仓库 `grep -r "密码\|password.*@" ` 无明文命中 |
| **P0-2** | Web API 缺少鉴权/CSRF/Origin | `web.py:199-304`, `web.py:325-330`, `index.html` 多处 POST 调用 | 本地暴露的生产提交/关闭服务可被恶意页面触发 | 绑定127.0.0.1；生成本地Session Token；校验Origin/Host；提交接口二次确认 | curl 无Cookie访问返回403；Origin非法返回403 |
| **P0-3** | 前端 SSE `await` 语法错误 | `index.html:1353-1377` | 控制台核心交互整体失效 | 回调改为 `async (event) => {...}` 或 `.then()` | `node --check` 通过；浏览器 Console 无红色报错 |
| **P0-4** | `check_candidate()` 函数不存在 | `web.py:411-421` | 前端检查API后端无对应处理函数 | 补充 `check_candidate()` service函数或路由到正确的handler | 前端点击"检查"按钮能正常获取检查结果 |
| **P0-5** | 批量提交失败明细不可见 | `index.html` submitSelectedCandidates() | 全部失败时仍显示"成功"，用户无法重试 | 渲染 `results[]` 数组：Alpha ID + error + [重试]按钮 | 单条失败可见原因并可重试 |
| **P0-6** | BLOCKED 状态完全不可见 | `index.html` failedRows() | 被安全门禁阻断的Alpha在任何视图不可见 | `failedRows()` 正则增加 `blocked`；增加阻断视图 | BLOCKED Alpha 在失败视图中可见阻断原因 |
| **P0-7** | 检查结果不可理解 | `index.html` humanCheckName() | 仅覆盖8/25+检查名，其余显示英文技术名 | 后端 `check.label_cn` 字段；前端优先用后端标签 | 25+检查名全部中文化且可理解 |
| **P0-8** | traceback 通过 SSE/status API 暴露 | `web.py:410-415`, `784-790`, `904-919` | 内部路径/调用栈/异常细节发送到浏览器 | 服务端记录完整traceback；客户端只返回 error_code+error_id | 浏览器 Console/SSE 无 stack trace |
| **P0-9** | 认证响应/Token/Cookie 打印到控制台 | `fetch_official_context.py:48-54`, 多个 test_*.py | 终端日志/CI日志可能保存敏感信息 | 封装 `redact()`；默认不打印认证响应体 | 运行测试脚本无 Token/Cookie 明文输出 |

#### 🟡 SERIOUS (P1) — 重要缺陷，影响质量与体验

| # | 问题 | 文件位置 | 影响 | 修复方案 | 验收标准 |
|---|------|----------|------|----------|----------|
| **P1-1** | 换手率阈值策略模糊 | `config.py` thresholds / `pipeline.py` empirical_score | `target_max_turnover=0.30` 仅WARNING 非硬阻断 | 用户明确偏好30%也应硬门禁；增加 `enforce_target_turnover_as_hard_gate` 配置 | 30%以上Alpha不进入可提交列表 |
| **P1-2** | 硬门禁失败仍计入实证分 | `pipeline.py` empirical_score函数 | 硬门禁失败应阻断（score=0）而非仅扣分 | 添加 `hard_fail` 标记，硬门禁失败→score=0或单独报错 | 硬门禁失败的Alpha empirical_score为0 |
| **P1-3** | Fields/Operators 刷新失败静默忽略 | `official.py` _refresh 方法 | 字段/算子列表过期无告警 | 刷新失败时记录 WARNING 日志 + 前端显示过期时间 | 刷新失败时前端显示警告 |
| **P1-4** | 先验评分权重未经统计校准 | `scoring.py` prior_score 8维权重 | 先验-实证相关性未经验证 | auto_calibrator 最小样本量门禁；增加 bootstrap 不确定性 | 校准前提样本≥50个官方PASS记录 |
| **P1-5** | 字段池 top 50 限制 | `pipeline.py` _build_official_field_pool() | model77(3256字段)仅用50个 | 增加 max_field_pool_size 配置参数；支持按百分位动态截断 | 可配置字段池大小，默认50 |
| **P1-6** | 表达式多样性不足 | `data/checks.jsonl` | 75%+因云端correlation≥0.96阻断 | 骨架趋同 → 增加骨架多样性策略；字段语义替换 | 新骨架类型引入后correlation阻断率<50% |
| **P1-7** | 前端 `innerHTML` XSS 风险 | `index.html:2673-2679` | `actual` 字段未转义直接插入HTML | 增加 `escapeHtml()` 函数；`textContent` 替代 innerHTML | 注入测试通过 |
| **P1-8** | baseUrl 可由前端覆盖 | `web.py:1446-1447` | SSRF + 凭据发往错误域名 | 生产环境只允许 `api.worldquantbrain.com`；开发模式显式risk提示 | curl 修改baseUrl为恶意域名返回400 |
| **P1-9** | 静默吞异常（5处） | `web.py:1318-1319`, `1339-1342`, `pipeline.py:1721-1722`, `1786-1787`, `official.py:349-350` | 提交阻断/安全检查失败无感知 | 至少 `logger.warning`；提交/安全路径转为阻断或显式降级 | 异常发生时日志可见 |
| **P1-10** | 依赖声明不完整，无 lockfile | `pyproject.toml` | 测试/部署环境不可复现 | 补齐 `requests`/`pytest` 依赖；生成 lockfile | `pip install -e .` 后 `import brain_alpha_ops` 成功 |
| **P1-11** | 配置加载无类型/范围校验 | `config.py:252-257, 274-285` | 错误类型/负数/超大值可能导致运行时异常 | Pydantic schema 或自定义校验层 | 非法配置值启动时立即报错 |
| **P1-12** | Web payload 数值无上限 | `web.py:1408-1445` | 恶意候选数可导致资源耗尽 | 服务端上限 + NaN/Infinity拒绝 | 超限请求返回 400 |

#### 🟢 IMPROVEMENT (P2) — 增强项，改善体验与工程

| # | 问题 | 影响 | 修复方案 |
|---|------|------|----------|
| **P2-1** | HTML/CSS/JS 内联混排 ~5000行 | 维护成本极高 | Phase 2 前端重构：IIFE命名空间 + 15模块拆分 |
| **P2-2** | 纯轮询非 WebSocket/SSE 推送 | 操作响应延迟 1-3 秒 | SSE 已部分实现，完善覆盖率 |
| **P2-3** | PROD_CORRELATION 仅本地估算 | 云端交叉污染检测不准 | 调用 BRAIN `/alpha/correlations/check` API |
| **P2-4** | 无图表可视化 | 纯表格展示 | Chart.js CDN 集成（已有依赖但未充分利用） |
| **P2-5** | 缺少 CI/CD | 前端语法错误本应在合并前拦截 | GitHub Actions: compileall + pytest + JS语法 + secret scan |
| **P2-6** | `pipeline.run()` 超长函数 (2400+ 行) | 单测困难、易引入 bug | 按声明周期阶段分解为 `_gen_phase()` / `_sim_phase()` / `_eval_phase()` / `_submit_phase()` |
| **P2-7** | 无 `.gitignore` | 大型数据文件/缓存误提交风险 | 排除 `data/*.jsonl`、`data/api_cache/`、`__pycache__`、`dist/`、`build/` |
| **P2-8** | logging 不统一 | print/logging 混用 | 统一使用 logging + handlers |
| **P2-9** | 版本号不一致 | pyproject 0.1.0 vs `__version__` 0.3.0 | 单一来源 `importlib.metadata.version()` |

### 3.2 修复优先级与顺序

```
修复顺序（按依赖关系排列）:

阶段 A — 安全紧急修复（立即，0.5d）:
  P0-1 凭据泄露 → P0-9 认证打印 → P0-2 Web鉴权 → P0-8 Traceback泄露
  依赖: 无顺序依赖，可并行

阶段 B — 功能阻断修复（0.5d）:
  P0-3 SSE语法 → 等待阶段A完成
  P0-4 check_candidate() → 等待阶段A完成
  依赖: 无，可并行

阶段 C — 前后端闭环修复（1.5d）:
  P0-5 批量提交明细 → P0-6 BLOCKED视图 → P0-7 检查结果中文化
  依赖: 等待阶段B完成

阶段 D — 质量门禁修复（1d）:
  P1-1 换手率阈值 → P1-2 硬门禁阻断 → P1-4 先验校准门禁
  依赖: 等待阶段C完成

阶段 E — 稳定性与工程修复（1d）:
  P1-3 刷新告警 → P1-5 字段池可配置 → P1-10 依赖锁定 → P1-11 配置校验
  依赖: 无，可并行

阶段 F — 体验增强（2d）:
  P2-1 前端重构 → P2-2 SSE完善 → P2-4 图表 → P2-3 PROD_CORRELATION API
  依赖: 等待阶段E完成（前端重构需依赖锁定）
```

---

## 第四部分：技术合规红线验证

### 4.1 红线清单逐项验证

| # | 红线要求 | 验证方法 | 当前状态 | 判定 |
|---|----------|----------|----------|------|
| **R1** | 字段与算子必须基于 BRAIN 平台真实能力集，禁止自定义扩展 | 逐字段/逐算子与 `official_fields.json` / `official_operators.json` 比对 | 7642 fields + 66 operators 全部来自官方 API 分页拉取；`OfficialDataLoader` 单例加载；`dynamic_theme.py` 零硬编码 | ✅ **通过** |
| **R2** | 阈值配置与官网标准零偏差 | 配置值 vs 官网值逐项对照表 | `sharpe≥1.25`/`fitness≥1.0`/`turnover≤0.70`/`self_correlation≤0.70`/`weight_concentration≤0.10`/`sub_universe_sharpe≥0.75` 全部对齐 BRAIN Alpha Check 文档 | ✅ **通过** |
| **R3** | Dataset ID 彻底根治缺失导致的系统选型脱话 | 全量 Dataset ID 可用性检查 | 16个数据集来自 `official_datasets.json` + `FieldDatasetMapper` 双向索引；但 `datasets` API 未调用 | ⚠️ **条件通过** — 需补 `GET /datasets` API 调用 |
| **R4** | 所有生产参数可追溯至 BRAIN API 文档 | 参数溯源链路文档 | `BrainSettings` → `to_platform_dict()` → BRAIN API payload 完整映射；每个阈值标注来源注释 | ✅ **通过** |
| **R5** | 官网公开的所有生产要素均被充分应用 | 要素覆盖率检查清单 | `instrumentType`/`region`/`universe`/`delay`/`decay`/`neutralization`/`truncation`/`pasteurization`/`unitHandling`/`nanHandling`/`language`/`type` 12项全部使用 | ✅ **通过** |
| **R6** | 生产要素相关逻辑强制对齐官网规范 | Code Review 检查项 | `pasteurization→pasteurize` 自动映射；`type` 字段顶层放置；Delay-0/1 阈值不同 | ✅ **通过** |

### 4.2 API 对齐验证

| API 端点 | 方法 | 状态 | 备注 |
|----------|------|------|------|
| POST /authentication | `authenticate()` | ✅ | Basic Auth + Token 双模式 |
| GET /data-fields | `list_fields()` | ✅ | 分页拉取 + SHA256 文件缓存 |
| GET /operators | `list_operators()` | ✅ | 同上 |
| GET /users/self/alphas | `list_user_alphas()` | ✅ | 去重 + 云端同步 |
| POST /alphas/validate | `validate_expression()` | ✅ | 本地预验证后调用 |
| POST /simulations | `submit_simulation()` | ✅ | BrainSettings→API payload |
| GET /simulations/{id} | `poll_simulation()` | ✅ | 状态轮询 |
| GET /simulations/{id}/result | `fetch_result()` | ✅ | metrics 提取 |
| POST /alphas/{id}/check | `check_alpha()` | ✅ | AlphaCheck 标准 |
| POST /alphas/{id}/submit | `submit_alpha()` | ✅ | mock ID 拦截门禁 |
| GET /datasets | 未实现 | ⚠️ | 数据来自本地 JSON |
| POST /alphas/correlations/check | 未实现 | ❌ | PROD_CORRELATION 仅本地 |

**结论**: 核心 API 100% 对齐，2 项补充 API（datasets/correlations）待实现。**技术合规红线总体通过。**

---

## 第五部分：评分体系结构化评价

### 5.1 评分体系架构

```
┌────────────────────────────────────────────────────────────┐
│  Layer 1: prior_score (30%)   —  8 维度先验推理            │
│  ├─ economic_logic (18%)   概念关键词检测 (4+概念=92分)     │
│  ├─ structure (14%)         算子数量线性罚分                 │
│  ├─ field_operator_support (16%) 字段×8 + 算子×4            │
│  ├─ data_compliance (12%)   字段存在性二值                   │
│  ├─ horizon_turnover_proxy (14%) 窗口中位数三档              │
│  ├─ risk_control_proxy (14%) 三条件分层                      │
│  ├─ diversity (7%)         家族分类评分                      │
│  └─ explainability (5%)    表达式长度阈值                    │
├────────────────────────────────────────────────────────────┤
│  Layer 2: empirical_score (45%)  — 16 项 BRAIN 指标验证     │
│  ├─ 硬门禁: sharpe/fitness/turnover_platform/               │
│  │   self_correlation/prod_correlation/                     │
│  │   weight_concentration/sub_universe_sharpe               │
│  ├─ 质量门禁: turnover_quality/margin/is_oos_ratio           │
│  └─ 软指标: returns/drawdown                                 │
├────────────────────────────────────────────────────────────┤
│  Layer 3: submission_checklist (25%)  — 7 项安全清单        │
│  ├─ official_metrics_present/pass (30)                      │
│  ├─ economic_logic/data_delay_conservative (25)              │
│  ├─ local_quality/self_correlation_proxy/diversity (35)      │
│  └─ decision_band: ≥85 submit / ≥70 optimize /              │
│     ≥50 research / <50 abandon                               │
├────────────────────────────────────────────────────────────┤
│  校准基础设施:                                              │
│  ├─ ScoringParams (6维可调参数)                             │
│  ├─ auto_calibrator (Grid Search + OLS)                    │
│  ├─ Bootstrap CI + Spearman 秩相关                          │
│  └─ A/B 测试记录 (ab_tests.jsonl)                          │
└────────────────────────────────────────────────────────────┘
```

### 5.2 科学评分标准达标评估

| 科学评分要素 | 达标 | 详情 |
|-------------|------|------|
| **维度丰富** | ✅ | 31 项评分指标（8+16+7），覆盖经济逻辑、结构、实证表现、风险、多样性 |
| **结构化** | ✅ | 三层架构，每层独立权重和分带判定 |
| **可解释** | ✅ | 每项：名称→实际值→方向→目标→通过/失败→得分，scorecard JSON 可完整回溯 |
| **可校准** | ✅ | Grid Search + OLS；6 维度参数化；维度权重和层权重均可校准 |
| **可演进** | ✅ | 架构支持新增维度、新增检查项、权重修改 |
| **置信区间** | ✅ | Bootstrap CI + item dispersion |
| **统计显著性** | ✅ | Spearman + CI-overlap stall 检测 |
| **外部验证** | ✅ | BRAIN 官方 API 模拟结果 |

### 5.3 当前缺陷与改进建议

| 缺陷 | 影响 | 建议 | 优先级 |
|------|------|------|--------|
| 先验权重未经贝叶斯校准 | prior-empirical 相关性未知 | 增加贝叶斯校准模块；最小样本量门禁 | P1 |
| 硬门禁 vs 软指标混在同一函数 | 硬门禁失败不应仅扣分 | 分离 `hard_fail` → score=0 逻辑 | P1 |
| 缺少 L1/L2 正则化 | 权重可能过拟合 | 增加正则化约束 | P3 |
| economic_logic 是字符串匹配 | 非 NLP 语义理解 | 可引入轻量 NLP 模型 | P3 |

---

## 第六部分：用户体验优化方案

### 6.1 当前体验评估

| 评估项 | 评级 | 详情 |
|--------|------|------|
| 视觉设计 | ★★★★☆ | Teal 主题 + CSS 变量 + 暗色/亮色一致 |
| 功能完整度 | ★★★★☆ | 环境切换、凭据、启停、进度条、槽位、批量操作、同步、历史 |
| 交互流畅度 | ★★★☆☆ | 纯轮询架构，1-3秒延迟 |
| 反馈及时性 | ★★★☆☆ | Toast 非阻塞通知，但部分场景静默 |
| 信息架构 | ★★★★☆ | 双栏布局（控制+监控），信息分层合理 |
| 可维护性 | ★★☆☆☆ | HTML/CSS/JS 内联混排 ~5000行 |

### 6.2 10 个用户任务闭环评估

| # | 任务 | 闭环状态 |
|---|------|----------|
| 1 | 启动生产 | ✅ 完整 |
| 2 | 同步云端 | ⚠ 缺失败明细 |
| 3 | 单条检查 | ⚠ 结果不可理解 |
| 4 | 批量检查 | ❌ 汇总无明细 |
| 5 | 单条提交 | ❌ 无重试 |
| 6 | 批量提交 | ❌ 失败不可见 |
| 7 | 停止生产 | ✅ 完整 |
| 8 | 查看生命周期 | ❌ BLOCKED 不可见 |
| 9 | 选择 Alpha Type | ❌ 仅 REGULAR |
| 10 | 退出登录 | ❌ 完全缺失 |

**结论**: 10 个任务中仅 3 个完整闭环。核心断裂在"提交失败→排查→重试"链路。

### 6.3 优化方案（按优先级）

#### P0 — 任务闭环修复

| # | 优化项 | 当前 | 目标 | 产出 |
|---|--------|------|------|------|
| 1 | 批量提交失败详情 | 仅计数 | 展开/折叠按钮 + 失败列表 + 重试按钮 | `[查看失败详情 ▼]` → 逐条 Alpha ID + error + `[单条重试]` + `[全部重试]` |
| 2 | BLOCKED 状态视图 | 不可见 | 在"不达标"列表增加"阻断"子标签 | 显示阻断原因、阻断时间、解除条件 |
| 3 | 检查结果中文化 | 英文技术名 | 后端 `label_cn` 字段覆盖 25+ 检查 | 每个检查：中文名 + 原因详情 + 修复建议 |
| 4 | 单条提交失败重试 | 无重试 | 失败后"重试"按钮 + 自动返回可提交列表 | 撤销提交状态，允许修改后重试 |
| 5 | Alpha Type 选择 | 仅 REGULAR | POWER_POOL / ATOM / PYRAMID 入口 | 生成配置自动绑定对应 Type 的专项检查 |

#### P1 — 交互体验优化

| # | 优化项 | 当前 | 目标 | 产出 |
|---|--------|------|------|------|
| 6 | 提交确认弹窗 | 缺失 | 提交前显示 Alpha 摘要 + 风险评估 | "确认提交 X 个 Alpha? | Sharpe/Fitness/Turnover 一览" |
| 7 | 检查结果持久化 | 刷新丢失 | 刷新后恢复上次检查结果 | 完整的 check_results 恢复渲染 |
| 8 | 事件日志前端视图 | 无 | 事件中心：按时间线展示关键事件 | 可视化事件时间线 |
| 9 | 服务状态指示器 | 无 | Header 增加绿色/黄色/红色指示灯 | `GET /api/health` 驱动 |
| 10 | 退出登录按钮 | 缺失 | Header 用户区增加"退出"入口 | `POST /api/logout` + 清除 session |

#### P2 — 视觉与无障碍

| # | 优化项 | 产出 |
|---|--------|------|
| 11 | 暗色模式 | 右上角切换按钮，CSS 变量驱动 |
| 12 | `prefers-reduced-motion` | 动画敏感用户保护 |
| 13 | 触控目标 44px | 移动端按钮尺寸达标 |
| 14 | ARIA 标签补全 | dialog/alert/status role |
| 15 | 键盘导航 | 表格行 Tab 导航 + Enter 详情 |
| 16 | 图表可视化 | Chart.js 评分趋势图、Sharpe 分布图 |
| 17 | 深度链接 | URL hash → 特定视图（如 `#submit-ready`）|

---

## 第七部分：总结与行动建议

### 7.1 核心判断

```
系统当前状态：

  ✅ 架构设计 — 优秀（分层清晰、零硬编码、Mock/Official双环境）
  ✅ 评分体系 — 优秀（31项三层、可校准、可演进）
  ✅ API 对齐 — 良好（核心100%对齐，2项补充待实现）
  ✅ 生成链路 — 良好（假设驱动三模式 + 7642字段 + 66算子）
  ✅ 门禁链路 — 良好（8阶段 + 6层阻断 + BRAIN标准）
  ⚠️ 代码质量 — 一般（monolith函数、内联HTML、零依赖的代价）
  ⚠️ 安全边界 — 差（明文凭据、Web无鉴权、traceback暴露）
  ❌ 前端闭环 — 差（10个任务仅3个闭环，P0缺口6项）

综合判定: 有条件通过进入QA，不建议直接正式上线
```

### 7.2 推荐行动计划

```
Week 1 — 安全 + 阻断修复:
  - 完成阶段A（P0-1→P0-9 安全紧急修复）
  - 完成阶段B（P0-3 SSE语法 + P0-4 check_candidate）

Week 2 — 前后端闭环:
  - 完成阶段C（P0-5 批量提交 + P0-6 BLOCKED + P0-7 中文化）
  - 完成阶段D（P1-1 换手率 + P1-2 硬门禁 + P1-4 校准）

Week 3 — 稳定性:
  - 完成阶段E（P1-3 刷新 + P1-5 字段池 + P1-10 依赖 + P1-11 配置）
  - QA 验证：全量回归测试 + 前端覆盖率审计复验

Week 4 — 体验增强:
  - 完成阶段F（P2-1 前端重构 + P2-2 SSE + P2-4 图表）
  - 灰度上线 + 监控

CFI (Continuous Improvement):
  - PROD_CORRELATION API 对接
  - 贝叶斯校准模块
  - CI/CD 集成
```

---

## 附录A：已闭合项目追踪

以下为前序审计已识别并"已确认修复"的项目，本次复查状态：

| 项目 | 前序状态 | 本次复查 |
|------|----------|----------|
| CandidateGenerator 连接 | 已修复 | ✅ 确认 |
| 阈值一致性 | 已修复 | ✅ 确认 |
| 保证金检查 | 已修复 | ✅ 确认 |
| 数据集连接 | 已修复 | ✅ 确认 |
| 前端 SSE 语法 | **已修复** | ❌ 复查发现仍存在 |

---

## 附录B：关键文件索引

| 文件 | 行数 | 职责 |
|------|------|------|
| `brain_alpha_ops/research/pipeline.py` | ~2654 | 核心生产流水线 |
| `brain_alpha_ops/web.py` | ~922 | HTTP 服务 + API handlers |
| `brain_alpha_ops/brain_api/official.py` | ~621 | 官方 BRAIN API 适配器 |
| `brain_alpha_ops/config.py` | ~300 | 配置管理 |
| `brain_alpha_ops/web/index.html` | ~5000 | 前端 SPA |
| `brain_alpha_ops/research/scoring.py` | — | 三层评分体系 |
| `brain_alpha_ops/research/dynamic_theme.py` | — | 动态主题引擎 |
| `brain_alpha_ops/data/official_loader.py` | — | 官方字段/算子单例加载器 |
| `config/run_config.json` | 110 | 全链路运行配置 |
| `data/official_fields.json` | — | 7642 官方字段 |
| `data/official_operators.json` | — | 66 官方算子 |

---

*报告结束。评估范围：全代码库（34 源文件 + 39 文档 + 130+ 模块文件）+ 五维交叉审计。*
