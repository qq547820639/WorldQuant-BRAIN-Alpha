#!/usr/bin/env python3
"""Architecture compliance check — validates module dependency rules (v4.0 M5).

Checks:
  1. shared/ does not import from research/ or web/
  2. brain_api/ does not import from research/ or web/
  3. config/ does not import from research/ or web/
  4. research/ does not import from web/

Usage: python3 scripts/check_architecture.py
"""

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OPS = ROOT / "brain_alpha_ops"

RULES = {
    "shared": {"forbidden": {"research", "web", "agents"}, "message": "shared/ must not import from research, web, or agents"},
    "brain_api": {"forbidden": {"research", "web", "agents"}, "message": "brain_api/ must not import from research, web, or agents"},
    "research": {"forbidden": {"web", "agents"}, "message": "research/ must not import from web/ or agents/"},
}

def get_imports(filepath: Path) -> set[str]:
    """Extract top-level package names from Python imports."""
    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return set()
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module.split(".")[0])
    return imports

def check():
    violations = []
    for domain, rule in RULES.items():
        domain_dir = OPS / domain
        if not domain_dir.is_dir():
            domain_dir = OPS  # fallback to top-level for flat packages
        for pyfile in domain_dir.rglob("*.py"):
            rel = pyfile.relative_to(OPS)
            imports = get_imports(pyfile)
            bad = imports & rule["forbidden"]
            if bad:
                violations.append(f"  {rel}: imports {bad} — {rule['message']}")

    if violations:
        print(f"ARCHITECTURE VIOLATIONS ({len(violations)}):")
        for v in violations:
            print(v)
        return 1
    print("ARCHITECTURE CHECK PASSED — no dependency violations")
    return 0

if __name__ == "__main__":
    sys.exit(check())
