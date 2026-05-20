import json
with open('experiments/validation_report.json') as f:
    data = json.load(f)

print(f"Total: {data['total_generated']} generated, {data['total_completed']} completed, {data['total_failed']} failed")
print()

for r in data['results']:
    if r['simulation_status'] == 'completed':
        s = r.get('sharpe'); fit = r.get('fitness'); t = r.get('turnover')
        print(f"#{r['index']}: Sharpe={s:.3f}  Fitness={fit:.3f}  Turnover={t:.4f}")
        print(f"     Expression: {r['expression'][:120]}")
        print(f"     BRAIN: {r['brain_pass_fail']}  Score: {r['total_score']:.1f}")
        print()

from collections import Counter
fail_types = Counter()
for r in data['results']:
    if r['simulation_status'] == 'failed':
        detail = r.get('brain_failure_detail', '')
        if 'unknown variable' in detail:
            fail_types['unknown_var'] += 1
        elif 'Unknown operator' in detail or 'unknown operator' in detail:
            fail_types['unknown_op'] += 1
        elif 'does not support' in detail:
            fail_types['bad_args'] += 1
        elif 'Required attribute' in detail:
            fail_types['missing_arg'] += 1
        else:
            fail_types['other'] += 1
print(f"Failure breakdown:")
for k, v in fail_types.most_common():
    print(f"  {k}: {v}")
print(f"  pass_rate: {data['total_completed']}/{data['total_generated']} = {data['total_completed']/max(data['total_generated'],1):.0%}")
