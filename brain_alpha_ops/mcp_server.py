"""Minimal stdio MCP-style adapter for Brain Alpha Ops tools.

It implements the small JSON-RPC surface needed by MCP clients to discover and
call the whitelisted tools.  The business logic stays in agent_tools.py.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, TextIO

from brain_alpha_ops.agent_tools import BrainAlphaToolbox
from brain_alpha_ops.config import load_run_config
from brain_alpha_ops.web import CHECK_JOBS, JOBS, SYNC_JOBS


JSONRPC_VERSION = "2.0"


def handle_request(request: dict[str, Any], toolbox: BrainAlphaToolbox) -> dict[str, Any] | None:
    request_id = request.get("id")
    method = str(request.get("method", "") or "")
    params = request.get("params") if isinstance(request.get("params"), dict) else {}

    if method == "notifications/initialized":
        return None
    if method == "initialize":
        return _result(request_id, {
            "protocolVersion": str(params.get("protocolVersion") or "2024-11-05"),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "brain-alpha-ops", "version": "0.3.0"},
        })
    if method == "tools/list":
        return _result(request_id, {
            "tools": [
                {
                    "name": tool["name"],
                    "description": tool["description"],
                    "inputSchema": tool["input_schema"],
                    "annotations": {
                        "liveApi": bool(tool.get("live_api")),
                        "destructive": bool(tool.get("destructive")),
                    },
                }
                for tool in toolbox.list_tools()
            ]
        })
    if method == "tools/call":
        tool_name = str(params.get("name", "") or "")
        arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
        payload = toolbox.call(tool_name, arguments)
        return _result(request_id, {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(payload, ensure_ascii=False, default=str),
                }
            ],
            "isError": not bool(payload.get("ok")),
        })
    return _error(request_id, -32601, f"method not found: {method}")


def serve_stdio(toolbox: BrainAlphaToolbox, stdin: TextIO | None = None, stdout: TextIO | None = None) -> None:
    input_stream = stdin or sys.stdin
    output_stream = stdout or sys.stdout
    for line in input_stream:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            if not isinstance(request, dict):
                raise ValueError("request must be a JSON object")
            response = handle_request(request, toolbox)
        except Exception as exc:
            response = _error(None, -32700, str(exc))
        if response is None:
            continue
        output_stream.write(json.dumps(response, ensure_ascii=False, default=str) + "\n")
        output_stream.flush()


def build_toolbox(config_path: str = "", *, allow_live_api: bool = False, allow_submit: bool = False) -> BrainAlphaToolbox:
    run_config = load_run_config(config_path or None)
    return BrainAlphaToolbox(
        run_config=run_config,
        allow_live_api=allow_live_api,
        allow_submit=allow_submit,
        job_stores={
            "production": JOBS,
            "sync": SYNC_JOBS,
            "check": CHECK_JOBS,
        },
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Brain Alpha Ops MCP-style stdio adapter.")
    parser.add_argument("--config", default="")
    parser.add_argument("--allow-live-api", action="store_true")
    parser.add_argument("--allow-submit", action="store_true")
    args = parser.parse_args(argv)

    serve_stdio(
        build_toolbox(
            args.config,
            allow_live_api=args.allow_live_api,
            allow_submit=args.allow_submit,
        )
    )
    return 0


def _result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": JSONRPC_VERSION,
        "id": request_id,
        "error": {"code": code, "message": message},
    }


if __name__ == "__main__":
    raise SystemExit(main())
