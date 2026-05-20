import json

from brain_alpha_ops.jsonl import count_jsonl_records, read_jsonl_records, read_jsonl_tail, read_jsonl_tail_with_stats, tail_text_lines


def test_read_jsonl_tail_reads_only_requested_trailing_records(tmp_path):
    path = tmp_path / "history.jsonl"
    path.write_text(
        "\n".join(json.dumps({"i": index}) for index in range(10)) + "\n",
        encoding="utf-8",
    )

    rows = read_jsonl_tail(path, limit=3)

    assert [row["i"] for row in rows] == [7, 8, 9]


def test_read_jsonl_tail_with_stats_skips_bad_lines(tmp_path):
    path = tmp_path / "history.jsonl"
    path.write_text(
        '{"ok": 1}\n\nnot-json\n[1,2]\n{"ok": 2}\n',
        encoding="utf-8",
    )

    result = read_jsonl_tail_with_stats(path, limit=10)

    assert [row["ok"] for row in result.rows] == [1, 2]
    assert result.exists is True
    assert result.parsed_count == 2
    assert result.skipped_blank_count == 1
    assert result.skipped_invalid_count == 2
    assert result.error == ""


def test_tail_text_lines_handles_missing_trailing_newline(tmp_path):
    path = tmp_path / "history.jsonl"
    path.write_text("a\nb\nc", encoding="utf-8")

    assert tail_text_lines(path, 2) == ["b", "c"]


def test_read_jsonl_records_supports_full_scan_and_tail_limit(tmp_path):
    path = tmp_path / "history.jsonl"
    path.write_text(
        "\n".join(json.dumps({"i": index}) for index in range(5)) + "\n",
        encoding="utf-8",
    )

    assert [row["i"] for row in read_jsonl_records(path, limit=None)] == [0, 1, 2, 3, 4]
    assert [row["i"] for row in read_jsonl_records(path, limit=2)] == [3, 4]


def test_count_jsonl_records_applies_predicate(tmp_path):
    path = tmp_path / "history.jsonl"
    path.write_text(
        '{"status":"PASS"}\n{"status":"FAIL"}\nnot-json\n{"status":"PASS"}\n',
        encoding="utf-8",
    )

    count = count_jsonl_records(path, predicate=lambda row: row.get("status") == "PASS")

    assert count == 2
