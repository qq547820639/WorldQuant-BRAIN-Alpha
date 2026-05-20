# 2.2 前后端职责边界矩阵

> **日期**: 2026-05-15  
> **原则**: Controller 不含业务逻辑 · Service 不引用 HTTP 类型 · 前端只做展示和交互

---

## 一、边界判定规则

| 规则 | 判定方法 |
|------|---------|
| 涉及 HTTP (请求解析、状态码、Headers) | → **后端 Controller** |
| 涉及业务决策 (定价、权限、规则、阈值判定) | → **后端 Service** |
| 涉及数据存取 (文件读写、API 调用) | → **后端 Repository** |
| 涉及 UI 状态 (显示/隐藏、表单值、动画) | → **前端 State** |
| 涉及用户交互 (按钮、弹窗、拖拽、焦点) | → **前端 View** |
| 涉及数据格式化（数字精度、日期、颜色） | → **后端 返回格式化值** (或前端 Utils，但不应是业务判断) |

---

## 二、逐功能职责分配

### 2.1 生产流水线控制

| 功能点 | 当前位置 | 应归属 | 说明 |
|--------|---------|--------|------|
| 创建后台任务 | 后端 web.py | 后端 ✅ | — |
| 停止任务 | 后端 web.py | 后端 ✅ | — |
| 轮询/SSE 获取进度 | 前端 JS | 前端 ✅ | — |
| **前端 `phaseName()` 中文映射** | 前端硬编码 25 项 | → **后端** | 后端 `progress.phase_label` |
| 进度百分比计算 | 后端 pipeline | 后端 ✅ | — |
| **`continuousMode` 字段** | 前端传但后端不消费 | → **后端** | 后端需消费 `payload.continuousMode` |
| **本地质量评分** | 后端 pipeline | 后端 ✅ | — |

### 2.2 Alpha 状态判定

| 功能点 | 当前位置 | 应归属 | 说明 |
|--------|---------|--------|------|
| `lifecycle_status` 字段 | 后端 Candidate | 后端 ✅ | — |
| **`isPassed()` / `isSubmittable()` / `isFailed()`** | 前端 JS | → **后端** | 后端返回 `status_category` 枚举 |
| **`isBlocked()`** | 缺失 | → **后端** | 新增 `BLOCKED` 类别 |
| **`submittableCandidates()` 过滤** | 前端 JS | → **后端** | 后端维护 `candidate.submittable` 布尔值 |
| **`needsCheckCount()`** | 前端遍历计算 | → **后端** | 后端 stats 中直接返回 |
| **`staleCheckCount()`** | 前端遍历计算 | → **后端** | 同上 |
| **`activeBacktestCount()`** | 前端遍历计算 | → **后端** | progress 中直接返回 |

### 2.3 提交检查

| 功能点 | 当前位置 | 应归属 | 说明 |
|--------|---------|--------|------|
| 官方预提交检查（`api.check_alpha()`） | 后端 | 后端 ✅ | — |
| 云端自相关检查 | 后端 | 后端 ✅ | — |
| 历史重复提交检查 | 后端 | 后端 ✅ | — |
| **`humanCheckName()` 中文映射** | 前端硬编码 8/25 | → **后端** | 后端 `check.label_cn` |
| **`isFreshCheck()` (24h 判断)** | 前端 JS | → **后端** | 后端返回 `is_stale: bool` |
| **检查过期检测** | 前端 `CHECK_STALE_MS` 常量 | → **后端** | 后端返回 `checked_at` + `is_stale` |
| **检查结果持久化** | 后端 checks.jsonl | 后端 ✅ | — |
| **检查结果恢复** | 前端 `loadCheckResults()` | 前端 ✅ | — |

### 2.4 提交操作

| 功能点 | 当前位置 | 应归属 | 说明 |
|--------|---------|--------|------|
| 官方 API 提交 | 后端 | 后端 ✅ | — |
| 提交前门禁检查 | 后端 `submission_preflight_error()` | 后端 ✅ | — |
| 提交审计记录 | 后端 `SubmissionLedger` | 后端 ✅ | — |
| **提交结果解析** | 前端 JSON.stringify 原样 | → **后端** | 后端返回结构化 `submission_summary` |
| **批量提交失败明细渲染** | 前端缺失 | → **前端** | 前端需渲染 `results[].error` |
| **自动提交触发** | 前端 `autoSubmitToggle` → 后端 `payload.autoSubmit` | 前后端协作 ✅ | — |
| **提交确认弹窗** | 前端 `confirmAction()` | 前端 ✅ | — |

### 2.5 数据展示

| 功能点 | 当前位置 | 应归属 | 说明 |
|--------|---------|--------|------|
| 表格渲染 | 前端 | 前端 ✅ | — |
| 图表渲染 | 前端 Chart.js | 前端 ✅ | — |
| 监控瓦片 | 前端 | 前端 ✅ | — |
| **策略表现标签 (`banditLabel()`)** | 前端拼接 | → **后端** | `bandit.label` 字符串 |
| **收敛状态标签 (`convergenceLabel()`)** | 前端判断 | → **后端** | `convergence.label` 字符串 |
| **回测前预检值 (`validationTileValue()`)** | 前端拼接 | → **后端** | `stats.validation_tile` 字符串 |
| **本地生产备注 (`localProductionNote()`)** | 前端拼接 | → **后端** | `stats.production_note` 字符串 |
| **云端状态摘要** | 后端返回 | 后端 ✅ | — |

### 2.6 配置与预设

| 功能点 | 当前位置 | 应归属 | 说明 |
|--------|---------|--------|------|
| 运行配置 | 后端 `config/run_config.json` | 后端 ✅ | — |
| **市场预设参数 (7项)** | 前端 `applyPreset()` 硬编码 | → **后端** | 新增 `config/presets.json` + `GET /api/presets` |
| **预设逆向映射 (`syncPresetFromSettings()`)** | 前端 JS | → **后端** | 后端 settings 响应中包含 `preset_id` |
| 配置值脱敏 | 后端 `public_run_config()` | 后端 ✅ | — |

### 2.7 身份与会话

| 功能点 | 当前位置 | 应归属 | 说明 |
|--------|---------|--------|------|
| 会话管理 (Session + CSRF) | 后端 web.py | 后端 ✅ | — |
| **用户 profile 刷新间隔 (30s)** | 前端 `setInterval` 硬编码 | 前端 ✅ | 前端控制轮询间隔合理 |
| **环境标识渲染** | 前端根据 `env.value` | 前端 ✅ | — |
| 登出 | 后端 `POST /api/logout` | 后端 ✅ | — |
| 关闭服务 | 后端 `POST /api/shutdown` | 后端 ✅ | — |

---

## 三、越界逻辑迁移清单

### 3.1 前端 → 后端迁移

| # | 当前前端代码 | 迁移后后端提供 | 前端改为 |
|---|------------|--------------|---------|
| 1 | `phaseName(phase)` — 25 项硬编码映射 | `progress.phase_label: string` | `progress.phase_label` |
| 2 | `humanCheckName(name)` — 8 项硬编码映射 | `check.label_cn: string` | `check.label_cn` |
| 3 | `isFreshCheck(result)` — 24h 硬编码计算 | `result.is_stale: bool` | `result.is_stale` |
| 4 | `isSubmittable()` / `isPassed()` / `isFailed()` | `candidate.status_category: AlphaStatus` | `candidate.status_category` |
| 5 | `submittableCandidates()` — 过滤逻辑 | 后端维护 `candidate.submittable: bool` | `candidate.submittable` |
| 6 | `needsCheckCount()` / `staleCheckCount()` | `stats.needs_check: int` / `stats.stale_checks: int` | `stats.needs_check` |
| 7 | `activeBacktestCount()` | `stats.active_backtests: int` | `stats.active_backtests` |
| 8 | `convergenceLabel()` / `banditLabel()` | `convergence.label: string` / `bandit.label: string` | 直接使用 |
| 9 | `validationTileValue()` / `localProductionNote()` | `stats.validation_tile: string` / `stats.production_note: string` | 直接使用 |
| 10 | `applyPreset()` — 7 套预设参数 | 后端 `GET /api/presets` + config 中包含 `preset_id` | 从 API 加载预设列表 |

### 3.2 后端 → 前端新增消费

| # | 当前后端返回但前端不渲染 | 前端应增加 |
|---|----------------------|----------|
| 11 | `submit_batch.results[].error` | 批量提交失败明细面板 |
| 12 | `lifecycle` 中 BLOCKED 状态 | 失败视图增加 BLOCKED 过滤/标签 |
| 13 | `check.cloud_correlation_risk.max_similarity` 等 | 检查详情中展示具体数值 |
| 14 | `check.cloud_status.match` | 云端匹配方式图标 |
| 15 | `check.requires_official_check` | 橙色"待官方检查"标签 |
| 16 | `submission` 结果 `status` / `message` | 结构化展示（非 JSON dump） |
| 17 | `profile.username` | Header 用户区显示 |

---

## 四、职责边界速查卡

```
┌─────────────────────────────────────────────────────┐
│                    前端负责                          │
├─────────────────────────────────────────────────────┤
│  • UI 状态管理 (显示/隐藏、表单值、选中态)            │
│  • 用户交互 (按钮点击、弹窗、焦点管理、快捷键)         │
│  • 渲染与动画 (DOM 更新、Chart.js、进度条、Toast)     │
│  • 轮询/SSE 连接管理                                 │
│  • 本地表单校验 (非空检查、类型检查)                   │
│  • 确认弹窗 (提交、关闭、切换环境)                     │
│  • 主题切换 (暗色/浅色)                               │
│  • 搜索与过滤 (表格内搜索、视图切换)                   │
├─────────────────────────────────────────────────────┤
│                    后端负责                          │
├─────────────────────────────────────────────────────┤
│  • 业务校验与规则 (门禁检查、状态机、阈值判定)         │
│  • 数据计算 (评分、统计、相似度、收敛分析)             │
│  • 数据持久化 (生命周期记录、检查结果、提交历史)        │
│  • BRAIN API 交互 (认证、查询、提交、模拟)             │
│  • 安全与鉴权 (Session、CSRF、Origin 校验)            │
│  • 配置管理 (阈值、预设、预算)                         │
│  • 错误码映射 (machine code → human label)            │
│  • 数据脱敏 (traceback → safe message)                │
│  • 格式化标签 (phase_label、check_label_cn、stats)    │
└─────────────────────────────────────────────────────┘
```

---

## 五、设计决策记录

| # | 决策 | 理由 |
|---|------|------|
| D1 | 统计数值（needs_check_count 等）在后端计算 | 原则：数据在哪里，计算就在哪里。避免前端遍历数组。 |
| D2 | 中文化标签在后端生成 | 避免前端 25+ 项硬编码映射表，后端新增检查项时前端自动生效。 |
| D3 | `is_stale` / `checked_at` 在后端返回 | 避免前端独立计算 24h 过期（时区风险）。 |
| D4 | 预设参数移至后端配置文件 | 单一真实源，前后端预设自动同步。 |
| D5 | 前端保持单文件 HTML（构建时内联） | 兼容 Windows .exe 打包 (`pyinstaller --add-data`)，在构建步骤中完成 JS 模块合并。 |
