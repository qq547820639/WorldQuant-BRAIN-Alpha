"""Shared runtime helpers for CLI, editor scripts, and the web console."""

from __future__ import annotations

import contextlib

from brain_alpha_ops.brain_api import OfficialBrainAPI
from brain_alpha_ops.config import RunConfig, validate_run_config
from brain_alpha_ops.execution_factory import create_execution_backend
from brain_alpha_ops.research.pipeline import AlphaResearchPipeline


def api_from_run_config(run_config: RunConfig, *, allow_plaintext_credentials: bool = False):
    validate_run_config(run_config, allow_plaintext_credentials=allow_plaintext_credentials)
    credentials = run_config.credentials.resolve()
    api = OfficialBrainAPI(run_config.ops.official_api, **credentials)
    api.set_market_scope(run_config.ops.settings)
    return api


def run_pipeline_from_config(run_config: RunConfig, progress_callback=None, stop_callback=None):
    # F-031: inject the execution backend selected by run_config.execution_mode
    # so the browser submit flow is actually reachable. Previously the runner
    # always built a bare OfficialBrainAPI and passed it as ``api=``, which
    # bypassed execution_factory entirely and left the browser path dead.
    validate_run_config(run_config)
    backend = create_execution_backend(
        mode=run_config.execution_mode,
        run_config=run_config,
    )
    with contextlib.ExitStack() as stack:
        # BrowserExecutionAdapter must be used as a context manager to
        # initialize its BrainBrowserRunner; ApiExecutionAdapter has no
        # __enter__ and is used inline.
        if hasattr(backend, "__enter__"):
            stack.enter_context(backend)
        return AlphaResearchPipeline(
            config=run_config.ops,
            execution_backend=backend,
            progress_callback=progress_callback,
            stop_callback=stop_callback,
        ).run(
            auto_submit=run_config.auto_submit
        )
