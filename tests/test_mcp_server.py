import json
from io import StringIO

from brain_alpha_ops.agent_tools import BrainAlphaToolbox
from tests.production_api_stub import ProductionBrainAPIStub
from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.mcp_server import handle_request, serve_stdio


def toolbox(tmp_path):
    config = RunConfig(environment="production")
    config.ops.storage_dir = str(tmp_path)
    return BrainAlphaToolbox(run_config=config, api=ProductionBrainAPIStub())


def test_mcp_initialize_and_tool_list(tmp_path):
    tb = toolbox(tmp_path)

    init = handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}, tb)
    tools = handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, tb)

    assert init["result"]["capabilities"]["tools"] == {}
    names = {tool["name"] for tool in tools["result"]["tools"]}
    assert "generate_candidates" in names
    assert "score_factor" in names
    assert "run_backtest" in names
    assert "run_batch_backtest" in names
    assert "run_parallel_backtest" in names
    assert "submit_alpha" in names
    listed = {tool["name"]: tool for tool in tools["result"]["tools"]}
    assert listed["score_factor"]["annotations"]["aliasFor"] == "score_candidate"
    assert listed["score_factor"]["annotations"]["chainStage"] == "screen"
    assert listed["run_backtest"]["annotations"]["aliasFor"] == "run_simulation"
    assert listed["run_backtest"]["annotations"]["liveApi"] is True
    assert listed["run_batch_backtest"]["annotations"]["aliasFor"] == "run_simulation_batch"
    assert listed["run_batch_backtest"]["annotations"]["liveApi"] is True
    assert listed["run_parallel_backtest"]["annotations"]["liveApi"] is True


def test_mcp_tool_call_returns_text_content(tmp_path):
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "score_candidate",
                "arguments": {"expression": "rank(ts_delta(close, 20))"},
            },
        },
        toolbox(tmp_path),
    )

    assert response["result"]["isError"] is False
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert payload["scorecard"]["total_score"] > 0


def test_mcp_tool_call_resolves_quantgpt_style_alias(tmp_path):
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 33,
            "method": "tools/call",
            "params": {
                "name": "score_factor",
                "arguments": {"expression": "rank(ts_delta(close, 20))"},
            },
        },
        toolbox(tmp_path),
    )

    assert response["result"]["isError"] is False
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert payload["tool_alias"] == "score_factor"
    assert payload["canonical_tool"] == "score_candidate"


def test_mcp_stdio_serves_line_delimited_json(tmp_path):
    request = json.dumps({"jsonrpc": "2.0", "id": 4, "method": "tools/list"}) + "\n"
    output = StringIO()

    serve_stdio(toolbox(tmp_path), stdin=StringIO(request), stdout=output)

    response = json.loads(output.getvalue().strip())
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == 4
    assert response["result"]["tools"]
