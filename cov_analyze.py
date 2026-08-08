import re

rows = []
with open('coverage_run.log', encoding='utf-8') as fh:
    for line in fh:
        m = re.match(r'^(brain_alpha_ops/\S+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)%$', line.strip())
        if m:
            name, stmts, miss, branch, brpart, cover = m.groups()
            rows.append((name, int(stmts), int(miss), int(cover)))

# Biggest contributors to coverage gap: large files with low cover
rows.sort(key=lambda r: (r[1] * (100 - r[3]) / 100), reverse=True)
print("=== TOP 40 largest uncovered-statement contributors (size * (100-cover)%) ===")
for name, stmts, miss, cover in rows[:40]:
    print(f'stmts={stmts:5d} miss={miss:5d} cover={cover:3d}%  {name}')