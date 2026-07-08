import importlib.util
import json
from pathlib import Path

import pytest


def _load_helper():
    module_path = Path(__file__).resolve().parents[1] / "tmp" / "labeling_helper.py"
    spec = importlib.util.spec_from_file_location("labeling_helper", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_case(root: Path, name: str, labels):
    case_dir = root / name
    case_dir.mkdir(parents=True)
    (case_dir / "label.json").write_text(
        json.dumps(labels, ensure_ascii=False),
        encoding="utf-8",
    )
    (case_dir / "info.json").write_text("{}", encoding="utf-8")
    return case_dir


def test_write_labeled_cases_copies_only_auto_matches(tmp_path):
    helper = _load_helper()
    src = tmp_path / "nodes_extend"
    auto_case = _write_case(
        src,
        "auto",
        [
            {"ranking": 2, "abnormal_node": [{"ip": "10.0.0.1"}]},
            {"ranking": 1, "abnormal_node": [{"ip": "10.0.0.2"}]},
        ],
    )
    manual_case = _write_case(
        src,
        "manual",
        [{"ranking": 1, "abnormal_node": [{"ip": "10.0.0.3"}]}],
    )

    res_data = [
        {"dir": str(auto_case), "skill_ips": ["10.0.0.2"]},
        {"dir": str(manual_case), "skill_ips": ["10.0.0.9"]},
    ]

    auto_labeled, need_manual = helper.classify_cases(res_data, use_skill=True)
    dst = helper.write_labeled_cases(src, auto_labeled, need_manual)

    assert (dst / "auto" / "label.json").exists()
    assert not (dst / "manual").exists()
    kept = json.loads((dst / "auto" / "label.json").read_text(encoding="utf-8"))
    assert kept == [{"ranking": 1, "abnormal_node": [{"ip": "10.0.0.2"}]}]
    assert need_manual[0]["csn"] == "manual"


def test_write_labeled_cases_refuses_existing_destination_without_overwrite(tmp_path):
    helper = _load_helper()
    src = tmp_path / "nodes_extend"
    auto_case = _write_case(
        src,
        "auto",
        [{"ranking": 1, "abnormal_node": [{"ip": "10.0.0.1"}]}],
    )
    res_data = [{"dir": str(auto_case), "skill_ips": ["10.0.0.1"]}]
    auto_labeled, need_manual = helper.classify_cases(res_data, use_skill=True)

    helper.write_labeled_cases(src, auto_labeled, need_manual)

    with pytest.raises(FileExistsError):
        helper.write_labeled_cases(src, auto_labeled, need_manual)
