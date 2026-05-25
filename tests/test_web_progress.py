from __future__ import annotations

from brain_alpha_ops.web_progress import enrich_progress


def test_enrich_progress_adds_known_phase_label_without_overwriting_existing_label():
    progress = enrich_progress({"phase": "cloud_sync", "percent": 25})

    assert progress["phase_label"] == "云端数据同步"

    explicit = enrich_progress({"phase": "cloud_sync", "phase_label": "custom"})
    assert explicit["phase_label"] == "custom"


def test_enrich_progress_falls_back_to_unknown_phase_value():
    assert enrich_progress({"phase": "custom_phase"})["phase_label"] == "custom_phase"
    assert enrich_progress({"message": "no phase"}) == {"message": "no phase"}
