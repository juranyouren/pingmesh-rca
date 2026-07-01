from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_prompts_package_exports_runtime_prompts():
    from prompts import PROMPT, SKILLED_PROMPT

    assert "Root Cause Device Localization" in PROMPT
    assert "默认信任算法排名" in SKILLED_PROMPT


def test_root_utils_package_removed_and_sys_utils_remains():
    assert not (REPO_ROOT / "utils").exists()

    from Sys.utils.case_utils import get_device_ip

    assert get_device_ip({"mgmt_ip": "10.0.0.1"}) == "10.0.0.1"
