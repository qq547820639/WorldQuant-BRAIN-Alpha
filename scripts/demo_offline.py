"""Offline demo mode — runs the full pipeline against recorded BRAIN responses.

No real BRAIN connection required.  Starts a local mock API server,
loads fixtures from fixtures/recorded_responses/, executes a single
pipeline cycle with auto_submit=false, and prints a results summary.

Usage::

    python scripts/demo_offline.py
    python scripts/demo_offline.py --config fixtures/demo_config.json
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, PROJECT_ROOT)

from fixtures.mock_brain_api import MockBRAINApiServer
from brain_alpha_ops.config_models import (
    BrainSettings,
    CredentialConfig,
    OpsConfig,
    OfficialAPIConfig,
    QualityThresholds,
    ResearchBudget,
    RunConfig,
    ScoringConfig,
    SubmissionPolicy,
)


DEMO_PORT = 9999
MOCK_FIXTURES_DIR = Path(PROJECT_ROOT) / "fixtures" / "recorded_responses"


def _build_demo_config(config_path: str | None = None) -> RunConfig:
    """Build a RunConfig for offline demo mode."""
    if config_path and Path(config_path).exists():
        raw = json.loads(Path(config_path).read_text(encoding="utf-8"))
        return RunConfig(
            environment=raw.get("environment", "demo"),
            auto_submit=raw.get("auto_submit", False),
            credentials=CredentialConfig(),
            web=raw.get("web", {}),
            ops=OpsConfig(
                storage_dir=raw.get("ops", {}).get("storage_dir", "data/demo"),
                settings=BrainSettings(),
                budget=ResearchBudget(
                    max_candidates_per_cycle=10,
                    max_cycles=1,
                    run_forever=False,
                    random_seed=42,
                ),
                scoring=ScoringConfig(
                    assistant_guidance_score_adjustment_enabled=False,
                ),
                thresholds=QualityThresholds(
                    require_official_pass=False,
                    require_official_metrics=False,
                    require_data_compliance=False,
                    require_economic_logic=False,
                ),
                submission_policy=SubmissionPolicy(
                    max_auto_submissions_per_day=0,
                    max_auto_submissions_per_run=0,
                    require_pre_submit_check_passed=False,
                ),
                official_api=OfficialAPIConfig(
                    base_url=f"http://127.0.0.1:{DEMO_PORT}",
                    timeout_seconds=10,
                    poll_attempts=5,
                    poll_interval_seconds=1.0,
                    min_request_interval_seconds=0.1,
                    rate_limit_retry_attempts=1,
                    rate_limit_backoff_seconds=5.0,
                    cache_dir="data/demo/api_cache",
                    allow_stale_context_on_rate_limit=True,
                ),
            ),
        )

    return RunConfig(
        environment="demo",
        auto_submit=False,
        demo_mode=True,
        credentials=CredentialConfig(),
        ops=OpsConfig(
            storage_dir="data/demo",
            settings=BrainSettings(),
            budget=ResearchBudget(
                max_candidates_per_cycle=10,
                max_cycles=1,
                run_forever=False,
                random_seed=42,
            ),
            scoring=ScoringConfig(
                assistant_guidance_score_adjustment_enabled=False,
            ),
            thresholds=QualityThresholds(
                require_official_pass=False,
                require_official_metrics=False,
                require_data_compliance=False,
                require_economic_logic=False,
            ),
            submission_policy=SubmissionPolicy(
                max_auto_submissions_per_day=0,
                max_auto_submissions_per_run=0,
                require_pre_submit_check_passed=False,
            ),
            official_api=OfficialAPIConfig(
                base_url=f"http://127.0.0.1:{DEMO_PORT}",
                timeout_seconds=10,
                poll_attempts=5,
                poll_interval_seconds=1.0,
                min_request_interval_seconds=0.1,
                rate_limit_retry_attempts=1,
                rate_limit_backoff_seconds=5.0,
                cache_dir="data/demo/api_cache",
                allow_stale_context_on_rate_limit=True,
            ),
        ),
    )


def _print_summary(result, elapsed: float) -> None:
    """Print a concise results summary."""
    print("\n" + "=" * 60)
    print("  Offline Demo — Results Summary")
    print("=" * 60)
    summary = getattr(result, "summary", {}) or {}
    print(f"  Run ID:        {result.run_id}")
    print(f"  Candidates:    {len(result.candidates)}")
    print(f"  Elapsed:       {elapsed:.1f}s")
    if summary:
        for key in ["produced", "passed_local", "submitted", "pool_size"]:
            if key in summary:
                print(f"  {key:14s} {summary[key]}")
    print()
    for i, candidate in enumerate(result.candidates[:5], 1):
        expr = getattr(candidate, "expression", "")[:60]
        score = (getattr(candidate, "scorecard", {}) or {}).get("total_score", "?")
        print(f"  [{i}] score={score}  {expr}")
    if len(result.candidates) > 5:
        print(f"  ... and {len(result.candidates) - 5} more")
    print("\n" + "=" * 60)
    print("  No real BRAIN connections were made.")
    print("=" * 60)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Run BRAIN Alpha Ops in offline demo mode")
    parser.add_argument("--config", default=None, help="Path to demo config JSON")
    args = parser.parse_args()

    print("=" * 60)
    print("  BRAIN Alpha Ops — Offline Demo Mode")
    print("=" * 60)

    config = _build_demo_config(args.config)

    print("\n[1/3] Starting mock BRAIN API server …")
    server = MockBRAINApiServer(
        host="127.0.0.1",
        port=DEMO_PORT,
        fixtures_dir=MOCK_FIXTURES_DIR,
    )
    server.start()
    print(f"  Mock server running at {server.base_url}")

    try:
        print("\n[2/3] Running pipeline (single cycle, auto_submit=false) …")
        from brain_alpha_ops.brain_api.api import BrainAPI

        api = BrainAPI(config.ops.official_api)
        from brain_alpha_ops.research.pipeline import AlphaResearchPipeline

        pipeline = AlphaResearchPipeline(config=config.ops, api=api)

        t0 = time.time()
        result = pipeline.run(auto_submit=False)
        elapsed = time.time() - t0

        print("\n[3/3] Pipeline completed.")
        _print_summary(result, elapsed)
        return 0

    except Exception as exc:
        print(f"\n  ERROR: {exc}")
        import traceback

        traceback.print_exc()
        return 1

    finally:
        server.stop()
        print("\n  Mock server stopped.")


if __name__ == "__main__":
    raise SystemExit(main())
