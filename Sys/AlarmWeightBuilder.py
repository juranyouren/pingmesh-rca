"""
Alarm Weight Table Builder
==========================
Scans all case directories, extracts every unique alarm name across the
dataset, and initialises a global weight dictionary {alarm_name: 0.0}.

This table is the foundation for alarm-level PageRank / attention weighting:
  - PageRank transfer matrix can use per-alarm-type weights
  - LLM reflection can push earned weights back into the table
  - Co-occurrence patterns can be scored against this table

Usage:
  # Mode 1: initialize all weights to 0
  builder = AlarmWeightBuilder(data_root="/path/to/nodes_labeled")
  builder.build()
  builder.save("alarm_weights.json")

  # Mode 2: learn weights from labeled data (P(root_cause | alarm))
  builder.learn_from_labels()
  builder.save("alarm_weights_learned.json")

  # later: load, update, save
  builder.load("alarm_weights.json")
  builder.update({"BGP_邻居中断": 0.8, "端口Down": 1.0})
  builder.save("alarm_weights.json")
"""

import os
import json
from collections import defaultdict


class AlarmWeightBuilder:

    def __init__(self, data_root=None):
        """
        data_root: 数据集根目录，递归扫描找出所有 case（含 info.json 的目录）。
        """
        self.data_root = data_root
        self.weights = {}          # {alarm_name: float}
        self.alarm_case_count = defaultdict(int)  # how many cases each alarm appears in
        self.case_count = 0

    # ── scan ──────────────────────────────────────────────────────────
    @staticmethod
    def _find_case_files(dirpath, filenames):
        """
        在目录下找到 node 文件和 info 文件。
        兼容两种数据格式：
          - graph_only 用的 merged_pingmesh-*-全链路.json + info.json
          - Collector 输出的 nodes.json + info.json
        Returns (node_file, info_file) or (None, None).
        """
        node_file = None
        info_file = None
        for f in filenames:
            if f == "info.json":
                info_file = f
            elif "pingmesh" in f and "全链路.json" in f:
                node_file = f
        # fallback: Collector 输出的 nodes.json
        if node_file is None and "nodes.json" in filenames:
            node_file = "nodes.json"
        return node_file, info_file

    def _list_cases(self):
        """Yield (dirpath, nodes_path) for every case under data_root."""
        if not self.data_root or not os.path.isdir(self.data_root):
            return
        for dirpath, _dirnames, filenames in os.walk(self.data_root):
            node_file, info_file = self._find_case_files(dirpath, filenames)
            if node_file and info_file:
                yield dirpath, os.path.join(dirpath, node_file)

    def _load_nodes(self, nodes_path):
        """Load node JSON and normalise to list-of-dicts."""
        with open(nodes_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return list(data.values())
        return data if isinstance(data, list) else []

    # ── helpers (shared by build and learn_from_labels) ───────────────
    @staticmethod
    def _get_device_ip(node):
        """Extract device IP from a node dict. graph_only.py convention:
           mgmt_ip > ip > name."""
        return node.get("mgmt_ip", node.get("ip", node.get("name", "")))

    @staticmethod
    def _extract_alarms_from_node(node):
        """Return list of alarm name strings from a single device node."""
        names = []
        for evt in node.get("alarms", []) + node.get("logs", []):
            if isinstance(evt, str):
                aname = evt.strip()
            else:
                aname = str(evt.get("alarm_name", evt.get("name", ""))).strip()
            if aname:
                names.append(aname)
        return names

    def _get_root_ips(self, dirpath):
        """Extract root cause device IPs from label.json (ranking <= 3)."""
        label_path = os.path.join(dirpath, "label.json")
        if not os.path.exists(label_path):
            return set()
        with open(label_path, "r", encoding="utf-8") as f:
            labels = json.load(f)
        if not isinstance(labels, list):
            return set()
        root_ips = set()
        for item in labels:
            if item.get("ranking", 999) <= 3:
                for node in item.get("abnormal_node", []):
                    ip = node.get("ip", "")
                    if ip:
                        root_ips.add(ip)
        return root_ips

    # ── build ─────────────────────────────────────────────────────────
    def build(self):
        """
        Scan all cases and collect every unique alarm name.
        All weights are initialised to 0.0.
        """
        seen = set()
        self.case_count = 0
        self.alarm_case_count.clear()

        for dp, np in self._list_cases():
            self.case_count += 1
            nodes = self._load_nodes(np)
            case_alarms = set()
            for nd in nodes:
                for aname in self._extract_alarms_from_node(nd):
                    seen.add(aname)
                    case_alarms.add(aname)
            for aname in case_alarms:
                self.alarm_case_count[aname] += 1

        self.weights = {name: 0.0 for name in sorted(seen)}
        return self

    # ── learn from labels ────────────────────────────────────────────
    def learn_from_labels(self):
        """
        Learn alarm weights from labeled data using conditional probability.

        For each labeled case, reads label.json to identify root cause device
        IPs (ranking <= 3), then matches against alarm occurrences in the
        topology node files to accumulate per-alarm statistics:

            P(root_cause | alarm) = root_cause_hits[alarm] / total_appearances[alarm]
            weight                = round(P * 100)

        Falls back to label.json-only statistics when node files contain no
        alarm data.  Output is graph_only.py-compatible via save().
        """
        root_cause_hits = defaultdict(int)
        total_appearances = defaultdict(int)
        self.case_count = 0
        self.alarm_case_count.clear()
        empty_alarm_cases = 0

        for dirpath, nodes_path in self._list_cases():
            self.case_count += 1
            root_ips = self._get_root_ips(dirpath)
            nodes = self._load_nodes(nodes_path)

            case_alarms = set()
            case_has_any_alarm = False

            for nd in nodes:
                device_ip = self._get_device_ip(nd)
                is_root = device_ip in root_ips

                for aname in self._extract_alarms_from_node(nd):
                    case_has_any_alarm = True
                    total_appearances[aname] += 1
                    case_alarms.add(aname)
                    if is_root:
                        root_cause_hits[aname] += 1

            if not case_has_any_alarm:
                empty_alarm_cases += 1

            for aname in case_alarms:
                self.alarm_case_count[aname] += 1

        # fallback when nodes carry no alarm data
        if empty_alarm_cases == self.case_count and self.case_count > 0:
            print("[AlarmWeightBuilder] nodes contain no alarm data, "
                  "falling back to label.json root-cause-only statistics.")
            self._learn_from_labels_fallback()
            return self

        # compute conditional-probability weights
        self.weights = {}
        for aname in sorted(total_appearances.keys()):
            p = root_cause_hits.get(aname, 0) / total_appearances[aname]
            self.weights[aname] = round(p * 100)

        nonzeros = sum(1 for v in self.weights.values() if v > 0)
        print(f"[AlarmWeightBuilder] learned {len(self.weights)} alarm weights "
              f"from {self.case_count} cases, {nonzeros} non-zero"
              f"{f' ({empty_alarm_cases} cases had no alarm data in nodes)' if empty_alarm_cases else ''}")
        return self

    def _learn_from_labels_fallback(self):
        """
        Fallback: read alarm names directly from label.json root cause devices.
        Weight = round(root_cause_cases[alarm] / total_cases * 100).

        Overestimates alarms that only appear on root cause devices (no
        denominator correction), but works without per-device alarm data
        in the topology node files.
        """
        root_cause_cases = defaultdict(int)
        self.case_count = 0

        for dirpath, _nodes_path in self._list_cases():
            self.case_count += 1
            label_path = os.path.join(dirpath, "label.json")
            if not os.path.exists(label_path):
                continue

            with open(label_path, "r", encoding="utf-8") as f:
                labels = json.load(f)
            if not isinstance(labels, list):
                continue

            seen_in_case = set()
            for item in labels:
                for node in item.get("abnormal_node", []):
                    for evt in node.get("alarms", []) + node.get("syslogs", []):
                        if isinstance(evt, dict):
                            aname = str(evt.get("name", "")).strip()
                        else:
                            aname = str(evt).strip()
                        if aname and aname not in seen_in_case:
                            seen_in_case.add(aname)
                            root_cause_cases[aname] += 1

        self.weights = {}
        for aname in sorted(root_cause_cases.keys()):
            self.weights[aname] = round(root_cause_cases[aname] / self.case_count * 100)

        nonzeros = sum(1 for v in self.weights.values() if v > 0)
        print(f"[AlarmWeightBuilder] fallback: {len(self.weights)} alarm types "
              f"from {self.case_count} cases, {nonzeros} non-zero "
              f"(label.json root-cause-only)")
        return self

    # ── persist ───────────────────────────────────────────────────────
    def save(self, path):
        """
        Save as a JSON array of {alarm_name, alarm_priority} objects,
        directly compatible with graph_only.py's reading convention.
        """
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        alarm_list = []
        for name in sorted(self.weights.keys()):
            alarm_list.append({
                "alarm_name": name,
                "alarm_priority": self.weights[name],
            })
        with open(path, "w", encoding="utf-8") as f:
            json.dump(alarm_list, f, ensure_ascii=False, indent=2)
        print(f"[AlarmWeightBuilder] saved {len(alarm_list)} alarm types → {path}")

    def load(self, path):
        """
        Load a weight file (array format or legacy dict format).
        Array format: [{alarm_name, alarm_priority}, ...]  ← graph_only.py native
        Dict  format: {"weights": {...}, ...}              ← legacy
        """
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)

        if isinstance(payload, list):
            for item in payload:
                name = item.get("alarm_name", "")
                if name:
                    self.weights[name] = float(item.get("alarm_priority", 0.0))
        elif isinstance(payload, dict):
            self.weights = payload.get("weights", {})
            self.alarm_case_count = defaultdict(int, payload.get("alarm_case_count", {}))
            self.case_count = payload.get("case_count", 0)

        print(f"[AlarmWeightBuilder] loaded {len(self.weights)} alarm types ← {path}")
        return self

    # ── update ────────────────────────────────────────────────────────
    def update(self, updates):
        """
        Merge weight dict into current table.  Positive values raise
        suspicion; zero leaves the alarm at its current weight.

        updates: {alarm_name: delta_or_value, ...}
          Use delta=True to add to existing weight instead of replacing.
        """
        for name, val in updates.items():
            if name in self.weights:
                self.weights[name] = val
            else:
                self.weights[name] = val  # new alarm type
        return self

    def update_delta(self, deltas):
        """Add delta values to existing weights (for PageRank / LLM feedback)."""
        for name, delta in deltas.items():
            if name in self.weights:
                self.weights[name] += delta
            else:
                self.weights[name] = delta
        return self

    # ── query ─────────────────────────────────────────────────────────
    def get(self, alarm_name):
        """Return weight for a single alarm, 0 if unseen."""
        return self.weights.get(alarm_name, 0.0)

    def top_k(self, k=20):
        """Return the k highest-weighted alarm names."""
        return sorted(self.weights.items(), key=lambda x: x[1], reverse=True)[:k]

    def stats(self):
        """Print a summary of the weight table."""
        nonzeros = sum(1 for v in self.weights.values() if v != 0.0)
        print(f"[AlarmWeightBuilder] {len(self.weights)} alarm types, "
              f"{nonzeros} non-zero, {self.case_count} cases scanned")
        if nonzeros:
            print("  Top-10 by weight:")
            for name, w in self.top_k(10):
                print(f"    {name:60s} {w:8.4f}  (in {self.alarm_case_count.get(name, 0)} cases)")
        return self


# ── quick CLI ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    mode = sys.argv[1] if len(sys.argv) > 1 else "build"
    data_root = sys.argv[2] if len(sys.argv) > 2 else \
        "/home/sbp/lixinyang/pingmesh/data/nodes_labeled"
    out_path = sys.argv[3] if len(sys.argv) > 3 else \
        "/home/sbp/lixinyang/pingmesh/data/weights/alarm_weights.json"

    builder = AlarmWeightBuilder(data_root=data_root)

    if mode == "learn":
        builder.learn_from_labels()
    else:
        builder.build()

    builder.stats()
    builder.save(out_path)
