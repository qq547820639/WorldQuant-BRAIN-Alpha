"""Compatibility entry point for the web console inline builder.

The canonical implementation lives in ``brain_alpha_ops/web/build_inline.py``.
Keeping this wrapper lets older build commands continue to work while avoiding
two independent placeholder parsers.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path


CANONICAL_PATH = Path(__file__).resolve().parent / "web" / "build_inline.py"


def _load_canonical_builder():
    spec = importlib.util.spec_from_file_location("brain_alpha_ops_web_build_inline", CANONICAL_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load inline builder from {CANONICAL_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_canonical = _load_canonical_builder()
build = _canonical.build
build_inline = _canonical.build_inline
check = _canonical.check
main = _canonical.main


__all__ = ["build", "build_inline", "check", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
