import os,json,base64,requests
u=os.environ.get("BRAIN_USERNAME","");p=os.environ.get("BRAIN_PASSWORD","")
s=requests.Session()
s.post("https://api.worldquantbrain.com/authentication",
    headers={"Authorization":"Basic "+base64.b64encode(f"{u}:{p}".encode()).decode()},timeout=60)
r=s.get("https://api.worldquantbrain.com/alphas/gJmj3ml0",timeout=60)
if r.status_code==200:
    d=r.json()
    status=d.get("status","?")
    checks=d.get("is",{}).get("checks",[])
    print(f"Status: {status}")
    for c in checks:
        print(f"  {c['name']}: {c['result']}")
else:
    print(f"HTTP {r.status_code}")
