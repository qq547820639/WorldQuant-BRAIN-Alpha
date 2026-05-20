import os, json, base64, requests, re, time

u = os.environ['BRAIN_USERNAME']; p = os.environ['BRAIN_PASSWORD']
auth = base64.b64encode(f'{u}:{p}'.encode()).decode()
s = requests.Session()
r = s.post('https://api.worldquantbrain.com/authentication', headers={'Authorization': f'Basic {auth}'}, timeout=60)
print(f'Auth: {r.status_code}')

with open('experiments/_intermediate_results.json') as f:
    data = json.load(f)
results = data['results']
completed = [r for r in results if r.get('status') == 'completed']
print(f'Completed in JSON: {len(completed)}')
print(f'First: index={completed[0]["index"]}, expr={completed[0]["expression"][:50]}')

sim_ids = []
with open('experiments/experiment_100c_20260516_033833.log', encoding='utf-8', errors='replace') as f:
    for line in f:
        m = re.search(r'Submitted:\s+(\w{20,})', line)
        if m:
            sim_ids.append(m.group(1).rstrip('.'))
print(f'Sim IDs: {len(sim_ids)}')
print(f'First 3 sims: {sim_ids[:3]}')

idx = completed[0]['index']
sim_id = sim_ids[idx - 1]
print(f'Match: index={idx}, sim_id={sim_id}')

r2 = s.get(f'https://api.worldquantbrain.com/simulations/{sim_id}', timeout=60)
sim_data = r2.json()
alpha_id = sim_data.get('alpha', '')
print(f'Sim status: {sim_data.get("status")}, alpha_id: {alpha_id}')

if alpha_id:
    time.sleep(2)
    r3 = s.get(f'https://api.worldquantbrain.com/alphas/{alpha_id}', timeout=60)
    alpha = r3.json()
    is_d = alpha.get('is', {})
    print(f'Grade: {alpha.get("grade")}')
    print(f'Sharpe: {is_d.get("sharpe")}, Fitness: {is_d.get("fitness")}, Turnover: {is_d.get("turnover")}')
