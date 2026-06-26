"""Authentication and expression-validation mixin for OfficialBrainAPI."""

from __future__ import annotations


class _OfficialAuthMixin:
    """Authentication-related thin wrappers delegating to ``self._auth_profile``."""

    def validate_expression(
        self,
        expression: str,
        settings: dict,
        known_operators: set | None = None,
        known_fields: set | None = None,
    ) -> dict:
        return self._expression_validator.validate_expression(
            expression,
            settings,
            known_operators=known_operators,
            known_fields=known_fields,
        )

    def authenticate(self) -> dict:
        return self._auth_profile.authenticate()

    def get_user_profile(self) -> dict:
        return self._auth_profile.get_user_profile()

    def _basic_auth(self) -> str:
        return self._auth_profile._basic_auth()

    def _has_session_cookie(self) -> bool:
        return self._auth_profile._has_session_cookie()
