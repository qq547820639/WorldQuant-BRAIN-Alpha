"""Tests for user profile integration (P1-8)."""

import pytest
from brain_alpha_ops.brain_api.mock import MockBrainAPI
from brain_alpha_ops.config import OfficialAPIConfig


class TestUserProfile:
    def test_mock_api_returns_consultant_profile(self):
        api = MockBrainAPI()
        api.authenticate()
        profile = api.get_user_profile()
        assert profile["tier"] == "Consultant"
        assert profile["level"] == 3
        assert profile["points"] == 1250.0
        assert "mock_consultant" in profile["username"]

    def test_mock_profile_has_all_required_fields(self):
        api = MockBrainAPI()
        api.authenticate()
        profile = api.get_user_profile()
        for field in ("tier", "level", "points", "username", "raw"):
            assert field in profile, f"Missing field: {field}"

    def test_user_profile_path_in_config(self):
        config = OfficialAPIConfig()
        assert config.user_profile_path == "/users/self"


class TestBrainAPIProtocol:
    def test_mock_has_get_user_profile(self):
        api = MockBrainAPI()
        assert hasattr(api, "get_user_profile")
        assert callable(api.get_user_profile)
