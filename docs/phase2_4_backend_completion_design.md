# 2.4 后端补全设计文档

> **日期**: 2026-05-15  
> **依据**: 阶段一后端缺陷清单 (35 项) + 阶段二职责边界矩阵  
> **原则**: 三层架构 (Controller → Service → Repository)，错误码统一，零静默吞异常

---

## 一、补全路线图

```
Phase A: 致命缺陷修复 (P0 × 3)
  └── check_candidate() 实现 + SSE 语法修复 + submit_batch 幂等

Phase B: 契约对齐 (P1 × 6)
  └── 新增字段 (checked_at, is_stale, label_cn, suggestion) + phase_label + error_code

Phase C: 状态机/校验补全 (P1 × 5 + P2 × 4)
  └── 状态机 BLOCKED 处理 + 配置校验 + 数据生命周期管理

Phase D: 基建增强 (P2 × 17)
  └── 日志/异常/资源管理
```

---

## 二、Phase A — 致命缺陷 (P0)

### A1: 实现 `check_candidate()` 函数

**问题**: `web.py` L419 调用不存在的函数  
**文件**: `brain_alpha_ops/web.py`

**设计**:

```python
def check_candidate(payload: dict) -> dict:
    """单条 Alpha 提交前检查，复用 check_candidate_availability 逻辑。"""
    candidate = payload.get("candidate")
    if not candidate:
        return {"ok": False, "error": "candidate not found", "error_code": "VALIDATION_ERROR"}
    
    mode = str(payload.get("mode", "quick"))
    sync_range = str(payload.get("syncRange", "3d"))
    
    run_config = run_config_from_payload(payload)
    api = api_from_run_config(run_config)
    repo = ResearchRepository(run_config.ops.storage_dir)
    api.authenticate()
    
    cloud_alphas, cloud_error = refresh_cloud_context_for_check(
        api, repo, sync_range, None, 1, mode, run_config.ops.settings.region
    )
    ledger = SubmissionLedger(run_config.ops.storage_dir)
    
    result = check_candidate_availability(candidate, mode, api, ledger, cloud_alphas, cloud_error)
    
    # 持久化检查结果
    repo.save_check_record({
        "job_id": str(payload.get("job_id", "")),
        **result,
    })
    
    return result
```

**注意**: `check_candidate_availability` 需增加 `checked_at` 时间戳注入（见 B1）。

**改动范围**: `web.py` 新增 ~25 行。

---

### A2: 修复 SSE `await` 语法错误

**问题**: `index.html` L1353-1377，非 async 回调内使用 `await`  
**文件**: `brain_alpha_ops/web/index.html`

**修复**:

```javascript
// 修复前
source.onmessage = (event) => {
  // ...
  await loadLifecycle();  // ← SyntaxError
};

// 修复后
source.onmessage = async (event) => {
  // ...
  await loadLifecycle();  // ← 正确
};
```

**改动范围**: `index.html` 1 行改动。

---

### A3: 批量提交幂等性增强

**问题**: 重试时已成功的项可能重复提交  
**文件**: `brain_alpha_ops/web.py`

**设计**:

```python
def submit_batch(payload: dict) -> dict:
    alpha_ids = [str(item) for item in payload.get("alpha_ids", []) if str(item)]
    # ... existing setup ...
    
    results = []
    submitted_set = set()  # 本次会话已成功提交的追踪
    
    for alpha_id in alpha_ids:
        if alpha_id in submitted_set:
            # 幂等：跳过已成功项
            results.append({
                "alpha_id": alpha_id,
                "ok": True, 
                "submission": {"status": "ALREADY_SUBMITTED", "message": "Already submitted in this batch"}
            })
            continue
            
        # ... existing submit logic ...
        
        if result.get("ok"):
            submitted_set.add(alpha_id)
    
    return {"ok": True, "submitted": len(submitted_set), "failed": len(alpha_ids) - len(submitted_set), "results": results}
```

**改动范围**: `web.py` submit_batch() 新增 ~5 行。

---

## 三、Phase B — 契约对齐 (P1)

### B1: Check 结果增加 `checked_at` 和 `is_stale`

**问题**: 前端 `isFreshCheck()` 需要时间戳  
**文件**: `brain_alpha_ops/web.py` (check_candidate_availability)

**设计**: 在 `check_candidate_availability` 返回 dict 中插入：

```python
from datetime import datetime, timezone, timedelta

now = datetime.now(timezone.utc).isoformat()
stale_threshold = timedelta(hours=24)

return {
    # ... existing fields ...
    "checked_at": now,
    "is_stale": False,  # 刚检查完肯定不 stale
}
```

在 `GET /api/check_results` 加载持久化结果时，动态计算 `is_stale`:

```python
def load_check_results() -> dict:
    rows = _read_storage_jsonl("checks.jsonl", limit=1000)
    for row in rows:
        checked_at = row.get("checked_at", "")
        if checked_at:
            try:
                dt = datetime.fromisoformat(checked_at)
                row["is_stale"] = (datetime.now(timezone.utc) - dt) > timedelta(hours=24)
            except (ValueError, TypeError):
                row["is_stale"] = True
    return {"results": rows}
```

---

### B2: 新增 `label_cn` 和 `suggestion` 字段

**问题**: 前端 `humanCheckName()` 仅覆盖 8/25 项  
**文件**: `brain_alpha_ops/web.py` (check_candidate_availability)

**设计**: 在 `add()` 函数中扩展为四元组：

```python
CHECK_LABELS = {
    "production_gate":      ("生产门禁", "确认 Alpha 已通过全部质量门禁"),
    "official_alpha_id":    ("官方 Alpha ID", "运行官方模拟以获取 official_alpha_id"),
    "not_failed_locally":   ("未本地失败", "检查 Alpha 生命周期状态"),
    "cloud_sync_available": ("云端同步可用", "运行云端同步以获取最新数据"),
    "not_submitted_before": ("未提交过", "检查本地提交记录"),
    "cloud_status_not_already_submitted": ("云端未提交", "云端该 Alpha 状态正常，可提交"),
    "cloud_self_correlation": ("云端自相关", "降低与已有 Alpha 的表达相似度"),
    "official_pre_submit_check": ("官方预提交检查", "执行全部检查模式以包含官方检查"),
    # BRAIN API 返回的动态检查项
    "LOW_SHARPE":           ("低 Sharpe", "提高 Alpha 风险调整后收益"),
    "LOW_FITNESS":          ("低 Fitness", "提高 Alpha 预测能力"),
    "LOW_TURNOVER":         ("低换手率", "增加 Alpha 交易信号频率"),
    "HIGH_TURNOVER":        ("高换手率", "降低换手率至 70% 以内"),
    "CONCENTRATED_WEIGHT":  ("权重集中", "降低单只股票权重至 10% 以内"),
    "SELF_CORRELATION":     ("自相关", "降低与自身历史收益的相关性"),
    "LOW_SUB_UNIVERSE_SHARPE": ("子宇宙低 Sharpe", "提高在子宇宙中的表现一致性"),
}

def add(name, passed, detail):
    label_cn, suggestion = CHECK_LABELS.get(name, (name, "请联系技术支持"))
    checks.append({
        "name": name,
        "label_cn": label_cn,
        "passed": bool(passed),
        "detail": detail,
        "suggestion": suggestion if not passed else "",
    })
```

---

### B3: 后端返回 `phase_label` 中文字段

**问题**: 前端 `phaseName()` 硬编码 25 项映射  
**文件**: `brain_alpha_ops/web.py` (progress 对象构造处)

**设计**: 在构建 progress dict 时附带 `phase_label`:

```python
PHASE_LABELS = {
    "queued": "排队",
    "auth": "认证",
    "scan": "扫描",
    "merge": "合并",
    "startup": "启动",
    "cloud_sync": "云端数据同步",
    "context": "加载上下文",
    "production_loop": "循环生产",
    "local_scoring": "本地评分排序",
    "candidate_pool": "候选池维护",
    "official_validation": "回测前预检",
    "official_simulation": "官方模拟回测",
    "checking": "批量检查",
    "submitting": "提交",
    "completed": "已完成",
    "stopped": "已停止",
    "failed": "失败",
    "stopping": "正在停止",
}

# 在 progress 构建时
progress["phase_label"] = PHASE_LABELS.get(phase, phase)
```

**改动范围**: `web.py` 进度构建处 + `run_job`/`run_sync_job`/`run_check_batch_job`。

---

### B4: 统一 error_code 返回

**问题**: 当前错误响应无机器可读 error_code  
**文件**: `brain_alpha_ops/web.py` (全线 POST handler)

**设计**: 所有 error 响应增加 `error_code`:

```python
# 示例改造
self._json({
    "ok": False, 
    "error": "已有生产任务正在运行，请先停止当前任务。",
    "error_code": "CONFLICT_RUNNING",
    "job_id": active_job_id
}, status=409)
```

**改动范围**: web.py 全线 error 响应点 ~15 处。

---

### B5: 后端消费 `continuousMode` 字段

**问题**: 前端传 `continuousMode` 但后端 `run_config_from_payload` 不消费  
**文件**: `brain_alpha_ops/web.py` (run_config_from_payload)

**设计**:

```python
# 在 run_config_from_payload 中增加
if "continuousMode" in payload:
    run_config.ops.budget.run_forever = bool(payload["continuousMode"])
```

---

### B6: 后端 stats 字段补充

**问题**: 前端 `needsCheckCount()` / `staleCheckCount()` 等遍历计算  
**文件**: pipeline 或 web.py progress.data 构建处

**设计**: 在 progress.data 中增加：

```python
"stats": {
    "needs_check_count": len([c for c in passed if c not in checked]),
    "stale_check_count": len([c for c in checked if is_stale(c)]),
    "active_backtests": sum(1 for b in backtests if b.get("status") == "active"),
    "validation_tile": f"{validated_passed}/{validated_attempted}",
    "production_note": f"第 {cycle} 轮" + (f"；本地继续，官方调用暂停" if halt_reason else ""),
}
```

---

## 四、Phase C — 状态机/校验补全

### C1: BLOCKED 状态在生命周期中可见

**问题**: `lifecycle_from_job()` 中 BLOCKED 记录无法被前端匹配  
**文件**: `brain_alpha_ops/web.py`

**设计**: 在 `lifecycle_from_job` 返回的每条记录中增加 `status_category`:

```python
def status_category(status, stage):
    status_upper = str(status).strip().upper()
    if "BLOCKED" in status_upper or stage == "submission_blocked":
        return "blocked"
    if status_upper in {"SUBMITTED", "ACTIVE", "PRODUCTION", "CONDUCTED"}:
        return "submitted"
    if any(word in status_upper for word in ("FAILED", "REJECTED")):
        return "failed"
    if any(word in status_upper for word in ("PASSED", "READY")):
        return "passed"
    return "other"
```

**改动范围**: web.py ~20 行。

---

### C2: 配置校验增强

**问题**: `run_config_from_payload` 不校验 settings 字段合法性  
**文件**: `brain_alpha_ops/web.py`

**设计**:

```python
VALID_REGIONS = {"USA", "CHN", "EUR", "GLB"}
VALID_UNIVERSES = {"TOP3000", "TOP1000", "TOP500"}
VALID_NEUTRALIZATIONS = {"SUBINDUSTRY", "INDUSTRY", "SECTOR", "MARKET", "NONE"}
VALID_TYPES = {"REGULAR", "POWER_POOL", "ATOM", "PYRAMID"}

def validate_settings(settings: dict) -> list[str]:
    errors = []
    if settings.get("region") not in VALID_REGIONS:
        errors.append(f"Invalid region: {settings.get('region')}")
    if settings.get("universe") not in VALID_UNIVERSES:
        errors.append(f"Invalid universe: {settings.get('universe')}")
    if settings.get("neutralization") not in VALID_NEUTRALIZATIONS:
        errors.append(f"Invalid neutralization: {settings.get('neutralization')}")
    if settings.get("type") not in VALID_TYPES:
        errors.append(f"Invalid alpha type: {settings.get('type')}")
    # ... more validations
    return errors
```

---

### C3: Fields/Operators 刷新失败不再静默

**问题**: `_refresh_context()` 异常被 pass 吞掉  
**文件**: `brain_alpha_ops/research/pipeline.py`

**设计**:

```python
try:
    fields = api.list_fields(...)
    operators = api.list_operators(...)
except Exception as exc:
    logger.warning("Failed to refresh fields/operators: %s", exc)
    # 使用缓存中的旧数据（如果存在）
    if not cached_fields:
        raise ContextRefreshError("No cached context available") from exc
```

---

### C4: 大文件生命周期管理

**问题**: `lifecycle.jsonl` (28MB) 无归档策略  
**文件**: `brain_alpha_ops/research/repository.py`

**设计**:

```python
MAX_LIFECYCLE_SIZE_MB = 50
MAX_LIFECYCLE_AGE_DAYS = 30

def maybe_archive_lifecycle(self):
    path = self._jsonl_path("lifecycle.jsonl")
    if not path.exists():
        return
    size_mb = path.stat().st_size / (1024 * 1024)
    if size_mb > MAX_LIFECYCLE_SIZE_MB:
        archive_path = path.with_name(f"lifecycle_{datetime.now().strftime('%Y%m%d')}.jsonl")
        path.rename(archive_path)
        # 清理超过 MAX_LIFECYCLE_AGE_DAYS 的归档
        for old in sorted(self.storage_dir.glob("lifecycle_*.jsonl")):
            age = (datetime.now() - datetime.fromtimestamp(old.stat().st_mtime)).days
            if age > MAX_LIFECYCLE_AGE_DAYS:
                old.unlink()
```

---

## 五、Phase D — 基建增强

### D1: 预设配置外部化

**文件**: 新增 `config/presets.json`

```json
{
  "usa_standard": {
    "label": "美股标准生产",
    "settings": {
      "region": "USA", "universe": "TOP3000", "delay": 1,
      "neutralization": "SUBINDUSTRY", "decay": 10, "truncation": 0.05,
      "pasteurization": "ON", "unitHandling": "VERIFY",
      "nanHandling": "ON", "instrumentType": "EQUITY", "type": "REGULAR", "language": "FASTEXPR"
    }
  },
  "usa_liquid": { "label": "美股高流动性", "settings": {...} },
  "usa_sector": { "label": "美股 Sector Neutral", "settings": {...} },
  "usa_market": { "label": "美股 Market Neutral", "settings": {...} },
  "europe_standard": { "label": "欧洲标准生产", "settings": {...} },
  "global_market": { "label": "全球 Market Neutral", "settings": {...} },
  "china_standard": { "label": "中国市场标准生产", "settings": {...} }
}
```

**API**: 新增 `GET /api/presets` → 返回预设列表。

---

### D2: 异常处理统一

**文件**: 新增 `brain_alpha_ops/errors.py`

```python
class AppError(Exception):
    def __init__(self, message: str, code: str, status_code: int = 500):
        self.message = message
        self.code = code
        self.status_code = status_code
        super().__init__(message)

class ValidationError(AppError):
    def __init__(self, message: str):
        super().__init__(message, "VALIDATION_ERROR", 400)

class AuthError(AppError):
    def __init__(self, message: str):
        super().__init__(message, "AUTH_FAILED", 401)

class SubmitBlockedError(AppError):
    def __init__(self, message: str):
        super().__init__(message, "SUBMIT_BLOCKED", 400)
```

---

## 六、补全优先级与估算

| 阶段 | 子任务 | 预计改动 | 文件 | 预计工时 |
|------|--------|---------|------|---------|
| A | check_candidate() 实现 | +25 行 | web.py | 1h |
| A | SSE await 修复 | 1 行 | index.html | 5min |
| A | submit_batch 幂等 | +5 行 | web.py | 30min |
| B | checked_at/is_stale 字段 | +15 行 | web.py | 30min |
| B | label_cn + suggestion 补全 | +30 行 | web.py | 1h |
| B | phase_label 中文化 | +20 行 | web.py | 30min |
| B | error_code 统一 | ~15 处 | web.py | 1h |
| B | continuousMode 消费 | +3 行 | web.py | 10min |
| B | stats 字段补充 | +20 行 | pipeline/web | 1h |
| C | BLOCKED status_category | +20 行 | web.py | 30min |
| C | 配置校验 | +30 行 | web.py | 30min |
| C | context 刷新非静默 | +5 行 | pipeline.py | 15min |
| C | 文件归档策略 | +25 行 | repository.py | 1h |
| D | 预设配置外部化 | +40 行 | config/ + web | 1h |
| D | 异常类层次 | +30 行 | errors.py | 30min |

**总计**: ~280 行新增，~20 处修改，预计 10h。

---

## 七、测试要点

| 测试场景 | 验证点 |
|---------|--------|
| 单条检查 | `POST /api/check` 返回完整 result + label_cn + checked_at |
| 批量检查 | `GET /api/check_status` items 含 label_cn |
| 检查恢复 | `GET /api/check_results` 老数据 is_stale 正确计算 |
| 批量提交 | 重试时已成功项返回 `ALREADY_SUBMITTED` |
| 配置校验 | 非法 region/type 返回 `VALIDATION_ERROR` |
| BLOCKED 视图 | lifecycle 中 blocked 记录含 `status_category: "blocked"` |
| 大文件归档 | lifecycle.jsonl > 50MB 时自动归档 |
| 预设加载 | `GET /api/presets` 返回 7 套预设 |
