from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from Sys_v1.utils.io_utils import load_json


def get_device_ip(node: Dict[str, Any]) -> str:
    return node.get("mgmt_ip", node.get("ip", node.get("name", "unknown"))) if isinstance(node, dict) else "unknown"


def find_full_link_file(dirpath: str, filenames: List[str]) -> Optional[str]:
    for fname in filenames:
        if "全链路" in fname and "pingmesh" in fname and fname.endswith(".json"):
            return fname
    for fname in filenames:
        if "鍏ㄩ摼璺" in fname and "pingmesh" in fname and fname.endswith(".json"):
            return fname
    return "nodes.json" if "nodes.json" in filenames else None


def case_node_path(dirpath: str) -> Optional[str]:
    if not os.path.isdir(dirpath):
        return None
    fname = find_full_link_file(dirpath, os.listdir(dirpath))
    return os.path.join(dirpath, fname) if fname else None


def load_case_nodes(dirpath: str) -> List[Dict[str, Any]]:
    path = case_node_path(dirpath)
    if not path:
        return []
    data = load_json(path, default=[])
    if isinstance(data, dict):
        return list(data.values())
    return data if isinstance(data, list) else []


def load_case_info(dirpath: str) -> Dict[str, Any]:
    data = load_json(os.path.join(dirpath, "info.json"), default={})
    return data if isinstance(data, dict) else {}


def read_gt_ips(dirpath: str, *, top_n: int = 3) -> List[str]:
    labels = load_json(os.path.join(dirpath, "label.json"), default=[])
    if not isinstance(labels, list):
        return []
    gt_ips: List[str] = []
    for label in sorted(labels, key=lambda item: item.get("ranking", 999))[:top_n]:
        for node in label.get("abnormal_node", []):
            ip = node.get("ip") if isinstance(node, dict) else None
            if ip and ip not in gt_ips:
                gt_ips.append(ip)
    return gt_ips
