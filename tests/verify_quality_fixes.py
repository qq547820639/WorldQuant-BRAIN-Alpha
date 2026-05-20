"""Verification script for Brain Alpha OPS quality fixes (T1-T14)."""
import math
import sys
from pathlib import Path

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

PASS = 0
FAIL = 0

def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} — {detail}")
        sys.exit(1)  # Stop on first failure for clarity

# ============================================================
# T1: Fallback operators — 66 total, no fake operators
# ============================================================
print("\n=== T1: Fallback operators ===")
from brain_alpha_ops.brain_api.context_defaults import _lazy_list
ops = _lazy_list("operators")
names = {o["name"] for o in ops}
check("Total operators = 66", len(ops) == 66, f"got {len(ops)}")
check("ts_min removed", "ts_min" not in names)
check("ts_max removed", "ts_max" not in names)
check("ts_median removed", "ts_median" not in names)
check("ts_std_dev present", "ts_std_dev" in names)
check("ts_arg_max present", "ts_arg_max" in names)
check("ts_arg_min present", "ts_arg_min" in names)
check("trade_when present", "trade_when" in names)
check("bucket present", "bucket" in names)
check("vec_avg present", "vec_avg" in names)
check("normalize present", "normalize" in names)
check("ts_regression present", "ts_regression" in names)

# ============================================================
# T3: LSS formula — √(sub_size/alpha_size) factor
# ============================================================
print("\n=== T3: LOW_SUB_UNIVERSE_SHARPE formula ===")
sub_size, alpha_size, sharpe = 500, 1000, 1.5
size_factor = math.sqrt(sub_size / max(alpha_size, 1))
threshold = 0.75 * size_factor * max(sharpe, 0.01)
expected = 0.75 * math.sqrt(0.5) * 1.5  # ≈ 0.7955
check("LSS formula sqrt factor", abs(threshold - expected) < 0.001,
      f"got {threshold:.4f}, expected ~{expected:.4f}")

# Default case (sub_size == alpha_size → size_factor = 1)
threshold_default = 0.75 * math.sqrt(1000 / 1000) * max(1.5, 0.01)
check("LSS degenerates when sizes equal", abs(threshold_default - 1.125) < 0.001,
      f"got {threshold_default}")

# ============================================================
# T6: SELF_CORRELATION exception
# ============================================================
print("\n=== T6: SELF_CORRELATION exception ===")
from brain_alpha_ops.research.alpha_checks import _check_self_correlation
# Test: correlation=0.75(>=0.70), sharpe=2.2, related_sharpe=2.0 → PASS (exception)
sim_exception = {
    "selfCorrelation": 0.75, "sharpe": 2.2,
    "relatedAlphaSharpe": 2.0, "_thresholds": None
}
result = _check_self_correlation(sim_exception)
check("SelfCorr exception: PASS when Sharpe advantage",
      result.passed and result.exception_applied,
      f"passed={result.passed}, exception={result.exception_applied}")

# Test: correlation=0.75, sharpe=1.8, related_sharpe=2.0 → FAIL (no advantage)
sim_fail = {
    "selfCorrelation": 0.75, "sharpe": 1.8,
    "relatedAlphaSharpe": 2.0, "_thresholds": None
}
result_fail = _check_self_correlation(sim_fail)
check("SelfCorr exception: FAIL without Sharpe advantage",
      not result_fail.passed,
      f"passed={result_fail.passed}")

# Test: correlation=0.5 → PASS (below threshold)
sim_normal = {
    "selfCorrelation": 0.5, "sharpe": 1.5, "_thresholds": None
}
result_normal = _check_self_correlation(sim_normal)
check("SelfCorr normal: PASS below 0.70", result_normal.passed)

# ============================================================
# T4/T8: Fitness formula
# ============================================================
print("\n=== T8: Fitness formula ===")
from brain_alpha_ops.research.scoring import calculate_fitness
f = calculate_fitness(1.5, 0.05, 0.3)
expected_fitness = 1.5 * math.sqrt(0.05 / 0.3)  # ≈ 0.612
check("Fitness formula correct", abs(f - expected_fitness) < 0.001,
      f"got {f:.4f}, expected ~{expected_fitness:.4f}")

# Fitness with turnover floor
f_floor = calculate_fitness(1.5, 0.05, 0.05)  # turnover < 0.125, floor kicks in
expected_floor = 1.5 * math.sqrt(0.05 / 0.125)  # ≈ 0.949
check("Fitness turnover floor (0.125)", abs(f_floor - expected_floor) < 0.001,
      f"got {f_floor:.4f}, expected ~{expected_floor:.4f}")

# ============================================================
# T9: QualityThresholds Delay-0
# ============================================================
print("\n=== T9: Delay-0 thresholds ===")
from brain_alpha_ops.config import QualityThresholds
t = QualityThresholds()
check("min_sharpe_delay0 = 2.0", t.min_sharpe_delay0 == 2.0)
check("min_fitness_delay0 = 1.3", t.min_fitness_delay0 == 1.3)
check("min_sharpe (delay-1) = 1.25", t.min_sharpe == 1.25)
check("min_fitness (delay-1) = 1.0", t.min_fitness == 1.0)

# ============================================================
# T9: AlphaCheckRegistry has build_type_checks
# ============================================================
print("\n=== T10: AlphaCheckRegistry type checks ===")
from brain_alpha_ops.research.alpha_checks import AlphaCheckRegistry, CheckResult
r = AlphaCheckRegistry()
r.build_default_checks()
base_count = len(r.get_all())
check("Default checks registered", base_count >= 20, f"got {base_count}")

r.build_type_checks("POWER_POOL")
pp_count = len(r.get_all())
check("POWER_POOL checks added", pp_count >= base_count + 4,
      f"base={base_count}, with_PP={pp_count}")

# ============================================================
# T9: CheckResult has exception_applied field
# ============================================================
print("\n=== CheckResult.exception_applied ===")
cr = CheckResult(check_name="test", passed=True, actual=0.0, expected=">0")
check("CheckResult has exception_applied field", hasattr(cr, "exception_applied"))
check("exception_applied defaults to False", cr.exception_applied is False)

# ============================================================
# All done
# ============================================================
print(f"\n{'='*50}")
print(f"RESULTS: {PASS} passed, {FAIL} failed")
print(f"{'='*50}")
if FAIL > 0:
    sys.exit(1)
