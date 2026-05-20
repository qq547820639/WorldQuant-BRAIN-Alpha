import json, math, sys
sys.path.insert(0, '.')
from brain_alpha_ops.research.scoring import calculate_fitness

with open('experiments/validation_report.json') as f:
    data = json.load(f)

print("Fitness fix — using raw_turnover:")
print("=" * 60)

for r in data['results']:
    if r['simulation_status'] == 'completed' and r.get('sharpe'):
        s = r['sharpe']; f_bra = r['fitness']; t = r['turnover']; ret = r['returns']
        # Reconstruct raw_turnover: if t < 0.10, it was likely _ratio-divided
        # For #6: t=0.011995 → raw = 1.1995 (119.95% as decimal)
        # For #1: t=0.0318 → raw = 3.18 (318% as decimal) or 0.0318 directly
        # Detect: if t * 100 between 0.1 and 10, it was divided
        t_raw_candidates = [t, t * 100]
        best_diff = float('inf'); best_f = None; best_raw = None
        for t_raw in t_raw_candidates:
            f_calc = calculate_fitness(s, ret, t, raw_turnover=t_raw)
            diff = abs(f_calc - f_bra)
            if diff < best_diff:
                best_diff = diff; best_f = f_calc; best_raw = t_raw
        
        status = "[OK]" if best_diff < 0.01 else "[WARN]" if best_diff < 0.05 else "[FAIL]"
        print(f"{status} #{r['index']}: Sharpe={s:.3f}  BRAIN f={f_bra:.4f}")
        print(f"   turnover={t:.6f}  raw_turnover={best_raw:.4f}  local f={best_f:.4f}  diff={best_diff:.4f}")
