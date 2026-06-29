"""趋势数据持久化 API。

P1-7: 提供趋势数据的写入（JSONL 追加）和读取（按天数过滤）功能。
数据文件位于 ``brain_alpha_ops/data/trends.jsonl``，每行一条 JSON 记录。
"""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime

_TRENDS_FILE = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "trends.jsonl"
)

_DEFAULT_DAYS = 30
_MAX_POINTS = 90

# Serialize concurrent appends so the JSONL file does not get interleaved
# records when multiple pipeline runs / web handlers call record_trend at
# the same time.
_TRENDS_LOCK = threading.Lock()


def get_trends(days: int = _DEFAULT_DAYS) -> list[dict]:
    """返回最近 N 天的趋势数据，最多返回 ``_MAX_POINTS`` 条。

    Args:
        days: 回溯天数，默认 30 天。

    Returns:
        list[dict]: 趋势记录列表，每条记录包含 date, ts, candidates, submissions, cycles 字段。
    """
    if not os.path.exists(_TRENDS_FILE):
        return []
    results: list[dict] = []
    cutoff = time.time() - days * 86400
    with open(_TRENDS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            if row.get("ts", 0) >= cutoff:
                results.append(row)
    # 按时间升序并限制最大条数
    results.sort(key=lambda r: r.get("ts", 0))
    return results[-_MAX_POINTS:]


def record_trend(
    candidates: int,
    submissions: int,
    completed_cycles: int = 0,
) -> None:
    """追加一条趋势记录到 JSONL 文件。

    Args:
        candidates: 当前候选总数。
        submissions: 当前提交总数。
        completed_cycles: 已完成的生产周期数（可选）。
    """
    os.makedirs(os.path.dirname(_TRENDS_FILE), exist_ok=True)
    record = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "ts": time.time(),
        "candidates": candidates,
        "submissions": submissions,
        "cycles": completed_cycles,
    }
    with _TRENDS_LOCK:
        with open(_TRENDS_FILE, "a", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False)
            f.write("\n")
