import os, json
from datetime import datetime

# Check lifecycle latest
f = "data/lifecycle.jsonl"
if os.path.exists(f):
    mtime = datetime.fromtimestamp(os.path.getmtime(f))
    print(f"lifecycle.jsonl: {os.path.getsize(f)/1024/1024:.1f} MB | mtime: {mtime.strftime('%H:%M:%S')}")
    with open(f, encoding="utf-8") as fh:
        lines = fh.readlines()
    print(f"Entries: {len(lines)}")
    for line in lines[-5:]:
        try:
            e = json.loads(line)
            print(f"  {e.get('alpha_id','?')[:15]} | status={e.get('lifecycle_status',e.get('status','?'))} | score={e.get('total_score',e.get('score','?'))} | sim={e.get('simulation_id',e.get('official_alpha_id','?'))[:15]}")
        except:
            print(f"  (parse error: {line[:80]})")

# Check if events.jsonl changed
f = "data/events.jsonl"
if os.path.exists(f):
    mtime = datetime.fromtimestamp(os.path.getmtime(f))
    print(f"\nevents.jsonl mtime: {mtime.strftime('%H:%M:%S')}")
