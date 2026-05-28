"""Build the shipped web console HTML from modular JavaScript sources."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
import sys


WEB_DIR = Path(__file__).resolve().parent
TEMPLATE_PATH = WEB_DIR / "index_template.html"
OUTPUT_PATH = WEB_DIR / "index.html"
INLINE_PATTERN = re.compile(r"<!--\s*inline:(js/.+?\.js)\s*-->")
INLINE_CSS_PATTERN = re.compile(r"<!--\s*inline-css:(css/.+?\.css)\s*-->")
SCRIPT_TEMPLATE = "<script>\n{content}\n</script>"
STYLE_TEMPLATE = "<style>\n{content}\n</style>"


def _read_source_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def build_inline(template_text: str, *, strict: bool = True) -> tuple[str, dict]:
    template_text = template_text.lstrip("\ufeff")
    replaced = 0
    css_replaced = 0
    missing: list[str] = []
    sources: list[str] = []
    css_sources: list[str] = []

    def replace_css_inline(match: re.Match) -> str:
        nonlocal css_replaced
        rel_path = match.group(1)
        css_path = WEB_DIR / rel_path
        if not css_path.is_file():
            missing.append(rel_path)
            if strict:
                raise FileNotFoundError(f"inline CSS source not found: {rel_path}")
            return match.group(0)
        css_replaced += 1
        css_sources.append(rel_path)
        css_content = _read_source_text(css_path)
        return STYLE_TEMPLATE.format(content=css_content)

    def replace_inline(match: re.Match) -> str:
        nonlocal replaced
        rel_path = match.group(1)
        js_path = WEB_DIR / rel_path
        if not js_path.is_file():
            missing.append(rel_path)
            if strict:
                raise FileNotFoundError(f"inline JS source not found: {rel_path}")
            return match.group(0)
        replaced += 1
        sources.append(rel_path)
        js_content = _read_source_text(js_path)
        return SCRIPT_TEMPLATE.format(content=js_content)

    html = INLINE_CSS_PATTERN.sub(replace_css_inline, template_text)
    html = INLINE_PATTERN.sub(replace_inline, html)
    return html, {
        "replaced": replaced,
        # Keep the legacy metric as a CSS-bundle indicator; css_sources carries
        # the exact file list when multiple stylesheets are inlined.
        "css_replaced": 1 if css_replaced else 0,
        "missing": missing,
        "sources": sources,
        "css_sources": css_sources,
    }


def build(*, output_path: Path = OUTPUT_PATH, strict: bool = True, write: bool = True) -> dict:
    if not TEMPLATE_PATH.is_file():
        return {"ok": False, "error": f"template not found: {TEMPLATE_PATH}", "replaced": 0, "missing": []}
    try:
        html, stats = build_inline(_read_source_text(TEMPLATE_PATH), strict=strict)
    except FileNotFoundError as exc:
        return {"ok": False, "error": str(exc), "replaced": 0, "missing": []}
    if write:
        output_path.write_text(html, encoding="utf-8")
    return {"ok": True, "output": str(output_path), "bytes": len(html.encode("utf-8")), **stats}


def check(output_path: Path = OUTPUT_PATH, *, strict: bool = True) -> dict:
    result = build(output_path=output_path, strict=strict, write=False)
    if not result.get("ok"):
        return result
    if not output_path.is_file():
        return {**result, "ok": False, "error": f"output not found: {output_path}"}
    expected, _stats = build_inline(_read_source_text(TEMPLATE_PATH), strict=strict)
    actual = output_path.read_text(encoding="utf-8")
    if actual != expected:
        return {
            **result,
            "ok": False,
            "error": "built index.html is stale; run brain_alpha_ops/web/build_inline.py",
            "expected_bytes": len(expected.encode("utf-8")),
            "actual_bytes": len(actual.encode("utf-8")),
        }
    return {**result, "ok": True, "error": ""}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build or check web/index.html from modular JS sources.")
    parser.add_argument("--check", action="store_true", help="Fail if index.html is not synchronized with index_template.html and js/*.js.")
    parser.add_argument("--output", default=str(OUTPUT_PATH), help="Output path for build mode.")
    parser.add_argument("--no-strict", action="store_true", help="Keep missing inline markers instead of failing.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    output_path = Path(args.output)
    result = check(output_path, strict=not args.no_strict) if args.check else build(output_path=output_path, strict=not args.no_strict)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif result.get("ok"):
        action = "Checked" if args.check else "Built"
        print(f"{action} {output_path} ({result.get('bytes', 0)} bytes, {result.get('replaced', 0)} modules inlined)")
    else:
        print(f"ERROR: {result.get('error', 'inline build failed')}", file=sys.stderr)
        if result.get("missing"):
            print("Missing sources:", ", ".join(result["missing"]), file=sys.stderr)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
