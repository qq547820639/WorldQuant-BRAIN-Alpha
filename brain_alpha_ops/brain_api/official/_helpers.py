"""Bound component helper classes for the OfficialBrainAPI."""

from __future__ import annotations

from typing import Any


class _BoundOfficialAPIComponent:
    def __init__(self, api: "OfficialBrainAPI"):
        object.__setattr__(self, "_api", api)

    def __getattr__(self, name: str) -> Any:
        try:
            api = object.__getattribute__(self, "_api")
        except AttributeError as exc:
            raise AttributeError(name) from exc
        return getattr(api, name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "_api":
            object.__setattr__(self, name, value)
            return
        setattr(self._api, name, value)


from brain_alpha_ops.brain_api.official_auth import OfficialAuthProfileMixin  # noqa: E402
from brain_alpha_ops.brain_api.official_context import (  # noqa: E402
    OfficialContextDataMixin,
)
from brain_alpha_ops.brain_api.official_request import (  # noqa: E402
    OfficialRequestMixin,
)
from brain_alpha_ops.brain_api.official_simulation import (  # noqa: E402
    OfficialSimulationSubmissionMixin,
)


class _OfficialAuthProfileClient(OfficialAuthProfileMixin, _BoundOfficialAPIComponent):
    pass


class _OfficialContextDataClient(OfficialContextDataMixin, _BoundOfficialAPIComponent):
    pass


class _OfficialRequestClient(OfficialRequestMixin, _BoundOfficialAPIComponent):
    pass


class _OfficialSimulationSubmissionClient(OfficialSimulationSubmissionMixin, _BoundOfficialAPIComponent):
    pass
