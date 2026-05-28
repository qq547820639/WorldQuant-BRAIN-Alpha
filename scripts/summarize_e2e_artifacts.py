"""Generate a redacted summary of browser E2E evidence artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brain_alpha_ops.e2e_report import build_e2e_artifact_summary, render_markdown_summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize E2E screenshots, console logs, and job ledgers.")
    parser.add_argument("--root", default=".", help="Workspace root.")
    parser.add_argument("--evidence-dir", default="data/e2e_screenshots", help="Directory containing E2E artifacts.")
    parser.add_argument("--output-json", help="Optional path for the JSON summary.")
    parser.add_argument("--output-md", help="Optional path for the Markdown summary.")
    parser.add_argument("--json", action="store_true", help="Print the JSON summary to stdout.")
    args = parser.parse_args(argv)

    payload = build_e2e_artifact_summary(root=args.root, evidence_dir=args.evidence_dir)
    if args.output_json:
        output_json = _resolve_output(Path(args.root), args.output_json)
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    if args.output_md:
        output_md = _resolve_output(Path(args.root), args.output_md)
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text(render_markdown_summary(payload), encoding="utf-8")
    if args.json or not (args.output_json or args.output_md):
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0 if payload.get("ok") else 1


def _resolve_output(root: Path, path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return root / candidate


if __name__ == "__main__":
    raise SystemExit(main())
