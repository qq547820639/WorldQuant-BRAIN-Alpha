from brain_alpha_ops.web_cloud_context_refresh import refresh_cloud_context_for_check_service


class Store:
    def __init__(self):
        self.updates = []

    def update(self, job_id, **kwargs):
        self.updates.append({"job_id": job_id, **kwargs})


class Repo:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.merged = []

    def latest_cloud_alphas(self):
        return list(self.rows)

    def merge_cloud_alphas(self, rows, sync_range):
        self.merged.append((list(rows), sync_range))
        return {"added": len(rows), "updated": 0, "skipped": 0, "failed": 0}


class Api:
    def __init__(self, fail_fields=False):
        self.fail_fields = fail_fields

    def list_user_alphas(self, sync_range, progress_callback=None):
        if progress_callback:
            progress_callback({"scanned": 1, "total": 1})
        return [{"id": "remote_1"}]

    def list_fields(self, *_args):
        if self.fail_fields:
            raise RuntimeError("fields failed")
        return [{"id": "close", "dataset": {"id": "fundamental"}}]

    def list_operators(self, *_args):
        return [{"name": "rank"}]


def test_refresh_cloud_context_uses_local_cache():
    store = Store()
    repo = Repo([{"id": "cached_1"}])

    rows, error = refresh_cloud_context_for_check_service(
        Api(),
        repo,
        "3d",
        "job_1",
        2,
        "quick",
        store=store,
        official_context_file_counts=lambda: {"fields_count": 1},
        datasets_from_fields=lambda fields: [],
        persist_official_context=lambda fields, operators, datasets: None,
        safe_error_message=str,
    )

    assert rows == [{"id": "cached_1"}]
    assert error == ""
    assert store.updates[-1]["progress"]["status_code"] == "CHECK_LOCAL_CACHE"


def test_refresh_cloud_context_remote_persists_and_reports_partial_errors():
    store = Store()
    repo = Repo()
    persisted = []

    rows, error = refresh_cloud_context_for_check_service(
        Api(fail_fields=True),
        repo,
        "7d",
        "job_1",
        1,
        "full",
        region="USA",
        refresh_remote=True,
        store=store,
        official_context_file_counts=lambda: {},
        datasets_from_fields=lambda fields: [{"id": "dataset"}],
        persist_official_context=lambda fields, operators, datasets: persisted.append((fields, operators, datasets)),
        safe_error_message=str,
    )

    assert rows == [{"id": "remote_1"}]
    assert "fields refresh failed" in error
    assert repo.merged[0][1] == "7d"
    assert persisted[0][0] == []
    assert persisted[0][1] == [{"name": "rank"}]
