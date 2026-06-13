# BRAIN-Alpha Ops v0.3.0 — 用户手册 (User Manual)

> **版本**: 0.3.0
> **日期**: 2026-06-13
> **目标读者**: 研究员 / 量化分析师
> **使用对象**: BRAIN Alpha Ops 本地 Web 控制台

---

## 目录

1. [快速开始](#1-快速开始)
2. [核心概念](#2-核心概念)
3. [Web 控制台导览](#3-web-控制台导览)
4. [典型工作流](#4-典型工作流)
5. [凭据管理](#5-凭据管理)
6. [配置调优](#6-配置调优)
7. [常见任务](#7-常见任务)
8. [FAQ](#8-faq)
9. [故障排除](#9-故障排除)

---

## 1. 快速开始

### 1.1 安装

#### 方式 A: 源码 (开发 / 自定义)

```bash
# 1. 克隆/拷贝项目
cd /path/to/WorldQuant-BRAIN-Alpha

# 2. 创建虚拟环境
python3.10+ -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 3. 安装依赖 (精确锁版)
pip install -r requirements.lock

# 4. 安装前端依赖
cd brain_alpha_ops/web/react_app
npm ci
cd ../../../

# 5. 构建前端
cd brain_alpha_ops/web/react_app
npm run build
cd ../../../

# 6. 启动
python launch_web.py
```

#### 方式 B: 打包可执行 (生产 / 分发)

```bash
# macOS
python build_prod.py
./dist/BrainAlphaOps

# Windows (在 Windows 上执行)
.\scripts\build_windows.ps1
.\dist\BrainAlphaOps.exe
```

### 1.2 首次启动

启动后会自动打开浏览器 (可 `--no-browser` 关闭) 访问 `http://127.0.0.1:8765/`。

**首次启动你将看到**:
1. "凭证与连接" 面板 (Step 1)
2. 输入 BRAIN 账户邮箱 + 密码 (或 Token)
3. 点击 "测试连接" → 期望 "BRAIN 连接测试通过"
4. 完成后, 系统自动进入 "Phase: discover" (默认发现模式)

### 1.3 三种运行模式

| 模式 | 描述 | 何时用 |
|---|---|---|
| **Discover (发现)** | 探索 + 生成候选, 不提交 | 起步调研 |
| **Validate (验证)** | 跑 BRAIN 平台 simulate/check | 评估候选 |
| **Submit (提交)** | 走预提交审查 + 独立审批后真正提交 | 选定的 alpha 上线 |

切换模式: 左侧导航栏 → "阶段控制" → 选择阶段。

---

## 2. 核心概念

### 2.1 Alpha 与 Candidate

| 术语 | 含义 |
|---|---|
| **Alpha** | 一个具体的量化因子表达式, 已通过 BRAIN 平台校验 |
| **Candidate** | 本地生成的候选 alpha, 正在排队等待 BRAIN 平台 simulate |
| **Expression** | 表达式字符串, 如 `rank(ts_delta(returns, 10))` |
| **Family** | 因子家族 (momentum/value/quality/liquidity/volatility/co_movement/...) |
| **Hypothesis** | 经济假设描述, 例如"高动量 + 低估值 = 短期反转" |

### 2.2 Pipeline Cycle (管线循环)

每轮 cycle 14 步:
```
1. 选择 dataset
2. (每 5 轮) 注入经验反馈
3. 应用 LLM 引导 (如有)
4. 刷新可观测性
5. 生成候选
6. 本地预筛 (LocalBacktestEngine)
7. 池化 + 排名
8. 提交非提交验证 (BRAIN validate_expression)
9. 池补给
10. simulate + 提交闸口
11. 策略切换评估
12. convergence 记录
13. stalled 检测 + fusion 触发
14. auto_calibrator 重调权重
```

### 2.3 Hard Gates (硬性闸口)

候选必须同时满足 9 项, 否则 `status="hard_gate_blocked"`:
1. sharpe ≥ min_sharpe (默认 1.25)
2. fitness ≥ min_fitness (默认 1.0)
3. turnover_min ≥ 0.01
4. turnover_platform ≤ 0.70
5. turnover_quality ≤ 0.30
6. self_correlation < 0.70
7. prod_correlation ≤ 0.70
8. weight_concentration ≤ 0.10
9. sub_universe_sharpe ≥ 阈值

### 2.4 提交防御机制

**BRAIN-Alpha Ops 采用三道防御**:
1. **模式闸**: 仅 "Submit" 阶段允许真实提交
2. **预提交审查**: 列出所有阻断项, 需逐一确认
3. **独立审批路径**: 第二步"独立审批路径执行前, 所有阻断项已被识别和处理"
4. **REAL_SUBMIT_DISABLED_WEB_FLOW kill-switch**: 默认 `True`, 需 `BRAIN_ALPHA_ENABLE_REAL_SUBMIT_TESTS=1` 才放行 (仅测试)

---

## 3. Web 控制台导览

### 3.1 顶部状态条

| 元素 | 含义 |
|---|---|
| 绿点 "已连接" | BRAIN API 可用 |
| 黄点 "本地缓存" | 离线模式, 使用历史缓存 |
| 红点 "错误" | 检查右侧 error panel |
| 阶段标签 | 当前 pipeline 阶段 (discover/validate/submit) |
| 任务 ID | 当前正在跑的 task_id |

### 3.2 左侧导航栏 (6 阶段)

| 阶段 | 用途 |
|---|---|
| 1. 凭证与连接 | 配置 BRAIN 账户 (Step 1) |
| 2. 数据与上下文 | 选择 dataset / region / 刷新官方 context |
| 3. 候选生成 | 配置 generation 参数, 启动 cycle |
| 4. 评分与校验 | 查看候选评分, 跑 BRAIN validate |
| 5. 模拟与回测 | 启动 BRAIN simulate, 监控 slot |
| 6. 预提交与提交 | 走预提交审查 + 独立审批 |

### 3.3 右侧主面板

根据所选阶段动态切换, 主要面板:
- **CandidateTable**: 候选列表, 可按 sharpe/fitness/turnover 排序
- **JobMonitor**: 任务进度 (SSE 实时推送)
- **QualityCheckPanel**: 9 hard gates 状态
- **ScoringPanel**: 综合评分, 含 prior + empirical 两层
- **SubmissionConfirmPanel**: 提交前最后审查

### 3.4 底部面板

- **PhaseState**: 当前阶段详细状态
- **LogRedactionBadge**: 日志脱敏状态 (调试用)
- **DataLineage**: 数据血缘 (debug)

---

## 4. 典型工作流

### 4.1 流程 A: 新人首次启动

```
1. launch_web.py → 浏览器打开
2. 填写 BRAIN 账户 → 测试连接
3. (默认) Discover 模式 → "启动候选池自动推进"
4. 等 5-15 分钟, 看到第一批候选
5. 切到 Validate 模式 → "批量 BRAIN 验证"
6. 等 30-60 分钟, 看到 BRAIN 平台评分
7. 切到 Submit 模式 → "预提交审查" → "独立审批"
8. 真正提交 (需显式确认, 不会自动)
```

### 4.2 流程 B: 日常研究循环

```
1. 启动 → 直接进入上次的 phase_state
2. 左侧 "任务监控" → 看上轮 cycle 结果
3. 切到 "质量检查" → 看 9 hard gates 状态
4. 切到 "候选管理" → 排序, 选 5 个高分候选
5. 切到 "BRAIN 操作" → "批量 simulate"
6. 等平台回填 → 看新的 sharpe/fitness
7. 反复 2-6, 收集 10-20 个高分候选
8. 切到 "提交审查" → 选 1-2 个 → "独立审批" → 真正提交
```

### 4.3 流程 C: 调整 generation 参数

```
1. 左侧 "系统配置" → 找到 `generation` 段
2. 调整: `num_candidates_per_cycle` (默认 10)
3. 调整: `family_weights` (默认均衡)
4. 调整: `mutation_rate` (默认 0.3)
5. 保存 → 下一 cycle 生效
```

---

## 5. 凭据管理

### 5.1 三种凭据注入方式 (按优先级)

| 优先级 | 方式 | 适用 |
|---|---|---|
| 1 (高) | 页面输入 (临时) | 一次性使用, 不留盘 |
| 2 (中) | 浏览器 sessionStorage | 同会话, 关闭浏览器清除 |
| 3 (低) | 维护者配置环境变量 | 长期 (推荐生产) |

### 5.2 维护者配置 (推荐生产)

```bash
# 在启动 launch_web.py 之前 export
export BRAIN_USERNAME="your@email.com"
export BRAIN_PASSWORD="..."  # 与 BRAIN_USERNAME 配对
# 或者
export BRAIN_TOKEN="..."  # 单独 token

# 启动
python launch_web.py
```

### 5.3 凭据安全保证

- 凭据**绝不带盘** (无 cookies 持久化, 无 localStorage)
- 浏览器只存 `brain_alpha_ops_session` cookie (HttpOnly; SameSite=Strict)
- 日志自动 redact (password/token/csrf/secret 等)
- 关闭浏览器即清空所有凭据

---

## 6. 配置调优

### 6.1 关键配置 (config/run_config.json)

| 段 | 字段 | 默认 | 说明 |
|---|---|---|---|
| `brain` | `delay` | 1 | 信号延迟 (1=次日开盘可用) |
| `brain` | `decay` | 10 | 衰减线 (越小越敏感) |
| `brain` | `neutralization` | SUBINDUSTRY | 中性化维度 |
| `pipeline` | `num_candidates_per_cycle` | 10 | 每轮生成候选数 |
| `pipeline` | `retained_alpha_pool_size` | 50 | 候选池目标容量 |
| `scoring` | `min_sharpe` | 1.25 | hard gate 阈值 |
| `scoring` | `min_fitness` | 1.0 | hard gate 阈值 |
| `rate_limit` | `min_request_interval_seconds` | 3.0 | BRAIN API 限频 |

### 6.2 预设 (config/presets.json)

7 个预设可一键切换:
- `conservative`: 保守, 严格 hard gate
- `balanced`: 平衡 (默认)
- `aggressive`: 激进, 放宽 hard gate
- `momentum_focus`: 偏动量因子
- `value_focus`: 偏价值因子
- `quality_focus`: 偏质量因子
- `liquidity_focus`: 偏流动性因子

切换: 左侧 "系统配置" → 顶部 "Presets" 下拉框。

---

## 7. 常见任务

### 7.1 任务 1: 启动一次完整的 cycle

**步骤**:
1. 左侧 "任务监控" → "启动生产流程" 按钮
2. 选择阶段 (默认 discover)
3. 选 preset (默认 balanced)
4. 点击 "启动" → 浏览器开始 SSE 实时推送
5. 等 5-15 分钟 → 状态变 "complete"
6. 切到 "候选管理" 查看结果

### 7.2 任务 2: 同步云端 alpha

**步骤**:
1. 左侧 "云端同步" → "立即同步"
2. 系统会从 BRAIN 拉取账户下所有 alpha
3. 等待 (取决于 alpha 数量, 通常 1-5 分钟)
4. "Alpha 库存" 面板会显示新同步的 alpha

### 7.3 任务 3: 跑 BRAIN 平台 validate (非提交)

**步骤**:
1. 左侧 "BRAIN 操作" → "批量验证"
2. 选 N 个候选 (默认 top 5)
3. 点击 "启动验证"
4. 等 BRAIN 平台返回 (每个 ~30s)
5. 验证通过后, alpha 进入 "可模拟" 队列

### 7.4 任务 4: 启动 BRAIN simulate (官方 slot)

**步骤**:
1. 左侧 "BRAIN 操作" → "模拟槽位" 面板
2. 查看当前 active_count / slot_limit (默认 3/3)
3. 选 N 个 validated 候选 → "启动模拟"
4. 等平台回填 (5-30 分钟)
5. 完成后自动进入 "可提交" 队列

### 7.5 任务 5: 真正提交 (二阶段)

**阶段 A: 预提交审查**
1. 左侧 "预提交审查" → 系统列出 1-2 个高分 alpha
2. 列出所有阻断项 (必须 0 阻断)
3. 阅读评分卡 + brain_checks + self_correlation
4. 点击 "已审查, 进入独立审批"

**阶段 B: 独立审批路径**
1. 系统切换到独立审批面板
2. 列出"为何此 alpha 安全" 的 5+ 条证据
3. 必须显式输入 "APPROVE" 文本
4. 点击 "确认提交" → 系统调用 BRAIN `POST /alphas/{id}/submit`

**注意**: REAL_SUBMIT_DISABLED_WEB_FLOW 默认 True, 真实提交被阻断。需在测试环境设置 `BRAIN_ALPHA_ENABLE_REAL_SUBMIT_TESTS=1`。

### 7.6 任务 6: 停掉一个 running 任务

**步骤**:
1. 左侧 "任务监控" → 找到 running 任务
2. 点击 "取消" 按钮
3. 系统会: 标记任务 cancelled, 等待当前 cycle step 完成, 然后退出
4. 不会立即 kill 线程 (避免破坏数据)

---

## 8. FAQ

### Q1: 启动后浏览器没自动打开
**A**: 浏览器被禁用了。手动访问 `http://127.0.0.1:8765/`, 或用 `python launch_web.py --no-browser` 启动后手动访问。

### Q2: 端口 8765 被占用
**A**: 系统会自动扫描下一个空闲端口, 启动日志会显示实际端口。

### Q3: 连接 BRAIN 失败
**A**:
- 检查账户邮箱/密码是否正确
- 检查能否访问 `https://api.worldquantbrain.com/` (浏览器试试)
- 看右侧 error panel, 关注 "BRAIN 官方接口暂时不可用 (HTTP 5xx)" 是平台问题
- 看 401/403 → 凭据失效, 重新测试连接

### Q4: cycle 跑很慢
**A**: 正常, 单 cycle 5-15 分钟, 因为 BRAIN 平台限频 3 req/s + 本地预筛 + 池化。**不要调高 min_request_interval_seconds**, 会触发平台封号。

### Q5: 真实提交按钮是灰的
**A**: REAL_SUBMIT_DISABLED_WEB_FLOW=True, 默认禁用。这是有意设计, 防止误操作。如确需在测试环境提交, 设 `BRAIN_ALPHA_ENABLE_REAL_SUBMIT_TESTS=1`。

### Q6: 怎么导出候选列表
**A**: 左侧 "候选管理" → 右上 "导出 CSV" 按钮。

### Q7: 数据存在哪里
**A**:
- 运行时数据: `data/` 目录下
- 候选: `data/candidates.jsonl`
- lifecycle: `data/lifecycle.jsonl` (9.6MB)
- 事件流: `data/events.jsonl` (1GB+, 累计)
- 派生索引: `data/expression_index.sqlite`, `data/records_index.sqlite`

### Q8: 重置 / 清空数据
**A**: 停掉服务后, `rm -rf data/candidates.jsonl data/lifecycle.jsonl data/jobs_*.json` 即可。**注意**: 不要删 `data/official_*.json` (官方 context, 需 refresh 重新生成)。

### Q9: 怎么在多台机器同步数据
**A**: **当前版本不支持云端同步** (by design, account-safety-first)。多机部署需手动 rsync `data/` (排除 `events.jsonl` 因太大)。

### Q10: 远程访问怎么开
**A**:
```bash
export BRAIN_ALPHA_OPS_WEB_ALLOW_REMOTE=true
export BRAIN_ALPHA_OPS_WEB_ADMIN_TOKEN="$(openssl rand -hex 32)"
python launch_web.py --host 0.0.0.0
```
**注意**: 远程访问需额外加 nginx 反向代理 + HTTPS, **强烈建议生产用 nginx + Let's Encrypt**。

---

## 9. 故障排除

### 9.1 启动失败

| 症状 | 解决 |
|---|---|
| `ModuleNotFoundError: brain_alpha_ops` | 检查 `pip install -e .` 或 `pythonpath` 配置 |
| `Address already in use` | 自动选下一个端口; 或 `lsof -i :8765` 杀掉占用 |
| `Permission denied` | macOS/Linux: `chmod +x` 启动脚本; Windows: 管理员权限 |

### 9.2 连接 BRAIN 失败

| 症状 | 解决 |
|---|---|
| HTTP 401/403 | 凭据失效, 重新输入 |
| HTTP 5xx | BRAIN 平台问题, 等 5 分钟重试 |
| 网络超时 | 检查能否访问 `api.worldquantbrain.com` |
| `token=***` 出现在日志 | 不应该, 这是 bug, 请报 issue |

### 9.3 cycle 卡住

| 症状 | 解决 |
|---|---|
| 10+ 分钟无进度更新 | 检查 "Web 流程长时间没有明确进度" 是否触发 → 自动停止 |
| 任务显示 "stalled" | 看左侧 "任务监控" → 选 stalled 任务 → "重置" |
| 线程残留 | `ps aux | grep brain_alpha` → kill -9 |

### 9.4 数据问题

| 症状 | 解决 |
|---|---|
| 候选不显示 | 检查 `data/candidates.jsonl` 文件权限 |
| sqlite 索引慢 | 1GB+ events.jsonl 时正常, 启动会等 30s |
| 报告 PDF 失败 | 重新 "导出 PDF" 即可, 单次失败不阻塞 |

---

## 10. 快捷键 / 高级

### 10.1 键盘

| 快捷键 | 作用 |
|---|---|
| `Ctrl+R` / `Cmd+R` | 刷新当前面板 |
| `Esc` | 关闭弹窗 |
| `?` | 帮助 (内置) |

### 10.2 CLI 参数

```bash
python launch_web.py --help
```

| 参数 | 默认 | 说明 |
|---|---|---|
| `--port` | 8765 | 监听端口 |
| `--host` | 127.0.0.1 | 监听地址 (远程访问需 0.0.0.0 + ALLOW_REMOTE=true) |
| `--no-browser` | False | 启动不打开浏览器 |
| `--debug` | False | 启用 debug 日志 (生产勿用) |

---

## 11. 反馈与改进

- **项目所有者**: PAN
- **使用问题**: 看 `README.md` 故障排除段
- **架构问题**: 看 `docs/` 目录
- **Bug 报告**: 整理 `data/events.jsonl` 末尾 stack trace 后报

---

**版本**: v0.3.0 (2026-06-13)
**配套文档**: `DELIVERY_REPORT_FINAL_20260613.md`, `DEPLOYMENT_GUIDE_20260613.md`, `TEST_REPORT_20260613.md`
