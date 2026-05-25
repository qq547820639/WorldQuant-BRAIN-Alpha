from __future__ import annotations

from brain_alpha_ops.research.pipeline_observability import (
    apply_observability_generation_guidance,
    failed_generation_guidance,
    refresh_observability_throttle,
)


class _Generator:
    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.guidance = None

    def set_observability_guidance(self, guidance):
        if self.fail:
            raise RuntimeError("guidance sink unavailable")
        self.guidance = guidance


def _snapshot():
    return {
        "expression_index": {
            "top_duplicates": [
                {
                    "expression_canonical": "rank(close)",
                    "expression_fingerprint": "abcdef1234567890",
                    "duplicate_count": 3,
                    "source_count": 2,
                    "sources": {"candidate": 1, "backtest": 1},
                    "alpha_ids": ["a1"],
                }
            ]
        }
    }


def _context():
    return {
        "risk_level": "medium",
        "health_flags": ["high_duplicate_expression_ratio"],
        "duplicate_ratio": 0.5,
        "blocking_flags": [],
        "warning_flags": ["duplicate_expression_history"],
        "recommended_actions": ["diversify generation"],
        "generated_at": "now",
    }


def test_apply_observability_generation_guidance_sets_generator_and_emits_event():
    events = []
    generator = _Generator()

    guidance = apply_observability_generation_guidance(
        snapshot=_snapshot(),
        context=_context(),
        cycle=2,
        generator=generator,
        event=lambda *args, **kwargs: events.append((args, kwargs)),
    )

    assert guidance["active"] is True
    assert guidance["status"] == "applied"
    assert guidance["applied_to_generator"] is True
    assert generator.guidance["avoid_expressions"]
    assert events[0][0][0] == "observability_generation_guidance_applied"


def test_apply_observability_generation_guidance_records_setter_failure():
    events = []

    guidance = apply_observability_generation_guidance(
        snapshot=_snapshot(),
        context=_context(),
        cycle=3,
        generator=_Generator(fail=True),
        event=lambda *args, **kwargs: events.append((args, kwargs)),
    )

    assert guidance["status"] == "apply_failed"
    assert guidance["applied_to_generator"] is False
    assert "guidance sink unavailable" in guidance["error"]
    assert events[0][0][0] == "observability_generation_guidance_failed"
    assert events[0][1]["data"]["error_code"] == "OBSERVABILITY_GENERATION_GUIDANCE_FAILED"


def test_refresh_observability_throttle_builds_ready_payload():
    events = []

    result = refresh_observability_throttle(
        storage_dir="data",
        cycle=4,
        generator=_Generator(),
        event=lambda *args, **kwargs: events.append((args, kwargs)),
        guard_snapshot=lambda: {"blocked_count": 0},
        observability_builder=lambda *args, **kwargs: _snapshot(),
    )

    assert result.throttle["ok"] is True
    assert result.throttle["status"] == "ready"
    assert result.throttle["generation_guidance"]["active"] is True
    assert result.blocking_flags == []


def test_refresh_observability_throttle_returns_failure_payload():
    events = []

    def fail(*_args, **_kwargs):
        raise RuntimeError("observability store unavailable")

    result = refresh_observability_throttle(
        storage_dir="data",
        cycle=5,
        generator=_Generator(),
        event=lambda *args, **kwargs: events.append((args, kwargs)),
        guard_snapshot=lambda: {"blocked_count": 1},
        observability_builder=fail,
    )

    assert result.throttle["ok"] is False
    assert result.throttle["status"] == "refresh_failed"
    assert result.generation_guidance["status"] == "refresh_failed"
    assert result.throttle["official_call_guard"] == {"blocked_count": 1}
    assert events[0][0][0] == "observability_refresh_failed"
    assert events[0][1]["data"]["error_code"] == "OBSERVABILITY_REFRESH_FAILED"


def test_failed_generation_guidance_is_compact_and_redacted_shape():
    payload = failed_generation_guidance(1, "Generator", "boom")

    assert payload["schema_version"] == "observability_generation_guidance_summary.v1"
    assert payload["active"] is False
    assert payload["generator_type"] == "Generator"
