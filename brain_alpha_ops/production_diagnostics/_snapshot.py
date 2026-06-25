"""Diagnostic snapshot orchestrator.

``build_diagnostic_snapshot`` is the entry point that the web console, CLI
scripts, and tests call.  It composes the probe outputs into a single
structured dict that can be rendered or consumed programmatically.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from brain_alpha_ops.compliance.redline_verifier import RedLineVerifier
from brain_alpha_ops.config import load_run_config
from brain_alpha_ops.data.loader import OfficialDataLoader
from brain_alpha_ops.data.official_context_validation import validate_official_context
from brain_alpha_ops.parameter_audit import build_parameter_audit_snapshot

from ._analysis import (
    _completed_items,
    _contract_comparison,
    _gap_matrix,
    _priority_items,
    _unfinished_items,
    _upgrade_plan,
)
from ._probes import (
    _frontend_inline_status,
    _history_replay_status,
    _official_context_counts,
    _official_refresh_status,
    _scoring_probe,
)


def build_diagnostic_snapshot(config_path: str | Path | None = None) -> dict[str, Any]:
    """Build a structured diagnosis that can be rendered or consumed by tests."""
    run_config = load_run_config(config_path)
    redline_report = RedLineVerifier(run_config).verify_all()
    loader = OfficialDataLoader.instance()
    scoring_probe = _scoring_probe(run_config)
    inline_status = _frontend_inline_status()
    history_replay = _history_replay_status(run_config)
    official_refresh = _official_refresh_status(run_config)
    official_validation = validate_official_context(config_path=config_path)
    parameter_audit = build_parameter_audit_snapshot(run_config, source="production_diagnostics")
    context_counts = _official_context_counts(loader, official_refresh)
    contract = _contract_comparison(
        run_config,
        redline_report,
        context_counts,
        scoring_probe,
        inline_status,
        history_replay,
        official_refresh,
        official_validation,
        parameter_audit,
    )
    gap_matrix = _gap_matrix(
        run_config,
        redline_report,
        context_counts,
        scoring_probe,
        inline_status,
        history_replay,
        official_refresh,
        official_validation,
        parameter_audit,
    )
    priorities = _priority_items(
        redline_report,
        context_counts,
        scoring_probe,
        inline_status,
        history_replay,
        official_refresh,
        official_validation,
        parameter_audit,
    )

    return {
        "ok": bool(
            redline_report.ok
            and scoring_probe["zero_deviation"]
            and inline_status["ok"]
            and official_validation.get("blocking_ok")
        ),
        "schema_version": "production_diagnosis.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "environment": run_config.environment,
        "storage_dir": run_config.ops.storage_dir,
        "redline": redline_report.to_dict(),
        "official_context": context_counts,
        "official_refresh": official_refresh,
        "official_context_validation": official_validation,
        "parameter_audit": parameter_audit,
        "contract_comparison": contract,
        "scoring_probe": scoring_probe,
        "frontend_inline": inline_status,
        "history_replay": history_replay,
        "gap_matrix": [asdict(row) for row in gap_matrix],
        "priority_items": [asdict(item) for item in priorities],
        "completed_items": _completed_items(history_replay),
        "unfinished_items": _unfinished_items(priorities, official_refresh),
        "upgrade_plan": _upgrade_plan(),
    }
