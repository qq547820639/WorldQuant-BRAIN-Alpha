from __future__ import annotations

import logging

from brain_alpha_ops.research.cross_review_pipeline import CrossReviewPipeline
from brain_alpha_ops.research.hypothesis_driven_generator import HypothesisDrivenGenerator
from brain_alpha_ops.research.local_backtest_engine import LocalBacktestEngine


def test_cross_review_pipeline_redacts_fallback_error_messages(caplog, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("cross-review token=secret-xyz")

    monkeypatch.setattr(
        "brain_alpha_ops.research.llm_review.cross_review_assistant_response",
        boom,
    )

    pipeline = CrossReviewPipeline(storage_dir="data")

    with caplog.at_level(logging.WARNING, logger="brain_alpha_ops.research.cross_review_pipeline"):
        decision = pipeline.review(
            request_pack={"prompt_digest": "pd_1"},
            primary_response='{"summary": "ok", "confidence": 0.9, "risk_flags": []}',
            force_review=True,
        )

    assert decision.decision in {"accept", "accept_with_warnings", "conservative_review_required", "reject"}
    assert "cross_review failed, falling back to offline reviewer:" in caplog.text
    assert "secret-xyz" not in caplog.text


def test_hypothesis_generator_redacts_theme_engine_failures(caplog):
    class FailingThemeEngine:
        def generate(self, dataset_id, n=1):
            raise RuntimeError(f"theme engine token=secret-{dataset_id}")

        def mutate_expression(self, expression, dataset_id, seed=None):
            return expression

    gen = HypothesisDrivenGenerator(
        loader=None,
        mapper=None,
        theme_engine=FailingThemeEngine(),
        selector=None,
        library=None,
    )
    gen.update_context(["close"], ["rank", "ts_delta"])

    with caplog.at_level(logging.WARNING, logger="brain_alpha_ops.research.hypothesis_driven_generator"):
        candidate = gen._generate_random_exploration("pv1")

    assert candidate is not None
    assert "_generate_random_exploration: ThemeEngine failed:" in caplog.text
    assert "secret-pv1" not in caplog.text


def test_local_backtest_redacts_unexpected_expression_failures(caplog):
    engine = LocalBacktestEngine(seed=1, n_dates=20, n_symbols=20)

    def fail_evaluate(_expression, _data):
        raise RuntimeError("local backtest token=secret-local-123")

    engine.evaluator.evaluate = fail_evaluate

    with caplog.at_level(logging.ERROR, logger="brain_alpha_ops.research.local_backtest_engine"):
        result = engine.evaluate("rank(close) + token=secret-expression-123")

    assert result["ok"] is False
    assert "unexpected error evaluating expression:" in caplog.text
    assert "secret-local-123" not in caplog.text
    assert "secret-expression-123" not in caplog.text
