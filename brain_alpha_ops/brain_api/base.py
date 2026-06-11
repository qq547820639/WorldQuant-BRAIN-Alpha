"""Shared API helpers."""

from __future__ import annotations

from typing import Protocol


class BrainAPI(Protocol):
    def authenticate(self) -> dict:
        ...

    def get_user_profile(self) -> dict:
        ...

    def list_fields(self, query: str = "all", region: str = "", dataset: str = "", progress_callback=None) -> list[dict]:
        ...

    def list_datasets(self, query: str = "all", region: str = "", progress_callback=None) -> list[dict]:
        ...

    def list_operators(self, query: str = "all", progress_callback=None) -> list[dict]:
        ...

    def list_data_categories(self, progress_callback=None) -> list[dict]:
        ...

    def search_datasets_limited(
        self,
        query: str = "all",
        region: str = "",
        *,
        limit: int = 50,
        offset: int = 0,
        **filters,
    ) -> dict:
        ...

    def search_datasets(
        self,
        query: str = "all",
        region: str = "",
        *,
        limit: int = 50,
        offset: int = 0,
        progress_callback=None,
        **filters,
    ) -> list[dict]:
        ...

    def search_fields_limited(
        self,
        query: str = "all",
        region: str = "",
        dataset: str = "",
        *,
        limit: int = 50,
        offset: int = 0,
        **filters,
    ) -> dict:
        ...

    def search_fields(
        self,
        query: str = "all",
        region: str = "",
        dataset: str = "",
        *,
        limit: int = 50,
        offset: int = 0,
        progress_callback=None,
        **filters,
    ) -> list[dict]:
        ...

    def locate_dataset(self, dataset_id: str) -> dict:
        ...

    def locate_field(self, field_id: str) -> dict:
        ...

    def locate_alpha(self, alpha_id: str) -> dict:
        ...

    def filter_alphas_limited(self, **filters) -> dict:
        ...

    def filter_alphas(self, progress_callback=None, **filters) -> list[dict]:
        ...

    def list_user_alphas(
        self,
        sync_range: str = "all",
        progress_callback=None,
        *,
        force_refresh: bool = False,
    ) -> list[dict]:
        ...

    def validate_expression(self, expression: str, settings: dict) -> dict:
        ...

    def submit_simulation(self, expression: str, settings: dict) -> str:
        ...

    def poll_simulation(self, simulation_id: str) -> str:
        ...

    def fetch_result(self, simulation_id: str) -> dict:
        ...

    def concurrent_simulate(self, alphas, concurrency: int = 3, *, return_exceptions: bool = False) -> list:
        ...

    def concurrent_check(self, alpha_ids, concurrency: int = 3, *, return_exceptions: bool = False) -> list:
        ...

    def check_alpha(self, alpha_id: str) -> dict:
        ...

    def submit_alpha(self, alpha_id: str, expression: str, settings: dict, *, bodyless: bool = True) -> dict:
        ...


class BrainAPIError(RuntimeError):
    """Raised for API errors that should be surfaced to the pipeline."""

    def __init__(self, message: str, *, status_code: int | None = None, payload=None, retry_after: float | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload
        self.retry_after = retry_after
