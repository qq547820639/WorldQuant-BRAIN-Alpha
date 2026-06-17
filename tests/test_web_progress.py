from __future__ import annotations

from brain_alpha_ops.web_progress import ProgressPayload, enrich_progress


def test_enrich_progress_adds_known_phase_label_without_overwriting_existing_label():
    progress = enrich_progress({"phase": "cloud_sync", "percent": 25})

    assert progress["phase_label"] == "云端数据同步"

    explicit = enrich_progress({"phase": "cloud_sync", "phase_label": "custom"})
    assert explicit["phase_label"] == "custom"


def test_enrich_progress_falls_back_to_unknown_phase_value():
    assert enrich_progress({"phase": "custom_phase"})["phase_label"] == "custom_phase"
    enriched = enrich_progress({"message": "no phase"})
    assert enriched["message"] == "no phase"
    assert enriched["status_message"] == "no phase"
    assert enriched["eta_seconds"] == 0


def test_enrich_progress_adds_unified_progress_fields():
    progress = enrich_progress({"phase": "checking", "checked": 2, "total": 4, "message": "Checking 2/4"})

    assert progress["percent_complete"] == 50.0
    assert progress["percent"] == 50.0
    assert progress["status_message"] == "Checking 2/4"


def test_cloud_scan_progress_uses_filter_window_count_as_reference_without_percent_or_eta():
    progress = enrich_progress({
        "operation": "sync_alphas",
        "phase": "scan",
        "status_code": "SCAN",
        "scanned": 10_000,
        "total": 10_800,
        "api_reported_total": 10_000,
        "percent_complete": 100,
        "percent": 100,
        "eta_seconds": 30,
        "eta_deadline_at_ms": 123_000,
        "message": "Scanning cloud alphas: 10000 / 10800",
        "pages_fetched": 100,
        "expected_pages": 100,
        "page_size": 100,
        "page_limit": 100,
        "next_offset": 10_000,
        "confirming_total_boundary": True,
    })

    assert "percent_complete" not in progress
    assert "percent" not in progress
    assert progress["indeterminate"] is True
    assert progress["open_ended"] is True
    assert progress["eta_seconds"] == 0
    assert "eta_deadline_at_ms" not in progress
    assert progress["status_message"] == (
        "已拉取 10,000 条云端 Alpha；接口分页参考数 10,000 条，不是云端 Alpha 总量，会继续按分页自动确认边界；当前第 100 页；"
        "本页 100 条，分页参数 100 条/页，下一请求确认分页边界，本页已满，继续确认下一页。"
    )
    assert "/ 100 页" not in progress["status_message"]


def test_cloud_scan_progress_explains_transient_retry_date_window_recovery():
    progress = enrich_progress({
        "operation": "sync_alphas",
        "phase": "scan",
        "status_code": "SCAN",
        "scanned": 23_700,
        "total": 23_700,
        "api_reported_total": 10_000,
        "page_size": 0,
        "page_limit": 100,
        "offset": 0,
        "cursor_before": "2026-01-02T00:00:00-04:00",
        "warning": "transient_page_retry_narrowed_by_date",
        "retry_exhausted": True,
        "error_status": 504,
    })

    assert "percent_complete" not in progress
    assert progress["status_message"] == (
        "已拉取 23,700 条云端 Alpha；接口分页参考数 10,000 条，不是云端 Alpha 总量，会继续按分页自动确认边界；"
        "分页参数 100 条/页，网关超时后自动缩小时间范围。"
    )


def test_context_stage_progress_ignores_stale_cloud_total_and_percent_without_stage_total():
    progress = enrich_progress({
        "operation": "sync_alphas",
        "phase": "context",
        "status_code": "CONTEXT_FIELDS",
        "status_message": "Updating official fields cache: 2550 / unknown",
        "scanned": 7294,
        "total": 10000,
        "fields_count": 2550,
        "percent_complete": 72.94,
        "eta_seconds": 49,
        "eta_deadline_at_ms": 123_000,
    })

    assert "percent_complete" not in progress
    assert "percent" not in progress
    assert progress["eta_seconds"] == 0
    assert "eta_deadline_at_ms" not in progress
    assert progress["status_message"] == "Updating official fields cache: 2550 / unknown"


def test_context_stage_progress_uses_stage_specific_counts_when_total_exists():
    progress = enrich_progress({
        "operation": "sync_alphas",
        "phase": "context",
        "status_code": "CONTEXT_FIELDS",
        "fields_count": 2550,
        "fields_total": 8599,
        "scanned": 7294,
        "total": 10000,
        "eta_seconds": 386,
    })

    assert progress["percent_complete"] == 29.7
    assert progress["percent"] == 29.7
    assert progress["eta_seconds"] == 386


def test_progress_payload_documents_unified_fields():
    assert {
        "task_id",
        "job_id",
        "phase",
        "phase_label",
        "percent_complete",
        "status_message",
        "eta_seconds",
    }.issubset(ProgressPayload.__annotations__)
