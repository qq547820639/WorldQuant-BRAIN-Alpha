"""Compatibility checks for the React web console build artifacts.

The legacy inline HTML builder has been retired.  This module keeps the older
``brain_alpha_ops.build_inline`` command surface available, but the command now
verifies that the React ``dist`` shell and its hashed assets are present.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
import shutil
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REACT_DIST = ROOT / "brain_alpha_ops" / "web" / "react_app" / "dist"
REACT_INDEX = REACT_DIST / "index.html"
ASSET_REF_RE = re.compile(r"""(?:src|href)=["'](/assets/[^"']+)["']""")


def build(output_path: str | Path | None = None) -> dict[str, Any]:
    """Copy the current React index shell when an explicit output is requested."""
    result = check()
    if not result["ok"]:
        return result
    if output_path is not None:
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REACT_INDEX, target)
        result = dict(result)
        result["output_path"] = str(target)
    return result


def build_inline(template: str) -> tuple[str, dict[str, Any]]:
    """Return *template* unchanged; inline markers are no longer supported."""
    stats = {
        "schema_version": "react_dist_readiness.v1",
        "replaced": 0,
        "css_replaced": 0,
        "missing": [],
        "deprecated": True,
    }
    return template.lstrip("\ufeff"), stats


def check(output_path: str | Path | None = None) -> dict[str, Any]:
    """Validate that the React dist index references existing local assets."""
    index_path = Path(output_path) if output_path is not None else REACT_INDEX
    try:
        html = index_path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return _error(index_path, "React dist index.html is missing; run the React build before release.")
    except OSError as exc:
        return _error(index_path, f"React dist index.html could not be read: {exc}")

    if "<!-- inline:" in html or "<!-- inline-css:" in html:
        return _error(index_path, "Legacy inline placeholders remain in the React shell.")

    asset_refs = sorted(set(ASSET_REF_RE.findall(html)))
    missing_assets = [
        ref
        for ref in asset_refs
        if not _asset_path(ref, index_path=index_path).is_file()
    ]
    ok = not missing_assets
    return {
        "ok": ok,
        "schema_version": "react_dist_readiness.v1",
        "frontend": "react",
        "index_path": str(index_path),
        "actual_bytes": len(html.encode("utf-8")),
        "asset_refs": asset_refs,
        "asset_count": len(asset_refs),
        "missing": missing_assets,
        "error": "" if ok else "React dist index.html references missing assets.",
    }


def _asset_path(ref: str, *, index_path: Path) -> Path:
    relative = ref.lstrip("/")
    return index_path.parent / relative


def _error(path: Path, message: str) -> dict[str, Any]:
    return {
        "ok": False,
        "schema_version": "react_dist_readiness.v1",
        "frontend": "react",
        "index_path": str(path),
        "actual_bytes": 0,
        "asset_refs": [],
        "asset_count": 0,
        "missing": [],
        "error": message,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate React web console build artifacts.")
    parser.add_argument("--check", action="store_true", help="Check React dist readiness.")
    parser.add_argument("--json", action="store_true", help="Output JSON.")
    parser.add_argument("--output", default="", help="Optional path to copy the React index shell.")
    args = parser.parse_args(argv)

    result = check() if args.check or not args.output else build(args.output)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        status = "PASS" if result.get("ok") else "FAIL"
        print(f"React dist readiness: {status}")
        if result.get("error"):
            print(result["error"])
    return 0 if result.get("ok") else 1


__all__ = ["build", "build_inline", "check", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
