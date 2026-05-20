from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.web_candidate_generation import generate_candidates_payload


class FakeToolbox:
    def __init__(self, result, calls):
        self.result = result
        self.calls = calls

    def call(self, name, arguments=None):
        self.calls.append((name, dict(arguments or {})))
        return self.result


class FakeRepository:
    def __init__(self, storage_dir, saves):
        self.storage_dir = storage_dir
        self.saves = saves

    def save_assistant_guidance(self, guidance, source):
        self.saves.append({"storage_dir": self.storage_dir, "guidance": dict(guidance), "source": source})


def test_generate_candidates_payload_delegates_to_toolbox_and_scores_candidates(tmp_path):
    run_config = RunConfig(environment="mock")
    run_config.ops.storage_dir = str(tmp_path)
    calls = []
    saves = []
    toolbox_result = {
        "ok": True,
        "assistant_guidance": {
            "ok": True,
            "applied": True,
            "usable": True,
            "confidence": 0.9,
            "top_fields": ["close"],
            "top_operators": ["rank"],
            "preferred_windows": [20],
            "historical_outcome_status": "strong",
            "historical_outcome": {"count": 2, "success_count": 1, "success_rate": 0.5},
        },
        "candidates": [
            {
                "alpha_id": "alpha_1",
                "expression": "rank(close)",
                "family": "demo",
                "hypothesis": "close rank",
                "data_fields": ["close"],
                "operators": ["rank"],
            }
        ],
    }

    payload = generate_candidates_payload(
        {"count": 2000, "assistant_min_confidence": 2, "use_research_memory": False},
        run_config_from_payload=lambda body: run_config,
        toolbox_factory=lambda config: FakeToolbox(toolbox_result, calls),
        repository_factory=lambda storage_dir: FakeRepository(storage_dir, saves),
    )

    assert payload["ok"] is True
    assert payload["count"] == 1
    assert calls[0][0] == "generate_candidates"
    assert calls[0][1]["count"] == 1000
    assert calls[0][1]["assistant_min_confidence"] == 1.0
    assert calls[0][1]["use_research_memory"] is False
    assert payload["candidates"][0]["scorecard"]["score_basis"] == "local_prior"
    assert "assistant_guided" in payload["candidates"][0]["source_tags"]
    assert payload["candidates"][0]["submission"]["assistant_guidance_digest"].startswith("ag_")
    assert saves[0]["source"] == "web_generate_candidates"


def test_generate_candidates_payload_returns_toolbox_error_without_post_processing(tmp_path):
    run_config = RunConfig(environment="mock")
    run_config.ops.storage_dir = str(tmp_path)

    payload = generate_candidates_payload(
        {"count": 3},
        run_config_from_payload=lambda body: run_config,
        toolbox_factory=lambda config: FakeToolbox({"ok": False, "error": "bad"}, []),
        repository_factory=lambda storage_dir: FakeRepository(storage_dir, []),
    )

    assert payload == {"ok": False, "error": "bad"}
