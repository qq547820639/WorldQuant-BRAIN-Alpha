from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.web_sync_payload import sync_cloud_alphas_payload


class Api:
    def __init__(self, fail_context=False):
        self.fail_context = fail_context

    def authenticate(self):
        return {"ok": True}

    def list_user_alphas(self, sync_range):
        return [{"id": "a1"}, {"id": "a2"}]

    def list_fields(self, *_args):
        if self.fail_context:
            raise RuntimeError("context failed")
        return [{"id": "close", "dataset": {"id": "fundamental"}}]

    def list_operators(self, *_args):
        return [{"name": "rank"}]


class Repo:
    def __init__(self, storage_dir):
        self.storage_dir = storage_dir

    def merge_cloud_alphas(self, rows, sync_range):
        return {"added": len(rows), "updated": 1, "skipped": 0, "failed": 0}


def test_sync_cloud_alphas_payload_merges_and_persists_context(tmp_path):
    run_config = RunConfig(environment="mock")
    run_config.ops.storage_dir = str(tmp_path)
    persisted = []

    payload = sync_cloud_alphas_payload(
        {"syncRange": "7d"},
        run_config_from_payload=lambda body: run_config,
        api_from_run_config=lambda config: Api(),
        repository_factory=Repo,
        datasets_from_fields=lambda fields: [{"id": "fundamental", "field_count": len(fields)}],
        persist_official_context=lambda fields, operators, datasets: persisted.append((fields, operators, datasets)),
        default_fields=[],
        default_operators=[],
    )

    assert payload["ok"] is True
    assert payload["range"] == "7d"
    assert payload["count"] == 2
    assert payload["fields_count"] == 1
    assert payload["operators_count"] == 1
    assert persisted


def test_sync_cloud_alphas_payload_uses_context_fallback(tmp_path):
    run_config = RunConfig(environment="mock")
    run_config.ops.storage_dir = str(tmp_path)

    payload = sync_cloud_alphas_payload(
        {},
        run_config_from_payload=lambda body: run_config,
        api_from_run_config=lambda config: Api(fail_context=True),
        repository_factory=Repo,
        datasets_from_fields=lambda fields: [],
        persist_official_context=lambda fields, operators, datasets: None,
        default_fields=[{"id": "fallback"}],
        default_operators=[{"name": "fallback_op"}],
    )

    assert payload["fields_count"] == 1
    assert payload["operators_count"] == 1
    assert payload["datasets_count"] == 0
