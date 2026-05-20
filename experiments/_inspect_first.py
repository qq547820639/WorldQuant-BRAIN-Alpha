"""Inspect first COMPLETED sim to determine BRAIN JSON structure."""
import os, sys, base64, json, requests
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

u = os.environ['BRAIN_USERNAME']
p = os.environ['BRAIN_PASSWORD']
auth = base64.b64encode(f'{u}:{p}'.encode()).decode()
s = requests.Session()
r = s.post('https://api.worldquantbrain.com/authentication', headers={'Authorization': f'Basic {auth}'}, timeout=60)
print(f'Auth: {r.status_code}')

log = 'experiments/experiment_100c_20260516_033833.log'
with open(log, encoding='utf-8', errors='replace') as f:
    for line in f:
        if 'OK (sharpe=0.00)' in line and 'Submitted:' in line:
            parts = line.split()
            for p in parts:
                if len(p) >= 20 and all(c.isalnum() for c in p[:5]):
                    sim_id = p.strip('.')
                    print(f'Sim: {sim_id}')
                    r2 = s.get(f'https://api.worldquantbrain.com/simulations/{sim_id}', timeout=60)
                    data = r2.json()
                    print(f'Top keys: {sorted(data.keys())}')
                    if 'is' in data:
                        is_d = data['is']
                        print(f'  "is" keys: {sorted(is_d.keys())}')
                        for k in ['sharpe','fitness','turnover','returns','drawdown']:
                            print(f'  is.{k} = {is_d.get(k)}')
                    raw = json.dumps(data, indent=2, default=str)
                    print(f'\n=== FULL JSON (first 2000 chars) ===')
                    print(raw[:2000])
                    # Save
                    with open('experiments/_inspect_result.json', 'w') as wf:
                        wf.write(raw)
                    print('\nSaved to experiments/_inspect_result.json')
                    import sys; sys.exit(0)
