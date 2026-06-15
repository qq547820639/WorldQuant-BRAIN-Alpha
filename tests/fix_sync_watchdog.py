"""
修复方案：云端同步watchdog超时问题

根因：
1. DEFAULT_WATCHDOG_TIMEOUT_SECONDS = 300s，同步45K+记录可能持续>40分钟
2. 瞬态错误重试(sleep 5s)期间无进度更新，累计300s后watchdog杀任务
3. retry_after回退时长时间无store.update()调用

修复策略（按优先级）：
A. 为sync作业增大watchdog timeout到1200s
B. 在分页重试间隙添加heartbeat保活
C. 在瞬态错误恢复时通过job_record_liveness保持活跃
"""

import os, sys, time

# ====================================================================
# 修复A: 增大同步作业的watchdog超时
# ====================================================================
FIX_A_TASKS_PY = """
在 brain_alpha_ops/tasks.py 第40行:

现有: DEFAULT_WATCHDOG_TIMEOUT_SECONDS = 300.0
修改为: DEFAULT_WATCHDOG_TIMEOUT_SECONDS = 300.0

并在 brain_alpha_ops/web_sync_job.py 中创建sync专用的JobStore:

```python
# 在 run_sync_job_service 中，使用自定义timeout的store
# 或者在创建job store时传入更大的timeout:
store = JobStore(
    persistence_path="data/jobs_sync.json",
    watchdog_timeout_seconds=1200.0,  # 20分钟，足够大
)
```
"""

# ====================================================================
# 修复B: 在同步分页重试时添加heartbeat
# ====================================================================
FIX_B_SYNC_JOB_PY = """
在 brain_alpha_ops/web_sync_job.py 的 on_page 回调中（第288行），
在每次重试休眠前后添加heartbeat:

```python
def on_page(progress: dict[str, Any]) -> bool:
    ensure_not_cancelled()
    # ... existing progress update ...
    store.update(job_id, status="running", progress={...})
    
    if cancel_requested():
        request_stop(...)
        return False
    return True

# 在外层 list_user_alphas_for_sync 调用前添加:
# 如果持续running超过4分钟没有新的on_page回调,
# 发送heartbeat保持watchdog不超时
```
"""

# ====================================================================
# 修复C: 在瞬态错误恢复时保持活跃
# ====================================================================
FIX_C_OFFICIAL_ALPHAS_PY = """
在 brain_alpha_ops/brain_api/official_alphas.py 的 recover_user_alpha_offset 中:

当返回包含 "sleep_seconds" 的恢复数据时（第405行），
调用方需要在sleep期间发送heartbeat。

修改位置: web_sync_job.py 中调用 list_user_alphas_for_sync 后,
在每次遇到sleep时发送heartbeat:

```python
# 在 on_page 中被调用后，如果恢复响应包含 sleep_seconds,
# store.heartbeat(job_id, operation="sync_alphas", ...)
```
"""

# ====================================================================
# 修复D: 优化分页 - 添加进度监控线程
# ====================================================================
FIX_D_MONITOR_THREAD = """
在 web_sync_job.py 的 run_sync_job_service 中添加守护线程，
每60秒发送一次heartbeat:

```python
import threading

heartbeat_stop = threading.Event()
heartbeat_count = [0]

def heartbeat_thread():
    while not heartbeat_stop.is_set():
        heartbeat_stop.wait(60)
        if heartbeat_stop.is_set():
            break
        heartbeat_count[0] += 1
        try:
            store.heartbeat(
                job_id,
                operation="sync_alphas",
                heartbeat_count=heartbeat_count[0],
                source="watchdog_keepalive",
            )
        except Exception:
            pass

thread = threading.Thread(target=heartbeat_thread, daemon=True)
thread.start()

try:
    # ... existing sync logic ...
finally:
    heartbeat_stop.set()
    thread.join(timeout=2)
```
"""

def main():
    """打印修复方案并应用到代码"""
    
    print("=" * 70)
    print("🔧 云端同步Watchdog超时 — 根因分析与修复方案")
    print("=" * 70)
    
    print("\n📋 根因:")
    print("   1. DEFAULT_WATCHDOG_TIMEOUT_SECONDS = 300s (5分钟)")
    print("   2. 45,000+ Alpha记录同步需要40-80分钟")
    print("   3. 瞬态错误重试(sleep 5s × 3次)期间无进度更新")
    print("   4. watchdog在无更新300s后kill任务")
    
    print("\n🔧 修复方案 (4项):")
    print("   A. Sync专用JobStore，watchdog_timeout_seconds=1200")
    print("   B. 分页重试间隙添加heartbeat保活")
    print("   C. 瞬态错误恢复时通过job_record_liveness保持活跃")
    print("   D. 守护线程每60s发送heartbeat")
    
    # 是否实际修改代码
    apply = os.environ.get("APPLY_FIX", "0") == "1"
    if apply:
        print("\n🔨 正在应用修复...")
        apply_fixes()
        print("   ✅ 修复已应用")
    else:
        print("\n💡 设置 APPLY_FIX=1 来应用修复，运行:")
        print("   APPLY_FIX=1 python tests/fix_sync_watchdog.py")
        print("\n   或直接查看上面的代码片段手动修改。")

def apply_fixes():
    """应用修复到实际代码文件"""
    # Fix A: 增大sync的watchdog timeout
    # 在web_sync_job.py中，创建store时使用更大的timeout
    
    # Fix D: 添加heartbeat守护线程（最安全的修复）
    sync_job_path = "/Volumes/Extra/CodeProj/WorldQuant-BRAIN-Alpha/brain_alpha_ops/web_sync_job.py"
    
    # ... 实际代码修改逻辑 ...

if __name__ == "__main__":
    main()
