# BRAIN Alpha Ops — AI 浏览器端到端测试提示词

> 本文档供 AI Agent 在系统浏览器（通过 `playwright-cli`）中模拟真实用户操作使用。
> AI 必须在完整阅读并掌握全部项目代码后，方可执行以下测试流程。

---

## 一、项目全局视角

### 1.1 项目定位
BRAIN Alpha Ops 是一个面向 WorldQuant BRAIN 平台的本地 Alpha 研究工作台。它通过本地 Web 控制台（纯 Python 标准库 HTTP 服务器 + React 18 前端），帮助量化研究员在同一个页面内完成：账号连接、云端同步、候选生成、官方回测、达标检查、评分归因和安全提交。

### 1.2 核心安全原则
- **默认不自动提交** — `auto_submit: false`
- **提交前必须同步云端** — `require_cloud_sync: true`
- **提交前必须通过达标检查** — `require_pre_submit_check_passed: true`
- **每日提交上限** — `max_auto_submissions_per_day: 3`
- **表达式相似度阻断** — `max_expression_similarity: 0.9`
- **SubmissionLedger 审计追踪** — 所有提交记录写入 `data/submissions.jsonl`

### 1.3 技术架构
- **后端**: Python 标准库 `http.server.ThreadingHTTPServer`，端口 `8765`
- **前端**: React 18 + Tailwind CSS，CDN 加载，Babel Standalone 实时编译
- **通信**: REST API (`/api/*`) + Server-Sent Events (`/sse`)
- **会话**: Cookie-based session，CSRF token 保护
- **数据**: JSONL 文件存储候选/提交/知识库，JSON 文件存储配置和官方上下文

### 1.4 运行配置 (`config/run_config.json`)
```
环境: production
区域: USA | Universe: TOP3000 | Delay: 1 | Decay: 10
中性化: SUBINDUSTRY | 语言: FASTEXPR
质量门槛: Sharpe≥1.25, Fitness≥1.0, Turnover∈[1%,70%], 自相关<0.70, 集中度≤10%
评分权重: Prior + Empirical + Checklist = 100
预算: 每周期20候选, 10回测, 3模拟, 最大10周期
```

---

## 二、Web 控制台 UI 元素清单

### 2.1 全局布局
```
┌─────────────────────────────────────────────────────────────┐
│ Header: 🧠 BRAIN Alpha Ops  |  v0.3  |  ● api.worldquantbrain.com │
├─────────────────────────────────────────────────────────────┤
│ Tab Bar: [📊 Dashboard] [🧬 Candidates] [📈 Scoring] [🚀 Submit] [⚙️ Config] │
├─────────────────────────────────────────────────────────────┤
│ Main Content Area (tabpanel)                                │
│                                                             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
│ Toast Notifications (fixed bottom-right)                    │
│ Screen Reader Announcer (#sr-announcer, aria-live)          │
```

### 2.2 Tab 详细元素

#### 📊 Dashboard Tab
| 元素 | 选择器 | 说明 |
|------|--------|------|
| KPI: Total Candidates | `[aria-label*="Total Candidates"]` | 候选总数 |
| KPI: Cloud Alphas | `[aria-label*="Cloud Alphas"]` | 云端 Alpha 数 |
| KPI: Backtests | `[aria-label*="Backtests"]` | 回测数 |
| KPI: Submissions | `[aria-label*="Submissions"]` | 提交数 |
| Pipeline Status | `[aria-label="Pipeline control panel"]` | 管线控制面板 |
| Start Pipeline 按钮 | `button:has-text("Start Pipeline")` | 启动管线 |
| Stop 按钮 | `button:has-text("Stop")` | 停止管线 |
| 进度条 | `[role="progressbar"]` | 管线进度 |
| 事件日志 | `[role="log"]` | 实时事件流 |
| Cloud Alpha Cache | `h3:has-text("Cloud Alpha Cache")` | 云端缓存面板 |
| Top Families | `h3:has-text("Top Families")` | 族系统计 |
| Top Fields | `h3:has-text("Top Fields")` | 字段统计 |
| Failure Patterns | `h3:has-text("Failure Patterns")` | 失败模式 |

#### 🧬 Candidates Tab
| 元素 | 选择器 | 说明 |
|------|--------|------|
| 过滤输入框 | `#candidate-filter` | 按表达式/族系/ID过滤 |
| Refresh 按钮 | `button:has-text("Refresh")` | 刷新候选列表 |
| 排序: Score | `th:has-text("Score")` | 按分数排序 |
| 排序: Sharpe | `th:has-text("Sharpe")` | 按 Sharpe 排序 |
| 排序: Fitness | `th:has-text("Fitness")` | 按 Fitness 排序 |
| 排序: TO | `th:has-text("TO")` | 按换手率排序 |
| 候选表格 | `[role="grid"]` | 候选数据表 |
| 状态徽章 | `.badge-success` / `.badge-danger` / `.badge-warning` | 生命周期状态 |

#### 📈 Scoring Tab
| 元素 | 选择器 | 说明 |
|------|--------|------|
| Alpha Expression | `code` (表达式代码块) | 当前候选表达式 |
| Scorecard 总分 | `.text-4xl.font-bold.text-indigo-400` | 总分/100 |
| Prior 进度条 | `ScoreBar:has-text("Prior")` | 先验分 |
| Empirical 进度条 | `ScoreBar:has-text("Empirical")` | 经验分 |
| Checklist 进度条 | `ScoreBar:has-text("Checklist")` | 检查清单分 |
| Official Metrics | `h3:has-text("Official Metrics")` | 官方指标面板 |
| Quality Gate | `h3:has-text("Quality Gate")` | 质量门禁检查项 |

#### 🚀 Submit Tab
| 元素 | 选择器 | 说明 |
|------|--------|------|
| 安全提醒 | `[role="alert"]:has-text("Account Safety")` | 黄色安全警告 |
| Alpha ID 输入 | `#alpha-id-input` | 输入官方 Alpha ID |
| Pre-Submit Check | `button:has-text("Pre-Submit Check")` | 提交前检查 |
| Submit Alpha | `button:has-text("Submit Alpha")` | 提交按钮（红色） |
| 确认复选框 | `input[aria-label="Confirm submission"]` | 提交确认勾选 |
| 检查结果 | `[aria-label="Pre-submit check result"]` | 检查结果 JSON |

#### ⚙️ Config Tab
| 元素 | 选择器 | 说明 |
|------|--------|------|
| Brain Settings | `h3:has-text("Brain Settings")` | 区域/宇宙/延迟等 |
| Budget | `h3:has-text("Budget")` | 预算配置 |
| Quality Thresholds | `h3:has-text("Quality Thresholds")` | 质量门槛 |
| Scoring | `h3:has-text("Scoring")` | 评分权重 |
| Environment | `h3:has-text("Environment")` | 环境与自动提交 |

### 2.3 通用交互元素
| 元素 | 选择器 | 说明 |
|------|--------|------|
| Skip to main content | `.skip-link` | 键盘跳过链接 |
| Toast 通知 | `[role="alert"]` (在 `[aria-label="Notifications"]` 内) | 操作反馈 |
| Error Banner | `.border-red-500/30[role="alert"]` | 错误提示 |
| Skeleton 加载 | `.skeleton` | 骨架屏 |
| Empty State | `.empty-state` | 空数据提示 |

---

## 三、API 端点参考

### 3.1 GET 端点
| 路径 | 功能 | 响应关键字段 |
|------|------|-------------|
| `/api/health` | 健康检查 | `{ok: true}` |
| `/api/status` | 管线状态 | `{ok, status, cycle, max_cycles, phase, progress}` |
| `/api/config` | 运行配置 | `{ok, settings, budget, thresholds, scoring, environment}` |
| `/api/candidates` | 候选列表 | `{ok, candidates: [{alpha_id, expression, lifecycle_status, scorecard, official_metrics}]}` |
| `/api/snapshot/cloud` | 云端快照 | `{ok, count, submitted_count, passed_unsubmitted_count, is_stale, sample_alphas}` |
| `/api/snapshot/memory` | 研究记忆 | `{ok, total_candidates, families, fields, failure_patterns}` |
| `/api/lifecycle` | 生命周期 | `{ok, lifecycle}` |
| `/api/check_results` | 检查结果 | `{ok, results}` |
| `/api/presets` | 预设配置 | `{ok, presets}` |

### 3.2 POST 端点
| 路径 | 功能 | 请求体 | 响应 |
|------|------|--------|------|
| `/api/test_connection` | 连接测试 | `{username, password, token}` | `{ok, connected, message}` |
| `/api/sync_alphas` | 云端同步 | `{sync_range, ...}` | `{ok, job_id}` |
| `/api/run` | 启动管线 | `{}` | `{ok, job_id}` |
| `/api/stop` | 停止管线 | `{job_id}` | `{ok}` |
| `/api/generate_candidates` | 生成候选 | `{count, ...}` | `{ok, candidates}` |
| `/api/check` | 提交前检查 | `{alpha_id}` | `{ok, checks, ...}` |
| `/api/submit` | 提交 Alpha | `{alpha_id, confirm_submit: true}` | `{ok, submission}` |
| `/api/check_batch` | 批量检查 | `{candidate_ids, ...}` | `{ok, job_id}` |
| `/api/submit_batch` | 批量提交 | `{alpha_ids, confirm_submit: true}` | `{ok, results}` |

### 3.3 SSE 端点
| 路径 | 功能 | 事件格式 |
|------|------|---------|
| `/sse?job_id=...&csrf_token=...&stream_token=...` | 实时状态流 | `data: {ok, status, progress, error}` |
| `/api/stream` | 同上（别名） | 同上 |

---

## 四、测试操作流程

### 前置条件
1. 确保 `playwright-cli` 已安装：`npm install -g @playwright/cli@latest`
2. 确保 Web 服务已启动：`python launch_web.py`（默认 `http://127.0.0.1:8765`）
3. 如需真实 API 测试，需准备 WorldQuant BRAIN 账号凭据

### 操作指令格式
使用 `playwright-cli` 命令与浏览器交互：
```bash
# 打开浏览器
playwright-cli open http://127.0.0.1:8765

# 获取页面快照（获取元素引用）
playwright-cli snapshot
cat .playwright-cli/page-*.yml

# 点击元素（使用快照中的引用）
playwright-cli click e15

# 输入文本
playwright-cli fill e5 "text content"

# 执行 JavaScript
playwright-cli eval "document.title"

# 截图
playwright-cli screenshot --filename=step1.png

# 关闭浏览器
playwright-cli close
```

---

### Step 1: 页面加载

**目标**: 验证 Web 控制台正确加载，React 应用初始化完成。

**操作序列**:
1. 打开浏览器并导航到 `http://127.0.0.1:8765`
2. 等待 3 秒让 React 应用完成初始化
3. 执行 `playwright-cli eval "document.title"` 验证标题包含 "BRAIN Alpha Ops"
4. 执行 `playwright-cli eval "document.getElementById('root').style.display"` 验证为 `"block"`
5. 执行 `playwright-cli snapshot` 获取页面元素引用
6. 验证 Header 区域显示 "BRAIN Alpha Ops" 和 "v0.3"
7. 验证 Tab 栏显示 5 个 Tab：Dashboard, Candidates, Scoring, Submit, Config
8. 验证 Dashboard Tab 默认激活（`aria-selected="true"`）
9. 验证 KPI 卡片区域存在（4 个卡片）
10. 截图保存

**预期结果**:
- 页面标题: "BRAIN Alpha Ops"
- React 根节点可见
- 5 个 Tab 全部渲染
- Dashboard 为默认激活 Tab
- KPI 卡片显示骨架屏或数据

**验证点**:
```javascript
// 通过 eval 验证
document.title // => "BRAIN Alpha Ops"
document.getElementById('root').style.display // => "block"
document.querySelectorAll('[role="tab"]').length // => 5
document.querySelector('[aria-selected="true"]')?.textContent // => "📊Dashboard"
```

---

### Step 2: 连接测试

**目标**: 验证 API 连接测试功能，包括成功和失败场景。

**操作序列**:

#### 2a. 健康检查（无需认证）
1. 执行 `curl -s http://127.0.0.1:8765/api/health` 验证返回 `{"ok": true}`
2. 执行 `curl -s http://127.0.0.1:8765/api/status` 验证状态接口可访问

#### 2b. 页面内连接测试（需认证）
1. 确保在 Dashboard Tab
2. 查找并记录页面上的连接状态指示器（Header 右侧的绿色/红色圆点）
3. 执行 `playwright-cli eval "document.querySelector('[role=\"status\"]')?.getAttribute('aria-label')"` 获取连接状态

#### 2c. 无效凭据测试
1. 使用 `curl` 发送无效凭据到 `/api/test_connection`：
   ```bash
   curl -s -X POST http://127.0.0.1:8765/api/test_connection \
     -H "Content-Type: application/json" \
     -d '{"username":"invalid","password":"invalid"}'
   ```
2. 验证返回 `{ok: false, error: "..."}` 格式的错误响应

#### 2d. 会话验证
1. 不带 Cookie 访问需认证的端点：`curl -s http://127.0.0.1:8765/api/config`
2. 验证返回 401 或重定向

**预期结果**:
- `/api/health` 无需认证即可访问
- `/api/status` 需要有效会话
- 无效凭据返回明确错误信息
- 无会话请求被正确拒绝

---

### Step 3: 云端同步

**目标**: 验证云端数据同步功能和状态展示。

**操作序列**:

#### 3a. 云端快照接口验证
1. 执行 `curl -s http://127.0.0.1:8765/api/snapshot/cloud?limit=10` 获取云端快照
2. 验证响应包含 `count`, `submitted_count`, `passed_unsubmitted_count`, `is_stale` 字段
3. 记录当前缓存状态（是否过期）

#### 3b. 研究记忆接口验证
1. 执行 `curl -s http://127.0.0.1:8765/api/snapshot/memory?limit=100&top_n=5` 获取研究记忆
2. 验证响应包含 `total_candidates`, `families`, `fields`, `failure_patterns` 字段

#### 3c. Dashboard 云端面板验证
1. 切换到 Dashboard Tab
2. 执行 `playwright-cli snapshot` 获取元素引用
3. 查找 "Cloud Alpha Cache" 面板
4. 验证面板显示：Total cached, Submitted, Passed (unsubmitted), Cache stale
5. 如果有 `sample_alphas`，验证表格显示 Alpha ID、Pass/Fail 状态、Sharpe/Fitness 值

#### 3d. 云端同步操作（如已认证）
1. 查找 "同步云端数据" 或类似按钮
2. 点击触发同步
3. 观察进度指示器变化
4. 等待同步完成
5. 验证 KPI 卡片中 "Cloud Alphas" 数值更新

**预期结果**:
- 云端快照接口返回结构化数据
- 研究记忆接口返回族系/字段/失败模式统计
- Dashboard 云端面板正确展示缓存状态
- 同步操作触发后进度条变化

---

### Step 4: 视图导航

**目标**: 验证所有 Tab 的切换和内容渲染。

**操作序列**:

#### 4a. Dashboard → Candidates
1. 执行 `playwright-cli snapshot` 获取 Tab 引用
2. 点击 "Candidates" Tab
3. 验证 Tab 的 `aria-selected` 变为 `"true"`
4. 验证 `tabpanel` 的 `aria-label` 包含 "candidates"
5. 验证候选表格或空状态提示渲染
6. 截图保存

#### 4b. Candidates → Scoring
1. 点击 "Scoring" Tab
2. 验证 Scoring 面板渲染
3. 查找 "Alpha Expression" 代码块
4. 查找 "Scorecard" 面板（总分、Prior/Empirical/Checklist 进度条）
5. 查找 "Official Metrics" 面板（Sharpe, Fitness, Turnover, Returns, Drawdown, Correlation, Concentration）
6. 查找 "Quality Gate" 面板（检查项列表）
7. 截图保存

#### 4c. Scoring → Submit
1. 点击 "Submit" Tab
2. 验证安全提醒面板（黄色警告："Account Safety Reminder"）
3. 验证 Alpha ID 输入框存在
4. 验证 "Pre-Submit Check" 按钮存在
5. 验证 "Submit Alpha" 按钮存在（红色危险样式）
6. 验证确认复选框存在
7. 截图保存

#### 4d. Submit → Config
1. 点击 "Config" Tab
2. 验证配置面板渲染
3. 验证显示 5 个配置区域：Brain Settings, Budget, Quality Thresholds, Scoring, Environment
4. 验证 Brain Settings 显示：Region=USA, Universe=TOP3000, Delay=1, Decay=10, Neutralization=SUBINDUSTRY
5. 验证 Quality Thresholds 显示：Min Sharpe=1.25, Min Fitness=1.0 等
6. 截图保存

#### 4e. Config → Dashboard（循环回到起点）
1. 点击 "Dashboard" Tab
2. 验证回到 Dashboard 视图
3. 验证 KPI 卡片数据仍然显示

**预期结果**:
- 每个 Tab 切换后内容正确渲染
- Tab 的 `aria-selected` 状态正确切换
- `tabpanel` 的 `aria-label` 正确更新
- 所有面板和组件按预期显示

---

### Step 5: 搜索功能

**目标**: 验证候选过滤和排序功能。

**操作序列**:

#### 5a. 切换到 Candidates Tab
1. 点击 "Candidates" Tab
2. 等待候选列表加载

#### 5b. 过滤测试
1. 执行 `playwright-cli snapshot` 获取过滤输入框引用
2. 在过滤输入框中输入 "rank"
3. 等待 500ms 让过滤生效
4. 验证表格行数减少（或显示 "No matches" 空状态）
5. 验证过滤结果中每行的 expression 或 family 包含 "rank"
6. 清空过滤输入框
7. 验证所有候选重新显示

#### 5c. 排序测试
1. 点击 "Score" 列标题
2. 验证排序方向指示器（↑ 或 ↓）出现
3. 记录第一行的 Score 值
4. 再次点击 "Score" 列标题（切换排序方向）
5. 验证排序方向指示器反转
6. 验证第一行 Score 值已变化

#### 5d. 多列排序
1. 点击 "Sharpe" 列标题
2. 验证 Sharpe 列成为主要排序列
3. 验证 Score 列的排序指示器消失

#### 5e. 刷新功能
1. 点击 "↻ Refresh" 按钮
2. 验证按钮变为 loading 状态
3. 等待刷新完成
4. 验证候选列表更新

**预期结果**:
- 过滤输入实时生效
- 排序点击切换升序/降序
- 多列排序正确切换主排序列
- 刷新按钮触发数据重新加载

---

### Step 6: 图表渲染与交互

**目标**: 验证 Dashboard 的数据可视化和交互元素。

**操作序列**:

#### 6a. KPI 卡片验证
1. 切换到 Dashboard Tab
2. 执行 `playwright-cli snapshot` 获取 KPI 卡片引用
3. 验证 4 个 KPI 卡片存在：
   - Total Candidates（显示候选总数和族系数）
   - Cloud Alphas（显示云端 Alpha 数和已提交数）
   - Backtests（显示回测数和待处理数）
   - Submissions（显示提交数）
4. 验证数值使用 `tabular-nums` 等宽字体
5. 验证趋势指示器（up/down/neutral）正确显示

#### 6b. Job Monitor 面板
1. 查找 "Pipeline Status" 面板
2. 验证状态指示器（绿色=连接，红色=断开）
3. 验证运行状态徽章（Running/Idle）
4. 如果管线正在运行：
   - 验证进度条显示并有百分比
   - 验证 Cycle/Phase/Candidates/Backtests 统计显示
   - 验证事件日志区域有条目滚动

#### 6c. Cloud Alpha Cache 面板
1. 查找 "Cloud Alpha Cache" 面板
2. 验证显示：Total cached, Submitted, Passed (unsubmitted), Cache stale
3. 如果有 `sample_alphas`：
   - 验证表格显示 Alpha ID（靛蓝色）
   - 验证 Pass/Fail 状态（绿色/红色）
   - 验证 Sharpe 和 Fitness 值

#### 6d. 族系/字段/失败模式面板
1. 查找 "Top Families" 面板
2. 验证显示族系名称、计数和成功率
3. 查找 "Top Fields" 面板
4. 验证显示字段名称、计数和成功率
5. 查找 "Failure Patterns" 面板
6. 验证显示失败原因和计数（红色文本）

#### 6e. 加载状态验证
1. 如果页面刚加载，验证骨架屏（`.skeleton`）显示
2. 验证骨架屏有 shimmer 动画效果
3. 等待数据加载完成
4. 验证骨架屏被实际数据替换

**预期结果**:
- KPI 卡片显示正确的数值和趋势
- Job Monitor 面板实时更新
- Cloud Alpha Cache 面板显示缓存统计
- 族系/字段/失败模式面板显示 Top 5 数据
- 加载状态正确显示骨架屏

---

### Step 7: 插件控制（Pipeline 启停）

**目标**: 验证 Pipeline 的启动、监控和停止功能。

**操作序列**:

#### 7a. 启动前状态验证
1. 切换到 Dashboard Tab
2. 验证 "Start Pipeline" 按钮可点击（`disabled=false`）
3. 验证 "Stop" 按钮不可点击（`disabled=true`）
4. 验证状态徽章显示 "Idle"
5. 验证进度条不存在或为 0%

#### 7b. 启动 Pipeline
1. 点击 "▶ Start Pipeline" 按钮
2. 验证 Toast 通知出现："Started job: ..."
3. 验证按钮状态变化：
   - "Start Pipeline" 变为 `disabled=true`
   - "Stop" 变为 `disabled=false`
4. 验证状态徽章变为 "Running"（绿色）
5. 验证进度条出现并开始增长
6. 验证 Cycle/Phase/Candidates/Backtests 统计开始更新
7. 验证事件日志区域开始滚动条目

#### 7c. 监控 Pipeline 运行
1. 等待 5-10 秒
2. 执行 `playwright-cli snapshot` 获取最新状态
3. 验证进度条百分比增加
4. 验证 Cycle 计数增加
5. 验证 Candidates 生成数增加
6. 验证事件日志有新条目（格式：`✓ Candidate alpha_xxx scored xx.x`）

#### 7d. 停止 Pipeline
1. 点击 "⏹ Stop" 按钮
2. 验证 Toast 通知出现："Pipeline stopped"
3. 验证按钮状态恢复：
   - "Start Pipeline" 变为 `disabled=false`
   - "Stop" 变为 `disabled=true`
4. 验证状态徽章变回 "Idle"
5. 验证进度条停止更新

#### 7e. SSE 连接验证
1. 执行 `playwright-cli eval "window.__BRAIN_ALPHA_OPS_CSRF_TOKEN__"` 验证 CSRF token 存在
2. 执行 `playwright-cli eval "window.__BRAIN_ALPHA_OPS_STREAM_TOKEN__"` 验证 stream token 存在
3. 如果管线正在运行，验证 SSE 连接状态指示器为绿色

**预期结果**:
- 启动按钮点击后触发管线运行
- 进度条和统计实时更新
- 事件日志滚动显示候选生成和回测结果
- 停止按钮正确终止管线
- SSE 连接正常建立和断开

---

### Step 8: 错误触发与恢复

**目标**: 验证错误处理机制、用户反馈和恢复路径。

**操作序列**:

#### 8a. 无效 API 请求
1. 访问不存在的端点：
   ```bash
   curl -s http://127.0.0.1:8765/api/nonexistent
   ```
2. 验证返回 404 或标准错误格式：`{ok: false, error: "...", error_code: "..."}`

#### 8b. 无效 POST 请求
1. 发送空 body 到需要参数的端点：
   ```bash
   curl -s -X POST http://127.0.0.1:8765/api/test_connection \
     -H "Content-Type: application/json" -d '{}'
   ```
2. 验证返回验证错误

#### 8c. Submit Tab 表单验证
1. 切换到 Submit Tab
2. 不输入 Alpha ID，直接点击 "Pre-Submit Check"
3. 验证输入框显示错误样式（红色边框 `.error`）
4. 验证错误消息出现："Alpha ID is required"
5. 验证 `aria-invalid="true"` 和 `aria-describedby` 正确设置
6. 输入少于 3 个字符，触发 "Alpha ID is too short" 错误
7. 输入有效 Alpha ID，验证错误清除

#### 8d. 提交确认验证
1. 在 Submit Tab 输入有效 Alpha ID
2. 不勾选确认复选框，直接点击 "Submit Alpha"
3. 验证 Toast 通知出现："Please confirm submission by checking the box"
4. 勾选确认复选框
5. 验证 "Submit Alpha" 按钮可点击

#### 8e. ErrorBanner 组件验证
1. 如果页面有错误状态，验证 ErrorBanner 组件渲染：
   - 红色边框样式（`.border-red-500/30`）
   - `role="alert"` 属性
   - 错误消息文本
   - "Retry" 按钮（如果适用）
2. 点击 "Retry" 按钮，验证重新加载

#### 8f. Toast 通知系统验证
1. 触发一个操作（如点击按钮）产生 Toast
2. 验证 Toast 出现在右下角固定位置
3. 验证 Toast 包含：图标（✓/✕/⚠/ℹ）、消息文本
4. 验证 Toast 样式：绿色=成功，红色=错误，黄色=警告，靛蓝=信息
5. 点击 Toast 或等待 5 秒，验证 Toast 消失
6. 验证 Toast 支持键盘操作（Enter/Space 关闭）

#### 8g. 屏幕阅读器播报验证
1. 执行 `playwright-cli eval "document.getElementById('sr-announcer')?.textContent"`
2. 触发一个操作（如 Tab 切换）
3. 再次执行上述 eval，验证播报内容更新
4. 验证 `aria-live="polite"` 和 `aria-atomic="true"` 属性

#### 8h. 网络断开恢复（模拟）
1. 如果管线正在运行，观察 SSE 断开行为
2. 验证 "Connection lost. Reconnecting..." 播报
3. 验证自动重连机制（最多 10 次，间隔 3 秒）
4. 如果重连失败，验证 "Connection failed. Please refresh the page." 播报

#### 8i. 键盘导航验证
1. 按 Tab 键遍历页面元素
2. 验证焦点顺序合理：Skip link → Tab bar → Main content
3. 验证 `:focus-visible` 样式正确应用（靛蓝色轮廓）
4. 按 Enter 激活 Skip link，验证焦点跳转到 `#main-content`
5. 在 Tab bar 使用左右箭头键切换 Tab
6. 在候选表格中使用 Enter 键触发排序

**预期结果**:
- 无效请求返回明确错误信息
- 表单验证实时显示错误
- Toast 通知正确显示和消失
- 屏幕阅读器播报内容正确更新
- 键盘导航流畅可用
- 网络断开后自动重连

---

## 五、测试报告模板

完成全部 8 步测试后，输出以下格式的测试报告：

```markdown
# BRAIN Alpha Ops E2E 测试报告

**测试时间**: YYYY-MM-DD HH:MM
**测试环境**: macOS / Chrome, http://127.0.0.1:8765
**测试账号**: [已认证 / 未认证]

## 测试结果汇总

| 步骤 | 名称 | 状态 | 备注 |
|------|------|------|------|
| 1 | 页面加载 | ✅/❌ | |
| 2 | 连接测试 | ✅/❌ | |
| 3 | 云端同步 | ✅/❌ | |
| 4 | 视图导航 | ✅/❌ | |
| 5 | 搜索功能 | ✅/❌ | |
| 6 | 图表渲染 | ✅/❌ | |
| 7 | 插件控制 | ✅/❌ | |
| 8 | 错误恢复 | ✅/❌ | |

## 详细发现

### 通过的验证点
- [列出所有通过的验证点]

### 失败的验证点
- [列出所有失败的验证点，包含实际值和预期值]

### 改进建议
- [列出发现的问题和改进建议]

## 截图证据
- [列出保存的截图文件路径]
```

---

## 六、注意事项

1. **认证依赖**: Step 2b、3d、7 的部分操作需要有效的 BRAIN 账号凭据。在无凭据环境下，这些步骤应标记为 "跳过（需认证）"
2. **数据依赖**: Step 5（搜索）、6（图表）的效果取决于是否有历史数据。首次运行可能显示空状态
3. **网络依赖**: Step 3（云端同步）需要访问 `api.worldquantbrain.com`。离线环境下应验证错误处理
4. **并发安全**: Step 7（Pipeline 启停）不应在生产环境随意测试，可能产生实际 API 调用
5. **截图保存**: 所有截图保存到 `data/e2e_screenshots/` 目录
6. **快照文件**: playwright-cli 快照保存到 `.playwright-cli/` 目录
