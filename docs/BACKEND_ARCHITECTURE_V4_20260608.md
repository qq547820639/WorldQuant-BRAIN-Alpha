# BRAIN Alpha Ops — 后端架构重构 v4.0

> **架构师**：Backend Architect
> **日期**：2026-06-08
> **范围**：模块重组、共享内核、Phase 感知进度、API 契约重定义、WebSocket 基础、Sync 超时修复

---

## 目录

1. [执行摘要](#1-执行摘要)
2. [当前架构评估](#2-当前架构评估)
3. [目标模块结构](#3-目标模块结构)
4. [共享内核实现](#4-共享内核实现)
5. [Phase 感知进度系统](#5-phase-感知进度系统)
6. [API 契约重定义](#6-api-契约重定义)
7. [WebSocket 基础](#7-websocket-基础)
8. [Sync 超时修复](#8-sync-超时修复)
9. [实施计划](#9-实施计划)

---

## 1. 执行摘要

当前后端是模块化单体，252 个 Python 文件。前端已升级至 v3.0（4 阶段导航），后端需要在以下维度对齐：

### 四个战场

| 战场 | 当前问题 | 目标 |
|------|----------|------|
| **模块组织** | 95 个顶层 .py 文件扁平散落 | 按 bounded context 分层目录 |
| **契约抽象** | 各层直接 import 具体实现 | Protocol 接口 + DI |
| **进度系统** | 作业级 progress dictionary | Phase 感知、stall 检测、elapsed 计时 |
| **实时通信** | SSE + 2s 轮询 | WebSocket 基础（v4.1 切换） |

### 向后兼容承诺

- 所有现有 `GET/POST` 路由 **URL 和响应格式不变**
- 新增 `GET /api/phase_state` 端点供前端 PhaseShell 消费
- 新增 `GET /api/connection_status` 端点替代隐式检测
- WebSocket 路径 `ws://localhost:8765/ws` 作为可选升级

---

## 2. 当前架构评估

### 2.1 模块依赖热力图

```
web_handler_dispatch ──► web_dispatch_context (7 子上下文)
                       ──► research/ (pipeline, generator...)
                       ──► config (config, config_models...)
                       ──► brain_api (base, official...)
                       ──► web_* (50+ 模块)

web_runtime_facade ────► web (直接引用 web 模块实例)
                       ──► 所有子模块通过 web.xxx 间接访问
```

**核心问题**：`web_handler_dispatch` 是上帝模块 — 它依赖几乎所有东西。

### 2.2 当前耦合点

| 耦合点 | 严重度 | 影响 |
|--------|--------|------|
| handler_dispatch → 7 个子上下文 | 中 | 修改一个子上下文就需重编译 handler_dispatch |
| web_runtime_facade → web 实例 | 高 | 所有 DI 通过 web 实例传递，形成胖上下文 |
| pipeline.py → research/* 所有模块 | 中 | pipeline 是编排器，耦合业务合理 |
| web_sync_job → brain_api + config | 低 | 边界清晰 |

### 2.3 需要新增的能力

| 能力 | 前端依赖 | 后端缺失 |
|------|----------|----------|
| Phase 状态查询 | `usePhaseState` hook | `GET /api/phase_state` 端点 |
| 连接状态独立 | TopBar 分离显示 | `GET /api/connection_status` |
| Stall 检测 | ProgressFeedback >10s | 后端 elapsed 时间戳 |
| WebSocket 升级 | 实时进度推送 | 无 WebSocket 处理器 |

---

## 3. 目标模块结构

### 3.1 目录重组

```
brain_alpha_ops/
├── __init__.py                      # 公开 API（不变）
│
├── shared/                          # 共享内核（NEW）
│   ├── __init__.py
│   ├── types.py                     # Candidate, PipelineEvent, PipelineResult
│   ├── errors.py                    # DomainError 类族
│   ├── ids.py                       # AlphaId, JobId 值对象
│   └── contracts.py                 # Protocol 接口（NEW）
│
├── config/                          # 配置域（NEW 子包）
│   ├── __init__.py
│   ├── models.py                    # ← config_models.py
│   ├── schema.py                    # ← config_schema.py
│   ├── loader.py                    # ← config.py (load_run_config)
│   ├── update.py                    # ← config_update.py
│   ├── validation.py                # ← config_domain_validation + type_validation
│   └── helpers.py                   # ← config_validation_helpers
│
├── brain_api/                       # BRAIN API 防腐蚀层（不变）
│   └── (现有文件)
│
├── data/                            # 数据持久化域（NEW 子包）
│   ├── __init__.py
│   ├── cloud_cache.py               # Cloud Alpha 快照缓存
│   ├── candidate_store.py           # Candidate JSON 持久化
│   ├── checkpoint.py                # 检查点管理
│   ├── repository.py                # ResearchRepository
│   └── sqlite_index.py              # SQLite 索引
│
├── research/                        # 研究流水线（近一步拆分子包）
│   ├── (现有文件重组到子目录)
│   ├── generator/
│   ├── scoring/
│   ├── backtest/
│   └── simulation/
│
├── web/                             # Web API 层（NEW 子包）
│   ├── __init__.py
│   ├── server.py                    # HTTP 服务器 + WebSocket
│   ├── routes.py                    # 路由注册
│   ├── handlers/                    # 按资源拆分（NEW）
│   │   ├── __init__.py
│   │   ├── auth.py                  # 连接测试 + 状态
│   │   ├── sync.py                  # 云端同步
│   │   ├── candidates.py            # 候选 CRUD
│   │   ├── scoring.py               # 评分路由
│   │   ├── checks.py                # 批量检查
│   │   ├── submission.py            # 提交审核
│   │   ├── config.py                # 配置路由
│   │   ├── phase.py                 # Phase 状态（NEW）
│   │   └── snapshots.py             # 快照/仪表盘
│   ├── middleware/                   # 中间件（NEW）
│   │   ├── __init__.py
│   │   ├── session.py
│   │   ├── csrf.py
│   │   └── rate_limit.py
│   ├── sse.py                       # SSE handler
│   ├── ws.py                        # WebSocket handler（NEW）
│   ├── jobs.py                      # 异步作业管理
│   └── progress.py                  # 统一进度 + Phase 感知（增强）
│
├── ux/                              # UX 辅助（不变）
└── agents/                          # Agent 工具（不变）
```

### 3.2 迁移清单

按优先级排序，每个迁移独立可测：

| 优先级 | 迁移项 | 文件数 | 风险 | 预计工时 |
|--------|--------|--------|------|----------|
| **1** | 创建 `shared/` 包（types, errors, contracts） | 3 | 低 | 2h |
| **2** | 创建 `web/handlers/phase.py`（新端点） | 1 | 低 | 1h |
| **3** | 增强 `web/progress.py`（stall + elapsed） | 1 | 低 | 1h |
| **4** | 修复 `web_sync_job.py`（timeout 处理） | 1 | 中 | 2h |
| **5** | 创建 `web/ws.py`（WebSocket 基础） | 1 | 中 | 3h |
| **6** | 创建 `web/middleware/` 子包 | 4 | 低 | 3h |
| **7** | 创建 `web/handlers/` 子包（重组路由） | 8 | 中 | 5h |
| **8** | 创建 `config/` 子包 | 5 | 低 | 3h |
| **9** | 创建 `data/` 子包 | 4 | 低 | 2h |

---

## 4. 共享内核实现

### 4.1 `brain_alpha_ops/shared/__init__.py`

```python
"""Shared kernel types, errors, and contracts."""
from brain_alpha_ops.shared.types import Candidate, PipelineEvent, PipelineResult
from brain_alpha_ops.shared.errors import (
    DomainError, ValidationError, TimeoutError,
    ConnectionError, SyncError, SubmissionError
)
from brain_alpha_ops.shared.ids import AlphaId, JobId, new_id
```

### 4.2 `brain_alpha_ops/shared/contracts.py`

```python
"""Cross-context service contracts using typing.Protocol."""

from __future__ import annotations
from typing import Any, Protocol, runtime_checkable

from brain_alpha_ops.shared.types import Candidate


# ── Progress Reporting ──────────────────────────────────────

@runtime_checkable
class ProgressReporter(Protocol):
    """Callback for reporting job progress from research/web to UI."""

    def report(
        self,
        phase: str,
        message: str,
        *,
        percent: float | None = None,
        scanned: int = 0,
        total: int = 0,
        elapsed_seconds: float = 0,
        eta_seconds: float | None = None,
    ) -> None: ...

    def is_cancelled(self) -> bool: ...


# ── Candidate Repository ────────────────────────────────────

@runtime_checkable
class CandidateRepository(Protocol):
    """Persistence interface for Candidate entities."""

    def find_by_id(self, alpha_id: str) -> Candidate | None: ...
    def find_by_family(self, family: str) -> list[Candidate]: ...
    def save(self, candidate: Candidate) -> None: ...
    def list_all(self, *, limit: int = 100, offset: int = 0) -> list[Candidate]: ...
    def count(self) -> int: ...


# ── BRAIN API Client ────────────────────────────────────────

@runtime_checkable
class BrainAPIClient(Protocol):
    """Interface to the official WorldQuant BRAIN API."""

    def authenticate(self) -> None: ...
    def list_user_alphas(
        self,
        range_spec: str,
        *,
        progress_callback: Any = None,
    ) -> list[dict[str, Any]]: ...
    def list_fields(
        self,
        scope: str,
        region: str,
        *,
        progress_callback: Any = None,
    ) -> list[dict[str, Any]]: ...
    def list_operators(
        self,
        scope: str,
        *,
        progress_callback: Any = None,
    ) -> list[dict[str, Any]]: ...
    def submit_validation(
        self,
        expression: str,
        settings: dict[str, Any],
    ) -> str: ...
    def poll_validation(self, validation_id: str) -> dict[str, Any]: ...
    def submit_simulation(
        self,
        expression: str,
        settings: dict[str, Any],
    ) -> str: ...
    def poll_simulation(self, simulation_id: str) -> dict[str, Any]: ...


# ── Phase State Provider ────────────────────────────────────

@runtime_checkable
class PhaseStateProvider(Protocol):
    """Provides phase progression state for the frontend PhaseShell."""

    def get_phase_state(self) -> dict[str, Any]:
        """
        Returns:
            {
                "current_phase": "connect",
                "connected": true,
                "context_fresh": false,
                "candidates_count": 0,
                "scored_count": 0,
                "readiness_passed": false,
                "sync_in_progress": false,
                "sync_scanned": 0,
                "sync_total": 0,
                "sync_elapsed_seconds": 0,
                "sync_stalled": false,
            }
        """
        ...


# ── Event Publisher ─────────────────────────────────────────

@runtime_checkable
class EventPublisher(Protocol):
    """Publishes domain events for cross-context communication (v4.1)."""

    def publish(self, event_type: str, payload: dict[str, Any]) -> None: ...
    def subscribe(self, event_type: str, handler: Any) -> None: ...
```

### 4.3 迁移步骤

从 `brain_alpha_ops/models.py` 到 `brain_alpha_ops/shared/types.py`：

1. 复制文件内容，保持接口不变
2. 在 `brain_alpha_ops/models.py` 中添加重导出：
   ```python
   from brain_alpha_ops.shared.types import *  # noqa: F401, F403
   ```
3. 逐步迁移所有 `from brain_alpha_ops.models import ...` 到 `from brain_alpha_ops.shared import ...`
4. 全部迁移完成后删除重导出

---

## 5. Phase 感知进度系统

### 5.1 端点设计

```
GET /api/phase_state
Response:
{
  "ok": true,
  "current_phase": "connect",       // PhaseId: connect|discover|evaluate|ready
  "connected": true,
  "context_fresh": false,
  "candidates_count": 0,
  "scored_count": 0,
  "readiness_passed": false,
  "sync": {
    "in_progress": false,
    "scanned": 0,
    "total": 0,
    "elapsed_seconds": 0,
    "stalled": false             // >10s no progress during SCAN
  },
  "connection": {
    "status": "connected",       // disconnected|testing|connected
    "last_tested_at": "2026-06-08T14:30:00Z",
    "credential_source": "page"  // page|managed
  },
  "readiness": {
    "eligible_count": 0,
    "ready": false
  }
}
```

### 5.2 实现

```python
# brain_alpha_ops/web/handlers/phase.py

def phase_state_payload(
    *,
    sync_jobs: "JobStoreLike",
    candidate_repo: "CandidateRepository",
    connection_tracker: "ConnectionTracker",
    readiness_service: Any,
) -> dict[str, Any]:
    """Build phase state payload for frontend PhaseShell/usePhaseState."""

    # Determine connection state
    connected = connection_tracker.is_connected()
    connection_status = connection_tracker.status

    # Determine sync progress
    active_sync = sync_jobs.latest_active()
    sync_in_progress = bool(active_sync)
    sync_data: dict[str, Any] = {
        "in_progress": False,
        "scanned": 0,
        "total": 0,
        "elapsed_seconds": 0,
        "stalled": False,
    }
    if active_sync:
        _, job = active_sync
        progress = job.get("progress", {})
        scanned = int(progress.get("scanned", 0) or 0)
        total = int(progress.get("total", 0) or 0)
        elapsed = float(progress.get("elapsed_seconds", 0) or 0)
        phase = str(progress.get("phase", ""))
        stalled = (
            phase == "scan"
            and scanned == 0
            and elapsed > 10
        )
        sync_data = {
            "in_progress": True,
            "scanned": scanned,
            "total": total,
            "elapsed_seconds": elapsed,
            "stalled": stalled,
        }

    # Determine context freshness
    # Context is "fresh" if cloud sync completed at least once
    latest_completed = next(
        (j for j_id, j in sync_jobs.list_all()
         if j.get("status") in ("completed", "completed_with_warnings")),
        None,
    )
    context_fresh = bool(latest_completed)

    # Count candidates
    candidates_count = candidate_repo.count()
    scored_count = _count_scored(candidate_repo)

    # Check readiness
    readiness = readiness_service.get_readiness()
    readiness_passed = bool(readiness.get("ready_to_submit"))

    # Determine current phase
    if not connected or not context_fresh:
        current_phase = "connect"
    elif candidates_count == 0:
        current_phase = "discover"
    elif not readiness_passed:
        current_phase = "evaluate"
    else:
        current_phase = "ready"

    return {
        "ok": True,
        "current_phase": current_phase,
        "connected": connected,
        "context_fresh": context_fresh,
        "candidates_count": candidates_count,
        "scored_count": scored_count,
        "readiness_passed": readiness_passed,
        "sync": sync_data,
        "connection": {
            "status": connection_status,
            "last_tested_at": connection_tracker.last_tested_at.isoformat()
                if connection_tracker.last_tested_at else None,
            "credential_source": "page" if connection_tracker.uses_page_credentials else "managed",
        },
        "readiness": {
            "eligible_count": readiness.get("eligible_count", 0),
            "ready": readiness_passed,
        },
    }


def _count_scored(repo) -> int:
    """Count candidates with non-null scorecard."""
    try:
        return sum(
            1 for c in repo.list_all(limit=1000)
            if c.scorecard and c.scorecard.get("total_score") is not None
        )
    except Exception:
        return 0
```

### 5.3 前端集成

前端 `usePhaseState` hook 改为调用 `/api/phase_state` 获取实时 Phase 状态，通过 SSE 或轮询更新。

---

## 6. API 契约重定义

### 6.1 新增端点

| 方法 | 路径 | 用途 | 消费端 |
|------|------|------|--------|
| `GET` | `/api/phase_state` | Phase 状态全量快照 | PhaseShell, MobileTabBar |
| `GET` | `/api/connection_status` | 连接状态 + 凭据来源 | TopBar |
| `GET` | `/api/phase_state?stream=1` | Phase 状态 SSE 流 | usePhaseState (实时) |

### 6.2 增强端点

| 端点 | 增强内容 |
|------|----------|
| `GET /api/sync_status` | + `elapsed_seconds`, `stalled` 字段 |
| `POST /api/sync_alphas` | + `syncRange` 默认支持 `1d/3d/7d` |
| `POST /api/sync_cancel` | + 取消确认消息更详细 |
| `GET /api/status` | + `connection` 子对象 |

### 6.3 状态码规范

所有端点返回统一结构：

```python
# Success
{"ok": True, "data": {...}}

# Error
{
    "ok": False,
    "error_code": "SYNC_TIMEOUT",    # 机器可读
    "error": "云端同步超时，请重试。", # 用户可读
    "recovery": {                     # 恢复选项（NEW）
        "retry": True,
        "retry_label": "重试",
        "alternatives": [
            {"action": "shrink_range", "label": "缩小范围(1d)"},
            {"action": "use_default_context", "label": "使用默认上下文"},
        ],
    },
    "error_id": "err_abc123",        # 追踪 ID
}
```

---

## 7. WebSocket 基础

### 7.1 连接协议

```
ws://localhost:8765/ws
```

### 7.2 消息格式

```python
# Client → Server
{
    "type": "subscribe",
    "channel": "sync_progress",  # or "phase_state", "job_status"
    "job_id": "job_abc123"       # optional filter
}

{
    "type": "unsubscribe",
    "channel": "sync_progress"
}

# Server → Client
{
    "type": "sync_progress",
    "data": {
        "phase": "scan",
        "scanned": 15234,
        "total": 25549,
        "elapsed_seconds": 42.3,
        "eta_seconds": 28.5,
        "stalled": false
    },
    "timestamp": "2026-06-08T14:30:00Z"
}
```

### 7.3 实现骨架

```python
# brain_alpha_ops/web/ws.py

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler
from typing import Any

logger = logging.getLogger(__name__)

class WebSocketManager:
    """Manages WebSocket connections and pub/sub."""

    def __init__(self):
        self._subscribers: dict[str, set[Any]] = {}
        self._lock = threading.Lock()

    def subscribe(self, channel: str, handler: Any) -> None:
        with self._lock:
            self._subscribers.setdefault(channel, set()).add(handler)

    def unsubscribe(self, channel: str, handler: Any) -> None:
        with self._lock:
            subscribers = self._subscribers.get(channel)
            if subscribers:
                subscribers.discard(handler)

    def publish(self, channel: str, data: dict[str, Any]) -> None:
        with self._lock:
            subscribers = list(self._subscribers.get(channel, set()))
        message = json.dumps({
            "type": channel,
            "data": data,
            "timestamp": _utc_now_iso(),
        })
        for handler in subscribers:
            try:
                handler(message)
            except Exception:
                logger.warning("ws publish failed for channel=%s", channel, exc_info=True)

    def handle_upgrade(self, handler: BaseHTTPRequestHandler) -> bool:
        """Attempt WebSocket upgrade. Returns True if upgraded."""
        upgrade = handler.headers.get("Upgrade", "").lower()
        if upgrade != "websocket":
            return False
        # ... WebSocket handshake + connection management
        return True


# Global instance (one per worker process)
ws_manager = WebSocketManager()
```

### 7.4 集成到现有服务器

在 `web_http_handler.py` 的 `do_GET` 中添加 WebSocket 升级检测：

```python
# In do_GET:
if ws_manager.handle_upgrade(self):
    return  # WebSocket connection established, skip normal HTTP handling
```

---

## 8. Sync 超时修复

### 8.1 问题分析

```
当前流程:
  Frontend → POST /api/sync_alphas → backend thread → list_user_alphas()
  Frontend → poll /api/sync_status every 2s → 0% progress (BRAIN API slow)
  ... 30s later ...
  BRAIN API returns timeout error → backend stores error in job
  Frontend poll detects error → shows "云端同步超时"

问题:
  1. sync线程没有"取消"信号的优雅处理 — Thread cannot be interrupted
  2. cloud_sync_max_elapsed_seconds = 0.0 (disabled) — 无默认超时
  3. 进度回调 on_page() 依赖 BRAIN API 的分页信息 — 无进度时前端就是 0%
  4. 没有超时后的降级路径 — 用户只能重试或无操作
```

### 8.2 修复方案

#### Fix 1: 默认超时 + 分阶段超时

```python
# config_models.py 中的 ResearchBudget 默认值
cloud_sync_max_elapsed_seconds: float = 300.0  # 从 0.0 改为 300s（5分钟）
```

在 `web_sync_job.py` 的 `on_page` 回调中，已存在 `elapsed_limit_reached` 检查（line 197），只需确保默认值生效。

#### Fix 2: on_page 本地点滴进度

```python
# 在 run_sync_job_service 中新增本地进度计数
_local_scanned = [0]  # mutable counter

def on_page(progress: dict[str, Any]) -> bool:
    ensure_not_cancelled()
    # Use API-reported progress if available, otherwise local counter
    api_scanned = int(progress.get("scanned", 0) or 0)
    api_total = int(progress.get("total", 0) or 0)
    if api_scanned > 0:
        stats["scanned"] = api_scanned
        stats["total"] = api_total or stats["total"]
    else:
        # API gives no progress — use local page counter as fallback
        _local_scanned[0] += 1
        stats["scanned"] = _local_scanned[0] * (stats.get("page_size", 100) or 100)
    # ... update store as before
```

#### Fix 3: 同步降级路径

```python
# 在 sync 超时时，提供降级选项
if elapsed_limit_reached(elapsed_limit_seconds):
    request_stop(
        f"云端同步已达到耗时上限 {elapsed_limit_seconds:g}s。",
        "云端同步达到耗时上限，可缩小同步范围或使用本地缓存继续。",
    )
    # Fallback: use cached context instead of failing
    context_fallback_available = _has_cached_context()
    if context_fallback_available:
        # Don't raise SyncJobCancelled — complete with warnings
        stats["context_status"] = "timeout_fallback"
```

#### Fix 4: 添加 Atomic Stop

```python
# 在 JobStore 中添加原子取消标记
class JobStore:
    def __init__(self):
        self._cancelled: set[str] = set()
        self._lock = threading.Lock()

    def cancel(self, job_id: str) -> None:
        with self._lock:
            self._cancelled.add(job_id)

    def is_cancelled(self, job_id: str) -> bool:
        with self._lock:
            return job_id in self._cancelled

    def clear_cancelled(self, job_id: str) -> None:
        with self._lock:
            self._cancelled.discard(job_id)
```

---

## 9. 实施计划

### Phase 1：致命修复（今天）

| 任务 | 文件 | 估计 |
|------|------|------|
| `cloud_sync_max_elapsed_seconds` 改为 300s | `config_models.py` | 1 行 |
| JobStore 原子取消 | `tasks.py` | +20 行 |
| on_page 本地进度计数 | `web_sync_job.py` | +10 行 |
| 降级路径处理 | `web_sync_job.py` | +15 行 |

### Phase 2：Phase 端点 + 共享内核（2-3h）

| 任务 | 文件 | 估计 |
|------|------|------|
| 创建 `shared/` 包 | 3 新文件 | 1h |
| 创建 `web/handlers/phase.py` | 1 新文件 | 1h |
| 路由注册 phase_state | `web_routes.py` | +3 行 |
| 增强 progress 返回 elapsed | `web_progress.py` | +10 行 |

### Phase 3：WebSocket 基础（3-4h）

| 任务 | 文件 | 估计 |
|------|------|------|
| 创建 `web/ws.py` | 1 新文件 | 2h |
| HTTP 升级检测 | `web_http_handler.py` | +15 行 |
| Pub/sub 集成到 sync_job | `web_sync_job.py` | +10 行 |

### Phase 4：模块重组（8-10h，可并行）

| 任务 | 文件 | 估计 |
|------|------|------|
| `config/` 子包迁移 | 5 文件 | 3h |
| `data/` 子包迁移 | 5 文件 | 2h |
| `web/handlers/` 拆分 | 8 文件 | 5h |
| `web/middleware/` 提取 | 4 文件 | 3h |

---

> **Backend Architect** | 2026-06-08 | BRAIN Alpha Ops Backend Architecture v4.0
