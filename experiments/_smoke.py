import sys; sys.path.insert(0, r"D:\Works\WorldQuant BRAIN Alpha")
from brain_alpha_ops.research.validated_generator import generate_validated_candidates, validate_expression
c = generate_validated_candidates(["momentum"], count=5)
print(f"Generated {len(c)} candidates:")
for x in c:
    r = validate_expression(x["expression"])
    print(f"  [{x['theme']}] {x['expression'][:70]}")
    if r["errors"]: print(f"    ERRORS: {r['errors']}")
    if r["warnings"]: print(f"    WARN: {r['warnings']}")
