"""Pipeline audit: run Round 7 candidates through FULL quality funnel.

Covers: prior_score → empirical_score → build_scorecard → evaluate_quality_gate.
Answers: how many "gold" alphas actually survive all quality gates?
"""
import json, sys
from pathlib import Path
from dataclasses import dataclass
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))

from brain_alpha_ops.config import load_run_config
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.scoring import build_scorecard, evaluate_quality_gate
from brain_alpha_ops.research.generator import extract_fields, extract_operators

# ═══════════════════════════════════════════════════════════════
# 1. Load Round 7 results
# ═══════════════════════════════════════════════════════════════
results_path = Path("experiments/_r7_reconstructed.json")
if not results_path.exists():
    print("ERROR: _intermediate_results.json not found")
    sys.exit(1)

data = json.loads(results_path.read_text(encoding="utf-8"))
completed = [r for r in data["results"] if r["status"] == "completed"]
print(f"Loaded {len(completed)} completed candidates from Round 7")

config = load_run_config()
thresholds = config.ops.thresholds
scoring_cfg = config.ops.scoring

# ═══════════════════════════════════════════════════════════════
# 2. Build Candidate objects with full metrics
# ═══════════════════════════════════════════════════════════════
candidates: list[Candidate] = []
for r in completed:
    expr = r["expression"]
    c = Candidate(
        alpha_id=f"r7_{r['index']}",
        expression=expr,
        family="r7_experiment",
        hypothesis=f"Round 7 auto-generated alpha #{r['index']}",
        data_fields=extract_fields(expr) or [],
        operators=extract_operators(expr) or [],
    )
    # Attach BRAIN metrics — prefer full_metrics if available
    fm = r.get("full_metrics") or {}
    c.official_metrics = {
        "sharpe": float(r.get("sharpe") or fm.get("sharpe") or 0),
        "fitness": float(r.get("fitness") or fm.get("fitness") or 0),
        "turnover": float(r.get("turnover") or fm.get("turnover") or 0),
        "returns": float(fm.get("returns") or 0),
        "drawdown": float(fm.get("drawdown") or 0),
        "correlation": 0.0,  # from SELF_CORRELATION check if available
        "weight_concentration": float(fm.get("weight_concentration") or 0),
        "sub_universe_sharpe": float(fm.get("sub_universe_sharpe") or 0),
        "margin": float(fm.get("margin") or 0),
        "is_oos_ratio": float(fm.get("is_oos_ratio") or 0),
        "pass_fail": "PASS" if fm.get("brain_pass") else "FAIL",
    }
    # Store brain checks for diagnostics
    c._brain_checks = fm.get("brain_checks", {})
    # Compute local_quality for checklist
    c.local_quality = {"passed": len(expr) > 10 and len(c.operators or []) >= 1}
    candidates.append(c)

# ═══════════════════════════════════════════════════════════════
# 3. Run full scoring pipeline
# ═══════════════════════════════════════════════════════════════
results: list[dict] = []
raw_golds = 0
scorecard_golds = 0       # passed build_scorecard with high total
gate_passed = 0            # passed evaluate_quality_gate
raw_silver = 0
gate_silver = 0

for c in candidates:
    sharpe = float((c.official_metrics or {}).get("sharpe", 0))
    prior = None
    empirical = None
    scorecard = None
    gate = None
    
    try:
        scorecard = build_scorecard(c, thresholds, scoring_cfg)
    except Exception as e:
        scorecard = {"error": str(e)[:100]}
    
    try:
        gate = evaluate_quality_gate(c, thresholds)
    except Exception as e:
        gate = {"error": str(e)[:100]}
    
    # Parse prior dimensions
    if scorecard and isinstance(scorecard, dict):
        prior = scorecard.get("prior", {})
        empirical = scorecard.get("empirical", {})
    
    is_raw_gold = sharpe >= 1.25
    is_raw_silver = sharpe >= 1.0
    
    # Gate check
    hard_gate_ok = not (gate.get("hard_gate_blocked", False) if isinstance(gate, dict) else False)
    gate_status = gate.get("status", "?") if isinstance(gate, dict) else "?"
    total_score = scorecard.get("total_score", 0) if isinstance(scorecard, dict) else 0
    
    if is_raw_gold:
        raw_golds += 1
        if hard_gate_ok:
            gate_passed += 1
    if is_raw_silver:
        raw_silver += 1
        if hard_gate_ok:
            gate_silver += 1
    
    # Collect failed checks
    hard_failures = []
    soft_warnings = []
    if isinstance(gate, dict):
        hard_failures = gate.get("failed_reasons", [])
        soft_warnings = gate.get("warnings", [])
    if isinstance(empirical, dict):
        hard_failures.extend(empirical.get("hard_gate_failures", []))
    
    results.append({
        "index": r["index"],
        "expression": r["expression"][:80],
        "sharpe": sharpe,
        "raw_gold": is_raw_gold,
        "raw_silver": is_raw_silver,
        "prior_score": prior.get("score", "?") if isinstance(prior, dict) else "?",
        "empirical_score": empirical.get("score", "?") if isinstance(empirical, dict) else "?",
        "total_score": total_score,
        "decision_band": scorecard.get("decision_band", "?") if isinstance(scorecard, dict) else "?",
        "gate_status": gate_status,
        "gate_passed": hard_gate_ok,
        "hard_failures": hard_failures[:5],
        "soft_warnings": soft_warnings[:3],
    })

# ═══════════════════════════════════════════════════════════════
# 4. Output funnel report
# ═══════════════════════════════════════════════════════════════
n = len(candidates)
print(f"\n{'='*64}")
print(f"  管线审计: Round 7 全门禁漏斗")
print(f"{'='*64}")
print(f"  总候选: {n}")
print(f"")

# Funnel stages
print(f"  {'阶段':<36} {'通过':>6} {'占比':>8} {'漏斗':>8}")
print(f"  {'-'*36} {'-'*6} {'-'*8} {'-'*8}")

stages = [
    ("1. BRAIN 原始 Sharpe >= 1.25", raw_golds),
    ("2. + 无硬门禁失败", gate_passed),
    ("3. BRAIN 原始 Sharpe >= 1.00", raw_silver),
    ("4. + 无硬门禁失败", gate_silver),
    ("5. total_score >= 60", sum(1 for r in results if r["total_score"] not in ("?", 0) and r["total_score"] >= 60)),
    ("6. decision_band = submit", sum(1 for r in results if "submit" in str(r["decision_band"]))),
]

for label, count in stages:
    pct = count / n * 100 if n > 0 else 0
    prev = stages[stages.index((label, count)) - 1][1] if stages.index((label, count)) > 0 else 0
    _ = f"{pct:.1f}%"
    print(f"  {label:<36} {count:>6} {pct:>7.1f}%")

# Gold candidates that passed gate
print(f"\n{'='*64}")
print(f"  通过全部门禁的金标候选:")
print(f"{'='*64}")

gold_passed = [r for r in results if r["raw_gold"] and r["gate_passed"]]
silver_passed = [r for r in results if r["raw_silver"] and r["gate_passed"]]
gold_failed = [r for r in results if r["raw_gold"] and not r["gate_passed"]]

print(f"\n  [OK] 原始金标 + 门禁通过: {len(gold_passed)}/{raw_golds}")
for r in gold_passed:
    bc = r.get("_brain", {})
    print(f"    #{r['index']:>3}  sharpe={r['sharpe']:>7.3f}  total={r['total_score']}  BRAIN={'PASS' if bc.get('brain_pass') else 'FAIL'}")

if gold_failed:
    print(f"\n  [X] 原始金标但门禁失败: {len(gold_failed)}/{raw_golds}")
    for r in gold_failed:
        fm = candidates[r["index"] - 1]._brain_checks if hasattr(candidates[r["index"] - 1], '_brain_checks') else {}
        bf = [k for k, v in fm.items() if v.get("result") == "FAIL"] if fm else []
        print(f"    #{r['index']:>3}  sharpe={r['sharpe']:>7.3f}  BRAIN_Fails={bf}")

print(f"\n  [OK] 原始银标 + 门禁通过: {len(silver_passed)}/{raw_silver}")

# Failure reason summary
from collections import Counter
fail_counter: Counter = Counter()
for r in results:
    for f in r.get("hard_failures", []):
        fail_counter[str(f)[:60]] += 1

if fail_counter:
    print(f"\n{'='*64}")
    print(f"  硬门禁失败原因 TOP 10:")
    print(f"{'='*64}")
    for reason, count in fail_counter.most_common(10):
        print(f"  {reason:<50} {count:>4}")

# Decision band distribution
band_counter: Counter = Counter()
for r in results:
    band = str(r.get("decision_band", "?"))[:30]
    band_counter[band] += 1

print(f"\n{'='*64}")
print(f"  Decision Band 分布:")
print(f"{'='*64}")
for band, count in band_counter.most_common():
    print(f"  {band:<40} {count:>4}")

# Final verdict
print(f"\n{'='*64}")
print(f"  最终结论")
print(f"{'='*64}")
print(f"  原始 Sharpe >= 1.25:   {raw_golds}/{n} ({raw_golds/n*100:.1f}%)")
print(f"  通过全部门禁的金标:     {len(gold_passed)}/{raw_golds} → 存活率 {len(gold_passed)/max(raw_golds,1)*100:.0f}%")
print(f"  原始 Sharpe >= 1.00:   {raw_silver}/{n} ({raw_silver/n*100:.1f}%)")
print(f"  通过全部门禁的银标:     {len(silver_passed)}/{raw_silver} → 存活率 {len(silver_passed)/max(raw_silver,1)*100:.0f}%")
print(f"  漏斗收缩比 (金标):       {raw_golds} → {len(gold_passed)}  ({(1-len(gold_passed)/max(raw_golds,1))*100:.0f}% 被门禁淘汰)")
