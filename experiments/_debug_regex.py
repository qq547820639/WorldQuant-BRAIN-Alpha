import re

expr = "rank(ts_delta(close, 5, 10))"
pattern = r'(?<![a-zA-Z_])(\w+)\(([^)]*(?:\([^)]*\)[^)]*)*)\)'

print(f"Testing: {expr}")
print(f"Pattern: {pattern}")
for m in re.finditer(pattern, expr):
    print(f"  Match: op={m.group(1)}, args={m.group(2)}")
    args = m.group(2).split(",")
    print(f"    split: {args} (count={len(args)})")
print("done")
