# 2.3 前端重构设计文档

> **日期**: 2026-05-15  
> **当前状态**: 单文件 `index.html` 4432 行（CSS 970 + HTML 200 + JS 3200）  
> **目标**: 消除硬编码/重复逻辑，数据流单向化，模块化可维护

---

## 一、架构决策

### 1.1 技术约束

- 前端必须保持**零依赖运行**（不引入 React/Vue 框架）— 与 Windows .exe 打包兼容
- 可以在构建时使用**简单内联工具**将多个 JS 文件合并到 `index.html`
- 保持 Python stdlib `http.server` 作为唯一后端框架
- Chart.js CDN 保持（后续可考虑离线化）

### 1.2 模块化方案选择

| 方案 | 可行性 | 选择 |
|------|--------|------|
| React/Vue SPA | ❌ 破坏 .exe 打包 | — |
| ES Modules (`<script type="module">`) | ⚠ file:// 协议不可用 | — |
| IIFE 模式 + 构建内联 | ✅ | **选用** |
| 命名空间模式 + 构建内联 | ✅ | **选用** |

**最终方案**: IIFE + 命名空间模式。

- 开发时 `web/js/` 下维护独立 `.js` 文件
- 构建时 Python 脚本遍历 `<!-- inline:js/xxx.js -->` 标记，内联到 `index.html`
- 每个模块用 IIFE 包裹，通过全局 `App` 命名空间通信

### 1.3 数据流架构

```
用户交互 → View 层 (HTML/DOM)
                │
                ▼
          Action 函数 (api-client.js)
                │
                ▼
          API Response (JSON)
                │
                ▼
          AppState 更新 (state.js)  ← 单一数据源
                │
                ▼
          Render 层 (views/*.js)  ← 纯函数: state → DOM
```

**原则**:
- View 层**不直接**修改 DOM — 通过 `AppState.set()` 触发 `App.render()`
- Render 函数是**纯函数**: `(state, container) → void`
- API 调用统一通过 `apiClient` 层，内建错误处理和 CSRF

---

## 二、模块拆分

### 2.1 文件结构

```
brain_alpha_ops/web/
├── index.html                  # HTML 框架 + CSS + 内联标记
├── js/
│   ├── app.js                  # 初始化、事件绑定、render 调度
│   ├── api-client.js           # API 统一封装
│   ├── state.js                # AppState 管理
│   ├── utils.js                # 通用工具函数
│   ├── views/
│   │   ├── candidates.js       # 候选池视图 (candidates/waiting/backtesting)
│   │   ├── results.js          # 结果视图 (passed/submittable/submitted/failed/blocked)
│   │   ├── cloud.js            # 云端 Alpha 视图
│   │   ├── lifecycle.js        # 生命周期视图
│   │   ├── detail.js           # 详情弹窗 (通用 renderFieldTable)
│   │   ├── monitor.js          # 监控面板 (opsMonitor 瓦片)
│   │   └── charts.js           # Chart.js 图表
│   └── components/
│       ├── toast.js            # Toast 通知
│       ├── spinner.js          # 加载动画
│       ├── modal.js            # 弹窗/确认
│       ├── progress.js         # 进度条/ETA
│       └── table.js            # 通用表格渲染
├── build_inline.py             # 构建脚本：合并 JS 到 index.html
```

### 2.2 各模块职责

| 模块 | 行数估算 | 职责 |
|------|---------|------|
| `app.js` | ~150 | `App.init()`, `App.render()`, 事件绑定, 快捷键, 初始化顺序 |
| `api-client.js` | ~80 | `apiClient.get()`, `apiClient.post()`, 统一 error_code → toast 映射 |
| `state.js` | ~100 | `AppState` 类：`get/set/subscribe`，触发 render |
| `utils.js` | ~50 | `escapeHtml`, `phaseName` (临时保留→待迁移后端), `formatScore` 等 |
| `views/candidates.js` | ~150 | 候选池视图的行渲染 + 搜索过滤 |
| `views/results.js` | ~250 | passed/submittable/submitted/failed/blocked 视图（合并 4 个 row 函数） |
| `views/cloud.js` | ~80 | cloud_row + 统计面板 |
| `views/lifecycle.js` | ~60 | lifecycle_row |
| `views/detail.js` | ~150 | 通用 `renderFieldTable()` + 各详情页字段配置 |
| `views/monitor.js` | ~120 | 9 个监控瓦片（数据来自 state，不再自己计算） |
| `views/charts.js` | ~100 | Chart.js 封装 |
| `components/toast.js` | ~40 | Toast 通知 |
| `components/spinner.js` | ~20 | 加载动画 |
| `components/modal.js` | ~30 | 确认弹窗 |
| `components/progress.js` | ~60 | 通用进度条渲染 |
| `components/table.js` | ~80 | 通用表格（列定义驱动） |

---

## 三、状态管理设计

### 3.1 AppState 结构

```javascript
const AppState = {
  // 核心数据
  currentResult: {
    summary: {},
    candidates: [],
    passed_candidates: [],
    cloud_alphas: [],
    lifecycle_records: [],
    backtests: []
  },
  
  // 任务状态
  activeJobId: "",
  isRunning: false,
  
  // 视图
  activeView: "candidates",
  selected: {kind: "", id: ""},
  
  // 检查
  checkResults: {},            // alpha_id → CheckResult
  selectedSubmitIds: new Set(),
  
  // 提交
  submitInFlight: false,
  lastSubmitResults: [],
  lastSubmitPayload: null,
  
  // 同步
  syncInFlight: false,
  syncJobId: "",
  cloudSyncCountdownUntil: 0,
  
  // 进度
  liveProgress: {},
  
  // 配置（从 /api/config 加载）
  config: {
    autoSubmit: false,
    runForever: false,
    budget: {}
  },
  
  // 用户
  userProfile: {tier: "--", level: null, points: null, username: ""},
  
  // 渲染控制
  maxRenderedRows: 300
};
```

### 3.2 状态更新触发渲染

```javascript
// state.js
class AppStateManager {
  constructor() {
    this._state = initialAppState();
    this._listeners = [];
  }
  
  get(path) {
    return path.split('.').reduce((obj, key) => obj?.[key], this._state);
  }
  
  set(path, value) {
    const keys = path.split('.');
    const last = keys.pop();
    const target = keys.reduce((obj, key) => {
      if (!obj[key]) obj[key] = {};
      return obj[key];
    }, this._state);
    target[last] = value;
    this._notify(path);
  }
  
  merge(path, partial) {
    const current = this.get(path) || {};
    this.set(path, {...current, ...partial});
  }
  
  onUpdate(callback) {
    this._listeners.push(callback);
  }
  
  _notify(path) {
    this._listeners.forEach(fn => fn(path, this._state));
  }
}

// 单一全局实例
window.App = new AppStateManager();
```

### 3.3 Render 调度

```javascript
// app.js
App.onUpdate((path, _state) => {
  // 只渲染受影响的视图
  if (path.startsWith('currentResult') || path === 'activeView') {
    renderCurrentView();
    renderInsight();
  }
  if (path.startsWith('liveProgress')) {
    renderOpsMonitor();
  }
  if (path.startsWith('checkResults')) {
    renderModuleActions();
  }
});

// 手动触发全量渲染（初始化时）
App.renderAll = () => {
  renderCurrentView();
  renderInsight();
  renderOpsMonitor();
  renderCharts();
  renderModuleActions();
};
```

---

## 四、API 客户端层

### 4.1 统一封装

```javascript
// api-client.js
const CSRF_TOKEN = "__BRAIN_ALPHA_OPS_CSRF_TOKEN__";

function apiUrl(path) {
  const url = new URL(path, window.location.origin);
  url.searchParams.set("csrf_token", CSRF_TOKEN);
  return `${url.pathname}${url.search}`;
}

async function apiFetch(path, options = {}) {
  try {
    const response = await fetch(apiUrl(path), {
      ...options,
      headers: {
        ...(options.headers || {}),
        "X-Brain-Alpha-CSRF": CSRF_TOKEN
      }
    });
    const data = await response.json();
    
    if (!data.ok) {
      const errorCode = data.error_code || "UNKNOWN";
      const message = data.error || errorMessages[errorCode] || "操作失败";
      throw new ApiError(message, errorCode, data);
    }
    
    return data;
  } catch (e) {
    if (e instanceof ApiError) throw e;
    throw new ApiError("网络连接失败，请检查服务是否运行", "NETWORK_ERROR");
  }
}

const apiClient = {
  get: (path) => apiFetch(path),
  post: (path, body) => apiFetch(path, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(body)
  })
};

// 错误码 → 用户消息映射
const errorMessages = {
  SESSION_INVALID: "会话已过期，请刷新页面。",
  ORIGIN_FORBIDDEN: "仅允许本地访问。",
  JOB_NOT_FOUND: "任务不存在或已过期。",
  CONFLICT_RUNNING: "已有任务在运行，请先停止。",
  CONFLICT_AUX_OP: "请等待当前操作完成后再试。",
  VALIDATION_ERROR: "参数错误，请检查输入。",
  AUTH_FAILED: "BRAIN API 认证失败，请检查凭据。",
  SUBMIT_BLOCKED: "提交被安全门禁阻断。",
  MISSING_OFFICIAL_ID: "缺少官方 Alpha ID，请先运行官方模拟。",
  INTERNAL_ERROR: "服务内部错误，请查看日志。",
  NETWORK_ERROR: "网络连接失败，请检查服务是否运行。",
};
```

### 4.2 操作函数迁移

所有现有的 `fetch(/api/xxx)` 调用替换为 `apiClient.get/post()`，统一约 15 处调用点。

---

## 五、消除重复代码

### 5.1 通用表格渲染 (components/table.js)

```javascript
// 列定义驱动
function renderTable(container, columns, rows, options = {}) {
  const {sortKey, maxRows = 300, emptyText = "暂无数据"} = options;
  
  if (!rows.length) {
    container.innerHTML = `<tr><td colspan="${columns.length}">${emptyText}</td></tr>`;
    return;
  }
  
  const displayRows = rows.slice(0, maxRows);
  
  container.innerHTML = displayRows.map((row, idx) => {
    const cells = columns.map(col => {
      const value = typeof col.accessor === 'function' 
        ? col.accessor(row, idx) 
        : row[col.accessor];
      return `<td class="${col.className || ''}">${col.render ? col.render(value, row) : escapeHtml(String(value ?? ''))}</td>`;
    }).join('');
    return `<tr data-kind="${row.kind || ''}" data-id="${row.id || ''}">${cells}</tr>`;
  }).join('');
}
```

### 5.2 详情弹窗通用化 (views/detail.js)

```javascript
function renderFieldTable(container, title, fields) {
  // fields = [{label, value, format: 'text'|'number'|'badge'|'json'|'score', className}]
  const rows = fields.map(f => `
    <tr>
      <td class="detail-label">${escapeHtml(f.label)}</td>
      <td class="detail-value ${f.className || ''}">${formatField(f)}</td>
    </tr>
  `).join('');
  
  container.innerHTML = `
    <h3>${escapeHtml(title)}</h3>
    <table class="detail-table">${rows}</table>
  `;
}

function formatField(field) {
  switch (field.format) {
    case 'badge': return renderBadge(field.value);
    case 'json': return `<pre>${escapeHtml(JSON.stringify(field.value, null, 2))}</pre>`;
    case 'score': return renderScore(field.value);
    default: return escapeHtml(String(field.value ?? '-'));
  }
}
```

### 5.3 视图合并

当前 6 个 row 渲染函数 → 合并为 3 个：

| 原函数 | 合并后 | 说明 |
|--------|--------|------|
| `candidateRow()` | `views/candidates.js` | 候选池专用（含操作按钮） |
| `passedRow()` + `submittableRow()` | `views/results.js` — `resultRow()` | 核心相同，仅操作按钮/勾选框不同 |
| `cloudRow()` | `views/cloud.js` | 云端专用 |
| `lifecycleRow()` | `views/lifecycle.js` | 生命周期专用 |
| `backtestSlotRow()` | 合并到 `views/monitor.js` | 回测槽在监控面板中 |

---

## 六、前端类型标注（JSDoc）

由于不引入 TypeScript，使用 JSDoc 标注关键类型：

```javascript
/**
 * @typedef {Object} Candidate
 * @property {string} alpha_id
 * @property {string} expression
 * @property {string} family
 * @property {string} lifecycle_status
 * @property {Object} scorecard
 * @property {number} scorecard.total_score
 */

/**
 * @typedef {"candidates"|"waiting"|"backtesting"|"passed"|"submittable"|"submitted"|"failed"|"cloud"|"lifecycle"|"stats"} ViewKind
 */

/**
 * @typedef {Object} CheckResult
 * @property {string} alpha_id
 * @property {boolean} passed
 * @property {boolean} submittable
 * @property {boolean} is_stale
 * @property {Array<{name: string, label_cn: string, passed: boolean, detail: string}>} checks
 */
```

---

## 七、构建流程

### build_inline.py

```python
"""将 web/js/ 下的模块内联到 index.html"""
import re
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parent / "brain_alpha_ops" / "web"
HTML_PATH = WEB_DIR / "index.html"
TEMPLATE_PATH = WEB_DIR / "index_template.html"

def build():
    html = TEMPLATE_PATH.read_text(encoding="utf-8")
    
    # 处理 <!-- inline:js/xxx.js --> 标记
    def replace_inline(match):
        js_path = WEB_DIR / match.group(1)
        if js_path.exists():
            return f"<script>\n{js_path.read_text(encoding='utf-8')}\n</script>"
        return match.group(0)
    
    html = re.sub(r'<!--\s*inline:(js/.+?\.js)\s*-->', replace_inline, html)
    HTML_PATH.write_text(html, encoding="utf-8")
    print(f"Built {HTML_PATH} ({len(html)} bytes)")

if __name__ == "__main__":
    build()
```

---

## 八、实施优先级

| 优先级 | 模块 | 原因 |
|--------|------|------|
| **P0** | `api-client.js` | 所有 API 调用的基础，优先统一 |
| **P0** | `state.js` | 数据流基础，后续所有重构依赖 |
| **P0** | `app.js` | 初始化 + render 调度 |
| **P0** | `views/results.js` | 包含 BLOCKED 修复、批量提交失败渲染 |
| **P1** | `views/detail.js` | 通用化详情弹窗 |
| **P1** | `components/table.js` | 通用化表格渲染 |
| **P1** | `components/progress.js` | 消除 3 段重复进度条 |
| **P1** | `views/monitor.js` | 监控瓦片改造 |
| **P2** | `utils.js` + 后端迁移 | phaseName 等迁移到后端后删除 |
| **P2** | JSDoc 类型标注 | 渐进添加 |
| **P2** | `build_inline.py` | 构建工具 |

---

## 九、兼容性

| 约束 | 保障 |
|------|------|
| `.exe` 打包 | `build_inline.py` 在 `pyinstaller` 前运行，产物仍是单文件 `index.html` |
| Chart.js CDN | 保持 `<script src="...">` 外链 |
| Iconify CDN | 保持外链 |
| 后向兼容 | 重构期间保留 `index_backup_*.html` |
