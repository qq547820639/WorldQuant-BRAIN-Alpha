import json

from brain_alpha_ops.research.experience import get_winning_patterns


def test_winning_patterns_reads_bounded_recent_history(tmp_path):
    path = tmp_path / "alpha_features.jsonl"
    rows = [
        {
            "alpha_id": "old",
            "pass_fail": "PASS",
            "sharpe": 3.0,
            "fitness": 2.0,
            "field_set": ["old_field", "close"],
            "operator_set": ["rank"],
            "window_values": [5],
            "family": "Old",
        },
        {
            "alpha_id": "new",
            "pass_fail": "PASS",
            "sharpe": 2.0,
            "fitness": 1.0,
            "field_set": ["new_field", "volume"],
            "operator_set": ["ts_mean"],
            "window_values": [20],
            "family": "New",
        },
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

    result = get_winning_patterns(str(tmp_path), min_sharpe=1.0, min_fitness=0.5, min_sample=1, history_limit=1)

    assert result["sample_size"] == 1
    assert result["total_records"] == 1
    assert result["history_limit"] == 1
    assert result["top_operators"] == ["ts_mean"]
    assert result["preferred_windows"] == [20]
