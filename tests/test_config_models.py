"""Tests for brain_alpha_ops.config_models — core configuration dataclasses."""
import pytest
from brain_alpha_ops.config_models import (
    BrainSettings,
    QualityThresholds,
    ScoringConfig,
    CredentialConfig,
    WebConfig,
    ResearchBudget,
)


class TestBrainSettings:
    def test_defaults_match_brain_platform(self):
        s = BrainSettings()
        assert s.instrumentType == "EQUITY"
        assert s.region == "USA"
        assert s.delay == 1
        assert s.decay == 10

    def test_to_platform_dict_excludes_type_and_dataset(self):
        s = BrainSettings()
        d = s.to_platform_dict()
        # The "type" key is popped from data and re-inserted at the top level
        assert "type" in d
        assert d["type"] == "REGULAR"
        # "settings" sub-dict should NOT contain "type" or "dataset"
        assert "type" not in d["settings"]
        assert "dataset" not in d["settings"]
        assert "instrumentType" in d["settings"]

    def test_custom_region_changes(self):
        s = BrainSettings(region="EUR")
        assert s.region == "EUR"


class TestQualityThresholds:
    def test_defaults_match_brain_platform(self):
        q = QualityThresholds()
        assert q.min_sharpe == 1.25
        assert q.min_fitness == 1.0
        assert q.min_turnover == 0.01
        assert q.max_self_correlation == 0.70
        assert q.max_weight_concentration == 0.10

    def test_regime_adjustments_present_for_all_regimes(self):
        """Verify that regime_adjustments contains entries for all expected regimes."""
        q = QualityThresholds()
        assert "normal" in q.regime_adjustments
        assert "low_vol" in q.regime_adjustments
        assert "high_vol" in q.regime_adjustments

    def test_normal_regime_has_identity_factors(self):
        q = QualityThresholds()
        normal = q.regime_adjustments["normal"]
        assert normal["sharpe_factor"] == 1.0
        assert normal["fitness_factor"] == 1.0

    def test_max_turnover_property_aliases_platform_max_turnover(self):
        q = QualityThresholds()
        assert q.max_turnover == q.platform_max_turnover


class TestScoringConfig:
    def test_frozen_prevents_direct_mutation(self):
        s = ScoringConfig()
        with pytest.raises(Exception):
            s.prior_layer_weight = 0.99

    def test_weights_sum_approximately_one(self):
        s = ScoringConfig()
        total = s.prior_layer_weight + s.empirical_layer_weight + s.checklist_layer_weight
        assert abs(total - 1.0) < 0.01

    def test_decision_bands_monotonic(self):
        s = ScoringConfig()
        thresholds = s.decision_thresholds
        assert thresholds["submit"] > thresholds["optimize"] > thresholds["research"]

    def test_get_layer_weights_returns_all_three_layers(self):
        s = ScoringConfig()
        w = s.get_layer_weights()
        assert set(w.keys()) == {"prior", "empirical", "checklist"}
        assert abs(sum(w.values()) - 1.0) < 0.01

    def test_get_local_weights_returns_prior_and_quality(self):
        s = ScoringConfig()
        w = s.get_local_weights()
        assert set(w.keys()) == {"prior", "quality"}
        assert abs(sum(w.values()) - 1.0) < 0.01


class TestCredentialConfig:
    def test_to_safe_dict_excludes_credential_values(self):
        c = CredentialConfig(username_env="TEST_USER", password_env="TEST_PASS")
        d = c.to_safe_dict()
        assert d["username_env"] == "TEST_USER"
        assert d["password_env"] == "TEST_PASS"
        # Safe dict must only contain env-var names, never actual credentials
        assert "username" not in d
        assert "password" not in d
        assert "token" not in d

    def test_empty_credentials_resolve_returns_dict(self):
        c = CredentialConfig()
        result = c.resolve()
        assert isinstance(result, dict)
        assert "username" in result
        assert "password" in result
        assert "token" in result

    def test_resolve_reads_from_env(self, monkeypatch):
        monkeypatch.setenv("BRAIN_USERNAME", "env_user")
        monkeypatch.setenv("BRAIN_PASSWORD", "env_pass")
        c = CredentialConfig()
        result = c.resolve()
        assert result["username"] == "env_user"
        assert result["password"] == "env_pass"

    def test_explicit_credential_overrides_env(self, monkeypatch):
        monkeypatch.setenv("BRAIN_USERNAME", "env_user")
        c = CredentialConfig(username="explicit_user")
        result = c.resolve()
        assert result["username"] == "explicit_user"


class TestWebConfig:
    def test_default_local_only(self):
        w = WebConfig()
        assert w.host == "127.0.0.1"
        assert w.allow_remote is False

    def test_default_port(self):
        w = WebConfig()
        assert w.port == 8765


class TestResearchBudget:
    def test_defaults_reasonable(self):
        b = ResearchBudget()
        assert b.max_candidates_per_cycle > 0
        assert b.min_local_quality_score > 0
        assert b.adaptive_min_cycles > 0

    def test_run_forever_defaults_false(self):
        b = ResearchBudget()
        assert b.run_forever is False

    def test_max_cycles_default(self):
        b = ResearchBudget()
        assert b.max_cycles == 10
