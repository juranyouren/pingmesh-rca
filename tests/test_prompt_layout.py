from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_prompts_package_exports_runtime_prompts():
    from prompts import PROMPT, SKILLED_PROMPT

    assert "Root Cause Device Localization" in PROMPT
    assert "拓扑 Top-K 与时序 Top-K 的并集" in SKILLED_PROMPT
    assert "精确字段由程序无损保留" in SKILLED_PROMPT
    assert "semantic_summary" in SKILLED_PROMPT
    assert "不包含根因判断" in SKILLED_PROMPT


def test_root_utils_package_removed_and_sys_utils_remains():
    assert not (REPO_ROOT / "utils").exists()

    from Sys.utils.case_utils import get_device_ip

    assert get_device_ip({"mgmt_ip": "10.0.0.1"}) == "10.0.0.1"
