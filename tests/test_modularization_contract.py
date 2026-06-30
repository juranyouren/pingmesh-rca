import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_main_system_has_no_skillbank_runtime_dependency():
    offenders = []
    for path in (REPO_ROOT / "Sys").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if "SkillBank" in text or "SkillExecutor" in text:
            offenders.append(path.relative_to(REPO_ROOT).as_posix())

    assert offenders == []
    assert not (REPO_ROOT / "Sys" / "RootCauseAnalyze" / "SkillNRefineAnalyzer.py").exists()


def test_builtin_skill_provider_replaces_skillbank_executor(tmp_path):
    from Sys.RootCauseAnalyze.skills.provider import BuiltinSkillProvider

    case_dir = tmp_path / "case-1"
    case_dir.mkdir()
    node_file = case_dir / "pingmesh-case-1-全链路.json"
    node_file.write_text(
        json.dumps({"a": {"mgmt_ip": "10.0.0.1", "alarms": [], "logs": []}}, ensure_ascii=False),
        encoding="utf-8",
    )
    (case_dir / "info.json").write_text(json.dumps({"alarm_time": 123}), encoding="utf-8")

    provider = BuiltinSkillProvider()

    assert [skill["skill_id"] for skill in provider.get_skill_conf()] == ["1", "2"]
    assert provider.get_node_list(str(case_dir)) == [{"mgmt_ip": "10.0.0.1", "alarms": [], "logs": []}]
    assert provider.get_alarminfo(str(case_dir)) == {"alarm_time": 123}
