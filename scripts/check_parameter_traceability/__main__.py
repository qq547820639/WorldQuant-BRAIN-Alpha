"""CLI entry point for ``python -m scripts.check_parameter_traceability``.

Delegates to :func:`scripts.check_parameter_traceability.main`.
"""

from __future__ import annotations

from . import main

if __name__ == "__main__":
    raise SystemExit(main())
