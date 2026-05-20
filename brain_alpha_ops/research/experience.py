"""经验学习系统 — 从官方回测结果中提炼高分 Alpha 的共同模式。

自动记录每次官方回测的特征（字段集、算子集、窗口值等），
提炼高分 Alpha 的共享模式，指导后续生成。

Data source: 所有特征来源于 BRAIN 官方 API 返回的实际指标。

Usage::

    from brain_alpha_ops.research.experience import record_alpha_result, get_winning_patterns

    # 每次拿到官方回测结果后记录
    record_alpha_result(candidate, storage_dir="data")

    # 提炼高分模式
    patterns = get_winning_patterns("data", min_sharpe=2.0)
    print(patterns["field_combinations"])
    print(patterns["top_operators"])
    print(patterns["preferred_windows"])
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple, TYPE_CHECKING

from brain_alpha_ops.jsonl import read_jsonl_records

if TYPE_CHECKING:
    from brain_alpha_ops.models import Candidate


DEFAULT_HISTORY_LIMIT = 5000


def _num(value: Any) -> float:
    try:
        if value in (None, ""):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _ratio(value: Any) -> float:
    numeric = _num(value)
    return numeric / 100.0 if abs(numeric) > 1.0 else numeric


# ── Record ──

def record_alpha_result(
    candidate: "Candidate",
    storage_dir: str = "data",
) -> None:
    """记录 Alpha 官方回测结果的特征到经验数据库。

    写入 data/alpha_features.jsonl，每行一个 JSON 记录。

    特征来源均为 BRAIN 官方 API 返回的实际数据：
      - field_set: 表达式使用的字段（来自 OfficialDataLoader 校验）
      - operator_set: 表达式使用的算子（来自 BRAIN /operators API）
      - window_values: 表达式中的数值参数
      - 各指标: sharpe/fitness/turnover/correlation/margin（来自模拟结果）

    P1 AB 对照：当 candidate 有 parent_id 时，自动查找父 Alpha 的官方结果
    并记录对比数据到 ab_tests.jsonl。
    """
    metrics = candidate.official_metrics or {}
    if not metrics:
        return

    # Extract windows from expression
    window_values = [int(v) for v in re.findall(r"\b(\d+)\b", candidate.expression) if 3 <= int(v) <= 252]

    features: Dict[str, Any] = {
        "alpha_id": candidate.alpha_id,
        "official_alpha_id": candidate.official_alpha_id or "",
        "expression": candidate.expression,
        "family": candidate.family,
        "field_set": sorted(candidate.data_fields or []),
        "operator_set": sorted(candidate.operators or []),
        "window_values": sorted(window_values),
        # Official metrics (sourced from BRAIN API normalize_metrics)
        "sharpe": _num(metrics.get("sharpe")),
        "fitness": _num(metrics.get("fitness")),
        "turnover": _ratio(metrics.get("turnover")),
        "returns": _num(metrics.get("returns", 0)),
        "correlation": abs(_ratio(metrics.get("correlation"))),
        "margin": _num(metrics.get("margin", 0)),
        "weight_concentration": _ratio(metrics.get("weight_concentration")),
        "sub_universe_sharpe": _num(metrics.get("sub_universe_sharpe", 0)),
        "pass_fail": metrics.get("pass_fail", "UNKNOWN"),
        # Source tracking
        "source": "BRAIN_official_simulation_result",
    }

    # P1: 记录 parent 信息用于 AB 对照
    if candidate.parent_id:
        features["parent_id"] = candidate.parent_id
        features["mutation_type"] = candidate.mutation_type or "unknown"

    path = os.path.join(storage_dir, "alpha_features.jsonl")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(features, ensure_ascii=False) + "\n")

    # ── P1: AB 对照 — 如果候选 Alpha 有父 Alpha，对比效果 ──
    if candidate.parent_id:
        _record_ab_comparison(candidate, storage_dir)


# ── Query ──

def get_winning_patterns(
    storage_dir: str = "data",
    min_sharpe: float = 1.0,
    min_fitness: float = 0.5,
    min_sample: int = 3,
    history_limit: int = DEFAULT_HISTORY_LIMIT,
) -> Dict[str, Any]:
    """提炼高分 Alpha 的共同特征模式。

    参数:
        storage_dir: 数据目录
        min_sharpe: 最低 Sharpe 阈值（筛选"高分"Alpha）
        min_fitness: 最低 Fitness 阈值
        min_sample: 最少样本数（样本不足时返回空模式）

    返回:
        {
            "sample_size": int,
            "total_records": int,
            "field_combinations": [{fields: [...], count: int, avg_sharpe: float}],
            "top_operators": [str],
            "preferred_windows": [int],
            "top_categories": [str],
            "summary": str,
        }
    """
    path = os.path.join(storage_dir, "alpha_features.jsonl")
    if not os.path.exists(path):
        return _empty_patterns("No experience database found — run official simulations first.")

    records = _load_records(path, limit=history_limit)
    if not records:
        return _empty_patterns("Experience database is empty.")

    total = len(records)

    # Filter: "winning" alphas
    winners = [
        r for r in records
        if r.get("pass_fail") == "PASS"
        and r.get("sharpe", 0) >= min_sharpe
        and r.get("fitness", 0) >= min_fitness
    ]

    if len(winners) < min_sample:
        return _empty_patterns(
            f"Only {len(winners)} winning alpha(s) with Sharpe >= {min_sharpe}, need {min_sample}+."
        )

    # ── Field combinations ──
    field_combos = Counter(
        tuple(sorted(r.get("field_set", [])))
        for r in winners
        if len(r.get("field_set", [])) >= 2
    ).most_common(5)

    # ── Top operators ──
    operator_counter = Counter(
        op for r in winners for op in r.get("operator_set", [])
    )
    top_operators = [op for op, _ in operator_counter.most_common(10)]

    # ── Preferred windows ──
    window_counter = Counter(
        w for r in winners for w in r.get("window_values", [])
    )
    preferred_windows = [w for w, _ in window_counter.most_common(5)]

    # ── Top families ──
    family_counter = Counter(r.get("family", "unknown") for r in winners)
    top_categories = [cat for cat, _ in family_counter.most_common(5)]

    # ── Avg metrics for winners ──
    avg_sharpe = sum(r.get("sharpe", 0) for r in winners) / len(winners)
    avg_fitness = sum(r.get("fitness", 0) for r in winners) / len(winners)

    return {
        "sample_size": len(winners),
        "total_records": total,
        "history_limit": history_limit,
        "avg_sharpe": round(avg_sharpe, 3),
        "avg_fitness": round(avg_fitness, 3),
        "field_combinations": [
            {"fields": list(f), "count": c, "avg_sharpe": round(
                sum(r.get("sharpe", 0) for r in winners if tuple(sorted(r.get("field_set", []))) == f) / max(c, 1), 3
            )}
            for f, c in field_combos
        ],
        "top_operators": top_operators,
        "preferred_windows": preferred_windows,
        "top_categories": top_categories,
        "source": "BRAIN_official_simulation_results",
        "summary": (
            f"From {total} total records, {len(winners)} winning alphas (Sharpe >= {min_sharpe}). "
            f"Avg Sharpe={avg_sharpe:.3f}, Avg Fitness={avg_fitness:.3f}. "
            f"Top operators: {', '.join(top_operators[:5])}. "
            f"Preferred windows: {preferred_windows}."
        ),
    }


def _load_records(path: str, *, limit: int | None = DEFAULT_HISTORY_LIMIT) -> List[Dict[str, Any]]:
    return read_jsonl_records(path, limit=limit)


def _empty_patterns(reason: str) -> Dict[str, Any]:
    return {
        "sample_size": 0,
        "total_records": 0,
        "avg_sharpe": 0.0,
        "avg_fitness": 0.0,
        "field_combinations": [],
        "top_operators": [],
        "preferred_windows": [],
        "top_categories": [],
        "source": "BRAIN_official_simulation_results",
        "summary": reason,
    }


# ═══════════════════════════════════════════════════════════════════════
# P1: AB 对照 — 变异的因果效果评估
# ═══════════════════════════════════════════════════════════════════════

def _record_ab_comparison(
    mutant: "Candidate",
    storage_dir: str = "data",
) -> None:
    """对比变异前后的 Alpha 官方模拟结果，记录到 ab_tests.jsonl。

    在 alpha_features.jsonl 中查找 parent_id 对应的父 Alpha 结果。
    如果找到，写入对比记录。
    """
    parent_id = mutant.parent_id
    if not parent_id:
        return
    mutation_type = mutant.mutation_type or "unknown"

    # 查找父 Alpha 的结果
    features_path = os.path.join(storage_dir, "alpha_features.jsonl")
    if not os.path.exists(features_path):
        return

    parent_record = None
    records = _load_records(features_path, limit=DEFAULT_HISTORY_LIMIT)
    for r in records:
        if r.get("alpha_id") == parent_id or r.get("official_alpha_id") == parent_id:
            parent_record = r
            break

    if not parent_record:
        return  # 父 Alpha 尚未有官方结果

    # 对比指标
    mutant_metrics = mutant.official_metrics or {}
    mutation_display = (
        (mutant.expression[:80] + "…")
        if len(mutant.expression) > 80
        else mutant.expression
    )

    comparison = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "parent_id": parent_id,
        "mutant_id": mutant.alpha_id,
        "mutation_type": mutation_type,
        "mutation_display": mutation_display,
        # Parent metrics
        "parent_sharpe": _num(parent_record.get("sharpe")),
        "parent_fitness": _num(parent_record.get("fitness")),
        "parent_turnover": _ratio(parent_record.get("turnover")),
        "parent_margin": _num(parent_record.get("margin")),
        "parent_pass_fail": parent_record.get("pass_fail", "UNKNOWN"),
        # Mutant metrics
        "mutant_sharpe": _num(mutant_metrics.get("sharpe")),
        "mutant_fitness": _num(mutant_metrics.get("fitness")),
        "mutant_turnover": _ratio(mutant_metrics.get("turnover")),
        "mutant_margin": _num(mutant_metrics.get("margin", 0)),
        "mutant_pass_fail": mutant_metrics.get("pass_fail", "UNKNOWN"),
        # Improvement
        "sharpe_delta": round(
            _num(mutant_metrics.get("sharpe")) - _num(parent_record.get("sharpe")), 4
        ),
        "fitness_delta": round(
            _num(mutant_metrics.get("fitness")) - _num(parent_record.get("fitness")), 4
        ),
        "turnover_delta": round(
            _ratio(mutant_metrics.get("turnover")) - _ratio(parent_record.get("turnover")), 4
        ),
        "margin_delta": round(
            _num(mutant_metrics.get("margin", 0)) - _num(parent_record.get("margin")), 4
        ),
        "improved": (
            _num(mutant_metrics.get("sharpe")) > _num(parent_record.get("sharpe"))
        ),
    }

    ab_path = os.path.join(storage_dir, "ab_tests.jsonl")
    os.makedirs(os.path.dirname(ab_path), exist_ok=True)
    with open(ab_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(comparison, ensure_ascii=False) + "\n")


def get_mutation_effectiveness(
    storage_dir: str = "data",
    min_samples: int = 3,
    history_limit: int = DEFAULT_HISTORY_LIMIT,
) -> Dict[str, Any]:
    """统计各 mutation_type 的改进效果。

    从 ab_tests.jsonl 中汇总每种变异模式的平均 Sharpe 提升、成功率等。

    返回:
        {
            "total_comparisons": int,
            "by_mutation_type": {...},
            "summary": str,
        }
    """
    ab_path = os.path.join(storage_dir, "ab_tests.jsonl")
    if not os.path.exists(ab_path):
        return {"total_comparisons": 0, "by_mutation_type": {}, "summary": "No AB test data."}

    records = _load_records(ab_path, limit=history_limit)
    if not records:
        return {"total_comparisons": 0, "by_mutation_type": {}, "summary": "AB test database empty."}

    by_type: Dict[str, Dict[str, Any]] = {}
    for r in records:
        mtype = r.get("mutation_type", "unknown")
        if mtype not in by_type:
            by_type[mtype] = {
                "count": 0, "improvements": 0,
                "avg_sharpe_delta": 0.0, "avg_fitness_delta": 0.0,
                "avg_turnover_delta": 0.0, "avg_margin_delta": 0.0,
            }
        info = by_type[mtype]
        info["count"] += 1
        if r.get("improved"):
            info["improvements"] += 1
        info["avg_sharpe_delta"] += r.get("sharpe_delta", 0)
        info["avg_fitness_delta"] += r.get("fitness_delta", 0)
        info["avg_turnover_delta"] += r.get("turnover_delta", 0)
        info["avg_margin_delta"] += r.get("margin_delta", 0)

    for mtype, info in by_type.items():
        n = max(info["count"], 1)
        info["improvement_rate"] = round(info["improvements"] / n, 3)
        info["avg_sharpe_delta"] = round(info["avg_sharpe_delta"] / n, 4)
        info["avg_fitness_delta"] = round(info["avg_fitness_delta"] / n, 4)
        info["avg_turnover_delta"] = round(info["avg_turnover_delta"] / n, 4)
        info["avg_margin_delta"] = round(info["avg_margin_delta"] / n, 4)

    total = len(records)
    total_improved = sum(1 for r in records if r.get("improved"))

    return {
        "total_comparisons": total,
        "total_improvement_rate": round(total_improved / max(total, 1), 3),
        "history_limit": history_limit,
        "by_mutation_type": {
            mtype: info
            for mtype, info in sorted(
                by_type.items(),
                key=lambda x: x[1].get("avg_sharpe_delta", 0),
                reverse=True,
            )
        },
        "source": "BRAIN_official_simulation_AB_comparisons",
        "summary": (
            f"From {total} AB comparisons: {total_improved} improved "
            f"({total_improved/max(total,1)*100:.1f}%). "
            f"Most effective mutation: "
            f"{max(by_type.items(), key=lambda x: x[1].get('avg_sharpe_delta', 0))[0] if by_type else 'N/A'}."
        ),
    }


# ── Hypothesis Weight Feedback ──────────────────────────────────────

def update_hypothesis_weights(
    library: Any,
    min_sharpe: float = 1.0,
    min_sample: int = 3,
    storage_dir: str = "data",
    history_limit: int = DEFAULT_HISTORY_LIMIT,
) -> Dict[str, Any]:
    """Update hypothesis experience weights based on winning alpha patterns.

    Reads alpha_features.jsonl to identify winner alphas, then computes
    winner ratios per hypothesis/field/expression_family and calls
    HypothesisLibrary.update_weights() with EMA smoothing.

    Parameters
    ----------
    library:
        An instance of HypothesisLibrary (from hypothesis_library.py).
    min_sharpe:
        Minimum Sharpe ratio to qualify as a "winner".
    min_sample:
        Minimum number of winners required before updating weights.
    storage_dir:
        Directory containing alpha_features.jsonl.

    Returns
    -------
    dict with keys:
        updated_hypotheses: list of updated hypothesis IDs
        winner_count: total number of winner records
        total_records: total records scanned
        summary: str
    """
    path = os.path.join(storage_dir, "alpha_features.jsonl")
    if not os.path.exists(path):
        return {
            "updated_hypotheses": [],
            "winner_count": 0,
            "total_records": 0,
            "summary": f"No experience database found at {path}.",
        }

    records = _load_records(path, limit=history_limit)
    if not records:
        return {
            "updated_hypotheses": [],
            "winner_count": 0,
            "total_records": 0,
            "summary": "Experience database is empty.",
        }

    total = len(records)

    # Filter winners
    winners = [
        r for r in records
        if r.get("pass_fail") == "PASS"
        and r.get("sharpe", 0) >= min_sharpe
    ]
    if len(winners) < min_sample:
        return {
            "updated_hypotheses": [],
            "winner_count": len(winners),
            "total_records": total,
            "summary": (
                f"Only {len(winners)} winners (Sharpe >= {min_sharpe}), "
                f"need {min_sample}+ to update weights."
            ),
        }

    winner_count = len(winners)

    # For each hypothesis in the library, compute winner ratios
    all_hypothesis_ids = library.get_ids() if hasattr(library, 'get_ids') else []
    updated_ids: List[str] = []

    for hyp_id in all_hypothesis_ids:
        hyp = library.get_by_id(hyp_id) if hasattr(library, 'get_by_id') else None
        if hyp is None:
            continue

        # Compute field category winner ratios
        field_cat_weights: Dict[str, float] = {}
        for fc in hyp.field_categories:
            # Count winners that used fields matching this category
            # Look in record field_set for category examples or partial matches
            matched = 0
            for r in winners:
                r_fields = [str(f).lower() for f in r.get("field_set", [])]
                examples = [str(e).lower() for e in fc.examples]
                # Match if any example or category keyword appears in record fields
                if any(
                    ex in " ".join(r_fields) or fc.category.lower() in " ".join(r_fields)
                    for ex in examples
                ):
                    matched += 1
            ratio = matched / winner_count if winner_count > 0 else 0.0
            field_cat_weights[fc.category] = ratio

        # Compute expression family winner ratios
        expr_fam_weights: Dict[str, float] = {}
        for ef in hyp.expression_families:
            # Look for structure keywords in winning expressions
            structure_keywords = set(re.findall(r'\b\w+\b', ef.structure.lower()))
            structure_keywords.discard('f1')
            structure_keywords.discard('f2')
            structure_keywords.discard('field')
            structure_keywords.discard('window')
            structure_keywords.discard('w')

            matched = 0
            for r in winners:
                expr = str(r.get("expression", "")).lower()
                if any(kw in expr for kw in structure_keywords if len(kw) > 2):
                    matched += 1
            ratio = matched / winner_count if winner_count > 0 else 0.0
            expr_fam_weights[ef.id] = ratio

        # Compute window winner ratios
        window_weights: Dict[str, float] = {}
        window_counter: Dict[int, int] = {}
        for r in winners:
            for w_str in r.get("window_values", []):
                try:
                    w = int(w_str)
                    window_counter[w] = window_counter.get(w, 0) + 1
                except (TypeError, ValueError):
                    continue
        for w, cnt in window_counter.items():
            window_weights[str(w)] = cnt / winner_count if winner_count > 0 else 0.0

        # Update library weights
        if hasattr(library, 'update_weights'):
            library.update_weights(
                hyp_id,
                field_cat_weights=field_cat_weights,
                expr_fam_weights=expr_fam_weights,
                window_weights=window_weights,
            )
        updated_ids.append(hyp_id)

    return {
        "updated_hypotheses": updated_ids,
        "winner_count": winner_count,
        "total_records": total,
        "summary": (
            f"Updated {len(updated_ids)} hypotheses based on {winner_count} winners "
            f"(from {total} total records, min_sharpe={min_sharpe})."
        ),
    }
