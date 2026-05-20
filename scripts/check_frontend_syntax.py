"""Check local frontend JavaScript syntax without a browser.

The web console is built by inlining JavaScript files into index.html. This
script extracts inline <script> blocks and asks Node.js to compile each block
with vm.Script. External CDN scripts are ignored.
"""

from __future__ import annotations

import argparse
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HTML = PROJECT_ROOT / "brain_alpha_ops" / "web" / "index.html"
BUNDLED_NODE_DIR = Path.home() / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies" / "node" / "bin"
BUNDLED_NODE_CANDIDATES = [BUNDLED_NODE_DIR / "node.exe", BUNDLED_NODE_DIR / "node"]


class InlineScriptExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.blocks: list[dict] = []
        self._current: dict | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "script":
            return
        attr_map = {key.lower(): value for key, value in attrs}
        if attr_map.get("src"):
            return
        self._current = {"line": self.getpos()[0], "content": []}

    def handle_data(self, data: str) -> None:
        if self._current is not None:
            self._current["content"].append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self._current is not None:
            content = "".join(self._current["content"]).strip()
            if content:
                self.blocks.append({"line": self._current["line"], "content": content})
            self._current = None


def extract_inline_scripts(html: str) -> list[dict]:
    parser = InlineScriptExtractor()
    parser.feed(html)
    return parser.blocks


def _node_path(explicit: str = "") -> str:
    if explicit:
        return explicit
    for candidate in BUNDLED_NODE_CANDIDATES:
        if candidate.is_file():
            return str(candidate)
    found = shutil.which("node")
    if found:
        return found
    return ""


def check_scripts(html_path: Path, *, node: str = "") -> dict:
    node_path = _node_path(node)
    if not node_path:
        return {"ok": False, "error": "node executable not found", "checked": 0, "failures": []}
    html = html_path.read_text(encoding="utf-8")
    blocks = extract_inline_scripts(html)
    failures: list[dict] = []

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        checker = tmp_dir / "check.js"
        checker.write_text(
            """
const fs = require('fs');
const vm = require('vm');
const file = process.argv[2];
try {
  new vm.Script(fs.readFileSync(file, 'utf8'), { filename: file });
} catch (err) {
  console.error(err && err.stack ? err.stack : String(err));
  process.exit(1);
}
""".strip(),
            encoding="utf-8",
        )
        for index, block in enumerate(blocks, start=1):
            script_path = tmp_dir / f"script_{index}.js"
            script_path.write_text(str(block["content"]), encoding="utf-8")
            proc = subprocess.run(
                [node_path, str(checker), str(script_path)],
                cwd=str(PROJECT_ROOT),
                text=True,
                capture_output=True,
                timeout=30,
            )
            if proc.returncode != 0:
                failures.append({
                    "script_index": index,
                    "html_line": block["line"],
                    "error": (proc.stderr or proc.stdout).strip(),
                })

    return {"ok": not failures, "checked": len(blocks), "failures": failures}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check inline frontend JavaScript syntax")
    parser.add_argument("--html", default=str(DEFAULT_HTML))
    parser.add_argument("--node", default=os.getenv("NODE", ""))
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    args = parser.parse_args(argv)

    result = check_scripts(Path(args.html), node=args.node)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif result["ok"]:
        print(f"OK: checked {result['checked']} inline script blocks")
    else:
        print(f"FAILED: {len(result['failures'])} script block(s) failed syntax checks")
        for failure in result["failures"]:
            print(f"- script #{failure['script_index']} near HTML line {failure['html_line']}:")
            print(failure["error"])
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
