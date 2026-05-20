"""P1 optimization verification tests — hard gates, _ratio, field pool."""
from brain_alpha_ops.config import QualityThresholds
from brain_alpha_ops.research.scoring import empirical_score, _ratio, evaluate_quality_gate
from brain_alpha_ops.models import Candidate


def run_all():
    passed = 0
    failed = 0

    # ── Test 1: _ratio with various values ──
    try:
        assert _ratio(0.05) == 0.05, "decimal pass-through"
        assert _ratio(0.0) == 0.0, "zero"
        assert _ratio(70) == 0.70, "percentage normalize"
        assert _ratio(2.5) == 0.025, "small percentage"
        assert _ratio(150) == 150.0, "large raw value (>100)"
        print("  PASS: test_ratio_values")
        passed += 1
    except AssertionError as e:
        print(f"  FAIL: test_ratio_values: {e}")
        failed += 1

    # ── Test 2: hard gate detection on bad metrics ──
    try:
        t = QualityThresholds()
        bad = {
            "sharpe": 0.5, "fitness": 0.3, "turnover": 0.85,
            "returns": -0.01, "drawdown": 0.15, "correlation": 0.75,
            "weight_concentration": 0.25, "sub_universe_sharpe": 0.1,
            "margin": 1.0,
        }
        result = empirical_score(bad, t)
        assert result["hard_gate_failed"] is True
        assert len(result["hard_gate_failures"]) >= 5
        # Verify specific hard gates are present
        gate_names = [f.split()[0] for f in result["hard_gate_failures"]]
        assert "sharpe" in gate_names
        assert "fitness" in gate_names
        print(f"  PASS: test_hard_gate_detection ({len(result['hard_gate_failures'])} failures)")
        passed += 1
    except AssertionError as e:
        print(f"  FAIL: test_hard_gate_detection: {e}")
        failed += 1

    # ── Test 3: good metrics → no hard gate failure ──
    try:
        t = QualityThresholds()
        # sub_universe_sharpe needs: >= 0.75 * sqrt(subSize/alphaSize) * sharpe
        # Default subSize=1000, alphaSize=1000, sharpe=1.5 → threshold 1.125
        good = {
            "sharpe": 1.5, "fitness": 1.2, "turnover": 0.25,
            "returns": 0.05, "drawdown": 0.05, "correlation": 0.1,
            "weight_concentration": 0.05, "sub_universe_sharpe": 1.5,
            "subUniverseSize": 1000, "alphaSize": 1000,
            "margin": 5.0,
        }
        result = empirical_score(good, t)
        assert result["hard_gate_failed"] is False
        assert len(result["hard_gate_failures"]) == 0
        print("  PASS: test_hard_gate_passes_on_good_metrics")
        passed += 1
    except AssertionError as e:
        print(f"  FAIL: test_hard_gate_passes_on_good_metrics: {e}")
        failed += 1

    # ── Test 4: evaluate_quality_gate blocks on hard gate ──
    try:
        t = QualityThresholds()
        bad = {
            "sharpe": 0.5, "fitness": 0.3, "turnover": 0.85,
            "returns": -0.01, "drawdown": 0.15, "correlation": 0.75,
            "weight_concentration": 0.25, "sub_universe_sharpe": 0.1,
            "margin": 1.0,
        }
        emp = empirical_score(bad, t)
        c = Candidate(alpha_id="test_hg", expression="rank(returns)", family="Momentum", hypothesis="Price momentum alpha")
        c.official_metrics = bad
        c.scorecard = {
            "empirical": emp,
            "submission_checklist": {"items": []},
            "total_score": 75,
        }
        gate = evaluate_quality_gate(c, t)
        assert gate["submission_ready"] is False
        assert gate["hard_gate_blocked"] is True
        assert "hard_gate_blocked" in gate["warnings"][0]
        print("  PASS: test_quality_gate_blocks_on_hard_gate")
        passed += 1
    except AssertionError as e:
        print(f"  FAIL: test_quality_gate_blocks_on_hard_gate: {e}")
        failed += 1

    # ── Test 5: non-hard-gate items don't block independently ──
    try:
        t = QualityThresholds()
        soft_bad = {
            "sharpe": 1.5, "fitness": 1.2, "turnover": 0.25,
            "returns": 0.05, "drawdown": 0.99,  # drawdown is soft
            "correlation": 0.1, "weight_concentration": 0.05,
            "sub_universe_sharpe": 1.5, "subUniverseSize": 1000, "alphaSize": 1000,
            "margin": 5.0,
        }
        emp = empirical_score(soft_bad, t)
        c = Candidate(alpha_id="test_soft", expression="rank(returns)", family="Momentum", hypothesis="Price momentum")
        c.official_metrics = soft_bad
        c.scorecard = {
            "empirical": emp,
            "submission_checklist": {"items": []},
            "total_score": 75,
        }
        gate = evaluate_quality_gate(c, t)
        # drawdown is NOT a hard gate, but failed_factors can still flag it
        assert gate["hard_gate_blocked"] is False
        assert not gate["submission_ready"]  # drawdown fails as soft indicator
        print("  PASS: test_soft_indicators_fail_without_hard_gate_block")
        passed += 1
    except AssertionError as e:
        print(f"  FAIL: test_soft_indicators_fail_without_hard_gate_block: {e}")
        failed += 1

    # ── Test 6: _build_official_field_pool max size ──
    try:
        from brain_alpha_ops.research.generator import CandidateGenerator
        gen = CandidateGenerator(max_field_pool_size=50)
        assert gen._max_field_pool_size == 50
        gen2 = CandidateGenerator()  # default
        assert gen2._max_field_pool_size == 50
        gen3 = CandidateGenerator(max_field_pool_size=5)  # floor
        assert gen3._max_field_pool_size == 10  # floor at 10
        print("  PASS: test_field_pool_max_size_default_50")
        passed += 1
    except AssertionError as e:
        print(f"  FAIL: test_field_pool_max_size_default_50: {e}")
        failed += 1

    print()
    print(f"P1 Verification: {passed} passed, {failed} failed")
    return failed == 0


if __name__ == "__main__":
    ok = run_all()
    raise SystemExit(0 if ok else 1)
