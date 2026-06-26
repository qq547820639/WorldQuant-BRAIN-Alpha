"""CLI entry point so ``python3 -m scripts.quality_gate`` works.

Replaces the former ``if __name__ == "__main__"`` block of the deleted
``scripts/quality_gate.py`` monolith (Task A5).
"""

from __future__ import annotations

import sys

from ._cli import main


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
