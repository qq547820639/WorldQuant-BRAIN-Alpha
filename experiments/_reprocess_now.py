"""Quick refetch: match sim_ids from log, fetch real alpha metrics, report."""
import os, sys, json, time, base64, re, requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Auth
u = os.environ['BRAIN_USERNAME']; p = os.environ['BRAIN_PASSWORD']
auth = base64.b64encode(f'{u}:{p}'.encode()).decode()
session = requests.Session()
session.post('https://api.worldquantbrain.com/authentication', headers={'Authorization': f'Basic {auth}'}, timeout=60)

# Load intermediate results
with open('experiments/_intermediate_results.json') as f:
    stored = json.load(f)
results = stored['results']
print(f"Loaded {len(results)} results")

# Extract sim_ids from log
sim_ids = []
with open('experiments/experiment_100c_20260516_033833_utf8.log', encoding='utf-8') as f:
    for line in f:
        m = re.search(r'Submitted:\s+(\w{20,})', line)
        if m:
            sim_ids.append(m.group(1).rstrip('.'))
print(f"Extracted {len(sim_ids)} sim_ids from log")

# Match and refetch
completed_metrics = []
extraction_sources = {}

for i, r in enumerate(results):
    if r.get('status') != 'completed':
        continue
    
    idx = r.get('index', -1)
    if idx < 1 or idx > len(sim_ids):
        r['metrics'] = {'sharpe': 0, 'fitness': 0, 'turnover': 0, 'failure_reason': 'no_sim_id'}
        continue
    
    sim_id = sim_ids[idx - 1]
    
    try:
        # Step 1: Get sim result to find alpha_id
        resp = session.get(f'https://api.worldquantbrain.com/simulations/{sim_id}', timeout=60)
        if resp.status_code != 200:
            r['metrics'] = {'sharpe': 0, 'fitness': 0, 'turnover': 0, 'failure_reason': f'sim_http_{resp.status_code}'}
            print(f"  [{idx}] sim HTTP {resp.status_code}")
            continue
        
        sim_data = resp.json()
        alpha_id = sim_data.get('alpha', '')
        if not alpha_id:
            r['metrics'] = {'sharpe': 0, 'fitness': 0, 'turnover': 0, 'failure_reason': 'no_alpha_id'}
            print(f"  [{idx}] no alpha_id")
            continue
        
        # Step 2: Get alpha details with real metrics
        time.sleep(2)
        resp2 = session.get(f'https://api.worldquantbrain.com/alphas/{alpha_id}', timeout=60)
        if resp2.status_code != 200:
            r['metrics'] = {'sharpe': 0, 'fitness': 0, 'turnover': 0, 'failure_reason': f'alpha_http_{resp2.status_code}'}
            print(f"  [{idx}] alpha HTTP {resp2.status_code}")
            continue
        
        alpha = resp2.json()
        is_data = alpha.get('is', {})
        metrics = {
            'sharpe': float(is_data.get('sharpe', 0)),
            'fitness': float(is_data.get('fitness', 0)),
            'turnover': float(is_data.get('turnover', 0)),
            'returns': float(is_data.get('returns', 0)),
            'drawdown': float(is_data.get('drawdown', 0)),
            'margin': float(is_data.get('margin', 0)),
            'extraction_source': 'alpha.is',
            'pass_fail': 'PASS' if float(is_data.get('sharpe', 0)) >= 1.25 else 'FAIL',
            'checks': is_data.get('checks', []),
            'alpha_id': alpha_id,
            'grade': alpha.get('grade', '?'),
        }
        r['metrics'] = metrics
        r['metrics_fixed'] = True
        src = 'alpha.is'
        extraction_sources[src] = extraction_sources.get(src, 0) + 1
        
        s = metrics['sharpe']
        print(f"  [{idx}/{len(results)}] {alpha_id} sharpe={s:.3f} fitness={metrics['fitness']:.3f} grade={alpha.get('grade','?')}")
        
    except Exception as e:
        r['metrics'] = {'sharpe': 0, 'fitness': 0, 'turnover': 0, 'failure_reason': f'exception: {type(e).__name__}'}
        print(f"  [{idx}] ERROR: {type(e).__name__}: {e}")

# Stats
completed = [r for r in results if r.get('metrics_fixed')]
sharpes = [r['metrics']['sharpe'] for r in completed]
fitnesses = [r['metrics']['fitness'] for r in completed]
turnovers = [r['metrics']['turnover'] for r in completed]

print(f"\n{'='*60}")
print(f"  RESULTS")
print(f"{'='*60}")
print(f"  Total: {len(results)}")
print(f"  Refetched: {len(completed)}")
print(f"  Failed (stored): {len(results) - len(completed)}")

if sharpes:
    s = sorted(sharpes)
    n = len(s)
    print(f"\n  Sharpe (n={n}):")
    print(f"    Min={min(s):.3f}  P25={s[n//4]:.3f}  Median={s[n//2]:.3f}  P75={s[3*n//4]:.3f}  Max={max(s):.3f}  Mean={sum(s)/n:.3f}")
    for th in [1.25, 1.0, 0.8, 0.5, 0.0, -0.5]:
        cnt = sum(1 for x in s if x >= th)
        print(f"    >= {th:4.1f}: {cnt:3d} ({cnt/n*100:.1f}%)")
    
    # Grade distribution
    grades = {}
    for r in completed:
        g = r['metrics'].get('grade', '?')
        grades[g] = grades.get(g, 0) + 1
    print(f"\n  Grade distribution:")
    for g, c in sorted(grades.items(), key=lambda x: -x[1]):
        print(f"    {g}: {c}")

# Save
out = {
    'completed': len(completed),
    'total': len(results),
    'sharpes': sharpes,
    'fitnesses': fitnesses,
    'results': results,
}
with open('experiments/_results_fixed.json', 'w') as f:
    json.dump(out, f, indent=2, default=str)
print(f"\nSaved: experiments/_results_fixed.json")
