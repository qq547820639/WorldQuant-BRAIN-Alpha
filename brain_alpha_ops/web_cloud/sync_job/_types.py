"""Types, protocols, and call signatures for cloud sync jobs."""
from __future__ import annotations

from typing import Any, Callable, Protocol

from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.research.repository import ResearchRepository


class JobStoreLike(Protocol):
    def update(self, job_id: str, **kwargs: Any) -> None:
        ...

    def is_cancelled(self, job_id: str) -> bool:
        ...


class SyncJobCancelled(RuntimeError):
    """Raised internally when a user asks to stop a cloud sync job."""


RunConfigFromPayload = Callable[[dict[str, Any]], RunConfig]
ApiFromRunConfig = Callable[[RunConfig], Any]
RepositoryFactory = Callable[[str], ResearchRepository]
DatasetsFromFields = Callable[[list[dict[str, Any]]], list[dict[str, Any]]]
PersistOfficialContext = Callable[[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]], None]
SafeErrorMessage = Callable[[Exception], str]
ErrorPayload = Callable[..., dict[str, Any]]
