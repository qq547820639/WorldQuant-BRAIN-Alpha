# 拆分 sync_job.py 和 guided_pipeline.py 为包

## Summary

继续完成 4 文件拆分任务的剩余 2 个文件：
1. `brain_alpha_ops/web_cloud/sync_job.py` (630行) → `sync_job/` 包（`_types.py` 已创建）
2. `brain_alpha_ops/ux/guided_pipeline.py` (517行) → `guided_pipeline/` 包

前两个文件（`ashare_adapter.py`、`loader.py`）已完成。本计划遵循项目已有的 5+ 次拆分模式（`snapshot/`、`loader/`、`ashare_adapter/` 等），使用 `_pkg()` helper 保证 monkeypatch 兼容性。

## Current State Analysis

### sync_job.py 现状
- `brain_alpha_ops/web_cloud/sync_job/` 目录已存在，内含 `_types.py`（28行：JobStoreLike、SyncJobCancelled、7个类型别名）
- 原 `sync_job.py` (630行) 仍然存在，需删除
- 结构：imports(18行) + 类型定义(已拆出) + 辅助函数/常量(130行) + `run_sync_job_service`(455行单函数) + `path_modified_at` re-export
- **关键约束**：`run_sync_job_service` 是 455 行的单体函数，内部有大量闭包共享可变状态（`stats`、`stop_state`、`heartbeat_count`），无法在不改变内部行为的前提下拆分

### guided_pipeline.py 现状
- 517行：imports(31行) + `classify_error`(22行，是 `guided_formatting.classify_error` 的副本，保留用于 monkeypatch) + `GuidedPipeline` 类(447行) + re-exports(10行)
- **关键约束**：测试 monkeypatch 3 个模块级属性：
  - `guided_pipeline._unified_classify`（被 `classify_error` 使用）
  - `guided_pipeline.run_pipeline_from_config`（被 `_phase_core_pipeline` 使用）
  - `guided_pipeline.GuidedPipeline`（被 `web_run_job.py` 晚期导入）

### 需要更新的测试
1. `tests/test_web_sync_payload.py` 第49行：`Path("brain_alpha_ops/web_cloud/sync_job.py").read_text()` — 路径不存在
2. `tests/test_review_gap_closure_tracker.py` 第312、1349行：`ROOT / "brain_alpha_ops" / "ux" / "guided_pipeline.py"` — 路径不存在

### 参考模式
- `brain_alpha_ops/data/ashare_adapter/_state.py`：`_pkg()` 返回 `sys.modules["brain_alpha_ops.data.ashare_adapter"]`
- `brain_alpha_ops/data/loader/__init__.py`：在包层级 re-export `runtime_project_root` 供 monkeypatch
- `brain_alpha_ops/data/loader/_refresh.py`：Mixin 模式 + 晚期导入避免循环引用
- `brain_alpha_ops/web_cloud/snapshot/__init__.py`：包级 re-export 所有公共 API

## Proposed Changes

### Part 1: 完成 sync_job.py 拆分

#### 1.1 创建 `brain_alpha_ops/web_cloud/sync_job/_helpers.py` (~135行)

包含原 sync_job.py 中的辅助函数和常量（行 42-172）：

```python
"""Helper functions and observability constants for cloud sync jobs."""
from __future__ import annotations

import time
from typing import Any

# 常量（原文件行 67-91）
_SCAN_OBSERVABILITY_INT_KEYS = frozenset({...})
_SCAN_OBSERVABILITY_FLOAT_KEYS = frozenset({...})
_SCAN_OBSERVABILITY_TEXT_KEYS = frozenset({...})
_SCAN_OBSERVABILITY_BOOL_KEYS = frozenset({...})
_SCAN_OBSERVABILITY_KEYS = (...)

# 函数（原文件行 42-64, 94-172）
def _timing_payload(started_at, *, done=0, total=0, now=None) -> dict[str, Any]: ...
def _scan_observability(progress: dict[str, Any]) -> dict[str, Any]: ...
def _cloud_scan_status_message(stats: dict[str, Any]) -> str: ...
def _sync_range_label(sync_range: str) -> str: ...
def _final_sync_status_message(stats, *, context_error, context_warnings) -> str: ...
```

从 `_types.py` 导入类型别名（如果函数签名需要）。函数体原样复制，不改任何逻辑。

#### 1.2 创建 `brain_alpha_ops/web_cloud/sync_job/_service.py` (~470行)

包含原 sync_job.py 的 `run_sync_job_service` 函数（行 175-629）。

> **注意**：此文件超过 350 行限制。`run_sync_job_service` 是 455 行的单体函数，内部有 8 个闭包（`_heartbeat_loop`、`cancel_requested`、`request_stop`、`ensure_not_cancelled`、`on_dataset_fallback`、`mark_cancelled`、`on_page`、`on_fields_progress`、`on_operators_progress`）共享可变状态（`stats` dict、`stop_state` dict、`heartbeat_count` list）。拆分这些闭包需要引入上下文对象或传递大量参数，会改变内部行为，违反"行为不变"的首要要求。因此保持原样。

```python
"""Cloud sync job service entry point."""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

from brain_alpha_ops.brain_api.user_alpha_sync import (
    list_user_alphas_for_sync,
    sync_range_from_payload,
)
from brain_alpha_ops.official_context_datasets import list_official_datasets_or_derive

from ._helpers import (
    _SCAN_OBSERVABILITY_KEYS,
    _cloud_scan_status_message,
    _final_sync_status_message,
    _scan_observability,
    _sync_range_label,
    _timing_payload,
)
from ._types import (
    ApiFromRunConfig,
    DatasetsFromFields,
    ErrorPayload,
    JobStoreLike,
    PersistOfficialContext,
    RepositoryFactory,
    RunConfigFromPayload,
    SafeErrorMessage,
    SyncJobCancelled,
)

logger = logging.getLogger(__name__)

def run_sync_job_service(...) -> None:
    # 原样复制函数体，不做任何修改
    ...
```

#### 1.3 创建 `brain_alpha_ops/web_cloud/sync_job/__init__.py` (~45行)

```python
"""Cloud sync jobs and payload builders.

Subpackage of ``brain_alpha_ops.web_cloud``. Splits the original
``sync_job.py`` monolith into focused modules while preserving the public
API surface via re-exports.
"""
from __future__ import annotations

from ._types import (
    ApiFromRunConfig,
    DatasetsFromFields,
    ErrorPayload,
    JobStoreLike,
    PersistOfficialContext,
    RepositoryFactory,
    RunConfigFromPayload,
    SafeErrorMessage,
    SyncJobCancelled,
)
from ._helpers import (
    _SCAN_OBSERVABILITY_BOOL_KEYS,
    _SCAN_OBSERVABILITY_FLOAT_KEYS,
    _SCAN_OBSERVABILITY_INT_KEYS,
    _SCAN_OBSERVABILITY_KEYS,
    _SCAN_OBSERVABILITY_TEXT_KEYS,
    _cloud_scan_status_message,
    _final_sync_status_message,
    _scan_observability,
    _sync_range_label,
    _timing_payload,
)
from ._service import run_sync_job_service

# Backward-compat re-export (原 sync_job.py 末尾)
from ..snapshot import path_modified_at  # noqa: F401

__all__ = [
    "JobStoreLike",
    "SyncJobCancelled",
    "run_sync_job_service",
    "_timing_payload",
    "_scan_observability",
    "_cloud_scan_status_message",
    "_sync_range_label",
    "_final_sync_status_message",
    "path_modified_at",
]
```

#### 1.4 删除原 `brain_alpha_ops/web_cloud/sync_job.py`

#### 1.5 更新 `tests/test_web_sync_payload.py` 第48-59行

将 `sync_job_source = Path("brain_alpha_ops/web_cloud/sync_job.py").read_text(encoding="utf-8")` 改为读取包内所有 .py 文件的合并源码：

```python
def test_sync_modules_keep_single_job_and_payload_owners():
    sync_job_dir = Path("brain_alpha_ops/web_cloud/sync_job")
    sync_job_source = "\n".join(
        p.read_text(encoding="utf-8") for p in sorted(sync_job_dir.glob("*.py"))
    )
    sync_payload_source = Path("brain_alpha_ops/web_cloud/sync_payload.py").read_text(encoding="utf-8")
    handler_source = Path("brain_alpha_ops/web/handlers/sync.py").read_text(encoding="utf-8")

    assert sync_job_source.count("def run_sync_job_service(") == 1
    assert "def sync_cloud_alphas_payload(" not in sync_job_source
    assert sync_payload_source.count("def sync_cloud_alphas_payload(") == 1
    assert "def run_sync_job_service(" not in sync_payload_source
    assert "from brain_alpha_ops.web_cloud.sync_job import" in handler_source
    assert "from brain_alpha_ops.web_cloud.sync_payload import sync_cloud_alphas_payload" in handler_source
    assert "def " not in handler_source
```

---

### Part 2: 拆分 guided_pipeline.py

#### 2.1 创建 `brain_alpha_ops/ux/guided_pipeline/_state.py` (~55行)

共享状态 + `classify_error` 函数。`classify_error` 通过 `_pkg()._unified_classify(...)` 读取包级属性，保证 monkeypatch 兼容。

```python
"""Shared state for the guided_pipeline package."""
from __future__ import annotations

import logging
import sys
from typing import Any

from brain_alpha_ops.redaction import redact_error_message

logger = logging.getLogger(__name__)


def _pkg() -> Any:
    """Return the parent package module so submodules can access
    ``_unified_classify`` and ``run_pipeline_from_config`` that tests may
    monkeypatch on the package."""
    return sys.modules["brain_alpha_ops.ux.guided_pipeline"]


def classify_error(error: Exception) -> dict[str, str]:
    """Classify an error and return actionable guidance."""
    try:
        info = _pkg()._unified_classify(error)
        return {
            "type": info.error_code or type(error).__name__,
            "message": redact_error_message(error, max_length=200),
            "fix": info.fix_hint or "未知错误。请在页面事件记录中查看提示，或让维护者查看诊断信息。",
            "retry": "yes" if info.retryable else ("maybe" if info.retryable is None else "no"),
        }
    except Exception:
        logger.warning("guided pipeline error classification fallback failed", exc_info=True)
        return {
            "type": type(error).__name__,
            "message": redact_error_message(error, max_length=200),
            "fix": "未知错误。请在页面事件记录中查看提示，或让维护者查看诊断信息。",
            "retry": "maybe",
        }
```

#### 2.2 创建 `brain_alpha_ops/ux/guided_pipeline/_base.py` (~165行)

`GuidedPipelineBase` 类：`__init__`、`on_progress`、`stop`、`_should_stop`、`run_guided`、`run`、`resume`、`_notify`、`print_progress`、`print_summary`。

从 `_state.py` 导入 `logger`、`classify_error`。从 `guided_storage`、`guided_display`、`guided_models` 直接导入（无需 monkeypatch 兼容）。`_phase_core_pipeline` 在 `_phases.py` 的 mixin 中定义。

```python
"""GuidedPipeline base class: lifecycle, progress, resume, and display."""
from __future__ import annotations

import logging
import threading  # 仅 resume 中 Event 间接需要（实际不需要，threading 在 _phases.py）
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.models import PipelineResult
from brain_alpha_ops.redaction import redact_error_message
from brain_alpha_ops.ux import guided_display, guided_storage
from brain_alpha_ops.ux.guided_models import CheckpointData, PipelinePhase

from ._state import classify_error, logger


class GuidedPipelineBase:
    """Base class for GuidedPipeline providing lifecycle and progress management."""

    PHASES = [...]

    def __init__(self, run_config, *, stop_callback=None): ...
    def on_progress(self, callback): ...
    def stop(self): ...
    def _should_stop(self): ...
    def run_guided(self): ...
    def run(self): ...
    def resume(self, run_id=None): ...
    def _notify(self, phase_id, status, data): ...
    def _save_checkpoint(self, run_id, phase, result=None): ...
    def load_checkpoint(self, run_id): ...
    def list_checkpoints(self): ...
    def latest_checkpoint(self): ...
    @staticmethod
    def _result_from_snapshot(snapshot): ...
    def _save_run_record(self, result): ...
    def list_history(self): ...
    def show_run(self, run_id): ...
    def history_analytics(self, *, limit=10): ...
    def print_progress(self): ...
    def print_summary(self, result=None): ...
```

#### 2.3 创建 `brain_alpha_ops/ux/guided_pipeline/_phases.py` (~285行)

`_PhasesMixin` 类：所有 `_phase_*` 方法。`_phase_core_pipeline` 通过 `_pkg().run_pipeline_from_config(...)` 调用，保证 monkeypatch 兼容。

```python
"""GuidedPipeline phase implementations mixin."""
from __future__ import annotations

import threading
import time
from typing import Any

from brain_alpha_ops.models import PipelineResult

from ._state import classify_error, logger, _pkg


class _PhasesMixin:
    """Mixin providing phase implementations for GuidedPipeline."""

    def _phase_init(self, run_id): ...
    def _phase_context(self, result): ...
    def _phase_redline(self, result): ...
    def _phase_core_pipeline(self, result): ...
    @staticmethod
    def _phase_id_from_core_progress(phase): ...
    def _phase_finalize(self, result): ...
```

关键：`_phase_core_pipeline` 中的 `run_pipeline_from_config(...)` 调用改为 `_pkg().run_pipeline_from_config(...)`。内部嵌套函数 `_run_within_timeout` 同样使用 `_pkg().run_pipeline_from_config(...)`。

#### 2.4 创建 `brain_alpha_ops/ux/guided_pipeline/__init__.py` (~70行)

```python
"""Guided user experience layer for progress, feedback, resume, and history.

Subpackage of ``brain_alpha_ops.ux``. Splits the original
``guided_pipeline.py`` monolith into focused modules while preserving the
public API surface via re-exports.
"""
from __future__ import annotations

# 在包层级定义 _unified_classify 和 run_pipeline_from_config，
# 供测试 monkeypatch（测试通过 monkeypatch.setattr(guided_pipeline, "...") 修改）
from brain_alpha_ops.error_knowledge import classify_ux_error as _unified_classify  # noqa: F401
from brain_alpha_ops.runner import run_pipeline_from_config  # noqa: F401

# classify_error 使用 _pkg()._unified_classify，所以 monkeypatch 生效
from ._state import classify_error, logger
from ._base import GuidedPipelineBase
from ._phases import _PhasesMixin


class GuidedPipeline(GuidedPipelineBase, _PhasesMixin):
    """Guided UX pipeline wrapper around the standard pipeline."""
    pass


# Backward-compat re-exports（原 guided_pipeline.py 末尾）
from ..guided_models import (  # noqa: F401
    CheckpointData,
    PipelinePhase,
    RunRecord,
)
from ..guided_formatting import (  # noqa: F401
    format_candidate_summary,
    format_error_for_user,
    format_pipeline_progress,
)

__all__ = [
    "GuidedPipeline",
    "CheckpointData",
    "PipelinePhase",
    "RunRecord",
    "classify_error",
    "format_candidate_summary",
    "format_error_for_user",
    "format_pipeline_progress",
    "run_pipeline_from_config",
]
```

#### 2.5 删除原 `brain_alpha_ops/ux/guided_pipeline.py`

#### 2.6 更新 `tests/test_review_gap_closure_tracker.py` 第312、1349行

将 `guided_source = (ROOT / "brain_alpha_ops" / "ux" / "guided_pipeline.py").read_text(encoding="utf-8")` 改为读取包内所有 .py 文件：

```python
guided_dir = ROOT / "brain_alpha_ops" / "ux" / "guided_pipeline"
guided_source = "\n".join(
    p.read_text(encoding="utf-8") for p in sorted(guided_dir.glob("*.py"))
)
```

---

## Assumptions & Decisions

1. **`_service.py` 超 350 行**：`run_sync_job_service` 是 455 行单体函数，内部闭包重度共享可变状态，拆分会改变行为。保持原样，优先满足"行为不变"要求。
2. **`classify_error` 保留在 guided_pipeline 包中**：虽然 `guided_formatting.py` 已有相同函数，但测试 monkeypatch `guided_pipeline._unified_classify` 并期望 `guided_pipeline.classify_error` 受影响。因此 `_state.py` 中的 `classify_error` 通过 `_pkg()._unified_classify(...)` 读取包级属性。
3. **`GuidedPipeline` 定义在 `__init__.py`**：通过多继承 `GuidedPipelineBase` + `_PhasesMixin` 组合，与 `loader/` 包的 `OfficialDataLoader` 模式一致。测试 monkeypatch `guided_pipeline.GuidedPipeline` 在包层级生效。
4. **`path_modified_at` re-export 路径**：原 `sync_job.py` 末尾 `from .snapshot import path_modified_at`。包版本使用 `from ..snapshot import path_modified_at`（因为 `sync_job/` 是 `web_cloud/` 的子包，`..` 指向 `web_cloud`）。
5. **不修改任何函数签名或行为**：所有函数体原样复制到新文件，仅调整导入路径和模块级属性访问方式（`_pkg().attr` 替代直接 `attr`）。

## Verification Steps

完成所有修改后，运行以下命令验证：

```bash
# 1. 包导入验证
python3 -c "from brain_alpha_ops.web_cloud.sync_job import *; print('sync_job OK')"
python3 -c "from brain_alpha_ops.ux.guided_pipeline import *; print('guided_pipeline OK')"

# 2. 关键符号验证
python3 -c "from brain_alpha_ops.web_cloud.sync_job import run_sync_job_service, _timing_payload, _scan_observability, _cloud_scan_status_message, _final_sync_status_message, _sync_range_label, JobStoreLike, SyncJobCancelled, path_modified_at; print('sync_job symbols OK')"
python3 -c "from brain_alpha_ops.ux.guided_pipeline import GuidedPipeline, classify_error, run_pipeline_from_config, _unified_classify, CheckpointData, PipelinePhase, RunRecord, format_candidate_summary, format_error_for_user, format_pipeline_progress; print('guided_pipeline symbols OK')"

# 3. 受影响测试
python3 -m pytest tests/test_web_sync_payload.py::test_sync_modules_keep_single_job_and_payload_owners -xvs
python3 -m pytest tests/test_web_sync_job.py -xvs
python3 -m pytest tests/test_guided_pipeline.py -xvs
python3 -m pytest tests/test_guided_pipeline_coverage.py -xvs
python3 -m pytest tests/test_review_gap_closure_tracker.py::test_current_silent_exception_review_evidence_matches_source -xvs

# 4. 受影响 handler 导入验证
python3 -c "from brain_alpha_ops.web.handlers.sync import run_sync_job_service, path_modified_at; print('handler imports OK')"
python3 -c "from brain_alpha_ops.web.business.web_run_job import run_guided_job_service; print('web_run_job OK')"
```
