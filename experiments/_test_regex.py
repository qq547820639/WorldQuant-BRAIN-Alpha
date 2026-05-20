import sys; sys.path.insert(0, r"D:\Works\WorldQuant BRAIN Alpha")
from brain_alpha_ops.research.validated_generator import validate_expression
tests = [
    ("rank(ts_delta(close, 5, 10))", False),
    ("-rank(ts_corr(close, 5))", False),
    ("rank(ts_delta(close, 5))", True),
    ("-rank(ts_std(close, 40))", True),
]
for expr, expected in tests:
    r = validate_expression(expr)
    ok = "PASS" if r["valid"] == expected else "FAIL"
    print(f"[{ok}] {r['valid']} | {expr[:55]}")
    if r["errors"]: print(f"      {r['errors']}")
