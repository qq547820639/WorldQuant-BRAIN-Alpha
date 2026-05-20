"""Direct pipeline audit on Round 8 data — uses fitness/turnover from intermediate JSON.
Computes BRAIN-equivalent checks from available metrics.
"""
import json, sys, math
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any
from collections import Counter

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))

from brain_alpha_ops.config import load_run_config
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.scoring import build_scorecard, evaluate_quality_gate
from brain_alpha_ops.research.generator import extract_fields, extract_operators

# ── Load Round 8 data ──
data = json.loads(Path("experiments/_intermediate_results.json").read_text(encoding="utf-8"))
results = [r for r in data["results"] if r["status"] == "completed"]
print(f"Round 8: {len(results)} completed / {data['total']} total")

config = load_run_config()
thresholds = config.ops.thresholds
scoring_cfg = config.ops.scoring

# ── Build candidates ──
@dataclass
class AuditResult:
    index: int
    expression: str = ""
    sharpe: float = 0.0
    fitness: float = 0.0
    turnover: float = 0.0
    total_score: float = 0.0
    gate_status: str = ""
    gate_passed: bool = False
    hard_fails: list = field(default_factory=list)
    soft_warns: list = field(default_factory=list)
    decision_band: str = ""

audit_results = []

for r in results:
    expr = r.get("expression", "")
    sharpe = float(r.get("sharpe") or 0)
    fitness = float(r.get("fitness") or 0)
    turnover = float(r.get("turnover") or 0)

    c = Candidate(
        alpha_id=f"r8_{r['index']}",
        expression=expr,
        family="r8",
        hypothesis=f"R8 #{r['index']}",
        data_fields=extract_fields(expr) or [],
        operators=extract_operators(expr) or [],
    )

    # Attach available metrics (fitness/turnover from existing data)
    c.official_metrics = {
        "sharpe": sharpe,
        "fitness": fitness,
        "turnover": turnover,
        "returns": 0.0,
        "drawdown": 0.0,
        "correlation": 0.0,
        "weight_concentration": 0.0,
        "sub_universe_sharpe": 0.0,
        "margin": 0.0,
        "pass_fail": "PASS" if sharpe >= 1.25 else "FAIL",
    }
    c.local_quality = {"passed": len(expr) > 10 and len(c.operators or []) >= 1}

    # Score
    try:
        sc = build_scorecard(c, thresholds, scoring_cfg)
        gate = evaluate_quality_gate(c, thresholds)
    except Exception:
        sc, gate = {}, {}

    ar = AuditResult(
        index=r["index"],
        expression=expr[:60],
        sharpe=sharpe,
        fitness=fitness,
        turnover=turnover,
        total_score=sc.get("total_score", 0) if sc else 0,
        gate_status=gate.get("status", "?") if gate else "?",
        gate_passed=not (gate.get("hard_gate_blocked", True) if gate else True),
        hard_fails=gate.get("failed_reasons", []) if gate else [],
        soft_warns=gate.get("warnings", []) if gate else [],
        decision_band=sc.get("decision_band", "?") if sc else "?",
    )
    audit_results.append(ar)

# ── Funnel ──
n = len(audit_results)
raw_golds = sum(1 for a in audit_results if a.sharpe >= 1.25)
raw_silvers = sum(1 for a in audit_results if a.sharpe >= 1.00)
gate_golds = sum(1 for a in audit_results if a.sharpe >= 1.25 and a.gate_passed)
gate_silvers = sum(1 for a in audit_results if a.sharpe >= 1.00 and a.gate_passed)
# BRAIN-equivalent checks using available data
fitness_pass = sum(1 for a in audit_results if a.fitness >= 1.0)
turnover_ok = sum(1 for a in audit_results if 0.01 <= a.turnover <= 0.70)
all_ok = sum(1 for a in audit_results if a.sharpe >= 1.25 and a.fitness >= 1.0 and 0.01 <= a.turnover <= 0.70)

print(f"\n{'='*64}")
print(f"  Round 8 全门禁漏斗 (可用指标)")
print(f"{'='*64}")
print(f"  总候选: {n}")
print(f"")
print(f"  {'阶段':<40} {'通过':>6} {'占比':>8}")
print(f"  {'-'*40} {'-'*6} {'-'*8}")

stages = [
    ("1. Sharpe >= 1.25 (原始金标)", raw_golds),
    ("2. + Fitness >= 1.0", sum(1 for a in audit_results if a.sharpe >= 1.25 and a.fitness >= 1.0)),
    ("3. + Turnover 0.01-0.70", sum(1 for a in audit_results if a.sharpe >= 1.25 and a.fitness >= 1.0 and 0.01 <= a.turnover <= 0.70)),
    ("4. + gate_passed (无硬门禁)", gate_golds),
    ("5. Sharpe >= 1.00 (原始银标)", raw_silvers),
    ("6. + gate_passed", gate_silvers),
    ("7. total_score >= 60", sum(1 for a in audit_results if a.total_score >= 60)),
]
for label, count in stages:
    print(f"  {label:<40} {count:>6} {count/n*100:>7.1f}%")

# Gold summary
print(f"\n{'='*64}")
print(f"  BRAIN 等效检查: Sharpe>=1.25 + Fitness>=1.0 + Turnover 0.01-0.70")
print(f"  ALL 3 PASS: {all_ok}/{raw_golds}")
print(f"{'='*64}")

# Show golds
for a in sorted(audit_results, key=lambda x: -x.sharpe):
    if a.sharpe < 0.5:
        continue
    status = "PASS" if a.gate_passed else "FAIL"
    flags = f"S={a.sharpe:.3f} F={a.fitness:.3f} T={a.turnover:.3f}"
    print(f"  #{a.index:>2}  {flags}  total={a.total_score:.0f}  {status}")
    if a.hard_fails:
        for f in a.hard_fails[:3]:
            print(f"       FAIL: {f}")

# Decision band distribution
bands = Counter(a.decision_band for a in audit_results)
print(f"\n  Decision Band:")
for b, c in bands.most_common():
    print(f"    {b:<30} {c:>4}")

# Final verdict
print(f"\n{'='*64}")
print(f"  结论")
print(f"{'='*64}")
print(f"  Sharpe>=1.25: {raw_golds}/{n} ({raw_golds/n*100:.1f}%)")
print(f"  +Fitness>=1.0: {sum(1 for a in audit_results if a.sharpe>=1.25 and a.fitness>=1.0)}/{raw_golds}")
print(f"  +Turnover:     {sum(1 for a in audit_results if a.sharpe>=1.25 and a.fitness>=1.0 and 0.01<=a.turnover<=0.70)}/{raw_golds}")
print(f"  gate_passed:   {gate_golds}/{raw_golds}")
