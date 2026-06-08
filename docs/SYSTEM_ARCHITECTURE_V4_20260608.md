# BRAIN Alpha Ops — 系统架构设计 v4.0

> **架构师**：Software Architect
> **日期**：2026-06-08
> **范围**：全域架构设计、域驱动分解、架构决策记录、演进路线图

---

## 目录

1. [执行摘要](#1-执行摘要)
2. [当前架构评估](#2-当前架构评估)
3. [域驱动设计](#3-域驱动设计)
4. [目标架构](#4-目标架构)
5. [架构决策记录 (ADRs)](#5-架构决策记录)
6. [模块分解与依赖规则](#6-模块分解与依赖规则)
7. [质量属性分析](#7-质量属性分析)
8. [演进路线图](#8-演进路线图)

---

## 1. 执行摘要

BRAIN Alpha Ops 是一个本地优先的量化研究 Web 控制台。当前架构是**模块化单体（Modular Monolith）**，代码库包含 252 个 Python 文件、192 个测试文件，在前一轮重构中已完成显著的模块化改进（web.py 从单文件拆为 56 个专项模块，pipeline.py 从 2654 行降至 679 行）。

### 核心架构决策

| 决策 | 选择 | 替代方案 | 权衡 |
|------|------|----------|------|
| 架构风格 | 模块化单体 | 微服务 | 放弃独立部署/独立扩缩；获得简单运维和低延迟 |
| 域模型 | 4 个有限界上下文 + 共享内核 | 单个大域模型 | 增加模块间显式契约成本；获得清晰边界和可替换性 |
| 前后端通信 | REST + SSE（当前），逐步引入 WebSocket | 纯 REST | 增加 SSE 连接管理复杂度；获得实时进度推送 |
| 持久化 | 文件系统 JSON + SQLite | PostgreSQL | 放弃分布式一致性；获得零运维部署 |
| 架构演进 | 绞杀者模式（Strangler Fig） | 大爆炸重写 | 演进慢但风险低；保持系统持续可用 |

### 当前架构评分

| 维度 | 评分 | 备注 |
|------|------|------|
| 模块化 | 7/10 | web 层模块化优秀，顶层 95 个文件待整理 |
| 可测试性 | 8/10 | 192 个测试、2155 用例通过 |
| 可扩展性 | 6/10 | 域边界模糊，配置与领域逻辑耦合 |
| 可观测性 | 5/10 | 结构化日志存在，缺分布式追踪 |
| 部署简单性 | 9/10 | 单进程，零外部依赖 |

---

## 2. 当前架构评估

### 2.1 C4 第 1 层：系统上下文

```
┌──────────────────────────────────────────────────────────────┐
│                      Quant Researcher                        │
│                   (浏览器 / localhost)                        │
└──────────────────────────┬───────────────────────────────────┘
                           │ HTTP (REST + SSE)
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                   BRAIN Alpha Ops                            │
│                  (本地 Web 控制台)                             │
│                                                              │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────────┐   │
│  │  Web API    │  │  Research    │  │  Data             │   │
│  │  (Flask-like│  │  Pipeline    │  │  (JSON + SQLite)  │   │
│  │   HTTP)     │  │              │  │                   │   │
│  └─────────────┘  └──────────────┘  └───────────────────┘   │
└──────────────────────────┬───────────────────────────────────┘
                           │ HTTPS (官方 API)
                           ▼
┌──────────────────────────────────────────────────────────────┐
│               WorldQuant BRAIN API                           │
│         (官方 Alpha 管理、回测、提交)                           │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 C4 第 2 层：容器视图

```
┌─────────────────────────────────────────────────────────────┐
│  Browser (SPA: React + TypeScript)                          │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐  │
│  │ Sidebar  │ │Dashboard │ │Candidate │ │Scoring Panel │  │
│  │ (nav)    │ │(overview)│ │Table     │ │(details)     │  │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────┘  │
└──────────────────────┬──────────────────────────────────────┘
                       │ HTTP REST + SSE (localhost:8765)
┌──────────────────────┴──────────────────────────────────────┐
│  Python Web Server (brain_alpha_ops.web)                    │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐  │
│  │Routes    │ │Handlers  │ │Session   │ │SSE Progress  │  │
│  │(dispatch)│ │(get/post)│ │Management│ │(streaming)   │  │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └──────┬───────┘  │
│       └─────────────┴────────────┴───────────────┘          │
│                          │                                   │
│  ┌───────────────────────┴─────────────────────────────┐    │
│  │  Research Pipeline (brain_alpha_ops.research)       │    │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐            │    │
│  │  │Generator │ │Scoring   │ │Simulation│            │    │
│  │  │(candidate│ │(quality  │ │(backtest)│            │    │
│  │  │ creation)│ │ gates)   │ │          │            │    │
│  │  └──────────┘ └──────────┘ └──────────┘            │    │
│  └───────────────────────┬─────────────────────────────┘    │
│                          │                                   │
│  ┌───────────────────────┴─────────────────────────────┐    │
│  │  BRAIN API Adapter (brain_alpha_ops.brain_api)      │    │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐            │    │
│  │  │Auth      │ │Alpha API │ │Sim API   │            │    │
│  │  └──────────┘ └──────────┘ └──────────┘            │    │
│  └─────────────────────────────────────────────────────┘    │
│                          │                                   │
│  ┌───────────────────────┴─────────────────────────────┐    │
│  │  Data Layer (data/ directory)                       │    │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐            │    │
│  │  │Cloud     │ │Candidate │ │Checkpoint│            │    │
│  │  │Cache     │ │Pool(JSON)│ │(JSONL)   │            │    │
│  │  └──────────┘ └──────────┘ └──────────┘            │    │
│  └─────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────┘
```

### 2.3 当前模块耦合热力图

```
模块组                    ┌───┬───┬───┬───┬───┬───┬───┐
web_handler_dispatch      │ ■ │ ■ │ ■ │ ■ │ □ │ □ │ ■ │  ← 高度耦合
web_runtime_facade        │ ■ │ ■ │ ■ │ ■ │ □ │ □ │ ■ │
research/pipeline.py      │ □ │ ■ │ ■ │ ■ │ ■ │ ■ │ □ │  ← 核心编排
research/generator.py     │ □ │ □ │ ■ │ ■ │ ■ │ □ │ □ │
brain_api/base.py         │ □ │ □ │ □ │ □ │ ■ │ □ │ □ │  ← 低耦合(好)
config_models.py          │ ■ │ ■ │ ■ │ □ │ □ │ □ │ □ │  ← 共享内核(好)
                          │ R │ W │ P │ G │ A │ C │ S │
                          │ o │ e │ i │ e │ d │ o │ t │
                          │ u │ b │ p │ n │ a │ n │ o │
                          │ t │   │ e │ e │ p │ f │ r │
                          │ e │   │ l │ r │ t │ i │ e │
                          │ s │   │ i │ a │ e │ g │   │
                          │   │   │ n │ t │ r │   │   │
                          │   │   │ e │ o │   │   │   │
                          │   │   │   │ r │   │   │   │
                          └───┴───┴───┴───┴───┴───┴───┘
■ = import 依赖存在    □ = 无直接依赖
```

**关键发现**：`web_handler_dispatch` 和 `web_runtime_facade` 是最重的耦合点，它们直接导入 pipeline、config、和存储模块。这是模块化单体的预期模式，但需要更清晰的边界。

---

## 3. 域驱动设计

### 3.1 有限界上下文

```
┌─────────────────────────────────────────────────────────────────┐
│                     BRAIN Alpha Ops Domain                       │
│                                                                 │
│  ┌─────────────────────┐    ┌─────────────────────────────┐     │
│  │  Web API Context    │    │  Research Pipeline Context  │     │
│  │                     │    │                             │     │
│  │  职责:              │    │  职责:                       │     │
│  │  · HTTP 路由/会话   │◄──►│  · Alpha 生成/变异           │     │
│  │  · 请求验证         │ D  │  · 评分/门禁/校验            │     │
│  │  · SSE 进度推送     │ T  │  · 回测流程编排              │     │
│  │  · 用户认证         │ O  │  · 候选池管理                │     │
│  │                     │    │                             │     │
│  │  聚合根:            │    │  聚合根:                     │     │
│  │  · Session          │    │  · Candidate                │     │
│  │  · Job              │    │  · PipelineRun              │     │
│  │  · SyncTask         │    │  · Scorecard                │     │
│  └─────────┬───────────┘    └──────────────┬──────────────┘     │
│            │                               │                     │
│  ┌─────────┴───────────┐    ┌──────────────┴──────────────┐     │
│  │  BRAIN API Context  │    │  Data & Storage Context     │     │
│  │                     │    │                             │     │
│  │  职责:              │    │  职责:                       │     │
│  │  · 官方 API 适配     │    │  · Cloud Alpha 缓存          │     │
│  │  · 认证/令牌管理     │    │  · Candidate 持久化          │     │
│  │  · 速率限制/重试     │    │  · 研究记忆/知识库           │     │
│  │  · 数据规范化        │    │  · 检查点/快照               │     │
│  │                     │    │                             │     │
│  │  聚合根:            │    │  聚合根:                     │     │
│  │  · AlphaRecord      │    │  · CloudSnapshot            │     │
│  │  · FieldDef         │    │  · ResearchMemory           │     │
│  │  · Simulation       │    │  · Checkpoint               │     │
│  └─────────────────────┘    └─────────────────────────────┘     │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Shared Kernel                                           │    │
│  │  · Candidate (DTO)    · RunConfig/ResearchBudget         │    │
│  │  · PipelineEvent      · BrainSettings                   │    │
│  │  · Domain Errors      · Value Objects (Score, AlphaId)  │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 上下文映射

```
Web API ──[Conformist]──► BRAIN API
   │                          │
   │ [Customer/Supplier]      │ [Anti-Corruption Layer]
   │                          │
   ▼                          ▼
Research Pipeline ◄──[Shared Kernel]──► Data & Storage
   │                                       │
   └──────[Published Language: DTOs]───────┘
```

| 映射关系 | 上游 | 下游 | 含义 |
|----------|------|------|------|
| **Conformist** | BRAIN API | Web API | Web 层必须跟随 BRAIN 官方 API 的变化，无力影响 |
| **Customer/Supplier** | Web API | Research Pipeline | Web 层是 Research 的客户，Research 需考虑 Web 的需求 |
| **Anti-Corruption Layer** | BRAIN API | Research Pipeline | `brain_api/` 隔离官方 API 的模型变化 |
| **Shared Kernel** | — | — | Candidate、RunConfig、BrainSettings 在各上下文间共享 |

### 3.3 核心聚合

#### Candidate（候选 Alpha）— Research Pipeline 上下文的核心聚合

```
Candidate (聚合根)
├── alpha_id: str             ← 唯一标识
├── expression: str           ← Alpha 表达式
├── family: str               ← 族标识
├── hypothesis: str           ← 假设来源
├── data_fields: list[str]    ← 使用的数据字段
├── operators: list[str]      ← 使用的算子
├── source_tags: list[str]    ← 来源标签
│
├── local_quality: dict       ← 本地质量评估 (值对象)
├── validation: dict          ← 官方验证结果 (值对象)
├── official_metrics: dict    ← 官方回测指标 (值对象)
├── scorecard: dict           ← 综合评分卡 (值对象)
├── gate: dict                ← 门禁状态 (值对象)
│
├── lifecycle_status: str     ← 生命周期状态
│   ├── "created" → "local_checked" → "official_validated"
│   ├── → "official_simulated" → "submission_ready"
│   └── → "submitted" / "rejected" / "archived"
│
└── invariants:
    · alpha_id 不可变
    · lifecycle 只能向前推进
    · 进入 "submitted" 后不可逆
```

#### Job（异步作业）— Web API 上下文的核心聚合

```
Job (聚合根)
├── job_id: str               ← 唯一标识
├── job_type: str             ← sync | generate | check | submit
├── status: JobStatus         ← 生命周期
│   ├── queued → running → completed / failed / stopped / cancelled
├── progress: UnifiedProgress ← 进度快照
├── result: dict              ← 完成结果
├── error: str | None         ← 错误信息
│
└── invariants:
    · 同一时刻每种 job_type 最多一个 running
    · 只有 running 可被停止
    · completed/failed/stopped 不可再转换
```

---

## 4. 目标架构

### 4.1 目标模块树

```
brain_alpha_ops/
├── __init__.py                     # 公开 API
│
├── shared/                         # 共享内核（零外部依赖）
│   ├── __init__.py
│   ├── types.py                    # Candidate, PipelineEvent, PipelineResult
│   ├── errors.py                   # DomainError, ValidationError, TimeoutError
│   ├── ids.py                      # new_id(), AlphaId, JobId (值对象)
│   └── contracts.py                # 跨上下文 DTO 和事件契约
│
├── config/                         # 配置域
│   ├── __init__.py
│   ├── models.py                   # BrainSettings, ResearchBudget, OpsConfig
│   ├── schema.py                   # JSON Schema 验证
│   ├── loader.py                   # load_run_config(), from_json()
│   └── update.py                   # 运行时配置热更新
│
├── brain_api/                      # BRAIN API 适配层（防腐蚀层）
│   ├── __init__.py
│   ├── client.py                   # BrainAPI 基类
│   ├── auth.py                     # 认证与令牌刷新
│   ├── alphas.py                   # list_user_alphas(), get_alpha_detail()
│   ├── fields.py                   # list_fields(), 字段缓存
│   ├── operators.py                # list_operators(), 算子缓存
│   ├── simulations.py              # submit_simulation(), poll_simulation()
│   ├── validations.py              # submit_validation(), poll_validation()
│   ├── pagination.py               # 分页抽象
│   ├── rate_limit.py               # 速率限制与重试
│   └── context.py                  # 官方上下文(字段/算子/数据集)管理
│
├── research/                       # 研究流水线
│   ├── __init__.py
│   ├── pipeline.py                 # 主编排器（精简，只做调度）
│   ├── generator/                  # Alpha 生成子系统
│   │   ├── __init__.py
│   │   ├── base.py                 # CandidateGenerator 接口
│   │   ├── experience.py           # 经验驱动生成
│   │   ├── hypothesis.py           # 假设驱动生成
│   │   ├── mutation.py             # 变异策略
│   │   └── validation.py           # 本地质量校验
│   ├── scoring/                    # 评分子系统
│   │   ├── __init__.py
│   │   ├── scorecard.py            # 评分卡构建
│   │   ├── gates.py                # 质量门禁
│   │   ├── anti_overfit.py         # 反过拟合分析
│   │   └── convergence.py          # 收敛追踪
│   ├── backtest/                   # 回测子系统
│   │   ├── __init__.py
│   │   ├── local.py                # 本地回测引擎
│   │   ├── submission.py           # 提交回测
│   │   ├── polling.py              # 轮询回测状态
│   │   ├── slots.py                # 回测槽位管理
│   │   └── finalization.py         # 回测结果处理
│   ├── simulation/                 # 仿真子系统
│   │   ├── __init__.py
│   │   ├── validator.py            # 官方验证
│   │   ├── simulator.py            # 官方仿真
│   │   └── guard.py                # 调用守卫(配额/速率)
│   ├── strategy/                   # 策略管理
│   │   ├── __init__.py
│   │   ├── plugins.py              # 策略插件加载
│   │   ├── lifecycle.py            # 策略生命周期
│   │   └── switch.py               # 策略切换
│   ├── memory.py                   # 研究记忆
│   ├── knowledge.py                # 知识库
│   ├── observability.py            # 可观测快照
│   └── repository.py               # 候选仓库
│
├── web/                            # Web API 层
│   ├── __init__.py
│   ├── server.py                   # HTTP 服务器
│   ├── routes.py                   # 路由注册
│   ├── handlers/                   # 请求处理器
│   │   ├── __init__.py
│   │   ├── auth.py                 # 认证/连接测试
│   │   ├── sync.py                 # 云端同步
│   │   ├── candidates.py           # 候选管理
│   │   ├── scoring.py              # 评分
│   │   ├── checks.py               # 批量检查
│   │   ├── submission.py           # 提交审核
│   │   ├── config.py               # 配置管理
│   │   └── snapshots.py            # 快照/仪表盘
│   ├── middleware/                  # 中间件
│   │   ├── __init__.py
│   │   ├── session.py              # 会话管理
│   │   ├── csrf.py                 # CSRF 保护
│   │   ├── rate_limit.py           # 请求速率限制
│   │   └── security.py             # 安全头/CSP
│   ├── sse.py                      # Server-Sent Events
│   ├── jobs.py                     # 异步作业管理
│   └── progress.py                 # 统一进度管理
│
├── data/                           # 数据持久化
│   ├── __init__.py
│   ├── cloud_cache.py              # 云端 Alpha 缓存
│   ├── candidate_store.py          # 候选持久化
│   ├── checkpoint.py               # 检查点管理
│   ├── sqlite_index.py             # SQLite 索引
│   └── repository.py               # ResearchRepository
│
├── ux/                             # UX 辅助（非核心）
│   ├── __init__.py
│   ├── errors.py                   # 用户友好的错误文案
│   ├── guided_pipeline.py          # 引导式流水线
│   └── history.py                  # 操作历史
│
└── agents/                         # Agent 工具（MCP 集成）
    ├── __init__.py
    ├── registry.py                 # 工具注册
    ├── research.py                 # 研究工具
    ├── guidance.py                 # 引导工具
    └── live.py                     # 实时工具
```

### 4.2 文件迁移映射

从当前扁平结构到目标层级结构：

| 当前路径 | 目标路径 | 原因 |
|----------|----------|------|
| `brain_alpha_ops/models.py` | `brain_alpha_ops/shared/types.py` | 跨上下文共享 |
| `brain_alpha_ops/errors.py` | `brain_alpha_ops/shared/errors.py` | 共享域错误 |
| `brain_alpha_ops/config.py` | `brain_alpha_ops/config/loader.py` | 配置子系统 |
| `brain_alpha_ops/config_models.py` | `brain_alpha_ops/config/models.py` | 配置模型归组 |
| `brain_alpha_ops/config_schema.py` | `brain_alpha_ops/config/schema.py` | 配置校验归组 |
| `brain_alpha_ops/research/generator.py` | `brain_alpha_ops/research/generator/` | 拆分大文件 |
| `brain_alpha_ops/research/scoring.py` | `brain_alpha_ops/research/scoring/` | 评分子系统 |
| `brain_alpha_ops/research/pipeline.py` | `brain_alpha_ops/research/pipeline.py` | 保留，精简为编排 |
| `brain_alpha_ops/web_handler_dispatch.py` | `brain_alpha_ops/web/handlers/` | 按资源拆分 |
| `brain_alpha_ops/web_http_handler.py` | `brain_alpha_ops/web/server.py` | 语义更清晰 |

### 4.3 边界间通信协议

```python
# shared/contracts.py — 跨上下文的契约

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

# ── Domain Events ──────────────────────────────────────────

@dataclass(frozen=True)
class CandidateGenerated:
    """Research Pipeline → Data: 新候选生成"""
    candidate_id: str
    expression: str
    family: str
    timestamp: str

@dataclass(frozen=True)
class SyncCompleted:
    """BRAIN API → Data: 云端同步完成"""
    scanned: int
    added: int
    updated: int
    fields_count: int
    timestamp: str

@dataclass(frozen=True)
class ScoreUpdated:
    """Research Pipeline → Web: 评分更新"""
    candidate_id: str
    score: float
    decision_band: str
    gate_status: dict

# ── Service Interfaces (Protocols) ─────────────────────────

@runtime_checkable
class CandidateRepository(Protocol):
    """Data context → Research context"""
    def find_by_id(self, alpha_id: str) -> Candidate | None: ...
    def find_by_family(self, family: str) -> list[Candidate]: ...
    def save(self, candidate: Candidate) -> None: ...
    def list_all(self, limit: int = 100) -> list[Candidate]: ...

@runtime_checkable
class BrainAPIClient(Protocol):
    """BRAIN API context → Research context"""
    def list_user_alphas(self, range: str) -> list[dict]: ...
    def submit_validation(self, expression: str, settings: dict) -> str: ...
    def poll_validation(self, validation_id: str) -> dict: ...

@runtime_checkable
class ProgressReporter(Protocol):
    """Web context → Research context (SSE callback)"""
    def report(self, phase: str, message: str, percent: float) -> None: ...
    def is_cancelled(self) -> bool: ...
```

---

## 5. 架构决策记录 (ADRs)

### ADR-001: 选择模块化单体而非微服务

- **Status**: Accepted
- **Context**: 系统是本地部署的单用户 Web 控制台。团队规模小（1-2 人），不需要独立扩缩。需要低延迟本地操作。
- **Decision**: 采用模块化单体架构，按域划分包边界，严格遵循依赖方向。
- **Consequences**:
  - ✅ 简单：单进程部署，零运维
  - ✅ 低延迟：无网络调用开销
  - ✅ 易调试：单进程内跟踪
  - ❌ 无法独立扩缩各模块
  - ❌ 模块间编译时耦合（Python import）
  - ❌ 一处 OOM 影响全局

### ADR-002: brain_api/ 作为防腐蚀层

- **Status**: Accepted
- **Context**: WorldQuant BRAIN API 有自己的数据模型和错误格式，不应直接污染研究域的模型。
- **Decision**: `brain_api/` 包作为防腐蚀层（Anti-Corruption Layer），负责：
  1. 将 BRAIN API 响应转换为域模型（Candidate, AlphaRecord）
  2. 将 BRAIN 错误码翻译为域错误（DomainError）
  3. 处理认证令牌刷新、速率限制等横切关注点
- **Consequences**:
  - ✅ BRAIN API 变更只影响 brain_api/ 包
  - ✅ 研究域使用自己的语言和模型
  - ✅ 可以 mock brain_api 进行测试
  - ❌ 额外翻译层 = 性能开销（可忽略，本地调用）

### ADR-003: JSON 文件 + SQLite 作为持久化方案

- **Status**: Accepted
- **Context**: 系统在用户本地运行，数据量受限于单用户行为。无需分布式一致性。
- **Decision**: 
  - Cloud Alpha 快照 → JSON 文件 (`data/cloud/`)
  - Candidate 池 → JSON 文件 (`data/candidates/`)
  - 研究记忆 → SQLite (`data/research_memory.sqlite`)
  - 检查点 → JSONL (`data/checkpoints/`)
- **Consequences**:
  - ✅ 零外部依赖，用户无需安装数据库
  - ✅ 数据可直接查看/编辑/备份
  - ✅ JSONL 追加写 = 天然 audit log
  - ❌ 无事务保证跨文件一致性
  - ❌ 并发写可能损坏（单用户场景可接受）
  - ❌ 大量 Alpha (>100k) 时 JSON 查询性能下降

### ADR-004: 从 REST+SSE 逐步过渡到 WebSocket

- **Status**: Accepted（2026-06-09）：WebSocketManager 骨架已实施
- **Context**: 当前 SSE 实现工作良好但有局限：单向推送、需轮询作业状态、无请求-响应匹配。
- **Decision**: 在 v4.1 中引入 WebSocket 支持：
  - 保留 REST 用于 CRUD 操作（连接测试、配置更新、一次性查询）
  - 新增 WebSocket 用于实时通信（同步进度、作业状态、评分结果）
  - 短期（v4.0）：保持 SSE + 轮询，修复进度反馈问题
  - 中期（v4.1）：引入 WebSocket 替代 SSE
- **Consequences**:
  - ✅ 双向通信，作业状态实时推送
  - ✅ 减少轮询开销
  - ✅ 支持请求-响应匹配
  - ❌ WebSocket 连接管理复杂度
  - ❌ 需要重连逻辑
  - ❌ 测试复杂度增加（需要 ws 客户端）

### ADR-005: 引入 Protocol（typing.Protocol）定义模块间契约

- **Status**: Accepted（2026-06-09）：`shared/contracts.py` 已投产，5 个 Protocol 接口
- **Context**: 模块间通过直接 import 耦合。需要在不引入重量级 DI 框架的前提下，定义清晰的接口边界。
- **Decision**: 使用 Python `typing.Protocol` 在 `shared/contracts.py` 中定义服务接口。各上下文通过依赖注入传递实现。
- **Consequences**:
  - ✅ 编译时类型检查（mypy/pyright）
  - ✅ 零运行时开销（Protocol 是结构性类型）
  - ✅ 易于 mock 测试
  - ❌ 需要显式依赖注入（当前是直接 import）
  - ❌ 迁移现有代码需要重构

---

## 6. 模块分解与依赖规则

### 6.1 依赖方向

```
              ┌──────────────┐
              │   agents/    │  ← 最外层：MCP 工具集成
              └──────┬───────┘
                     │ 依赖
              ┌──────▼───────┐
              │    web/      │  ← Web API：HTTP 路由、SSE
              └──────┬───────┘
                     │ 依赖
       ┌─────────────┼─────────────┐
       │             │             │
  ┌────▼────┐  ┌────▼────┐  ┌─────▼─────┐
  │research/│  │ brain_  │  │   data/   │  ← 核心域
  │         │  │  api/   │  │           │
  └────┬────┘  └────┬────┘  └─────┬─────┘
       │            │             │
       └────────────┼─────────────┘
                    │ 依赖
              ┌─────▼──────┐
              │  shared/   │  ← 共享内核：类型、错误、契约
              └────────────┘
```

### 6.2 依赖规则（可自动化检查）

```python
# 规则 1: shared/ 不得导入任何同层或上层模块
# 规则 2: research/ 不得导入 web/ 或 agents/
# 规则 3: brain_api/ 不得导入 research/、web/、agents/
# 规则 4: data/ 不得导入 research/、web/、agents/
# 规则 5: web/ 可以导入 research/、brain_api/、data/、config/、shared/
# 规则 6: agents/ 可以导入所有下层模块

# 自动化检查（可用 import-linter 或自定义脚本）：
# import-linter:
#   root: brain_alpha_ops
#   layers:
#     - shared
#     - config
#     - brain_api
#     - data
#     - research
#     - web
#     - agents
#   rules:
#     - lower_layers: [shared, config]
#     - mid_layers: [brain_api, data, research]
#     - upper_layers: [web, agents]
```

### 6.3 当前违规清单（需逐步修复）

| 违规 | 位置 | 修复计划 |
|------|------|----------|
| `web_*.py` → `brain_alpha_ops.models` | 所有 web 模块 | ADR-005: 迁移到 shared/types.py |
| `web_*.py` → `brain_alpha_ops.config` | handler 模块 | 已经是 config context 的合法依赖 |
| `research/*.py` → `brain_alpha_ops.models` | 研究模块 | ADR-005: 迁移到 shared/types.py |
| `research/pipeline.py` → `brain_alpha_ops.config` | 编排器 | 保持（config 是共享内核） |

---

## 7. 质量属性分析

### 7.1 可扩展性

| 扩展场景 | 当前能力 | 目标状态 | 差距 |
|----------|----------|----------|------|
| 新增 Alpha 生成策略 | ⚠️ 需修改 generator.py | 实现 GeneratorPlugin 协议，注册即可 | 中等 |
| 新增评分维度 | ⚠️ 评分逻辑分散 | ScoringPlugin 协议 | 中等 |
| 新增 BRAIN API 端点 | ✅ brain_api/ 封装良好 | 保持不变 | 无 |
| 新增 Web 路由 | ✅ 路由注册清晰 | 保持不变 | 无 |
| 新增持久化后端 | ❌ 硬编码 JSON/SQLite | Repository 接口抽象 | 高 |
| 多用户支持 | ❌ 单用户设计 | 需架构根变革 | 极高 |

### 7.2 可靠性

| 故障场景 | 当前处理 | 目标 |
|----------|----------|------|
| BRAIN API 不可用 | ✅ 错误返回 + toast | 增加指数退避重试 |
| 云端同步超时 | ❌ 无恢复路径 (P0) | stall 检测 + retry/cancel |
| SSE 连接断开 | ✅ 自动重连 | 保持不变 |
| 磁盘满 | ❌ 未处理 | 存储操作前检查空间 |
| 异常 Alpha 表达式 | ✅ 沙箱执行 | 保持不变 |
| 内存泄漏 | ❌ 未监控 | 周期性内存快照 |

### 7.3 可观测性

| 指标 | 当前 | 目标 |
|------|------|------|
| 结构化日志 | ✅ Python logging | ✅ 保持 |
| 请求追踪 | ❌ 无 trace ID | 每个请求生成 correlation_id |
| 作业生命周期 | ⚠️ 部分 | 完整的 create→start→progress→complete 事件链 |
| 错误聚合 | ❌ 无 | 错误按类型/频率聚合 |
| 性能度量 | ❌ 无 | 关键路径耗时（API 调用、评分计算） |
| 健康检查 | ✅ `/api/health` | 增加依赖健康（BRAIN API 可达性） |

---

## 8. 演进路线图

### 路线图总览

```
Q2 2026 (当前)          Q3 2026                Q4 2026               Q1 2027+
════════════════════════════════════════════════════════════════════════════

v3.0 (当前)              v4.0 (目标)            v4.1                   v5.0
模块化单体               域驱动模块化单体        增强通信               架构升级

┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐
│ · 95 顶层模块    │  │ · 4 有限界上下文  │  │ · WebSocket 替代 │  │ · 插件架构    │
│ · web 层已拆分   │  │ · shared/ 共享核 │  │   SSE+轮询       │  │ · 策略市场    │
│ · 192 测试文件   │  │ · contracts.py  │  │ · Protocol 契约  │  │ · 多环境配置  │
│ · 手动依赖管理   │  │ · import-linter │  │ · 事件总线       │  │ · 性能调优    │
└─────────────────┘  └─────────────────┘  └─────────────────┘  └──────────────┘
```

### v4.0 里程碑（Q3 2026，12 周）

#### Milestone 1: 共享内核提取（Week 1-2）

- [ ] 创建 `brain_alpha_ops/shared/` 包
- [ ] 迁移 `models.py` → `shared/types.py`
- [ ] 迁移 `errors.py` → `shared/errors.py`
- [ ] 创建 `shared/contracts.py`（Protocol 定义）
- [ ] 更新所有 import 路径
- [ ] 验证全部 2155 测试通过

#### Milestone 2: 配置域整理（Week 3-4）

- [ ] 创建 `config/` 子包
- [ ] 迁移配置相关文件（models, schema, loader, update, validation）
- [ ] 消除顶层重复的 config_*.py 文件
- [ ] 验证配置热更新能力

#### Milestone 3: Web 层重组（Week 5-7）

- [ ] 创建 `web/handlers/` 子包
- [ ] 按资源拆分 web_handler_dispatch.py
- [ ] 创建 `web/middleware/` 子包
- [ ] 提取 session/csrf/rate_limit 中间件
- [ ] 接口契约不变，对外 URL 不变

#### Milestone 4: Research 子系统拆分（Week 8-10）

- [ ] 创建 `research/generator/` 子包
- [ ] 创建 `research/scoring/` 子包
- [ ] 创建 `research/backtest/` 子包
- [ ] 创建 `research/simulation/` 子包
- [ ] pipeline.py 精简为纯编排器
- [ ] 各子系统独立可测

#### Milestone 5: 自动化治理（Week 11-12）

- [ ] 配置 import-linter 检查依赖规则
- [ ] 添加 CI 中的依赖违规检测
- [ ] 更新 ARCHITECTURE.md
- [ ] 生成模块依赖图

### v4.1 里程碑（Q4 2026，8 周）

- [ ] 引入 Protocol 契约替代直接 import
- [ ] WebSocket 替代 SSE（渐进迁移）
- [ ] 引入简单事件总线用于跨上下文通信
- [ ] 增加 correlation_id 追踪

### v5.0 展望（Q1 2027+）

- [ ] 插件架构：生成策略、评分策略可插拔
- [ ] 策略市场：社区贡献的生成/评分插件
- [ ] 多环境配置管理
- [ ] 性能剖析与优化
- [ ] 考虑是否需要从单体中提取独立进程（如 BRAIN API 代理）

---

## 附录 A：技术栈

| 层 | 技术 | 版本 | 备注 |
|----|------|------|------|
| 运行时 | Python | 3.10+ | |
| Web 框架 | 自研（基于 http.server） | — | 轻量，零第三方 Web 依赖 |
| 前端 | React + TypeScript + Tailwind | 18.x | SPA |
| 构建 | Vite | 5.x | |
| 数据结构 | dataclasses + Protocol | 3.10+ | |
| 持久化 | JSON 文件 + SQLite | — | |
| 类型检查 | mypy / pyright | — | CI 中执行 |
| 测试 | pytest | 7.x+ | 2155 用例 |

## 附录 B：架构原则

1. **本地优先**：所有功能离线可用，BRAIN API 为可选依赖
2. **安全第一**：提交操作必须经过人工审核，不可自动执行
3. **可逆性优先**：选择容易回退的决策，而非"最优"但不可逆的决策
4. **模块边界=文件边界**：每个 py 文件定义明确的单一职责
5. **测试驱动架构**：模块的可测试性 = 架构的健康度指标

---

> **下一步**：
> 1. 评审并确认 5 个 ADR
> 2. 启动 v4.0 Milestone 1：共享内核提取
> 3. 同步推进 UX 架构 Phase A 修复（参见 UX_ARCHITECTURE_REDESIGN_20260608.md）

---
**Software Architect** | 2026-06-08 | BRAIN Alpha Ops 系统架构设计 v4.0
