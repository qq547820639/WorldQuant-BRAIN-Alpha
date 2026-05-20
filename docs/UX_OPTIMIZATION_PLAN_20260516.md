# 用户体验优化方案与实施计划

> **评估日期**: 2026-05-16  
> **评估对象**: `brain_alpha_ops/web.py` (后端) + `brain_alpha_ops/web/` (前端) + 用户交互全链路

---

## 1. UX 现状诊断

### 1.1 交互流程评分

| 流程阶段 | 当前状态 | 评分 |
|----------|---------|:----:|
| 系统启动 | `launch_web.py` → 自动打开浏览器 → 登录页 | 4/5 |
| 认证流程 | Session + CSRF 双因子，凭据环境变量注入 | 4/5 |
| 配置加载 | 预设选择 + 自定义 JSON 编辑 | 3/5 |
| 运行控制 | 启动/停止按钮，参数面板 | 3/5 |
| 进度监控 | SSE 流式推送（有 JS 语法错误） | 1/5 |
| 结果查看 | 表格 + charts + detail 面板 | 3/5 |
| 错误处理 | text 显示，无操作建议 | 2/5 |
| 历史回溯 | 无显式入口 | 1/5 |

**综合 UX 评分**: **2.6/5** (受 P0 阻断缺陷严重影响)

### 1.2 关键缺陷诊断

#### 🔴 P0-1: SSE 进度反馈断裂

**位置**: `brain_alpha_ops/web/index.html` → `waitForJobSSE()` 函数  
**原因**: 回调函数体内使用了 `await`，但外层函数未声明为 `async`  
**影响**: Web 控制台无法获取实时进度更新，用户看到的是静态页面

```javascript
// 当前错误代码 (简化):
function waitForJobSSE(jobId) {
  fetch(`/api/job/${jobId}/stream`).then(response => {
    const reader = response.body.getReader();
    pump(reader);
  });
  
  function pump(reader) {
    reader.read().then(({done, value}) => {
      // ...
      const data = JSON.parse(value);
      await updateUI(data);  // ❌ SyntaxError: await in non-async function
    });
  }
}

// 修复:
function waitForJobSSE(jobId) {
  fetch(`/api/job/${jobId}/stream`).then(response => {
    const reader = response.body.getReader();
    pump(reader);
  });
  
  async function pump(reader) {  // ✅ 声明为 async
    const {done, value} = await reader.read();
    // ...
    const data = JSON.parse(value);
    await updateUI(data);  // ✅ 合法
  }
}
```

#### 🔴 P0-5: BLOCKED 状态不可见

**位置**: 前端 `submittableCandidates()` 过滤逻辑  
**原因**: 后端返回的 `gate.status` 中存在 `BLOCKED` 状态，但前端过滤逻辑仅处理 `SUBMISSION_READY` / `NEEDS_ITERATION`  
**影响**: 用户无法看到被阻断的候选 Alpha，无法诊断阻断原因

#### 🟡 P1-2: checkName 映射不完整

**位置**: 前端 `humanCheckName()` 函数  
**原因**: 硬编码了 8 个检查名称的中文映射，但后端实际有 25+ 个检查项  
**影响**: 新增检查项在前端显示为原始英文名，可读性差

#### 🟡 P2-5: 前端代码结构混乱

**位置**: `brain_alpha_ops/web/index.html` (~4400 行单文件)  
**问题**:
- 54 个全局 `let` 变量散布在单文件中
- 前端业务逻辑 (phaseName/humanCheckName/submittableCandidates) 耦合在 UI 渲染中
- 缺少模块化（虽然 `js/` 目录已拆分，但 `index.html` 内仍有大量内联脚本）

---

## 2. 优化方案

### 2.1 Phase 1: 紧急修复 (1-2 天) — 恢复基本可用性

| ID | 修复内容 | 文件 | 优先级 |
|----|---------|------|:------:|
| F-1 | 修复 `waitForJobSSE` 中 `await` 语法错误 | `web/index.html` | 🔴 P0 |
| F-2 | 补充 BLOCKED 状态的前端展示 | `web/index.html` + `js/views/detail.js` | 🔴 P0 |
| F-3 | 修复 `submittableCandidates()` 过滤逻辑 | `web/js/app.js` | 🔴 P0 |
| F-4 | 补充 5 个缺失的 UI 图标 | `web/index.html` | 🔴 P0 |

### 2.2 Phase 2: 契约对齐 (3-4 天) — 前后端职责分离

| ID | 修复内容 | 文件 | 优先级 |
|----|---------|------|:------:|
| C-1 | 将 `phaseName()` 从 JS 迁移到后端 API 响应 (`progress.phase_label`) | `web.py` + `web/index.html` | 🟡 P1 |
| C-2 | 将 `humanCheckName()` 从 JS 迁移到后端 (`check.label_cn`) | `web.py` + `web/js/views/detail.js` | 🟡 P1 |
| C-3 | checkResult 添加 `suggestion` 字段 (修复建议) | `alpha_checks.py` | 🟡 P1 |
| C-4 | API 响应结构版本化 (`api_version: "v2.0"`) | `web.py` | 🟡 P1 |
| C-5 | 补充 `/api/health` 健康检查路由 | `web.py` | 🟡 P1 |
| C-6 | 补充 `/api/shutdown` 优雅关闭路由 | `web.py` | 🟡 P1 |

### 2.3 Phase 3: 体验升级 (持续) — 交互优化

| ID | 改进内容 | 说明 |
|----|---------|------|
| E-1 | 进度条从文本 → 可视化进度条组件 | 用 `components/progress.js` |
| E-2 | 错误消息添加彩色标签 + 可折叠详情 | Error/Warning/Info 三级 |
| E-3 | 结果展示: JSON dump → 图表可视化 | Sharpe 直方图 / Turnover 散点图 |
| E-4 | 添加"断点续跑"UI 入口 | 基于 `lifecycle.jsonl` 恢复 |
| E-5 | 参数保存/加载面板 | 预设配置可视化切换 |
| E-6 | 运行历史浏览器 | 按 run_id 筛选 + 时间线 |
| E-7 | 暗色模式 | CSS 变量方案 |

---

## 3. API 路由覆盖现状

### 3.1 后端 22 路由 → 前端 UI 映射

| 路由 | 后端状态 | 前端 UI | 覆盖 |
|------|:------:|---------|:------:|
| `GET /` | ✅ | ✅ 主面板 | 完整 |
| `GET /api/session` | ✅ | ✅ 登录页 | 完整 |
| `POST /api/session` | ✅ | ✅ 登录页 | 完整 |
| `DELETE /api/session` | ✅ | ✅ 登出按钮 | 完整 |
| `GET /api/health` | ❌ 缺失 | ❌ | 缺失 |
| `GET /api/config` | ✅ | ✅ 配置面板 | 完整 |
| `POST /api/config` | ✅ | ✅ 配置编辑 | 完整 |
| `GET /api/presets` | ✅ | ✅ 预设列表 | 完整 |
| `GET /api/context` | ✅ | ⚠️ 仅显示字段数 | 部分 |
| `POST /api/context/refresh` | ✅ | ✅ 刷新按钮 | 完整 |
| `POST /api/run` | ✅ | ✅ 运行按钮 | 完整 |
| `POST /api/stop` | ✅ | ✅ 停止按钮 | 完整 |
| `GET /api/job/{id}` | ✅ | ✅ 进度条 | 完整 |
| `GET /api/job/{id}/stream` | ✅ | ❌ SSE 语法错误 | 断裂 |
| `GET /api/candidates` | ✅ | ✅ 候选列表 | 完整 |
| `GET /api/candidates/{id}` | ✅ | ✅ 详情面板 | 完整 |
| `POST /api/candidates/batch-check` | ✅ | ✅ 批量检查按钮 | 完整 |
| `POST /api/submit` | ✅ | ⚠️ 无确认弹窗 | 部分 |
| `POST /api/submit_batch` | ✅ | ❌ 无结果展示 | 缺失 |
| `GET /api/ledger` | ✅ | ⚠️ 无 UI | 部分 |
| `GET /api/cloud_alphas` | ✅ | ⚠️ 无 UI | 部分 |
| `POST /api/logout` | ❌ 缺失 | ❌ | 缺失 |

### 3.2 缺失 UI 元素

| 元素 | 数量 | 说明 |
|------|:----:|------|
| 缺失图标 | 5 | health/shutdown/history/export/filter |
| 缺失按钮 | 5 | 断点续跑/导出CSV/历史回溯/筛选/暗色模式 |
| 缺失下拉 | 1 | 运行历史选择器 |
| 缺失状态标签 | 4 | BLOCKED/WAITING/DEFERRED/CANCELLED |

---

## 4. 实施路线图

```
Week 1 (5/17 - 5/23) — Phase 1 紧急修复
  ├── Day 1: F-1 (SSE await 修复)
  ├── Day 2: F-2 (BLOCKED 状态展示) + F-3 (过滤逻辑)
  ├── Day 3: F-4 (缺失图标)
  └── Day 4-5: 回归测试 + 验证

Week 2 (5/24 - 5/30) — Phase 2 契约对齐
  ├── Day 1-2: C-1 (phaseName 迁移) + C-2 (humanCheckName 迁移)
  ├── Day 3: C-3 (suggestion 字段) + C-4 (API 版本化)
  └── Day 4-5: C-5 (health) + C-6 (shutdown)

Week 3+ (持续) — Phase 3 体验升级
  ├── E-1 (可视化进度) + E-2 (错误标签)
  ├── E-3 (图表) + E-4 (断点续跑)
  ├── E-5 (参数面板) + E-6 (历史浏览器)
  └── E-7 (暗色模式)
```

---

## 5. 验收标准

| 阶段 | 验收条件 |
|------|---------|
| Phase 1 | SSE 进度推送正常工作；BLOCKED 状态在 UI 上可见且可展开；所有 API 路由有对应 UI |
| Phase 2 | `phaseName`/`humanCheckName` 由后端提供；`suggestion` 字段在错误展示中出现；`/api/health` 返回 200 |
| Phase 3 | 进度条可视化；错误有颜色区分 + 折叠；Sharpe 分布图可交互；断点续跑入口可用 |

---

> 当前最紧急的修复是 **P0-1 (SSE await 语法)** 和 **P0-5 (BLOCKED 状态)**, 修复后 Web 控制台可恢复基本可用性。
