"""Editor-friendly local web console launcher."""

from __future__ import annotations

import sys

from brain_alpha_ops.web import main


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
