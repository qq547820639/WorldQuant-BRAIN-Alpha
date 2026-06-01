from __future__ import annotations

from scripts.check_web_handler_dispatch_context import check_web_handler_dispatch_context


def test_web_handler_dispatch_context_contract_is_grouped_and_compatible():
    result = check_web_handler_dispatch_context()

    assert result["ok"] is True
    assert result["schema_version"] == "web_handler_dispatch_context_check.v1"
    assert result["top_level_field_count"] == 7
    assert result["top_level_field_names"] == [
        "core",
        "session",
        "job",
        "config",
        "research",
        "assistant",
        "actions",
    ]
    assert max(result["group_field_counts"].values()) <= 14
    assert result["flat_constructor_ok"] is True
    assert result["grouped_constructor_ok"] is True
    assert result["legacy_access_ok"] is True
    assert result["dataclasses_replace_ok"] is True
    assert result["duplicate_field_names"] == []
    assert result["findings"] == []
