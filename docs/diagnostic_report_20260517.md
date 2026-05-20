# BRAIN Alpha Ops — 一页纸诊断报告 & Gap 分析矩阵

**报告日期**: 2026-05-17 | **项目版本**: v0.3.0 | **评估人**: 代码开发助手

---

## 1. 总体健康评分: 5.5 / 10

| 维度 | 状态 | 核心发现 |
|------|------|---------|
| 安全性 | 🔴 严重 | REIVEW.md 中 5 个严重问题未修（明文凭据、Web 鉴权缺失、traceback 泄露、前端语法阻塞、大数据泄露） |
| 功能完备性 | 🟡 中等 | 核心流水线完整，但 2500+ 行超大类、静默吞异常、融合逻辑不完整 |
| 测试覆盖 | 🔴 低 | 17 个测试文件但 pytest 不可运行；无 CI；依赖未声明完整 |
| 代码质量 | 🟡 中等 | 领域逻辑扎实，但单文件过长、副作用导入、版本号不一致 |

---

## 2. Gap 分析矩阵 — 六维度对照

| # | 评估维度 | 当前状态 | 目标状态 | Gap 等级 | 阻塞项 |
|---|---------|---------|---------|---------|--------|
| 1 | **功能闭环** | ✅ 生成→验证→仿真→提交 四段流水线存在 | 完全闭环：断点续跑、历史回溯、自适应策略、融合 pipeline | 🟡 MEDIUM | Web 前端语法错误阻塞控制台；`run_forever` 无优雅停止 |
| 2 | **BRAIN 平台技术合规** | 🟡 阈值来自 QualityThresholds，字段从 OfficialDataLoader 加载 | 零自定义扩展、零阈值偏差、Dataset ID 全量可用、参数完整可溯 | 🔴 HIGH | MockBrainAPI 仍有硬编码 FIELDS/OPERATORS fallback；`config.py` 无类型校验覆盖 |
| 3 | **参数准确性** | 🟡 `_ratio()` 对 BRAIN API 返回值的百分比/小数归一化有启发式逻辑 | 零偏差：严格按 BRAIN API 文档的指标定义，Fitness 交叉验证强制对齐 | 🔴 HIGH | `_ratio()` 启发式 >1.0/=百分比 可能误判边界值；turnover 原始值/归一化值混用 |
| 4 | **数据链路** | 🟡 official_*.json 经 API 拉取→缓存→lazy load；context_defaults 不可用时返回空列表 | 全链路可溯：每条数据带 source/sourced_at/version；Dataset 级别可追溯 | 🟡 MEDIUM | 缺少数据版本溯源；缓存 key 不含版本号；无 JSON Schema 校验 |
| 5 | **用户体验** | 🔴 前端语法错误导致控制台无法使用；后端 traceback 直接暴露 | 流程引导、实时状态反馈、可操作错误提示、结构化结果展示、断点续跑 | 🔴 HIGH | index.html 中 await 在非 async 回调中；无错误码体系；无向导式流程 |
| 6 | **评分体系** | 🟡 三层权重 (prior/empirical/checklist)、8 维 prior、12 项 empirical 检查 | 可配置 Pass/Fail 门禁、多维结构化评分归因、可解释可校准可演进 | 🟡 MEDIUM | 缺少评分历史追踪；prior-empirical 偏差无自动校准触发；评分归因不完整 |

---

## 3. 六条技术红线 — 逐条对标

### 🔴 红线-1: 字段/算子禁自定义扩展
| 检查项 | 现状 | 偏差 |
|--------|------|------|
| MockBrainAPI.FIELDS | 硬编码 18 个字段 fallback | **存在** — `_init_from_official_loader()` 失败后回退硬编码 |
| MockBrainAPI.OPERATORS | 硬编码 25 个算子 fallback | **存在** — 同上 |
| context_defaults | 加载失败返回空列表 ✅ | 正确 |
| pipeline 字段校验 | 使用 DEFAULT_FIELDS | **风险** — 若 mock 未加载 official JSON，使用硬编码集合 |

### 🔴 红线-2: 阈值零偏差
| 检查项 | 现状 | 偏差 |
|--------|------|------|
| min_sharpe (Delay-1) | 1.25 ✅ | 对齐 BRAIN LOW_SHARPE |
| min_fitness (Delay-1) | 1.0 ✅ | 对齐 BRAIN LOW_FITNESS |
| platform_max_turnover | 0.70 ✅ | 对齐 BRAIN HIGH_TURNOVER |
| max_self_correlation | 0.70 ✅ | 对齐 BRAIN SELF_CORRELATION |
| max_weight_concentration | 0.10 ✅ | 对齐 BRAIN CONCENTRATED_WEIGHT |
| sub_universe_sharpe_min_ratio | 0.75 ✅ | 对齐 BRAIN LOW_SUB_UNIVERSE_SHARPE |
| target_max_turnover | 0.30 ⚠️ | 顾问标准，非 BRAIN 硬性要求 — 已标记 |
| min_margin_bps | 4.0 ⚠️ | 顾问标准 — 标注来源为 "经验" |

### 🔴 红线-3: Dataset ID 全量可用
| 检查项 | 现状 | 偏差 |
|--------|------|------|
| Dataset 数据源 | `data/official_datasets.json` (16 个) | ✅ |
| Candidate.dataset_id | 模型中有字段 | ⚠️ pipeline 中未完整填充 |
| Dataset 轮换 | `dataset_strategy: "rotate"` | ⚠️ 轮换逻辑需验证完整性 |

### 🔴 红线-4: 参数全链路可溯
| 检查项 | 现状 | 偏差 |
|--------|------|------|
| 配置来源 | `config/run_config.json` → dataclass | ✅ |
| 评分参数来源 | prior_weights_override 注入 | ✅ |
| 阈值来源追踪 | QualityThresholds 注释标注 | ⚠️ 运行时无 source 字段追踪 |
| 指标归一化日志 | `_ratio()` 有 debug 日志 | ✅ |
| 全链路审计 | PipelineEvent | ⚠️ 缺少参数快照事件 |

### 🔴 红线-5: 要素全覆盖
| 检查项 | 现状 | 偏差 |
|--------|------|------|
| BRAIN Alpha Check 全部硬门禁 | ✅ 12 项 empirical 检查覆盖 | ✅ |
| BRAIN Fitness 公式对齐 | `calculate_fitness()` | ✅ |
| SELF_CORRELATION 豁免规则 | `_build_self_correlation_item()` | ✅ |
| 市场环境调整 | `regime_adjustments` | ✅ |
| Sub-Universe Sharpe | `sub_universe_sharpe` 检查 | ✅ |
| IS/OOS 稳健性 | `is_oos_ratio` 检查 | ✅ |
| 顾问标准 Margin | `margin_bps` 检查 | ✅ |

### 🔴 红线-6: 代码强对齐
| 检查项 | 现状 | 偏差 |
|--------|------|------|
| BRAIN API Document 对齐 | 基于官方 API 响应结构 | ✅ |
| 字段名对齐 | 使用 BRAIN API 原生字段名 | ✅ |
| 算子名对齐 | 从 official_operators.json 加载 | ✅ |
| Mock 输出对齐 | `_metrics_for()` 使用 QualityThresholds | ✅ |
| API 端点对齐 | `OfficialAPIConfig` 路径模板 | ✅ |

---

## 4. 问题清单 — 按严重度排序

| 优先级 | ID | 问题 | 影响 | 红线 |
|--------|----|------|------|------|
| **P0** | R-01 | 测试脚本明文凭据 | 账号安全 | — |
| **P0** | R-05 | 前端语法错误阻塞控制台 | 用户体验全损 | — |
| **P0** | R-03 | Web API 无鉴权 | 生产误触发 | — |
| **P1** | GAP-1 | MockBrainAPI 硬编码 fallback | 字段/算子自定义扩展 | 🔴 红线-1 |
| **P1** | GAP-2 | `_ratio()` 启发式归一化边界偏差 | 阈值偏差 | 🔴 红线-2 |
| **P1** | GAP-3 | Candidate.dataset_id 未完整填充 | Dataset 不可溯 | 🔴 红线-3 |
| **P1** | GAP-4 | 参数缺运行时溯源 | 参数不可溯 | 🔴 红线-4 |
| **P1** | R-02 | 认证响应打印到控制台 | 凭据泄露 | — |
| **P1** | R-04 | traceback 暴露给前端 | 信息泄露 | — |
| **P2** | M-05 | 配置无类型校验 | 运行时异常 | — |
| **P2** | M-09 | 依赖声明不完整 | 不可复现 | — |
| **P2** | M-11 | 静默吞异常 | 审计缺失 | — |
| **P3** | L-01 | 核心类过长 | 维护性 | — |
| **P3** | L-05 | 无 CI/CD | 质量门禁缺失 | — |

---

## 5. 修复路线图

```
Week 1 (P0 紧急修复):
├── 修复 R-05: 前端语法错误 (1 行改动)
├── 修复 R-01: 删除明文凭据，改为环境变量
├── 修复 R-03: Web API 鉴权加固
├── 修复 R-02/R-04: 敏感信息脱敏

Week 2 (P1 红线对齐):
├── GAP-1: MockBrainAPI 强制从 official JSON 加载
├── GAP-2: 评分归一化函数添加边界检测与偏差报告
├── GAP-3: 全链路填充 dataset_id
├── GAP-4: 参数溯源机制

Week 3 (P2 质量提升):
├── M-05: 配置 schema 校验
├── M-09: 补全依赖声明 + lockfile
├── M-11: 静默异常感知化

Week 4 (P3 持续改进):
├── 模块拆分
├── CI/CD 建立
└── 历史评分数据库建立
```

---

*本报告基于对项目 135+ 文件、REVIEW.md 中 21 项发现以及全部核心模块代码的静态分析。*
