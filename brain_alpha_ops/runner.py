"""Shared runtime helpers for CLI, editor scripts, and the web console."""

from __future__ import annotations

from brain_alpha_ops.brain_api import MockBrainAPI, OfficialBrainAPI
from brain_alpha_ops.config import RunConfig, validate_run_config
from brain_alpha_ops.research.pipeline import AlphaResearchPipeline


def api_from_run_config(run_config: RunConfig):
    validate_run_config(run_config)
    environment = run_config.environment.lower()
    if environment == "mock":
        return MockBrainAPI()
    if environment == "production":
        credentials = run_config.credentials.resolve()
        api = OfficialBrainAPI(run_config.ops.official_api, **credentials)
        api.set_market_scope(run_config.ops.settings)
        return api
    raise ValueError(f"unknown environment: {run_config.environment}")


def run_pipeline_from_config(run_config: RunConfig, progress_callback=None, stop_callback=None):
    validate_run_config(run_config)
    api = api_from_run_config(run_config)
    return AlphaResearchPipeline(
        config=run_config.ops,
        api=api,
        progress_callback=progress_callback,
        stop_callback=stop_callback,
    ).run(
        auto_submit=run_config.auto_submit
    )
