import json

from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.assistant import assistant_response_to_generation_guidance, build_assistant_request_pack, parse_assistant_response
from brain_alpha_ops.research.context import build_assistant_context_pack
from brain_alpha_ops.research.repository import ResearchRepository


def test_assistant_request_pack_wraps_context_with_schema_and_draft(tmp_path):
    config = RunConfig(environment="mock")
    config.ops.storage_dir = str(tmp_path)
    ResearchRepository(str(tmp_path)).save_candidate(
        "run_1",
        Candidate(
            alpha_id="a1",
            expression="rank(ts_delta(close, 20))",
            family="Momentum",
            hypothesis="price momentum",
            data_fields=["close"],
            operators=["rank", "ts_delta"],
            source_tags=["assistant_guided", "assistant_guidance_ag_requestdigest"],
            official_metrics={"sharpe": 1.8, "fitness": 1.2, "pass_fail": "PASS"},
            scorecard={"total_score": 88},
            gate={"submission_ready": True},
            submission={"assistant_guidance_digest": "ag_requestdigest"},
            lifecycle_status="submission_ready",
        ),
    )
    context = build_assistant_context_pack(config, top_n=3)

    request = build_assistant_request_pack(context)

    assert request["ok"] is True
    assert request["schema_version"] == "assistant_request_pack.v1"
    assert request["context_schema_version"] == "assistant_context_pack.v1"
    assert request["request"]["messages"][0]["role"] == "system"
    assert request["request"]["response_schema"]["schema_version"] == "assistant_response.v1"
    assert request["prompt_diagnostics"]["schema_version"] == "assistant_request_prompt_diagnostics.v1"
    assert request["prompt_diagnostics"]["estimated_prompt_tokens"] > 0
    assert request["request"]["model_hints"]["prompt_budget"]["estimated_prompt_tokens"] == request["prompt_diagnostics"]["estimated_prompt_tokens"]
    assert "rank" in request["prompt"]
    assert "prompt" not in request["context_pack"]
    assert request["offline_draft"]["schema_version"] == "assistant_response.v1"
    assert request["offline_draft"]["candidate_adjustments"]
    assert request["offline_draft"]["evidence"]["top_guidance_digest"] == "ag_requestdigest"
    assert "ag_requestdigest" in request["offline_draft"]["summary"]
    assert any(
        item.get("target") == "assistant_guidance_digest"
        for item in request["offline_draft"]["candidate_adjustments"]
    )
    assert any("ag_requestdigest" in item for item in request["offline_draft"]["recommended_next_actions"])


def test_assistant_request_pack_compacts_prompt_when_budget_is_exceeded():
    context = {
        "ok": True,
        "schema_version": "assistant_context_pack.v1",
        "prompt": "large prompt\n" + ("duplicate evidence " * 5000),
        "latest_result": {"top_candidates": [{"alpha_id": f"a{i}", "expression": "rank(close)"} for i in range(20)]},
        "generation_focus": {"fields": [f"field_{i}" for i in range(20)]},
    }

    request = build_assistant_request_pack(
        context,
        include_offline_draft=False,
        max_prompt_tokens=1200,
    )

    budget = request["request"]["model_hints"]["prompt_budget"]
    assert budget["budget_applied"] is True
    assert budget["max_prompt_tokens"] == 1200
    assert budget["truncated_sections"]
    assert "review_chain" in request
    assert [row["role"] for row in request["review_chain"]] == [
        "generator_advisor",
        "risk_reviewer",
        "expression_novelty_reviewer",
    ]


def test_parse_assistant_response_extracts_fenced_json():
    raw = (
        "Model notes before JSON\n```json\n"
        + json.dumps(
            {
                "summary": "Focus on price momentum while checking stale cloud risk.",
                "next_actions": ["refresh cache", "generate five variants"],
                "risks": ["cloud_cache_stale"],
                "ideas": [{"focus": "operators", "proposal": ["rank", "ts_delta"], "reason": "memory"}],
                "questions": ["refresh now?"],
                "confidence": 82,
            }
        )
        + "\n```"
    )

    parsed = parse_assistant_response(raw)

    assert parsed["ok"] is True
    assert parsed["recommended_next_actions"] == ["refresh cache", "generate five variants"]
    assert parsed["risk_flags"] == ["cloud_cache_stale"]
    assert parsed["candidate_adjustments"][0]["target"] == "operators"
    assert parsed["confidence"] == 0.82


def test_assistant_response_to_generation_guidance_maps_adjustments_and_flags():
    response = {
        "summary": "Use close momentum with guarded submission.",
        "recommended_next_actions": ["refresh cloud cache", "wait for pending backtests"],
        "risk_flags": ["submit_requires_confirmation"],
        "candidate_adjustments": [
            {"target": "fields", "value": ["close", "volume"], "rationale": "memory"},
            {"target": "operators", "value": ["rank", "ts_delta"], "rationale": "memory"},
            {"target": "windows", "value": [20, "60"], "rationale": "lookbacks"},
            {"target": "failure_mode", "value": "LOW_SHARPE", "rationale": "recurring"},
        ],
        "confidence": 0.74,
    }

    guidance = assistant_response_to_generation_guidance(response, min_confidence=0.7)

    assert guidance["ok"] is True
    assert guidance["schema_version"] == "assistant_generation_guidance.v1"
    assert guidance["guidance_digest"].startswith("ag_")
    assert guidance["usable"] is True
    assert guidance["top_fields"] == ["close", "volume"]
    assert guidance["top_operators"] == ["rank", "ts_delta"]
    assert guidance["preferred_windows"] == [20, 60]
    assert guidance["avoid_patterns"][0]["value"] == "LOW_SHARPE"
    assert guidance["operational_flags"]["refresh_cloud_before_submit"] is True
    assert guidance["operational_flags"]["wait_for_pending_backtests"] is True
    assert guidance["operational_flags"]["submit_requires_confirmation"] is True


def test_assistant_response_to_generation_guidance_marks_low_confidence_unusable():
    guidance = assistant_response_to_generation_guidance(
        {"summary": "Weak signal.", "candidate_adjustments": [], "confidence": 0.25},
        min_confidence=0.8,
    )

    assert guidance["usable"] is False
    assert guidance["confidence"] == 0.25
