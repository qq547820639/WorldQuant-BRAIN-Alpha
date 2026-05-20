"""Shared API helpers."""

from __future__ import annotations

from typing import Protocol


class BrainAPI(Protocol):
    def authenticate(self) -> dict:
        ...

    def get_user_profile(self) -> dict:
        ...

    def list_fields(self, query: str = "all", region: str = "", progress_callback=None) -> list[dict]:
        ...

    def list_datasets(self, query: str = "all", region: str = "", progress_callback=None) -> list[dict]:
        ...

    def list_operators(self, query: str = "all", progress_callback=None) -> list[dict]:
        ...

    def list_user_alphas(self, sync_range: str = "3d", progress_callback=None) -> list[dict]:
        ...

    def validate_expression(self, expression: str, settings: dict) -> dict:
        ...

    def submit_simulation(self, expression: str, settings: dict) -> str:
        ...

    def poll_simulation(self, simulation_id: str) -> str:
        ...

    def fetch_result(self, simulation_id: str) -> dict:
        ...

    def check_alpha(self, alpha_id: str) -> dict:
        ...

    def submit_alpha(self, alpha_id: str, expression: str, settings: dict) -> dict:
        ...


class BrainAPIError(RuntimeError):
    """Raised for API errors that should be surfaced to the pipeline."""

    def __init__(self, message: str, *, status_code: int | None = None, payload=None, retry_after: float | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload
        self.retry_after = retry_after
