"""Response processing tests extracted from ``tests/test_official_adapter.py``.

Covers: normalize_metrics, normal_field, response parsing, build_simulation_payload.
Full suite in ``test_official_adapter.py``.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from brain_alpha_ops.brain_api.official_helpers import normal_field, build_official_url
from brain_alpha_ops.brain_api.official import build_simulation_payload, normalize_metrics
from brain_alpha_ops.config import BrainSettings


def test_build_simulation_payload_contains_settings_and_expression():
    """Simulation payload must embed settings and expression."""
    payload = build_simulation_payload("rank(close)", BrainSettings())
    assert "regular" in payload
    assert payload["regular"] == "rank(close)"
    assert "settings" in payload
    assert "instrumentType" in payload["settings"]


def test_normalize_metrics_extracts_checks():
    """Metrics normalizer must extract BRAIN check results."""
    result = normalize_metrics({
        "is": {"sharpe": 2.0, "fitness": 1.5, "turnover": 0.3},
        "checks": [
            {"name": "SELF_CORRELATION", "result": "PASS", "value": 0.5},
        ],
    })
    assert "sharpe" in result
    assert result["sharpe"] == 2.0
    assert "self_correlation" in result


def test_normalize_metrics_keeps_prod_correlation_separate_from_generic_correlation():
    """prodCorrelation must not be folded into generic correlation field."""
    result = normalize_metrics({
        "is": {
            "sharpe": 1.8,
            "correlation": 0.3,
            "prodCorrelation": 0.45,
        },
    })
    assert result.get("correlation") is not None
    assert result.get("prod_correlation") is not None


def test_normal_field_preserves_wqb_filter_metadata():
    """Field normalizer must preserve WQB filter metadata."""
    item = {
        "id": "close",
        "name": "close",
        "dataset": {"id": "price", "name": "Price"},
        "type": "DOUBLE",
    }
    result = normal_field(item)
    assert result["id"] == "close"
    assert result["dataset_id"] == "price"


def test_normalize_metrics_preserves_self_correlation_check_status():
    """Self-correlation check status must be preserved."""
    result = normalize_metrics({
        "is": {"sharpe": 1.5},
        "checks": [
            {"name": "SELF_CORRELATION", "result": "PASS", "value": 0.4},
        ],
    })
    assert result.get("self_correlation_status") is not None
