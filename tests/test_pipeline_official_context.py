from __future__ import annotations

from brain_alpha_ops.brain_api.base import BrainAPIError
from brain_alpha_ops.config import OpsConfig
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.generator import CandidateGenerator
from brain_alpha_ops.research.pipeline_official_context import (
    OfficialContextLoadService,
    active_dataset_field_names,
    configured_official_context_files_exist,
    official_context_reasons,
    refresh_context_validation_cache,
)


class _API:
    def __init__(self, *, fail_rate_limit: bool = False):
        self.fail_rate_limit = fail_rate_limit

    def list_fields(self, *_args, **_kwargs):
        if self.fail_rate_limit:
            raise BrainAPIError("rate limited", status_code=429)
        return [{"id": "close", "name": "close", "dataset": "pv1"}]

    def list_operators(self, *_args, **_kwargs):
        return [{"name": "rank"}]


class _Mapper:
    def __init__(self):
        self.calls = 0

    def fields_for(self, dataset_id):
        self.calls += 1
        return ["close"] if dataset_id == "pv1" else []


def _service(tmp_path, api=None):
    events = []
    progress = []
    halts = []
    config = OpsConfig(storage_dir=str(tmp_path))
    return (
        OfficialContextLoadService(
            config=config,
            api=api or _API(),
            generator=CandidateGenerator(),
            local_data_dir_existed_at_start=False,
            progress=lambda *args, **kwargs: progress.append((args, kwargs)),
            event=lambda *args, **kwargs: events.append((args, kwargs)),
            halt_official_calls=halts.append,
        ),
        events,
        progress,
        halts,
    )


def test_configured_official_context_files_exist_checks_expected_names(tmp_path):
    assert configured_official_context_files_exist(tmp_path) is False
    (tmp_path / "official_fields.json").write_text("[]", encoding="utf-8")

    assert configured_official_context_files_exist(tmp_path) is True


def test_context_validation_reasons_cover_fields_operators_and_dataset():
    state = refresh_context_validation_cache(
        [{"id": "close", "name": "close"}],
        [{"name": "rank"}],
    )
    mapper = _Mapper()
    candidate = Candidate(
        alpha_id="a1",
        expression="rank(volume)",
        family="test",
        hypothesis="context validation",
        data_fields=["volume"],
        operators=["ts_mean"],
    )

    reasons = official_context_reasons(
        candidate,
        available_fields=state.field_names,
        available_operators=state.operator_names,
        active_dataset_id="pv1",
        mapper=mapper,
        dataset_field_names_cache=state.dataset_field_names_cache,
    )

    assert any("fields unavailable" in reason for reason in reasons)
    assert any("operators unavailable" in reason for reason in reasons)
    assert any("not in active dataset 'pv1'" in reason for reason in reasons)
    assert active_dataset_field_names("pv1", mapper, state.dataset_field_names_cache) == {"close"}
    assert mapper.calls == 1


def test_official_context_service_falls_back_to_api_when_json_unavailable(tmp_path, monkeypatch):
    service, events, progress, halts = _service(tmp_path)

    class EmptyLoader:
        def refresh(self, *_args, **_kwargs):
            return {"status": "refresh_failed"}

        def get_fields(self):
            return []

        def get_operators(self):
            return []

    monkeypatch.setattr(
        "brain_alpha_ops.data.OfficialDataLoader.instance",
        lambda: EmptyLoader(),
    )

    result = service.load()

    assert result.context_summary["source"] == "official_api_or_cache"
    field_names = [str(row.get("id") or row.get("name") or "") for row in result.fields]
    operator_names = [str(row.get("name") or "") for row in result.operators]
    assert field_names[0] == "close"
    assert operator_names[0] == "rank"
    assert progress
    assert halts == []
    assert any(args[0] == "context_loaded" for args, _kwargs in events)


def test_official_context_service_uses_local_official_cache_shape_on_rate_limit(tmp_path, monkeypatch):
    service, _events, progress, halts = _service(tmp_path, api=_API(fail_rate_limit=True))

    class EmptyLoader:
        def refresh(self, *_args, **_kwargs):
            return {"status": "refresh_failed"}

        def get_fields(self):
            return []

        def get_operators(self):
            return []

    monkeypatch.setattr(
        "brain_alpha_ops.data.OfficialDataLoader.instance",
        lambda: EmptyLoader(),
    )

    result = service.load()

    assert result.context_summary["source"] == "official_api_or_cache"
    assert result.context_summary["fields_count"] == len(result.fields)
    assert result.context_summary["operators_count"] == len(result.operators)
    assert "Official context API is rate-limited" in result.context_summary["warning"]
    assert "locally cached official field context" in result.context_summary["warning"]
    assert halts
    assert any(args[0] == "official_deferred" for args, _kwargs in progress)
