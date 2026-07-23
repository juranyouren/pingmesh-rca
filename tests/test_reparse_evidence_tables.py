import json

from scripts.build_evidence_tables import SUMMARY_PARSER_VERSION
from scripts.reparse_evidence_tables import reparse_case


def _write_fixture(case_dir):
    records = [
        {
            "task_id": "task-1",
            "device_ip": "10.0.0.1",
            "raw_response": '前缀文字 {"summary":"从 JSON 提取"} 后缀文字',
            "summary": "旧摘要一",
            "parse_mode": "raw_fallback",
            "prompt": "保留的 prompt",
        },
        {
            "task_id": "task-2",
            "device_ip": "10.0.0.2",
            "raw_response": "模型推理内容</think>\n直接使用的最终摘要",
            "summary": "旧摘要二",
            "parse_mode": "raw_fallback",
            "prompt": "保留的 prompt",
        },
    ]
    outputs_path = case_dir / "small_model_outputs.jsonl"
    outputs_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records),
        encoding="utf-8",
    )
    table = {
        "case_id": "case-a",
        "rows": [
            {
                "candidate_ip": "10.0.0.1",
                "semantic_summary": "旧摘要一",
                "summary_context": {"parse_mode": "raw_fallback"},
                "provenance": {"summary_task_id": "task-1"},
            },
            {
                "candidate_ip": "10.0.0.2",
                "semantic_summary": "旧摘要二",
                "summary_context": {"parse_mode": "raw_fallback"},
                "provenance": {"summary_task_id": "task-2"},
            },
        ],
    }
    table_path = case_dir / "evidence_table.json"
    table_path.write_text(
        json.dumps(table, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return outputs_path, table_path


def test_reparse_preview_does_not_modify_cached_files(tmp_path):
    case_dir = tmp_path / "case-a"
    case_dir.mkdir()
    outputs_path, table_path = _write_fixture(case_dir)
    before_outputs = outputs_path.read_text(encoding="utf-8")
    before_table = table_path.read_text(encoding="utf-8")

    report = reparse_case(case_dir, apply=False)

    assert report["status"] == "preview"
    assert report["changed_records"] == 2
    assert report["parse_mode_counts"] == {"json": 1, "after_think": 1}
    assert outputs_path.read_text(encoding="utf-8") == before_outputs
    assert table_path.read_text(encoding="utf-8") == before_table


def test_reparse_apply_updates_derived_fields_but_preserves_raw_output(tmp_path):
    case_dir = tmp_path / "case-a"
    case_dir.mkdir()
    outputs_path, table_path = _write_fixture(case_dir)

    report = reparse_case(case_dir, apply=True)

    records = [
        json.loads(line)
        for line in outputs_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    table = json.loads(table_path.read_text(encoding="utf-8"))
    assert report["status"] == "updated"
    assert records[0]["raw_response"] == '前缀文字 {"summary":"从 JSON 提取"} 后缀文字'
    assert records[0]["summary"] == "从 JSON 提取"
    assert records[0]["parse_mode"] == "json"
    assert records[1]["summary"] == "直接使用的最终摘要"
    assert records[1]["parse_mode"] == "after_think"
    assert all(
        record["parser_version"] == SUMMARY_PARSER_VERSION for record in records
    )
    assert table["rows"][0]["semantic_summary"] == "从 JSON 提取"
    assert table["rows"][1]["semantic_summary"] == "直接使用的最终摘要"
    assert table["summary_parser_version"] == SUMMARY_PARSER_VERSION
