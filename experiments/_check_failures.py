import json
with open('experiments/validation_report.json') as f:
    data = json.load(f)
for r in data['results']:
    if r['simulation_status'] == 'failed':
        detail = str(r.get('brain_failure_detail', ''))[:250]
        print(f"#{r['index']}: {r['expression'][:120]}")
        print(f"   Error: {detail}")
        print()
