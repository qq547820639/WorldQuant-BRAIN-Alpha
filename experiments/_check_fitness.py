import json, math

with open('experiments/validation_report.json') as f:
    data = json.load(f)

for r in data['results']:
    if r['simulation_status'] == 'completed' and r.get('sharpe'):
        s = r['sharpe']
        f = r['fitness']
        t = r['turnover']
        ret = r['returns']
        print(f"#{r['index']}: Sharpe={s:.4f}  Fitness(BRAIN)={f:.4f}  Returns={ret:.4f}  Turnover={t:.6f}")
        print(f"  Expression: {r['expression'][:80]}")
        
        # Standard formula
        denom = max(t, 0.125)
        ratio = abs(ret) / denom
        local_f = s * math.sqrt(ratio)
        print(f"  Standard: denom=max({t:.6f},0.125)={denom:.4f} ratio={ratio:.4f} f={local_f:.4f}")
        print(f"  BRAIN f={f:.4f}  diff={abs(f-local_f):.4f}")
        
        # What if BRAIN uses daily/annualized values differently?
        # Try: no sqrt, just sharpe * ratio
        f1 = s * ratio
        # Try: denominator = max(turnover * 100, 12.5), numerator = returns
        f2 = s * math.sqrt(abs(ret) / max(t * 100, 12.5))
        # Try: what threshold would make it work?
        # f = s * sqrt(abs(ret) / max(t, X)) => X = abs(ret) / (f/s)^2
        if f > 0 and s > 0:
            implied_denom = abs(ret) / ((f/s) ** 2)
            print(f"  Implied denominator: {implied_denom:.4f} (Z = implied_turnover_threshold)")
        
        print()
