import sys; sys.path.insert(0, r"D:\Works\WorldQuant BRAIN Alpha")
from brain_alpha_ops.research.validated_generator import generate_validated_candidates, validate_expression, TEMPLATES, FIELD_POOLS

print(f"Templates: {sum(len(v) for v in TEMPLATES.values())} across {len(TEMPLATES)} themes")
print(f"Field pools: {len(FIELD_POOLS)} categories, {sum(len(v) for v in FIELD_POOLS.values())} fields")

c = generate_validated_candidates(count=10)
print(f"\nGenerated {len(c)} candidates:")
for x in c:
    r = validate_expression(x["expression"])
    ok = "OK" if r["valid"] else "FAIL"
    print(f"  [{ok}] [{x['theme']}] {x['expression'][:75]}")
    if r["errors"]: print(f"    ERR: {r['errors']}")
