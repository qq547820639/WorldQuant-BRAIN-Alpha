"""Minimal smoke test — verify the pipeline can complete or timeout cleanly."""

from __future__ import annotations

import logging
import time

import pytest

from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.config_models import ResearchBudget
from brain_alpha_ops.ux.guided_pipeline import GuidedPipeline
from brain_alpha_ops.models import PipelineResult, Candidate, new_id

logger = logging.getLogger(__name__)


def _make_smoke_config(tmp_path: str) -> RunConfig:
    """Build a RunConfig with tiny budget and unreachable BRAIN API."""
    config = RunConfig(environment="development")
    config.ops.storage_dir = str(tmp_path)

    # Override budget with tiny limits
    budget = config.ops.budget
    budget.max_candidates_per_cycle = 3
    budget.max_official_validations_per_cycle = 1
    budget.max_official_simulations_per_cycle = 0
    budget.max_official_concurrent_simulations = 0
    budget.retained_alpha_pool_size = 5
    budget.official_backtest_batch_size = 1
    budget.min_local_quality_score = 0.0
    budget.min_prior_score_for_official_validation = 0.0
    budget.min_prior_score_for_official_simulation = 999.0
    budget.stop_official_calls_on_rate_limit = True
    budget.run_forever = False
    budget.cycle_pause_seconds = 0.1
    budget.official_retry_pause_seconds = 1.0
    budget.adaptive_strategy_enabled = False
    budget.require_cloud_sync = False
    budget.cloud_sync_range = "none"
    budget.max_cycles = 2
    budget.dataset_strategy = "fixed"
    budget.generation_mode_ratio = "100/0/0"
    budget.use_assistant_guidance = False
    # Extra timeout enforcement fields
    budget.max_cycle_runtime_seconds = 30
    budget.max_pipeline_runtime_seconds = 60
    budget.phase4_timeout_seconds = 60

    # Lower thresholds so everything passes local prefilter
    config.ops.thresholds.min_sharpe = -999.0
    config.ops.thresholds.min_fitness = -999.0

    # Unreachable API
    config.ops.official_api = "http://127.0.0.1:1"

    # Credentials  
    config.credentials.username = "smoke_test"
    config.credentials.token = "fake_token_for_smoke"

    config.auto_submit = False
    return config


# ── Fake API ──

class FakeBrainAPI:
    def authenticate(self): pass
    def get_user_profile(self): return {"tier": "smoke", "level": 0, "points": 0}
    def get_fields(self, **kw): return []
    def get_operators(self, **kw): return []
    def get_datasets(self, **kw): return []
    def get_alphas(self, **kw): return []
    def get_directory(self, **kw): return []
    def simulate_alpha(self, alpha_id, **kw): return {"status": "simulated", "alpha_id": alpha_id}
    def validate_expression(self, expression, **kw): return {"valid": True, "expression": expression}
    def set_market_scope(self, settings): pass
    def __getattr__(self, name):
        def _noop(*a, **kw): return {}
        return _noop


# ── Fake generator ──

def _fake_generate(count: int, dataset_id: str = "") -> list[Candidate]:
    candidates = []
    for i in range(min(count, 3)):
        candidates.append(Candidate(
            alpha_id=new_id("smoke"),
            expression="rank(ts_delta(close, 20))",
            family="momentum",
            hypothesis="Smoke test alpha",
            data_fields=["close"],
            operators=["ts_delta", "rank"],
            dataset_id=dataset_id or "smoke",
            template_source="smoke_test",
        ))
    return candidates


# ── Tests ──

def test_pipeline_completes_or_timeouts(monkeypatch, tmp_path):
    """Pipeline must complete or timeout cleanly within 75s — never hang."""
    import brain_alpha_ops.ux.guided_pipeline as gp_module

    config = _make_smoke_config(str(tmp_path))
    pipeline = GuidedPipeline(config)

    monkeypatch.setattr(
        gp_module,
        "run_pipeline_from_config",
        lambda *a, **kw: _run_pipeline_minimal(config),
    )

    start = time.time()
    result = None
    error_reason = None

    try:
        result = pipeline._phase_core_pipeline(
            PipelineResult(run_id="smoke_run", candidates=[], events=[], summary={})
        )
    except Exception as e:
        error_reason = str(e)

    elapsed = time.time() - start

    assert elapsed < 75, (
        f"Smoke test took {elapsed:.1f}s — exceeds 75s hard limit. HANGING."
    )

    if result is not None:
        summary = result.summary
        logger.info("Smoke pipeline completed in %.1fs: %s", elapsed, summary)
        assert isinstance(summary, dict)
    else:
        logger.warning("Smoke pipeline timed out after %.1fs: %s", elapsed, error_reason)
        assert error_reason is not None

    logger.info("Smoke test PASSED: pipeline exit within %.1fs", elapsed)


def _run_pipeline_minimal(config: RunConfig) -> PipelineResult:
    """Minimal pipeline that bypasses heavy computation."""
    from brain_alpha_ops.research.pipeline import AlphaResearchPipeline
    from brain_alpha_ops.research.generator import CandidateGenerator

    fake_api = FakeBrainAPI()

    orig_generate = CandidateGenerator.generate
    def _fast_generate(self, count, dataset_id=""):
        return _fake_generate(count, dataset_id)
    CandidateGenerator.generate = _fast_generate

    try:
        pipeline = AlphaResearchPipeline(
            config=config.ops,
            api=fake_api,
            progress_callback=None,
            stop_callback=None,
        )
        pipeline._sync_cloud_alphas = lambda: (
            setattr(pipeline, 'cloud_alphas', []) or
            setattr(pipeline, '_refresh_cloud_similarity_index', lambda: None)
        )
        pipeline._refresh_cloud_similarity_index = lambda: None

        result = pipeline.run(auto_submit=False)
        return result
    finally:
        CandidateGenerator.generate = orig_generate


def test_pipeline_timeout_returns_error(monkeypatch, tmp_path):
    """Verify _phase_core_pipeline raises timeout error instead of hanging."""
    import brain_alpha_ops.ux.guided_pipeline as gp_module

    config = _make_smoke_config(str(tmp_path))
    config.ops.budget.phase4_timeout_seconds = 2
    config.ops.budget.max_pipeline_runtime_seconds = 2

    pipeline = GuidedPipeline(config)

    def _hang_forever(*args, **kwargs):
        time.sleep(300)
        return PipelineResult(run_id="hang", candidates=[], events=[], summary={})

    monkeypatch.setattr(gp_module, "run_pipeline_from_config", _hang_forever)

    start = time.time()
    try:
        pipeline._phase_core_pipeline(
            PipelineResult(run_id="timeout_test", candidates=[], events=[], summary={})
        )
        pytest.fail("Should have raised timeout error")
    except Exception as e:
        elapsed = time.time() - start
        error_msg = str(e)
        logger.info("Timeout test: %s after %.1fs", type(e).__name__, elapsed)
        assert elapsed < 15, f"Timeout took too long: {elapsed:.1f}s"
        assert "timeout" in error_msg.lower(), f"Expected timeout msg, got: {error_msg}"
