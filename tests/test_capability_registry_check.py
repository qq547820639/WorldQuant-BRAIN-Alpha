from __future__ import annotations

from scripts.check_capability_registry import check_capability_registry


def test_capability_registry_check_runs_offline_and_reports_alignment():
    result = check_capability_registry()

    assert result["ok"] is True
    assert result["schema_version"] == "brain_capability_registry_check.v1"
    assert result["official_api_called"] is False
    assert result["summary"]["parameter_count"] >= 12
    assert result["summary"]["settings_count"] >= 9
    assert isinstance(result["findings"], list)
