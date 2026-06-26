"""Locate and get mixin for alpha query operations."""

from __future__ import annotations

from ..base import BrainAPIError
from ..official_filtering import (
    resolve_compat_alias,
)
from ..official_helpers import (
    normal_alpha as _normal_alpha,
)
from ..official_helpers import (
    normal_dataset as _normal_dataset,
)
from ..official_helpers import (
    normal_field as _normal_field,
)


class _AlphaQueryLocateMixin:

    def _hidden_for_audit_log(self):
        """Stub: returns None. Override in subclass to enable audit logging."""
        return None

    def locate_dataset(self, dataset_id: str) -> dict:
        value = str(dataset_id or "").strip()
        if not value:
            raise BrainAPIError("dataset_id is required")
        path = self.config.data_set_path_template.format(dataset_id=value)
        data, _headers = self._request("GET", path)
        return _normal_dataset(data if isinstance(data, dict) else {})

    def locate_field(self, field_id: str) -> dict:
        value = str(field_id or "").strip()
        if not value:
            raise BrainAPIError("field_id is required")
        path = self.config.data_field_path_template.format(field_id=value)
        data, _headers = self._request("GET", path)
        return _normal_field(data if isinstance(data, dict) else {})

    def locate_alpha(self, alpha_id: str) -> dict:
        value = str(alpha_id or "").strip()
        if not value:
            raise BrainAPIError("alpha_id is required")
        path = self.config.alpha_path_template.format(alpha_id=value)
        data, _headers = self._request("GET", path)
        return _normal_alpha(data if isinstance(data, dict) else {})

    def get_dataset(self, dataset_id: str = "", *, id: str = "") -> dict:
        return self.locate_dataset(resolve_compat_alias("dataset_id", dataset_id, id, alias_name="id"))

    def get_field(self, field_id: str = "", *, id: str = "") -> dict:
        return self.locate_field(resolve_compat_alias("field_id", field_id, id, alias_name="id"))

    def get_alpha(self, alpha_id: str = "", *, id: str = "") -> dict:
        return self.locate_alpha(resolve_compat_alias("alpha_id", alpha_id, id, alias_name="id"))
