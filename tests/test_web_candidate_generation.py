from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.web_candidate_generation import generate_candidates_payload


class FakeToolbox:
    def __init__(self, result, calls):
        self.result = result
        self.calls = calls

    def call(self, name, arguments=None):
        self.calls.append((name, dict(arguments or {})))
        return self.result


class RaisingToolbox:
    def __init__(self, exc, calls):
        self.exc = exc
        self.calls = calls

    def call(self, name, arguments=None):
        self.calls.append((name, dict(arguments or {})))
        raise self.exc


class FakeRepository:
    def __init__(self, storage_dir, saves):
        self.storage_dir = storage_dir
        self.saves = saves

    def save_assistant_guidance(self, guidance, source):
        self.saves.append({"storage_dir": self.storage_dir, "guidance": dict(guidance), "source": source})


def test_generate_candidates_payload_delegates_to_toolbox_and_scores_candidates(tmp_path):
    run_config = RunConfig(environment="production")
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


def test_generate_candidates_payload_empty_payload_uses_defaults(tmp_path):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)
    run_config.ops.settings.dataset = "dataset_default"
    calls = []

    payload = generate_candidates_payload(
        {},
        run_config_from_payload=lambda body: run_config,
        toolbox_factory=lambda config: FakeToolbox({"ok": True, "candidates": []}, calls),
        repository_factory=lambda storage_dir: FakeRepository(storage_dir, []),
    )

    assert payload["ok"] is True
    assert payload["count"] == 0
    assert calls[0][1]["count"] == 10
    assert calls[0][1]["dataset_id"] == "dataset_default"
    assert calls[0][1]["use_research_memory"] is True
    assert calls[0][1]["top_n"] == 10
    assert calls[0][1]["min_success_rate"] == 0.0
    assert calls[0][1]["assistant_min_confidence"] == 0.0


def test_generate_candidates_payload_resolves_empty_dataset_from_cache(tmp_path):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)
    (tmp_path / "official_datasets.json").write_text(
        '[{"id":"ds_a"},{"id":"pv1"},{"id":"ds_b"}]',
        encoding="utf-8",
    )
    run_config.ops.settings.dataset = ""
    calls = []

    payload = generate_candidates_payload(
        {},
        run_config_from_payload=lambda body: run_config,
        toolbox_factory=lambda config: FakeToolbox({"ok": True, "candidates": []}, calls),
        repository_factory=lambda storage_dir: FakeRepository(storage_dir, []),
    )

    assert payload["ok"] is True
    assert calls[0][1]["dataset_id"] == "pv1"
    assert run_config.ops.settings.dataset == "pv1"


def test_generate_candidates_payload_returns_toolbox_error_without_post_processing(tmp_path):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)

    payload = generate_candidates_payload(
        {"count": 3},
        run_config_from_payload=lambda body: run_config,
        toolbox_factory=lambda config: FakeToolbox({"ok": False, "error": "bad"}, []),
        repository_factory=lambda storage_dir: FakeRepository(storage_dir, []),
    )

    assert payload == {"ok": False, "error": "bad"}


def test_generate_candidates_payload_returns_structured_error_on_toolbox_exception(tmp_path):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)
    calls = []

    payload = generate_candidates_payload(
        {"count": 3},
        run_config_from_payload=lambda body: run_config,
        toolbox_factory=lambda config: RaisingToolbox(RuntimeError("token secret-token-123 failed"), calls),
        repository_factory=lambda storage_dir: FakeRepository(storage_dir, []),
    )

    assert payload["ok"] is False
    assert payload["error_code"] == "GENERATE_CANDIDATES_TOOLBOX_ERROR"
    assert payload["error_type"] == "RuntimeError"
    assert payload["phase"] == "web_generate_candidates"
    assert "secret-token-123" not in payload["error"]
    assert calls[0][0] == "generate_candidates"


def test_generate_candidates_payload_rejects_non_mapping_toolbox_response(tmp_path):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)

    payload = generate_candidates_payload(
        {"count": 3},
        run_config_from_payload=lambda body: run_config,
        toolbox_factory=lambda config: FakeToolbox(["not", "a", "dict"], []),
        repository_factory=lambda storage_dir: FakeRepository(storage_dir, []),
    )

    assert payload["ok"] is False
    assert payload["error_code"] == "GENERATE_CANDIDATES_VALIDATION_ERROR"
    assert payload["error_category"] == "validation"
