import json

import pytest

from brain_alpha_ops.research.assistant import AssistantResponseParseError
from brain_alpha_ops.research.llm_review import CrossReviewService, FallbackLLMProvider, LLMProviderRouter, OpenAICompatibleProvider, PromptRunLedger, StaticLLMProvider


def _response(*, actions=None, risks=None, confidence=0.8):
    return json.dumps(
        {
            "summary": "Use memory-supported generation.",
            "recommended_next_actions": actions or ["refresh cloud cache"],
            "risk_flags": risks or ["cloud_sync_required"],
            "candidate_adjustments": [],
            "follow_up_questions": [],
            "confidence": confidence,
        }
    )


def test_cross_review_accepts_consistent_high_confidence_responses():
    result = CrossReviewService().review(
        {"prompt_digest": "pd_1"},
        _response(),
        reviewer_response=_response(),
        min_confidence=0.6,
    )

    assert result["ok"] is True
    assert result["decision"] == "accept"
    assert result["agreement"] is True
    assert result["conservative"] is False


def test_cross_review_uses_conservative_decision_on_conflict():
    result = CrossReviewService().review(
        {"prompt_digest": "pd_1"},
        _response(actions=["generate candidates"], risks=["cloud_sync_required"]),
        reviewer_response=_response(actions=["stop submission"], risks=["duplicate_expression_history"]),
        min_confidence=0.6,
    )

    assert result["decision"] == "conservative_review_required"
    assert result["agreement"] is False
    assert result["conservative"] is True
    assert sorted(result["risk_flags"]) == ["cloud_sync_required", "duplicate_expression_history"]


def test_cross_review_rejects_non_json_model_response():
    with pytest.raises(AssistantResponseParseError):
        CrossReviewService().review({"prompt_digest": "pd_1"}, "not json")


def test_cross_review_can_call_provider_when_reviewer_not_supplied():
    provider = StaticLLMProvider(_response(actions=["refresh cloud cache"]))

    result = CrossReviewService(provider).review({"prompt_digest": "pd_1"}, _response())

    assert result["decision"] == "accept"
    assert result["reviewer_confidence"] == 0.8


def test_fallback_llm_provider_uses_next_provider_after_failure():
    class FailingProvider:
        name = "failing"

        def complete(self, request):
            raise RuntimeError("provider down token=secret")

    provider = FallbackLLMProvider([FailingProvider(), StaticLLMProvider(_response(), name="backup")])

    output = provider.complete({"messages": []})

    assert json.loads(output)["confidence"] == 0.8


def test_fallback_llm_provider_reports_all_failures_without_key_material():
    class FailingProvider:
        name = "failing"

        def complete(self, request):
            raise RuntimeError("provider down")

    provider = FallbackLLMProvider([FailingProvider()])

    with pytest.raises(RuntimeError, match="all LLM providers failed"):
        provider.complete({"messages": []})


def test_llm_provider_router_uses_task_route():
    provider = LLMProviderRouter(
        [
            StaticLLMProvider(_response(confidence=0.1), name="general"),
            StaticLLMProvider(_response(confidence=0.9), name="reviewer"),
        ],
        task_routes={"cross_review": ["reviewer"]},
    )

    output = provider.complete({"task": "cross_review", "messages": []})

    assert json.loads(output)["confidence"] == 0.9
    snapshot = provider.snapshot()
    assert snapshot["schema_version"] == "llm_provider_router.v1"
    assert snapshot["health"]["reviewer"]["ok_count"] == 1
    assert "general" not in snapshot["health"]


def test_llm_provider_router_falls_back_and_records_redacted_health():
    class FailingProvider:
        name = "primary"

        def complete(self, request):
            raise RuntimeError("provider down token=secret-123")

    provider = LLMProviderRouter(
        [FailingProvider(), StaticLLMProvider(_response(), name="backup")],
        task_routes={"cross_review": ["primary", "backup"]},
    )

    output = provider.complete({"task": "cross_review", "messages": []})

    assert json.loads(output)["confidence"] == 0.8
    health = provider.snapshot()["health"]
    assert health["primary"]["error_count"] == 1
    assert health["backup"]["ok_count"] == 1
    assert "secret-123" not in health["primary"]["last_error"]


def test_prompt_run_ledger_records_digests_without_response_text(tmp_path):
    row = PromptRunLedger(tmp_path).record(
        request_pack={"prompt": "hello", "context_pack": {"x": 1}},
        model="offline",
        temperature=0.2,
        response_text="secret-token-123 response",
        parse_status="parsed",
    )

    text = (tmp_path / "prompt_runs.jsonl").read_text(encoding="utf-8")
    assert row["schema_version"] == "prompt_run_ledger.v1"
    assert row["model"] == "offline"
    assert row["parse_status"] == "parsed"
    assert "secret-token-123" not in text


def test_openai_compatible_provider_posts_chat_completion_request():
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, _exc_type, _exc, _tb):
            return False

        def read(self):
            return json.dumps({"choices": [{"message": {"content": _response()}}]}).encode("utf-8")

    def transport(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["headers"] = dict(request.header_items())
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return Response()

    provider = OpenAICompatibleProvider(
        api_key="test-key",
        base_url="https://provider.example/v1",
        model="reviewer-model",
        temperature=0.1,
        transport=transport,
    )

    output = provider.complete(
        {
            "messages": [{"role": "user", "content": "review"}],
            "response_schema": {"schema_version": "assistant_response.v1"},
        }
    )

    assert json.loads(output)["confidence"] == 0.8
    assert captured["url"] == "https://provider.example/v1/chat/completions"
    assert captured["timeout"] == 60.0
    assert captured["payload"]["model"] == "reviewer-model"
    assert captured["payload"]["temperature"] == 0.1
    assert captured["payload"]["response_format"] == {"type": "json_object"}
    assert captured["headers"]["Authorization"] == "Bearer test-key"
